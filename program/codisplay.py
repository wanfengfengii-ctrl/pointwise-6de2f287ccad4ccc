"""Bilingual co-display convention: validation, joint walks and beat planning.

All arithmetic stays interval based so signed 64-bit window endpoints never
have to be enumerated.  Display windows are half-open ``[start, start+duration)``
even though scheduling windows use closed integer intervals.
"""
from dataclasses import dataclass

from local_service import Problem, integer, object_fields
from scripts.validation import LANGUAGES

INT64_MAX = 2 ** 63 - 1
STATUSES = ('waiting', 'satisfied', 'missed')
TERMINAL_STATUSES = ('satisfied', 'missed')

STATE_TABLE_SQL = '''
    CREATE TABLE IF NOT EXISTS co_display_state (
        show_id TEXT PRIMARY KEY,
        status TEXT NOT NULL CHECK (status IN ('waiting', 'satisfied', 'missed'))
    );
'''


@dataclass(frozen=True)
class CoDisplay:
    # language -> tuple of closed offset intervals ``(low, high)``, normalized.
    windows: dict
    min_seconds: int


def merge_intervals(intervals):
    """Union of closed integer intervals as disjoint sorted closed intervals."""
    ordered = sorted((int(low), int(high)) for low, high in intervals)
    merged = []
    for low, high in ordered:
        if not merged or low > merged[-1][1] + 1:
            merged.append([low, high])
        elif high > merged[-1][1]:
            merged[-1][1] = high
    return tuple((low, high) for low, high in merged)


def parse_window(raw, language):
    if not isinstance(raw, (list, tuple)) or not raw:
        raise Problem(400, 'invalid_co_display_window', language=language)
    intervals = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise Problem(400, 'invalid_co_display_window', language=language)
        low = integer(item[0], 'offset')
        high = integer(item[1], 'offset')
        if low < 0 or high < 0 or low > high:
            raise Problem(400, 'invalid_co_display_window', language=language)
        intervals.append((low, high))
    return merge_intervals(intervals)


def parse_co_display(raw):
    """Validate a request/manifest ``co_display`` object into a CoDisplay."""
    if raw is None:
        return None
    if isinstance(raw, CoDisplay):
        return raw
    if not isinstance(raw, dict):
        raise Problem(400, 'invalid_co_display')
    object_fields(raw, 'windows', 'min_seconds')
    min_seconds = integer(raw['min_seconds'], 'min_seconds')
    if min_seconds <= 0:
        raise Problem(400, 'invalid_min_seconds')
    windows_raw = raw['windows']
    if not isinstance(windows_raw, dict) or set(windows_raw) != set(LANGUAGES):
        raise Problem(400, 'invalid_co_display_windows')
    windows = {language: parse_window(windows_raw[language], language) for language in LANGUAGES}
    return CoDisplay(windows=windows, min_seconds=min_seconds)


def co_display_view(co_display):
    return {
        'windows': {language: [[low, high] for low, high in co_display.windows[language]]
                    for language in LANGUAGES},
        'min_seconds': co_display.min_seconds,
    }


def lane_outputs(outputs):
    """Return the ``(zh_output, en_output)`` pair for a single-cue show."""
    cues = {output.cue_id for output in outputs}
    if len(cues) != 1:
        raise Problem(400, 'co_display_requires_single_cue')
    by_language = {}
    for output in outputs:
        if output.language in LANGUAGES:
            by_language[output.language] = output
    if set(by_language) != set(LANGUAGES):
        raise Problem(400, 'incomplete_cue')
    zh_output, en_output = by_language['zh'], by_language['en']
    if zh_output.screen == en_output.screen:
        raise Problem(400, 'co_display_requires_separate_screens')
    return zh_output, en_output


