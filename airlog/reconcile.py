from collections import defaultdict

from scripts.validation import LANGUAGES


def missing_languages(manifest, records):
    expected = defaultdict(set)
    for work in manifest.outputs:
        expected[work.cue_id].add(work.language)
    for record in records:
        if record.show_id == manifest.show_id and record.cue_id in expected:
            expected[record.cue_id].discard(record.language)
    return {cue_id: tuple(language for language in LANGUAGES if language in missing)
            for cue_id, missing in expected.items()}
