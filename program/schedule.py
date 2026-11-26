from dataclasses import dataclass

from local_service import Problem, integer, label, object_fields
from scripts.revisions import ApprovedRevision
from scripts.validation import LANGUAGES


@dataclass(frozen=True)
class Lane:
    offset: int
    screen: str
    duration: int


@dataclass(frozen=True)
class ScheduledOutput:
    cue_id: str
    language: str
    at: int
    screen: str
    duration: int
    text: str

    @property
    def end(self):
        return self.at + self.duration


def read_lanes(lanes):
    object_fields(lanes, *LANGUAGES)
    result = {}
    for language in LANGUAGES:
        fields = object_fields(lanes[language], 'offset', 'screen', 'duration')
        duration = integer(fields['duration'], 'duration')
        if duration <= 0:
            raise Problem(400, 'invalid_duration', language=language)
        result[language] = Lane(integer(fields['offset'], 'offset'), label(fields['screen'], 'screen'), duration)
    return result


def schedule_sort_key(output):
    return output.at, output.cue_id, LANGUAGES.index(output.language)


def build_schedule(revision: ApprovedRevision, start, lanes):
    integer(start, 'start')
    configured = read_lanes(lanes)
    if not revision.cues:
        raise Problem(400, 'empty_manifest')
    outputs = []
    for cue in revision.cues:
        for language in LANGUAGES:
            lane = configured[language]
            at = start + cue.second + lane.offset
            if at < 0:
                raise Problem(400, 'negative_output_time', cue_id=cue.cue_id, language=language)
            integer(at, 'at')
            outputs.append(ScheduledOutput(cue.cue_id, language, at, lane.screen,
                                           lane.duration, getattr(cue, language)))
    return tuple(sorted(outputs, key=schedule_sort_key))
