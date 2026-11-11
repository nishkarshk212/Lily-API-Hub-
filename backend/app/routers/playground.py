"""API Testing Playground executor targeting the live gateway middleware."""

import base64
import json
import re
import time
from urllib.parse import unquote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decrypt_secret
from app.models.api_key import ApiKey
from app.models.user import User
from app.routers.deps import get_current_user
from app.schemas.domain import PlaygroundExecuteRequest

router = APIRouter(prefix="/api/playground", tags=["API Playground"])


@router.post("/execute")
async def execute_playground_request(
    payload: PlaygroundExecuteRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    endpoint = payload.endpoint.strip()
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    if not endpoint.startswith("/v1/"):
        if endpoint == "/v1":
            endpoint = "/v1/status"
        else:
            endpoint = f"/v1/{endpoint.lstrip('/')}"

    api_key_value = (payload.raw_api_key or "").strip()
    if payload.api_key_id:
        key_row = db.get(ApiKey, payload.api_key_id)
        if not key_row or key_row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Selected API key not found.")
        decrypted = decrypt_secret(key_row.encrypted_key)
        if not decrypted:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to decrypt API key.")
        api_key_value = decrypted

    req_headers = {str(k): str(v) for k, v in payload.headers.items() if str(k).strip()}
    if api_key_value:
        if payload.auth_mode == "bearer":
            req_headers["Authorization"] = f"Bearer {api_key_value}"
        else:
            req_headers["X-API-Key"] = api_key_value

    query_str = urlencode({k: v for k, v in payload.query_params.items() if str(k).strip()})
    target_path = f"{endpoint}?{query_str}" if query_str else endpoint

    req_body = None
    if payload.method in ("POST", "PUT", "PATCH") and payload.body is not None:
        if isinstance(payload.body, (dict, list)):
            req_body = json.dumps(payload.body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(payload.body, str) and payload.body.strip():
            req_body = payload.body.encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

    started = time.perf_counter()
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://beta-gateway.local") as client:
        resp = await client.request(
            method=payload.method,
            url=target_path,
            headers=req_headers,
            content=req_body,
        )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    parsed_body = None
    is_json = False
    ctype = (resp.headers.get("content-type") or "").lower()
    if ctype.startswith(("audio/", "video/", "application/octet-stream")):
        disp = resp.headers.get("content-disposition") or ""
        fn_star = re.search(r"filename\*=UTF-8''([^;\s]+)", disp)
        fn_plain = re.search(r'filename="([^"]+)"', disp)
        filename = unquote(fn_star.group(1)) if fn_star else (fn_plain.group(1) if fn_plain else "download.bin")
        size_b = len(resp.content)
        parsed_body = {
            "binary": True,
            "mime_type": ctype.split(";")[0].strip(),
            "filename": filename,
            "size_bytes": size_b,
            "preview_base64": base64.b64encode(resp.content).decode("ascii") if size_b <= 8 * 1024 * 1024 else None,
            "note": "Use ?mode=json to retrieve signed download_url without buffering binary in the Playground."
            if size_b > 8 * 1024 * 1024
            else "Binary media streamed cleanly from gateway.",
        }
    else:
        try:
            parsed_body = resp.json()
            is_json = True
        except Exception:
            parsed_body = resp.text

    return {
        "status_code": resp.status_code,
        "latency_ms": latency_ms,
        "size_bytes": len(resp.content),
        "is_json": is_json,
        "body": parsed_body,
        "headers": dict(resp.headers),
        "target_endpoint": target_path,
        "method": payload.method,
    }

