from local_service import label
from program.codisplay import parse_co_display, verify_joint_walk
from program.manifest import build_manifest
from program.schedule import build_schedule
from program.show import ShowBinding
from scripts.revisions import load_approved_revision


def rehearse(scripts, shows, show_id, revision, start, lanes, co_display=None):
    label(show_id, 'show_id')
    convention = parse_co_display(co_display)
    with scripts.transaction() as connection:
        approved = load_approved_revision(scripts, connection, revision)
    schedule = build_schedule(approved, start, lanes)
    if convention is not None:
        # Raises 400 for an ineligible show shape or out-of-range starts and
        # 409 when the two lanes have no jointly readable walk.
        verify_joint_walk(schedule, convention)
    manifest = build_manifest(show_id, approved.revision, schedule, convention)
    shows.save_rehearsal(ShowBinding(show_id, approved.revision, start, lanes), manifest)
    return manifest
