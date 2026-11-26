from dataclasses import dataclass

from local_service import create_tables


@dataclass(frozen=True)
class AirRecord:
    show_id: str
    cue_id: str
    language: str
    aired_at: int
    version: str
    text: str


class AirRecordStore:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS air_record (
                id INTEGER PRIMARY KEY, show_id TEXT NOT NULL, cue_id TEXT NOT NULL,
                language TEXT NOT NULL, aired_at INTEGER NOT NULL,
                version TEXT NOT NULL, text TEXT NOT NULL,
                UNIQUE (show_id, cue_id, language)
            );
        ''')

    def append(self, connection, record):
        connection.execute('''
            INSERT INTO air_record(show_id, cue_id, language, aired_at, version, text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (record.show_id, record.cue_id, record.language, record.aired_at, record.version, record.text))

    def list_records(self, connection, show_id, cue_id=None):
        statement = 'SELECT show_id, cue_id, language, aired_at, version, text FROM air_record WHERE show_id = ?'
        parameters = [show_id]
        if cue_id is not None:
            statement += ' AND cue_id = ?'
            parameters.append(cue_id)
        rows = connection.execute(statement + ' ORDER BY id', parameters)
        return tuple(AirRecord(**dict(row)) for row in rows)
