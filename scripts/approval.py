from dataclasses import asdict

from scripts.draft import load_draft
from scripts.revisions import save_approved_revision
from scripts.validation import validate_approval_cues


def approve(repository, script_id):
    with repository.transaction(write=True) as connection:
        draft = load_draft(repository, connection, script_id)
        validate_approval_cues([asdict(cue) for cue in draft.cues])
        return save_approved_revision(repository, connection, draft)
