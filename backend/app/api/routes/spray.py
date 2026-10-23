from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db
from app.api.idempotency import REPLAY_HEADER, idempotency_key, serialised
from app.api.schemas import ErrorOut, SprayLogIn, SprayLogOut
from app.domain.types import FarmerProfile
from app.services.container import Container
from app.services.spray_service import SprayService

router = APIRouter(prefix="/v1/spray-logs", tags=["spray diary"], responses={401: {"model": ErrorOut}})


@router.post("", response_model=SprayLogOut, responses={400: {"model": ErrorOut}, 404: {"model": ErrorOut}})
def create_spray_log(body: SprayLogIn, response: Response, farmer: FarmerProfile = Depends(get_current_farmer),
                     request_key: str | None = Depends(idempotency_key), db: Session = Depends(get_db),
                     container: Container = Depends(get_container)) -> SprayLogOut:
    """The 'Sprayed' tick. Writes to the DB and to Zoho (adapter). Returns warnings, e.g. a nutrient logged the same day (HP 2026 point 7).

    Which medicine: `product_id` (one of the advice's products, or any product of the approved catalogue); else, when only
    `advice_id` is sent (the plain 'I sprayed this' tick), the advice's first product, the one that was read aloud; else the
    typed `free_text`, which is matched exactly (brand, active ingredient in English or Hindi, or product id) against the
    catalogue so the spray checks run. A name that cannot be matched, or that fits several different products, is saved as
    typed with the yellow warning `PRODUCT_NOT_RECOGNISED`. An advice without products (the expert route) needs a typed name
    (422 `spray_needs_product` otherwise). The advice must belong to the logged-in farmer (404 `advice_not_found`).

    Idempotent: send an `Idempotency-Key` header (a fresh UUID per queued entry, kept on every retry). A replay by the same
    farmer returns the stored entry (same id, 200, header `Idempotent-Replayed: true`) and writes nothing to Zoho again.
    """
    service = SprayService(container, db)
    with serialised("spray", farmer.id, request_key):
        replay = service.find_by_request_id(farmer, request_key)
        if replay is not None:
            response.headers[REPLAY_HEADER] = "true"
            return replay
        return service.create(farmer, body, client_request_id=request_key)


@router.get("", response_model=list[SprayLogOut])
def list_spray_logs(limit: int = 50, farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
                    container: Container = Depends(get_container)) -> list[SprayLogOut]:
    return SprayService(container, db).list_logs(farmer, limit)
