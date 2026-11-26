import time

from local_service import Problem, integer


class LocalClock:
    def __init__(self, source=None):
        self.source = source if source is not None else time.time_ns
        self.nanoseconds = source is None

    def now(self):
        sampled = self.source()
        if self.nanoseconds:
            sampled //= 1_000_000_000
        now = integer(sampled, 'clock')
        if now < 0:
            raise Problem(400, 'negative_clock')
        return now


def due_outputs(inbox, cues, connection, show_id, now):
    if inbox.get_receipt(connection, show_id) is None:
        raise Problem(404, 'unknown_show', show_id=show_id)
    return cues.pending_outputs(connection, show_id, now)
