from collections import defaultdict
from dataclasses import dataclass

from airlog.reconcile import missing_languages
from airlog.records import AirRecord


@dataclass(frozen=True)
class CueReadback:
    cue_id: str
    records: tuple[AirRecord, ...]
    missing: tuple[str, ...]
    complete: bool


def summarize_readback(manifest, records, cue_id=None):
    by_cue = defaultdict(list)
    for record in records:
        if record.show_id == manifest.show_id:
            by_cue[record.cue_id].append(record)
    missing = missing_languages(manifest, records)
    identities = (cue_id,) if cue_id is not None else tuple(missing)
    return tuple(CueReadback(identity, tuple(by_cue[identity]), missing[identity], not missing[identity])
                 for identity in identities)
