from local_service import Problem, label, transaction
from editorial.receipts import CorrectionReceipt, PreloadReceipt


def confirm_preload(store, pending, response):
    expected = {'show_id': pending.show_id, 'manifest_id': pending.manifest_id, 'status': 'received'}
    if response == expected:
        with transaction(store.database, write=True) as connection:
            return store.save_preload(connection, PreloadReceipt(**expected))
    with transaction(store.database) as connection:
        return store.get_preload(connection, pending.show_id)


def confirm_correction(store, pending, response):
    if isinstance(response, dict) and response.get('request') == pending.request:
        status = response.get('status')
        version = response.get('version')
        if status in ('accepted', 'already_shown') and isinstance(version, str) and version:
            with transaction(store.database, write=True) as connection:
                return store.save_verdict(connection, CorrectionReceipt(pending.request, status, version))
    with transaction(store.database) as connection:
        return store.get_correction(connection, pending.request['correction_id'])


def verdict(store, client, correction_id):
    label(correction_id, 'correction_id')
    with transaction(store.database) as connection:
        receipt = store.get_correction(connection, correction_id)
    if receipt is None:
        raise Problem(404, 'unknown_correction', correction_id=correction_id)
    if receipt.status != 'pending':
        return receipt
    return confirm_correction(store, receipt, client.lookup_correction(correction_id))
