import hashlib
import json
from dataclasses import asdict, dataclass

from local_service import Problem, canonical_json, integer, label, object_fields
from program.conflicts import find_screen_conflicts
from program.schedule import ScheduledOutput, schedule_sort_key
from scripts.revisions import revision_number
from scripts.validation import LANGUAGES


@dataclass(frozen=True)
class ShowManifest:
    show_id: str
    revision: str
    outputs: tuple[ScheduledOutput, ...]


def build_manifest(show_id, revision, outputs):
    label(show_id, 'show_id')
    revision_number(revision)
    if not outputs:
        raise Problem(400, 'empty_manifest')
    lanes = {}
    for output in outputs:
        label(output.cue_id, 'cue_id')
        label(output.screen, 'screen')
        label(output.text, 'text')
        integer(output.at, 'at')
        integer(output.duration, 'duration')
        if output.at < 0 or output.duration <= 0 or output.language not in LANGUAGES:
            raise Problem(400, 'invalid_output', cue_id=output.cue_id)
        languages = lanes.setdefault(output.cue_id, set())
        if output.language in languages:
            raise Problem(400, 'duplicate_output', cue_id=output.cue_id, language=output.language)
        languages.add(output.language)
    if any(languages != set(LANGUAGES) for languages in lanes.values()):
        raise Problem(400, 'incomplete_cue')
    conflicts = find_screen_conflicts(outputs)
    if conflicts:
        windows = []
        for conflict in conflicts:
            windows.append({
                'screen': conflict.screen,
                'outputs': [
                    {'cue_id': item.cue_id, 'language': item.language, 'window': [item.at, item.end]}
                    for item in (conflict.earlier, conflict.later)
                ],
            })
        raise Problem(409, 'screen_conflict', conflicts=windows)
    return ShowManifest(show_id, revision, tuple(sorted(outputs, key=schedule_sort_key)))


def encode_manifest(manifest):
    return canonical_json(asdict(manifest))


def decode_manifest(body):
    try:
        value = json.loads(body)
    except (ValueError, RecursionError) as error:
        raise Problem(400, 'invalid_manifest') from error
    object_fields(value, 'show_id', 'revision', 'outputs')
    if not isinstance(value['outputs'], list):
        raise Problem(400, 'invalid_manifest')
    outputs = [
        ScheduledOutput(**object_fields(output, 'cue_id', 'language', 'at', 'screen', 'duration', 'text'))
        for output in value['outputs']
    ]
    return build_manifest(value['show_id'], value['revision'], outputs)


def manifest_identity(manifest):
    return hashlib.sha256(encode_manifest(manifest).encode('utf-8')).hexdigest()
