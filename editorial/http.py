import argparse
import json
from dataclasses import asdict
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlencode

from editorial.corrections import CorrectionRequest, correct
from editorial.preload import preload
from editorial.receipts import ReceiptStore
from editorial.reconcile import verdict
from local_service import JsonHandler, Problem, bind, call, object_fields, transaction
from program.manifest import encode_manifest, manifest_identity, manifest_view
from program.rehearsal import rehearse
from program.show import ShowRepository
from scripts.approval import approve
from scripts.draft import load_draft, save_draft
from scripts.repository import ScriptRepository
from scripts.revisions import load_approved_revision
from scripts.validation import correction_parameters


class ProjectionClient:
    def __init__(self, base, timeout=1):
        self.base = base
        self.timeout = timeout

    def _exchange(self, method, path, payload=None):
        try:
            status, response = call(self.base, method, path, payload, timeout=self.timeout)
        except (OSError, HTTPException, ValueError):
            return None
        if 200 <= status < 300:
            return response
        if status == 404 or status >= 500:
            return None
        if isinstance(response, dict) and isinstance(response.get('error'), str):
            details = dict(response)
            code = details.pop('error')
            raise Problem(status, code, **details)
        return None

    def send_preload(self, manifest):
        return self._exchange('POST', '/inbox', {
            'manifest_id': manifest_identity(manifest), 'manifest': json.loads(encode_manifest(manifest)),
        })

    def lookup_preload(self, show_id):
        return self._exchange('GET', '/inbox?' + urlencode({'show_id': show_id}))

    def send_correction(self, request):
        return self._exchange('POST', '/decision', request)

    def lookup_correction(self, correction_id):
        return self._exchange('GET', '/decision?' + urlencode({'correction_id': correction_id}))

    def observe_readback(self, parameters):
        try:
            return call(self.base, 'GET', '/readback?' + urlencode(parameters), timeout=self.timeout)
        except (OSError, HTTPException, ValueError):
            raise Problem(503, 'readback_unavailable') from None


class EditorialHandler(JsonHandler):
    def dispatch(self, method, path, data):
        scripts, shows, receipts, client = self.server.services
        route = method, path
        if route == ('POST', '/draft'):
            fields = object_fields(data, 'script_id', 'cues')
            return 200, {'script_id': save_draft(scripts, **fields)}
        if route == ('GET', '/draft'):
            object_fields(data, 'script_id')
            with scripts.transaction() as connection:
                return 200, asdict(load_draft(scripts, connection, data['script_id']))
        if route == ('POST', '/approve'):
            object_fields(data, 'script_id')
            return 200, {'revision': approve(scripts, data['script_id'])}
        if route == ('GET', '/revision'):
            object_fields(data, 'revision')
            with scripts.transaction() as connection:
                return 200, asdict(load_approved_revision(scripts, connection, data['revision']))
        if route == ('POST', '/rehearse'):
            required = ('show_id', 'revision', 'start', 'lanes')
            if not isinstance(data, dict) or set(data) - set(required) - {'co_display'} \
                    or set(required) - set(data):
                object_fields(data, *required)
            fields = {key: data[key] for key in required}
            if 'co_display' in data and data['co_display'] is None:
                raise Problem(400, 'invalid_co_display')
            fields['co_display'] = data.get('co_display')
            manifest = rehearse(scripts, shows, **fields)
            return 200, manifest_view(manifest)
        if route == ('GET', '/rehearse'):
            object_fields(data, 'show_id')
            with transaction(shows.database) as connection:
                manifest = shows.get_manifest(connection, data['show_id'])
            if manifest is None:
                raise Problem(404, 'no_formal_manifest', show_id=data['show_id'])
            return 200, manifest_view(manifest)
        if route == ('POST', '/preload'):
            object_fields(data, 'show_id')
            receipt = preload(shows, receipts, client, data['show_id'])
            return (200 if receipt.status == 'received' else 202), asdict(receipt)
        if route == ('POST', '/correct'):
            receipt = correct(shows, receipts, client, CorrectionRequest(**correction_parameters(data)))
            return receipt_status(receipt.status), receipt.public()
        if route == ('GET', '/verdict'):
            object_fields(data, 'correction_id')
            receipt = verdict(receipts, client, data['correction_id'])
            return receipt_status(receipt.status), receipt.public()
        if route == ('GET', '/readback'):
            return client.observe_readback(data)
        raise Problem(404, 'unknown_route')


def receipt_status(status):
    return {'accepted': 200, 'pending': 202, 'already_shown': 409}[status]


def initialize(database, *, sample=False):
    scripts = ScriptRepository(database)
    shows = ShowRepository(database)
    receipts = ReceiptStore(database)
    for store in (scripts, shows, receipts):
        store.initialize()
    if sample:
        path = Path(__file__).resolve().parents[1] / 'examples' / 'bilingual.json'
        with path.open(encoding='utf-8') as stream:
            save_draft(scripts, **json.load(stream), if_absent=True)
    return scripts, shows, receipts


def serve(database, projection_url, port=0, *, sample=False, timeout=1):
    stores = initialize(database, sample=sample)
    return bind(EditorialHandler, port, services=(*stores, ProjectionClient(projection_url, timeout)))


def main():
    parser = argparse.ArgumentParser(description='Bilingual subtitle editorial service')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--db', required=True)
    init.add_argument('--sample', action='store_true')
    run = commands.add_parser('serve')
    run.add_argument('--db', required=True)
    run.add_argument('--projection', required=True)
    run.add_argument('--port', type=int, default=8764)
    args = parser.parse_args()
    if args.command == 'init':
        initialize(args.db, sample=args.sample)
    else:
        with serve(args.db, args.projection, args.port) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
