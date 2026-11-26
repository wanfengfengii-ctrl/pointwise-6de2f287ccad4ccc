import hashlib
import json
from dataclasses import asdict, dataclass

from local_service import Problem, canonical_json, integer, label, object_fields
from program.codisplay import CoDisplay, parse_co_display
from program.conflicts import find_screen_conflicts
from program.schedule import ScheduledOutput, schedule_sort_key
from scripts.revisions import revision_number
from scripts.validation import LANGUAGES


@dataclass(frozen=True)
class ShowManifest:
    show_id: str
    revision: str
    outputs: tuple[ScheduledOutput, ...]
    co_display: CoDisplay | None = None


def build_manifest(show_id, revision, outputs, co_display=None):
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
    return ShowManifest(show_id, revision, tuple(sorted(outputs, key=schedule_sort_key)),
                        co_display=co_display)


def manifest_view(manifest):
    """JSON-safe manifest dict; ordinary shows stay free of co_display."""
    value = asdict(manifest)
    if value.get('co_display') is None:
        value.pop('co_display', None)
    return value


def encode_manifest(manifest):
    return canonical_json(manifest_view(manifest))


def decode_manifest(body):
    try:
        value = json.loads(body)
    except (ValueError, RecursionError) as error:
        raise Problem(400, 'invalid_manifest') from error
    if not isinstance(value, dict):
        raise Problem(400, 'invalid_manifest')
    keys = set(value)
    required = {'show_id', 'revision', 'outputs'}
    if required - keys or keys - required - {'co_display'}:
        object_fields(value, 'show_id', 'revision', 'outputs')
    if not isinstance(value['outputs'], list):
        raise Problem(400, 'invalid_manifest')
    outputs = [
        ScheduledOutput(**object_fields(output, 'cue_id', 'language', 'at', 'screen', 'duration', 'text'))
        for output in value['outputs']
    ]
    co_display = parse_co_display(value['co_display']) if 'co_display' in value else None
    return build_manifest(value['show_id'], value['revision'], outputs, co_display)


def manifest_identity(manifest):
    return hashlib.sha256(encode_manifest(manifest).encode('utf-8')).hexdigest()
