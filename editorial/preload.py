from editorial.receipts import PreloadReceipt
from editorial.reconcile import confirm_preload
from local_service import Problem, label, transaction
from program.manifest import manifest_identity


def preload(shows, receipts, client, show_id):
    label(show_id, 'show_id')
    with transaction(shows.database, write=True) as connection:
        manifest = shows.get_manifest(connection, show_id)
        if manifest is None:
            raise Problem(404, 'no_formal_manifest', show_id=show_id)
        pending = receipts.get_preload(connection, show_id)
        existing = pending is not None
        if pending is None:
            pending = receipts.save_preload(connection, PreloadReceipt(show_id, manifest_identity(manifest), 'pending'))
            shows.pin_manifest(connection, show_id)
    if pending.status == 'received':
        return pending
    response = client.lookup_preload(show_id) if existing else None
    if response is None:
        response = client.send_preload(manifest)
    return confirm_preload(receipts, pending, response)
