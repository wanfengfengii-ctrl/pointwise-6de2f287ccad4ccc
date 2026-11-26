import json
from dataclasses import dataclass

from local_service import Problem, canonical_json, create_tables, transaction
from program.codisplay import STATE_TABLE_SQL, get_state, put_state
from scripts.revisions import revision_number
from scripts.validation import correction_parameters


@dataclass(frozen=True)
class CueExecution:
    show_id: str
    cue_id: str
    version: str
    zh: str
    en: str
    started: bool


@dataclass(frozen=True)
class CorrectionDecision:
    request: dict
    status: str
    version: str


@dataclass(frozen=True)
class OutputWork:
    cue_id: str
    language: str
    at: int


class CueStore:
    def __init__(self, database):
        self.database = database

    def initialize(self):
        create_tables(self.database, '''
            CREATE TABLE IF NOT EXISTS cue_group (
                show_id TEXT NOT NULL, cue_id TEXT NOT NULL, version TEXT NOT NULL,
                zh TEXT NOT NULL, en TEXT NOT NULL,
                started INTEGER NOT NULL DEFAULT 0 CHECK (started IN (0, 1)),
                PRIMARY KEY (show_id, cue_id)
            );
            CREATE TABLE IF NOT EXISTS output_work (
                show_id TEXT NOT NULL, cue_id TEXT NOT NULL, language TEXT NOT NULL,
                at INTEGER NOT NULL, ordinal INTEGER NOT NULL,
                done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1)),
                PRIMARY KEY (show_id, cue_id, language),
                UNIQUE (show_id, ordinal),
                FOREIGN KEY (show_id, cue_id) REFERENCES cue_group(show_id, cue_id)
            );
            CREATE TABLE IF NOT EXISTS correction_decision (
                correction_id TEXT PRIMARY KEY, request TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('accepted', 'already_shown')),
                version TEXT NOT NULL
            );
        ''' + STATE_TABLE_SQL)

    def register_manifest_cues(self, connection, manifest):
        texts = {}
        for output in manifest.outputs:
            texts.setdefault(output.cue_id, {})[output.language] = output.text
        connection.executemany('''
            INSERT INTO cue_group(show_id, cue_id, version, zh, en) VALUES (?, ?, ?, ?, ?)
        ''', [(manifest.show_id, cue_id, manifest.revision, pair['zh'], pair['en'])
              for cue_id, pair in texts.items()])
        connection.executemany('''
            INSERT INTO output_work(show_id, cue_id, language, at, ordinal) VALUES (?, ?, ?, ?, ?)
        ''', [(manifest.show_id, output.cue_id, output.language, output.at, index)
              for index, output in enumerate(manifest.outputs)])

    def pending_outputs(self, connection, show_id, now):
        rows = connection.execute('''
            SELECT cue_id, language, at FROM output_work
            WHERE show_id = ? AND done = 0 AND at <= ? ORDER BY ordinal
        ''', (show_id, now))
        return tuple(OutputWork(**dict(row)) for row in rows)

    def _execution(self, connection, show_id, cue_id):
        row = connection.execute('''
            SELECT version, zh, en, started FROM cue_group WHERE show_id = ? AND cue_id = ?
        ''', (show_id, cue_id)).fetchone()
        if row is None:
            raise Problem(404, 'unknown_cue', show_id=show_id, cue_id=cue_id)
        return CueExecution(show_id, cue_id, row['version'], row['zh'], row['en'], bool(row['started']))

    def apply_correction(self, request):
        request = correction_parameters(request)
        correction_id = request['correction_id']
        show_id, cue_id = request['show_id'], request['cue_id']
        with transaction(self.database, write=True) as connection:
            old = self._decision(connection, correction_id)
            if old is not None:
                if old.request != request:
                    raise Problem(409, 'correction_parameter_mismatch', correction_id=correction_id)
                return old
            execution = self._execution(connection, show_id, cue_id)
            version = execution.version
            if execution.started:
                status = 'already_shown'
            else:
                status = 'accepted'
                version = next_version(version)
                connection.execute('''
                    UPDATE cue_group SET version = ?, zh = ?, en = ? WHERE show_id = ? AND cue_id = ?
                ''', (version, request['zh'], request['en'], show_id, cue_id))
            connection.execute('INSERT INTO correction_decision VALUES (?, ?, ?, ?)',
                               (correction_id, canonical_json(request), status, version))
            return CorrectionDecision(request, status, version)

    def _decision(self, connection, correction_id):
        row = connection.execute('''
            SELECT request, status, version FROM correction_decision WHERE correction_id = ?
        ''', (correction_id,)).fetchone()
        if row is None:
            return None
        return CorrectionDecision(json.loads(row['request']), row['status'], row['version'])

    def lookup_correction(self, correction_id):
        with transaction(self.database) as connection:
            return self._decision(connection, correction_id)

    def select_output(self, connection, show_id, work):
        execution = self._execution(connection, show_id, work.cue_id)
        return execution.version, getattr(execution, work.language)

    def mark_output(self, connection, show_id, work):
        connection.execute('UPDATE cue_group SET started = 1 WHERE show_id = ? AND cue_id = ?',
                           (show_id, work.cue_id))
        connection.execute('''
            UPDATE output_work SET done = 1 WHERE show_id = ? AND cue_id = ? AND language = ?
        ''', (show_id, work.cue_id, work.language))

    def co_display_state(self, connection, show_id):
        return get_state(connection, show_id)

    def save_co_display_state(self, connection, show_id, status):
        put_state(connection, show_id, status)


def next_version(version):
    # Revisions use Vn. Cue versions are scoped by show and cue, including corrections.
    digits = version[1:]
    number = int(digits) if len(digits) > 19 or int(digits) >= 2**63 else revision_number(version)
    return f'V{number + 1}'
