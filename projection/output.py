from airlog.records import AirRecord
from local_service import Problem, label, transaction
from program.codisplay import TERMINAL_STATUSES, plan_advance
from projection.cues import OutputWork
from projection.timing import due_outputs


def _advance_co_display(connection, inbox, cues, records, show_id, manifest, now):
    terminal = cues.co_display_state(connection, show_id)
    if terminal in TERMINAL_STATUSES:
        return ()

    prior = records.list_records(connection, show_id)
    starts = {record.language: record.aired_at for record in prior}
    status, emit_languages = plan_advance(manifest, starts, now)

    cue_id = manifest.outputs[0].cue_id
    aired = []
    for language in emit_languages:
        work = OutputWork(cue_id, language, now)
        version, text = cues.select_output(connection, show_id, work)
        record = AirRecord(show_id, cue_id, language, now, version, text)
        records.append(connection, record)
        cues.mark_output(connection, show_id, work)
        aired.append(record)

    if status in TERMINAL_STATUSES:
        cues.save_co_display_state(connection, show_id, status)
    return tuple(aired)


def advance(inbox, cues, records, clock, show_id):
    label(show_id, 'show_id')
    aired = []
    with transaction(inbox.database, write=True) as connection:
        now = clock.now()
        if inbox.get_receipt(connection, show_id) is None:
            raise Problem(404, 'unknown_show', show_id=show_id)
        manifest = inbox.get_manifest(connection, show_id)
        if manifest is not None and manifest.co_display is not None:
            return _advance_co_display(
                connection, inbox, cues, records, show_id, manifest, now)
        for work in due_outputs(inbox, cues, connection, show_id, now):
            version, text = cues.select_output(connection, show_id, work)
            record = AirRecord(show_id, work.cue_id, work.language, now, version, text)
            records.append(connection, record)
            cues.mark_output(connection, show_id, work)
            aired.append(record)
    return tuple(aired)
