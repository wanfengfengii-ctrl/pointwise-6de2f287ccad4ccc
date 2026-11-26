import json
import sqlite3
from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, Request, build_opener


class Problem(Exception):
    def __init__(self, status, code, **details):
        super().__init__(code)
        self.status = status
        self.payload = {'error': code, **details}


def integer(value, field):
    if type(value) is not int or not -(2**63) <= value < 2**63:
        raise Problem(400, 'invalid_integer', field=field)
    return value


def label(value, field):
    if not isinstance(value, str) or not value.strip():
        raise Problem(400, 'invalid_string', field=field)
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise Problem(400, 'invalid_string', field=field) from error
    return value


def object_fields(value, *required):
    if not isinstance(value, dict) or set(value) != set(required):
        raise Problem(400, 'invalid_fields', expected=list(required))
    return value


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def connect(database):
    connection = sqlite3.connect(database, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    return connection


def create_tables(database, schema):
    with closing(connect(database)) as connection:
        connection.executescript(schema)


@contextmanager
def transaction(database, *, write=False):
    with closing(connect(database)) as connection:
        connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        with connection:
            yield connection


class JsonHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        self._respond()

    def do_POST(self):
        self._respond()

    def _input(self):
        if self.command == 'POST':
            try:
                size = int(self.headers.get('Content-Length', ''))
                if not 0 < size <= 8 * 1024 * 1024:
                    raise ValueError
                value = json.loads(self.rfile.read(size).decode('utf-8'))
            except (ValueError, UnicodeError, RecursionError) as error:
                raise Problem(400, 'invalid_json') from error
            if not isinstance(value, dict):
                raise Problem(400, 'invalid_json')
            return value
        try:
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True, errors='strict')
        except UnicodeError as error:
            raise Problem(400, 'invalid_query') from error
        if any(len(values) != 1 for values in query.values()):
            raise Problem(400, 'duplicate_query_parameter')
        return {key: values[0] for key, values in query.items()}

    def _respond(self):
        try:
            result = self.dispatch(self.command, urlsplit(self.path).path, self._input())
        except Problem as error:
            result = error.status, error.payload
        if result is None:
            self.close_connection = True
            return
        status, value = result
        body = canonical_json(value).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return


def call(base, method, path, payload=None, *, timeout=3):
    data = None if payload is None else canonical_json(payload).encode('utf-8')
    request = Request(base.rstrip('/') + path, data=data, method=method,
                      headers={'Content-Type': 'application/json'})
    try:
        response = build_opener(ProxyHandler({})).open(request, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.loads(response.read().decode('utf-8'))


def bind(handler, port, **state):
    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    server.__dict__.update(state)
    return server


def address(server):
    return f'http://127.0.0.1:{server.server_port}'


@contextmanager
def running(server):
    with server:
        worker = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        worker.start()
        try:
            yield address(server)
        finally:
            server.shutdown()
            worker.join()
