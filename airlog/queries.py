from dataclasses import asdict

from airlog.summary import summarize_readback
from local_service import Problem, label, transaction
from program.codisplay import get_state, readback_block


def readback(inbox, records, show_id, cue_id=None):
    label(show_id, 'show_id')
    if cue_id is not None:
        label(cue_id, 'cue_id')
    with transaction(inbox.database) as connection:
        manifest = inbox.get_manifest(connection, show_id)
        if manifest is None:
            raise Problem(404, 'unknown_show', show_id=show_id)
        if cue_id is not None and not any(output.cue_id == cue_id for output in manifest.outputs):
            raise Problem(404, 'unknown_cue', show_id=show_id, cue_id=cue_id)
        aired = records.list_records(connection, show_id, cue_id)
        cues = summarize_readback(manifest, aired, cue_id)
        result = {'show_id': show_id, 'records': [asdict(record) for record in aired],
                  'cues': [asdict(cue) for cue in cues],
                  'complete': all(cue.complete for cue in cues)}
        if manifest.co_display is not None:
            persisted = get_state(connection, show_id)
            co_display = readback_block(manifest, aired, persisted)
            result['co_display'] = co_display
            result['complete'] = co_display['status'] == 'satisfied'
        return result
