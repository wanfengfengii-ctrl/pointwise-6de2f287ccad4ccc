import json
from contextlib import contextmanager

from local_service import canonical_json, create_tables, transaction


class ScriptRepository:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS draft (
                script_id TEXT PRIMARY KEY, cues TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approved_revision (
                id INTEGER PRIMARY KEY, script_id TEXT NOT NULL, cues TEXT NOT NULL,
                FOREIGN KEY (script_id) REFERENCES draft(script_id)
            );
        ''')

    @contextmanager
    def transaction(self, *, write=False):
        with transaction(self.database, write=write) as connection:
            yield connection

    def put_draft(self, connection, script_id, cues, *, if_absent=False):
        if if_absent:
            statement = 'INSERT INTO draft VALUES (?, ?) ON CONFLICT(script_id) DO NOTHING'
        else:
            statement = '''INSERT INTO draft VALUES (?, ?)
                           ON CONFLICT(script_id) DO UPDATE SET cues = excluded.cues'''
        connection.execute(statement, (script_id, canonical_json(cues)))

    def get_draft(self, connection, script_id):
        row = connection.execute('SELECT cues FROM draft WHERE script_id = ?', (script_id,)).fetchone()
        return json.loads(row['cues']) if row else None

    def insert_revision(self, connection, script_id, cues):
        row = connection.execute(
            'INSERT INTO approved_revision(script_id, cues) VALUES (?, ?)',
            (script_id, canonical_json(cues)),
        )
        return row.lastrowid

    def get_revision(self, connection, revision_id):
        row = connection.execute(
            'SELECT script_id, cues FROM approved_revision WHERE id = ?', (revision_id,),
        ).fetchone()
        if row is None:
            return None
        return row['script_id'], json.loads(row['cues'])
