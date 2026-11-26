from dataclasses import asdict, dataclass

from editorial.reconcile import confirm_correction
from local_service import Problem, transaction
from scripts.validation import correction_parameters


@dataclass(frozen=True)
class CorrectionRequest:
    correction_id: str
    show_id: str
    cue_id: str
    zh: str
    en: str


def correct(shows, receipts, client, request: CorrectionRequest):
    parameters = correction_parameters(asdict(request))
    with transaction(receipts.database, write=True) as connection:
        old = receipts.get_correction(connection, request.correction_id)
        if old is None:
            manifest = shows.get_manifest(connection, request.show_id)
            preload = receipts.get_preload(connection, request.show_id)
            if not preload or manifest is None or not any(
                output.cue_id == request.cue_id for output in manifest.outputs
            ):
                raise Problem(404, 'unknown_cue', show_id=request.show_id, cue_id=request.cue_id)
        receipt = receipts.register_correction(connection, parameters)
    if receipt.status != 'pending':
        return receipt
    response = client.lookup_correction(request.correction_id) if old is not None else None
    if response is None:
        response = client.send_correction(parameters)
    return confirm_correction(receipts, receipt, response)
