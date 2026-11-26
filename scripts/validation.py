from local_service import Problem, integer, label, object_fields

LANGUAGES = ('zh', 'en')


def validate_text_pair(zh, en):
    return label(zh, 'zh'), label(en, 'en')


def validate_draft_cues(cues):
    if not isinstance(cues, (list, tuple)):
        raise Problem(400, 'invalid_cues')
    seen = set()
    for cue in cues:
        object_fields(cue, 'cue_id', 'second', 'zh', 'en')
        cue_id = label(cue['cue_id'], 'cue_id')
        integer(cue['second'], 'second')
        validate_text_pair(cue['zh'], cue['en'])
        if cue_id in seen:
            raise Problem(400, 'duplicate_cue', cue_id=cue_id)
        seen.add(cue_id)


def validate_approval_cues(cues):
    validate_draft_cues(cues)
    if not cues:
        raise Problem(400, 'empty_draft')


def correction_parameters(value):
    fields = ('correction_id', 'show_id', 'cue_id', 'zh', 'en')
    object_fields(value, *fields)
    request = {field: label(value[field], field) for field in fields[:3]}
    request['zh'], request['en'] = validate_text_pair(value['zh'], value['en'])
    return request
