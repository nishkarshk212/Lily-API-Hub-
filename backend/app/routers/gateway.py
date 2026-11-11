"""Public API Gateway router mounted at /v1/*."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.gateway_service import handle_gateway_request

router = APIRouter(tags=["Beta API Gateway (/v1)"])


@router.api_route("/v1", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway_root_dispatch(request: Request, db: Session = Depends(get_db)):
    return await handle_gateway_request(request, "", db)


@router.api_route("/v1/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway_dispatch(subpath: str, request: Request, db: Session = Depends(get_db)):
    return await handle_gateway_request(request, subpath, db)

