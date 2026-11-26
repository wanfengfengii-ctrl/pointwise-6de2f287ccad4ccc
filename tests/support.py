from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from urllib.parse import urlencode

from editorial.http import serve as serve_editorial
from local_service import JsonHandler, bind, call, running
from projection.http import serve as serve_projection
from projection.timing import LocalClock


V1 = ('请入场', 'Please enter')
V2 = ('请就座', 'Please take your seat')


def cue(name='C', second=10, texts=V1):
    return {'cue_id': name, 'second': second, 'zh': texts[0], 'en': texts[1]}


def lanes(zh=0, en=2, *, same_screen=False, duration=2):
    return {'zh': {'offset': zh, 'screen': 'left', 'duration': duration},
            'en': {'offset': en, 'screen': 'left' if same_screen else 'right', 'duration': duration}}


def aired(records):
    return [(row['language'], row['aired_at'], row['version'], row['text']) for row in records]


class ReplyGate:
    def __init__(self):
        self.held = Event()
        self.release = Event()


class Relay(JsonHandler):
    def dispatch(self, method, path, data):
        control = self.server.control
        route = method, path
        if route in control.block:
            control.delayed[route] = data
            return 503, {'error': 'link_unavailable'}
        request_path = self.path if method == 'GET' else path
        result = call(control.target, method, request_path, data if method == 'POST' else None)
        if route in control.lose:
            control.lose.remove(route)
            return None
        gate = control.hold.get(route)
        if gate is not None:
            gate.held.set()
            if not gate.release.wait(6):
                return 503, {'error': 'test_relay_timeout'}
        return result


class House:
    def __init__(self, test, *, sample=False):
        self.test = test
        self.resources = ExitStack()
        self.desk_run = ExitStack()
        self.screen_run = ExitStack()
        test.addCleanup(self.resources.close)
        root = Path(self.resources.enter_context(TemporaryDirectory(prefix='subtitle-test-')))
        self.desk_db = root / 'desk.sqlite'
        self.screen_db = root / 'screen.sqlite'
        self.second = 0
        self.block = set()
        self.delayed = {}
        self.lose = set()
        self.hold = {}
        self.relay = self.resources.enter_context(running(bind(Relay, 0, control=self)))
        self.resources.callback(self.screen_run.close)
        self.resources.callback(self.desk_run.close)
        self.restart_screen()
        self.restart_desk(sample=sample)

    def restart_screen(self):
        self.screen_run.close()
        self.target = self.screen_run.enter_context(running(
            serve_projection(self.screen_db, clock=LocalClock(lambda: self.second)),
        ))

    def restart_desk(self, *, sample=False):
        self.desk_run.close()
        self.desk = self.desk_run.enter_context(running(
            serve_editorial(self.desk_db, self.relay, sample=sample, timeout=8),
        ))

    def _request(self, expected, base, method, path, data=None):
        status, result = call(base, method, path, data, timeout=10)
        self.test.assertEqual(expected, status, (method, path, result))
        return result

    def edit(self, expected, method, path, data=None):
        return self._request(expected, self.desk, method, path, data)

    def project(self, expected, method, path, data=None):
        return self._request(expected, self.target, method, path, data)

    def deliver(self, route, expected=200):
        method, path = route
        return self.project(expected, method, path, self.delayed[route])

    def draft(self, cues, *, script_id='weekend', expected=200):
        return self.edit(expected, 'POST', '/draft', {'script_id': script_id, 'cues': cues})

    def approve(self, script_id='weekend'):
        return self.edit(200, 'POST', '/approve', {'script_id': script_id})['revision']

    def prepare(self, cues=None):
        self.draft([cue()] if cues is None else cues)
        return self.approve()

    def rehearse(self, revision, *, show='S', start=0, setup=None, expected=200):
        return self.edit(expected, 'POST', '/rehearse', {
            'show_id': show, 'revision': revision, 'start': start,
            'lanes': lanes() if setup is None else setup,
        })

    def preload(self, show='S', *, expected=200):
        return self.edit(expected, 'POST', '/preload', {'show_id': show})

    def ready(self, *, setup=None):
        manifest = self.rehearse(self.prepare(), setup=setup)
        self.test.assertEqual('received', self.preload()['status'])
        return manifest

    def advance(self, second, show='S', *, expected=200):
        self.second = second
        return self.project(expected, 'POST', '/advance', {'show_id': show})

    def read(self, show='S', cue_id=None, *, expected=200):
        query = {'show_id': show}
        if cue_id is not None:
            query['cue_id'] = cue_id
        return self.project(expected, 'GET', '/readback?' + urlencode(query))

    def correction(self, *, correction_id='Q', show='S', cue_id='C', texts=V2, expected=200):
        return self.edit(expected, 'POST', '/correct', {
            'correction_id': correction_id, 'show_id': show, 'cue_id': cue_id,
            'zh': texts[0], 'en': texts[1],
        })

    def verdict(self, correction_id='Q', *, expected=200):
        return self.edit(expected, 'GET', '/verdict?' + urlencode({'correction_id': correction_id}))
