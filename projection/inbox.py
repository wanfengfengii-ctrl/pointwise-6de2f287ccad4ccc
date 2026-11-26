from local_service import Problem, create_tables, transaction
from program.manifest import decode_manifest, encode_manifest, manifest_identity
from projection.cues import CueStore


class ProjectionInbox:
    def __init__(self, database, cues: CueStore):
        self.database = database
        self.cues = cues

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS received_manifest (
                show_id TEXT PRIMARY KEY, manifest_id TEXT NOT NULL, manifest TEXT NOT NULL
            );
        ''')

    def accept_manifest(self, manifest, identity):
        content = encode_manifest(manifest)
        if identity != manifest_identity(manifest):
            raise Problem(400, 'manifest_identity_mismatch')
        with transaction(self.database, write=True) as connection:
            row = connection.execute('SELECT manifest_id, manifest FROM received_manifest WHERE show_id = ?',
                                     (manifest.show_id,)).fetchone()
            if row is None:
                connection.execute('INSERT INTO received_manifest VALUES (?, ?, ?)',
                                   (manifest.show_id, identity, content))
                self.cues.register_manifest_cues(connection, manifest)
            elif (row['manifest_id'], row['manifest']) != (identity, content):
                raise Problem(409, 'different_manifest_received', show_id=manifest.show_id)
            return self.get_receipt(connection, manifest.show_id)

    def get_receipt(self, connection, show_id):
        row = connection.execute('SELECT manifest_id FROM received_manifest WHERE show_id = ?',
                                 (show_id,)).fetchone()
        if row is None:
            return None
        return {'show_id': show_id, 'manifest_id': row['manifest_id'], 'status': 'received'}

    def get_manifest(self, connection, show_id):
        row = connection.execute('SELECT manifest FROM received_manifest WHERE show_id = ?', (show_id,)).fetchone()
        return decode_manifest(row['manifest']) if row else None
