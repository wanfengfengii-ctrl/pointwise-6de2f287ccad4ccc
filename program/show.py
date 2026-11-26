import json
from dataclasses import asdict, dataclass

from local_service import Problem, canonical_json, create_tables, transaction
from program.manifest import decode_manifest, encode_manifest


@dataclass(frozen=True)
class ShowBinding:
    show_id: str
    revision: str
    start: int
    lanes: dict


class ShowRepository:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS rehearsal (
                show_id TEXT PRIMARY KEY, binding TEXT NOT NULL, manifest TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1))
            );
        ''')

    def save_rehearsal(self, binding, manifest):
        raw = canonical_json(asdict(binding))
        schedule = encode_manifest(manifest)
        with transaction(self.database, write=True) as connection:
            old = connection.execute(
                'SELECT binding, manifest, pinned FROM rehearsal WHERE show_id = ?', (binding.show_id,),
            ).fetchone()
            if old and old['pinned']:
                if (old['binding'], old['manifest']) != (raw, schedule):
                    raise Problem(409, 'show_already_preloading', show_id=binding.show_id)
                return
            connection.execute('''
                INSERT INTO rehearsal(show_id, binding, manifest) VALUES (?, ?, ?)
                ON CONFLICT(show_id) DO UPDATE SET binding = excluded.binding, manifest = excluded.manifest
            ''', (binding.show_id, raw, schedule))

    def get_binding(self, connection, show_id):
        row = connection.execute('SELECT binding FROM rehearsal WHERE show_id = ?', (show_id,)).fetchone()
        return ShowBinding(**json.loads(row['binding'])) if row else None

    def get_manifest(self, connection, show_id):
        row = connection.execute('SELECT manifest FROM rehearsal WHERE show_id = ?', (show_id,)).fetchone()
        return decode_manifest(row['manifest']) if row else None

    def pin_manifest(self, connection, show_id):
        connection.execute('UPDATE rehearsal SET pinned = 1 WHERE show_id = ?', (show_id,))
