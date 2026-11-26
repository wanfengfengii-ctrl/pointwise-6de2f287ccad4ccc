from dataclasses import dataclass
from itertools import groupby

from program.schedule import ScheduledOutput, schedule_sort_key


@dataclass(frozen=True)
class ScreenConflict:
    screen: str
    earlier: ScheduledOutput
    later: ScheduledOutput


def find_screen_conflicts(outputs):
    ordered = sorted(outputs, key=lambda output: (output.screen, schedule_sort_key(output)))
    conflicts = []
    for screen, group in groupby(ordered, key=lambda output: output.screen):
        active = []
        for output in group:
            active = [earlier for earlier in active if output.at < earlier.end]
            conflicts.extend(ScreenConflict(screen, earlier, output) for earlier in active)
            active.append(output)
    return tuple(conflicts)
