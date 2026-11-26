from airlog.records import AirRecord
from local_service import label, transaction
from projection.timing import due_outputs


def advance(inbox, cues, records, clock, show_id):
    label(show_id, 'show_id')
    aired = []
    with transaction(inbox.database, write=True) as connection:
        now = clock.now()
        for work in due_outputs(inbox, cues, connection, show_id, now):
            version, text = cues.select_output(connection, show_id, work)
            record = AirRecord(show_id, work.cue_id, work.language, now, version, text)
            records.append(connection, record)
            cues.mark_output(connection, show_id, work)
            aired.append(record)
    return tuple(aired)
