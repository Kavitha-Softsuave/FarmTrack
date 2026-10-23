from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db
from app.api.schemas import DeviceIn, ErrorOut
from app.db.models import DeviceRow, new_id
from app.domain.types import FarmerProfile
from app.security.errors import ApiError
from app.services.container import Container

router = APIRouter(prefix="/v1/devices", tags=["devices"], responses={401: {"model": ErrorOut}})


@router.post("", status_code=204)
def register_device(body: DeviceIn, farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
                    container: Container = Depends(get_container)) -> Response:
    """Register or update the push token for this device. A token seen before moves to the farmer now logged in on it."""
    token = body.push_token.strip()
    if not token:
        raise ApiError(422, "invalid_push_token", "The push token cannot be empty.")
    now = container.clock.now()
    app_version = (body.app_version or "").strip()[:20] or None          # the column is 20 wide: PostgreSQL refuses more
    device = db.scalars(select(DeviceRow).where(DeviceRow.push_token == token)).first()
    if device is None:
        db.add(DeviceRow(id=new_id(), farmer_id=farmer.id, platform=body.platform, push_token=token,
                         app_version=app_version, updated_at=now))
    else:
        device.farmer_id = farmer.id
        device.platform = body.platform
        device.app_version = app_version
        device.updated_at = now
    db.commit()
    return Response(status_code=204)
