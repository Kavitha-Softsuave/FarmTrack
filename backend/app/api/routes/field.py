from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_container, get_current_farmer, get_db
from app.api.schemas import ErrorOut, FieldOut
from app.domain.types import FarmerProfile
from app.services.container import Container
from app.services.field_service import FieldService

router = APIRouter(prefix="/v1", tags=["field"], responses={401: {"model": ErrorOut}})


@router.get("/field", response_model=FieldOut)
def get_field(farmer: FarmerProfile = Depends(get_current_farmer), db: Session = Depends(get_db),
              container: Container = Depends(get_container)) -> FieldOut:
    """My field: latest sensor readings (stale flag), 7-day forecast, weather risks, spoken summary."""
    return FieldService(container, db).get(farmer)