def start_intervals(output, co_display, language):
    """Closed legal actual-start intervals after applying relative offsets."""
    intervals = []
    for low_offset, high_offset in co_display.windows[language]:
        low = output.at + low_offset
        high = output.at + high_offset
        integer(low, 'at')
        integer(high, 'at')
        if high > INT64_MAX:
            raise Problem(400, 'invalid_integer', field='at')
        intervals.append((low, high))
    return tuple(intervals)


def overlap_seconds(zh_start, en_start, zh_duration, en_duration):
    if zh_start is None or en_start is None:
        return 0
    return max(0, min(zh_start + zh_duration, en_start + en_duration)
               - max(zh_start, en_start))


def _expanded_partner_range(fixed_start, own_duration, partner_duration, min_seconds):
    """Range of partner starts yielding overlap >= min with a fixed start.

    For zh start x and en start y feasibility is
    ``y - (zh_duration - m) <= x <= y + (en_duration - m)``, so fixing x
    leaves ``x - (en_duration - m) <= y <= x + (zh_duration - m)``.
    """
    reach_zh = own_duration - min_seconds
    reach_en = partner_duration - min_seconds
    if reach_zh < 0 or reach_en < 0:
        return None
    return fixed_start - reach_en, fixed_start + reach_zh


def qualifying_intervals(fixed_language, fixed_start, zh_output, en_output, co_display):
    """Legal partner-start intervals that reach the minimum overlap."""
    minimum = co_display.min_seconds
    if fixed_language == 'zh':
        range_pair = _expanded_partner_range(
            fixed_start, zh_output.duration, en_output.duration, minimum)
        partner_output = en_output
        partner_language = 'en'
    else:
        # Swap roles: treat en as "own" and zh as "partner".
        range_pair = _expanded_partner_range(
            fixed_start, en_output.duration, zh_output.duration, minimum)
        partner_output = zh_output
        partner_language = 'zh'
    if range_pair is None:
        return ()
    range_low, range_high = range_pair
    result = []
    for low, high in start_intervals(partner_output, co_display, partner_language):
        clipped_low = max(low, range_low)
        clipped_high = min(high, range_high)
        if clipped_low <= clipped_high:
            result.append((clipped_low, clipped_high))
    return tuple(result)


def has_point_after(intervals, second):
    """Some integer start in the closed intervals is strictly after second."""
    return any(high > second for low, high in intervals)


def contains_second(intervals, second):
    return any(low <= second <= high for low, high in intervals)


def _joint_exists(zh_intervals, en_intervals, zh_duration, en_duration, minimum, now=None,
                  strict_after=False):
    """Interval-aware existence of a feasible joint start pair.

    When ``now`` is given, both starts must be ``>= now`` (or ``> now`` when
    ``strict_after``).
    """
    if zh_duration < minimum or en_duration < minimum:
        return False
    reach_zh = zh_duration - minimum
    reach_en = en_duration - minimum
    floor = None if now is None else (now + 1 if strict_after else now)
    for y_low, y_high in en_intervals:
        if floor is not None:
            y_low = max(y_low, floor)
            if y_low > y_high:
                continue
        # For a whole en interval, feasible zh values span
        # [y_low - reach_zh, y_high + reach_en] (integer union).
        span_low = y_low - reach_zh
        span_high = y_high + reach_en
        for x_low, x_high in zh_intervals:
            left = max(x_low, span_low)
            right = min(x_high, span_high)
            if floor is not None:
                left = max(left, floor)
            if left <= right:
                return True
    return False


def verify_joint_walk(outputs, co_display):
    """400 for wrong show shape/range, 409 when no joint walk exists."""
    zh_output, en_output = lane_outputs(outputs)
    zh_intervals = start_intervals(zh_output, co_display, 'zh')
    en_intervals = start_intervals(en_output, co_display, 'en')
    if not _joint_exists(zh_intervals, en_intervals,
                         zh_output.duration, en_output.duration, co_display.min_seconds):
        raise Problem(409, 'no_joint_walk')
    return zh_output, en_output


