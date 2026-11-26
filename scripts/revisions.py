import re
from dataclasses import asdict, dataclass

from local_service import Problem
from scripts.draft import ScriptDraft


@dataclass(frozen=True)
class ApprovedCue:
    cue_id: str
    second: int
    zh: str
    en: str


@dataclass(frozen=True)
class ApprovedRevision:
    revision: str
    script_id: str
    cues: tuple[ApprovedCue, ...]


def revision_number(revision):
    if not isinstance(revision, str) or re.fullmatch(r'V[1-9][0-9]{0,18}', revision) is None:
        raise Problem(404, 'unapproved_revision')
    number = int(revision[1:])
    if number >= 2**63:
        raise Problem(404, 'unapproved_revision')
    return number


def save_approved_revision(repository, connection, draft: ScriptDraft):
    number = repository.insert_revision(connection, draft.script_id, [asdict(cue) for cue in draft.cues])
    return f'V{number}'


def load_approved_revision(repository, connection, revision):
    result = repository.get_revision(connection, revision_number(revision))
    if result is None:
        raise Problem(404, 'unapproved_revision')
    script_id, cues = result
    return ApprovedRevision(revision, script_id, tuple(ApprovedCue(**cue) for cue in cues))
