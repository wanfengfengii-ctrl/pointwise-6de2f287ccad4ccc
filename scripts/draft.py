from dataclasses import dataclass

from local_service import Problem, label
from scripts.validation import validate_draft_cues


@dataclass(frozen=True)
class CueDraft:
    cue_id: str
    second: int
    zh: str
    en: str


@dataclass(frozen=True)
class ScriptDraft:
    script_id: str
    cues: tuple[CueDraft, ...]


def save_draft(repository, script_id, cues, *, if_absent=False):
    label(script_id, 'script_id')
    validate_draft_cues(cues)
    with repository.transaction(write=True) as connection:
        repository.put_draft(connection, script_id, cues, if_absent=if_absent)
    return script_id


def load_draft(repository, connection, script_id):
    label(script_id, 'script_id')
    cues = repository.get_draft(connection, script_id)
    if cues is None:
        raise Problem(404, 'unknown_draft', script_id=script_id)
    return ScriptDraft(script_id, tuple(CueDraft(**cue) for cue in cues))
