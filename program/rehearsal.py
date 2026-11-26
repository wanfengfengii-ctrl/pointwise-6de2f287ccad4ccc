from local_service import label
from program.manifest import build_manifest
from program.schedule import build_schedule
from program.show import ShowBinding
from scripts.revisions import load_approved_revision


def rehearse(scripts, shows, show_id, revision, start, lanes):
    label(show_id, 'show_id')
    with scripts.transaction() as connection:
        approved = load_approved_revision(scripts, connection, revision)
    schedule = build_schedule(approved, start, lanes)
    manifest = build_manifest(show_id, approved.revision, schedule)
    shows.save_rehearsal(ShowBinding(show_id, approved.revision, start, lanes), manifest)
    return manifest
