import argparse
from dataclasses import asdict

from airlog.queries import readback
from airlog.records import AirRecordStore
from local_service import JsonHandler, Problem, bind, canonical_json, label, object_fields, transaction
from program.manifest import decode_manifest
from projection.cues import CueStore
from projection.inbox import ProjectionInbox
from projection.output import advance
from projection.timing import LocalClock


class ProjectionHandler(JsonHandler):
    def dispatch(self, method, path, data):
        inbox, cues, records, clock = self.server.services
        route = method, path
        if route == ('POST', '/inbox'):
            object_fields(data, 'manifest_id', 'manifest')
            manifest = decode_manifest(canonical_json(data['manifest']))
            return 200, inbox.accept_manifest(manifest, data['manifest_id'])
        if route == ('GET', '/inbox'):
            object_fields(data, 'show_id')
            show_id = label(data['show_id'], 'show_id')
            with transaction(inbox.database) as connection:
                receipt = inbox.get_receipt(connection, show_id)
            if receipt is None:
                raise Problem(404, 'unknown_show', show_id=show_id)
            return 200, receipt
        if route == ('POST', '/advance'):
            object_fields(data, 'show_id')
            show_id = data['show_id']
            emitted = advance(inbox, cues, records, clock, show_id)
            body = {'records': [asdict(item) for item in emitted]}
            with transaction(inbox.database) as connection:
                manifest = inbox.get_manifest(connection, show_id)
                if manifest is not None and manifest.co_display is not None:
                    body['co_display_status'] = (
                        cues.co_display_state(connection, show_id) or 'waiting')
            return 200, body
        if route == ('GET', '/readback'):
            object_fields(data, *('show_id', 'cue_id') if 'cue_id' in data else ('show_id',))
            return 200, readback(inbox, records, **data)
        if route == ('POST', '/decision'):
            return 200, asdict(cues.apply_correction(data))
        if route == ('GET', '/decision'):
            object_fields(data, 'correction_id')
            correction_id = label(data['correction_id'], 'correction_id')
            decision = cues.lookup_correction(correction_id)
            if decision is None:
                raise Problem(404, 'unknown_correction', correction_id=correction_id)
            return 200, asdict(decision)
        raise Problem(404, 'unknown_route')


def initialize(database):
    cues = CueStore(database)
    inbox = ProjectionInbox(database, cues)
    records = AirRecordStore(database)
    for store in (inbox, cues, records):
        store.initialize()
    return inbox, cues, records


def serve(database, port=0, *, clock=None):
    stores = initialize(database)
    return bind(ProjectionHandler, port, services=(*stores, clock if clock is not None else LocalClock()))


def main():
    parser = argparse.ArgumentParser(description='Bilingual subtitle projection service')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--db', required=True)
    run = commands.add_parser('serve')
    run.add_argument('--db', required=True)
    run.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.command == 'init':
        initialize(args.db)
    else:
        with serve(args.db, args.port) as server:
            server.serve_forever()


if __name__ == '__main__':
    main()
