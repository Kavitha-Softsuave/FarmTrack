from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_farmer, get_db
from app.api.schemas import ErrorOut, FarmerOut, FarmerPatch
from app.db.repo import farmer_profile, get_farmer_row
from app.domain.types import FarmerProfile
from app.security.errors import ApiError
from app.services.presenters import farmer_out

router = APIRouter(prefix="/v1", tags=["me"], responses={401: {"model": ErrorOut}})


@router.get("/me", response_model=FarmerOut)
def get_me(farmer: FarmerProfile = Depends(get_current_farmer)) -> FarmerOut:
    return farmer_out(farmer)


@router.patch("/me", response_model=FarmerOut)
def patch_me(body: FarmerPatch, farmer: FarmerProfile = Depends(get_current_farmer),
             db: Session = Depends(get_db)) -> FarmerOut:
    row = get_farmer_row(db, farmer.id)
    if row is None:
        raise ApiError(401, "invalid_token", "Your session is not valid. Please log in again.")
    if body.language is not None:
        row.language = body.language
    if body.name is not None:
        name = "".join(ch for ch in body.name if ch.isprintable()).strip()
        if not name:
            raise ApiError(422, "invalid_name", "The name cannot be empty.")
        row.name = name
    db.commit()
    return farmer_out(farmer_profile(row))
