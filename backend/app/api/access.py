from fastapi import APIRouter, Request

from app.services.ip_access_service import build_access_status


router = APIRouter(prefix="/access", tags=["access"])


@router.get("/status")
def access_status(request: Request):
    return build_access_status(request)