import json
from dataclasses import dataclass

from local_service import Problem, canonical_json, create_tables


@dataclass(frozen=True)
class PreloadReceipt:
    show_id: str
    manifest_id: str
    status: str


@dataclass(frozen=True)
class CorrectionReceipt:
    request: dict
    status: str
    version: str | None = None

    def public(self):
        response = {key: self.request[key] for key in ('correction_id', 'show_id', 'cue_id')}
        return {**response, 'status': self.status, 'version': self.version}


class ReceiptStore:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS preload_receipt (
                show_id TEXT PRIMARY KEY, manifest_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'received'))
            );
            CREATE TABLE IF NOT EXISTS correction_receipt (
                correction_id TEXT PRIMARY KEY, request TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'already_shown')),
                version TEXT
            );
        ''')

    def get_preload(self, connection, show_id):
        row = connection.execute('SELECT * FROM preload_receipt WHERE show_id = ?', (show_id,)).fetchone()
        return PreloadReceipt(**dict(row)) if row else None

    def save_preload(self, connection, receipt):
        connection.execute('''
            INSERT INTO preload_receipt VALUES (?, ?, ?)
            ON CONFLICT(show_id) DO UPDATE SET status = excluded.status
            WHERE preload_receipt.manifest_id = excluded.manifest_id
              AND preload_receipt.status = 'pending'
        ''', (receipt.show_id, receipt.manifest_id, receipt.status))
        stored = self.get_preload(connection, receipt.show_id)
        if stored.manifest_id != receipt.manifest_id:
            raise Problem(409, 'manifest_mismatch', show_id=receipt.show_id)
        return stored

    def register_correction(self, connection, request):
        connection.execute('''
            INSERT INTO correction_receipt(correction_id, request, status) VALUES (?, ?, 'pending')
            ON CONFLICT(correction_id) DO NOTHING
        ''', (request['correction_id'], canonical_json(request)))
        receipt = self.get_correction(connection, request['correction_id'])
        if receipt.request != request:
            raise Problem(409, 'correction_parameter_mismatch', correction_id=request['correction_id'])
        return receipt

    def get_correction(self, connection, correction_id):
        row = connection.execute(
            'SELECT request, status, version FROM correction_receipt WHERE correction_id = ?', (correction_id,),
        ).fetchone()
        return CorrectionReceipt(json.loads(row['request']), row['status'], row['version']) if row else None

    def save_verdict(self, connection, receipt):
        correction_id = receipt.request['correction_id']
        connection.execute('''
            UPDATE correction_receipt SET status = ?, version = ?
            WHERE correction_id = ? AND request = ? AND status = 'pending'
        ''', (receipt.status, receipt.version, correction_id, canonical_json(receipt.request)))
        return self.get_correction(connection, correction_id)