def plan_advance(manifest, starts, now):
    """Decide one beat for a co-display show.

    ``starts`` maps already-aired languages to their actual start second.
    Returns ``(status, emit_languages)`` where status is the resulting
    co-display status for this invocation (``waiting`` unless terminal).
    """
    co_display = manifest.co_display
    zh_output, en_output = lane_outputs(manifest.outputs)
    durations = {'zh': zh_output.duration, 'en': en_output.duration}

    if len(starts) == 2:
        overlap = overlap_seconds(starts['zh'], starts['en'],
                                  durations['zh'], durations['en'])
        return ('satisfied' if overlap >= co_display.min_seconds else 'missed'), ()

    if len(starts) == 1:
        fixed_language, fixed_start = next(iter(starts.items()))
        intervals = qualifying_intervals(
            fixed_language, fixed_start, zh_output, en_output, co_display)
        if has_point_after(intervals, now):
            return 'waiting', ()
        if contains_second(intervals, now):
            partner = 'en' if fixed_language == 'zh' else 'zh'
            return 'satisfied', (partner,)
        return 'missed', ()

    zh_intervals = start_intervals(zh_output, co_display, 'zh')
    en_intervals = start_intervals(en_output, co_display, 'en')
    minimum = co_display.min_seconds

    # A fully future joint walk means every undisplayed lane can wait.
    if _joint_exists(zh_intervals, en_intervals, durations['zh'], durations['en'],
                     minimum, now=now, strict_after=True):
        return 'waiting', ()

    # No joint walk can use only strictly future starts any more.
    # Is there still a joint walk using present (>= now) starts?
    if not _joint_exists(zh_intervals, en_intervals, durations['zh'], durations['en'],
                         minimum, now=now):
        return 'missed', ()

    # Commit at most one lane now when that leaves the partner a strictly
    # future legal start.  zh wins the symmetric fork by fixed language order.
    if contains_second(zh_intervals, now):
        zh_partners = qualifying_intervals('zh', now, zh_output, en_output, co_display)
        if has_point_after(zh_partners, now):
            return 'waiting', ('zh',)
    if contains_second(en_intervals, now):
        en_partners = qualifying_intervals('en', now, zh_output, en_output, co_display)
        if has_point_after(en_partners, now):
            return 'waiting', ('en',)

    # Neither lane can be left pending: both must start this same second.
    if contains_second(zh_intervals, now):
        zh_partners = qualifying_intervals('zh', now, zh_output, en_output, co_display)
        if contains_second(zh_partners, now):
            return 'satisfied', ('zh', 'en')

    # Defensive: a present joint walk existed but no committable action remains.
    return 'missed', ()


def get_state(connection, show_id):
    row = connection.execute(
        'SELECT status FROM co_display_state WHERE show_id = ?', (show_id,),
    ).fetchone()
    return row['status'] if row is not None else None


def readback_block(manifest, aired, persisted_status):
    """Build the read-only co_display block without advancing any state."""
    zh_output, en_output = lane_outputs(manifest.outputs)
    starts = {language: None for language in LANGUAGES}
    for record in aired:
        if record.language in starts and starts[record.language] is None:
            starts[record.language] = record.aired_at
    overlap = overlap_seconds(starts['zh'], starts['en'],
                              zh_output.duration, en_output.duration)
    if persisted_status in TERMINAL_STATUSES:
        status = persisted_status
    elif starts['zh'] is not None and starts['en'] is not None:
        status = 'satisfied' if overlap >= manifest.co_display.min_seconds else 'missed'
    else:
        status = 'waiting'
    return {'status': status, 'starts': starts, 'overlap_seconds': overlap}


def put_state(connection, show_id, status):
    connection.execute('''
        INSERT INTO co_display_state(show_id, status) VALUES (?, ?)
        ON CONFLICT(show_id) DO UPDATE SET status = excluded.status
    ''', (show_id, status))
