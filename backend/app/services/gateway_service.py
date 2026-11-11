"""Real-time API Gateway engine: key validation, expiry, rate limit, atomic quotas, Master API proxy, logging."""

from collections import deque
from datetime import datetime, timezone
import fnmatch
import hashlib
import hmac
import ipaddress
import json
import socket
import threading
import time
from typing import Any, Deque, Dict, Optional, Tuple
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy import case, or_, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret, sha256_hex, utc_now
from app.models.api_key import ApiKey
from app.models.gateway import ApiRequestLog, MasterGatewayConfig
from app.models.plan import Subscription, SubscriptionPlan
from app.models.user import User
from app.services.auth_service import as_utc, get_client_ip
from app.services.branding_service import get_effective_branding


class SlidingWindowRateLimiter:
    """Thread-safe 60-second sliding window rate limiter keyed by API key ID."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[str, Deque[float]] = {}

    def check_and_record(self, key_id: str, limit_per_minute: int) -> Tuple[bool, int, int]:
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            bucket = self._buckets.setdefault(key_id, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit_per_minute:
                retry_after = max(1, int(60 - (now - bucket[0])) + 1)
                return False, 0, retry_after
            bucket.append(now)
            remaining = max(0, limit_per_minute - len(bucket))
            return True, remaining, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = SlidingWindowRateLimiter()


def extract_api_key_from_headers(headers: Dict[str, str], db: Optional[Session] = None) -> Optional[str]:
    lowered = {k.lower(): v for k, v in headers.items()}
    x_api_key = lowered.get("x-api-key")
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    auth = lowered.get("authorization", "")
    if auth.lower().startswith("bearer "):
        candidate = auth[7:].strip()
        brand = get_effective_branding(db)
        if candidate.startswith((brand["api_key_prefix_live"], brand["api_key_prefix_test"], "beta_")) or "_" in candidate:
            return candidate
    return None


def extract_api_key(request: Request, db: Optional[Session] = None) -> Optional[str]:
    return extract_api_key_from_headers(dict(request.headers), db)


def _is_endpoint_allowed(pattern_spec: str, path: str) -> bool:
    patterns = [p.strip() for p in (pattern_spec or "*").split(",") if p.strip()]
    if "*" in patterns:
        return True
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def _atomic_consume_quota(
    db: Session,
    subscription_id: str,
    daily_limit: int,
    monthly_limit: int,
) -> Tuple[bool, str, int, int]:
    """Atomically validate & increment daily and cycle quotas without race conditions."""
    now = utc_now()
    today_str = now.strftime("%Y-%m-%d")

    stmt = (
        update(Subscription)
        .where(
            Subscription.id == subscription_id,
            Subscription.status == "active",
            Subscription.expires_at > now,
            Subscription.cycle_requests_used < monthly_limit,
            or_(
                Subscription.daily_usage_date != today_str,
                Subscription.daily_requests_used < daily_limit,
            ),
        )
        .values(
            daily_requests_used=case(
                (Subscription.daily_usage_date == today_str, Subscription.daily_requests_used + 1),
                else_=1,
            ),
            daily_usage_date=today_str,
            cycle_requests_used=Subscription.cycle_requests_used + 1,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    result = db.execute(stmt)

    if result.rowcount == 1:
        sub = db.get(Subscription, subscription_id)
        db.refresh(sub)
        daily_rem = max(0, daily_limit - sub.daily_requests_used)
        monthly_rem = max(0, monthly_limit - sub.cycle_requests_used)
        return True, "ok", daily_rem, monthly_rem

    sub = db.get(Subscription, subscription_id)
    if not sub:
        return False, "SUBSCRIPTION_NOT_FOUND", 0, 0
    if sub.cycle_requests_used >= monthly_limit:
        return False, "MONTHLY_QUOTA_EXCEEDED", 0, 0
    if sub.daily_usage_date == today_str and sub.daily_requests_used >= daily_limit:
        return False, "DAILY_QUOTA_EXCEEDED", 0, max(0, monthly_limit - sub.cycle_requests_used)
    return False, "SUBSCRIPTION_INACTIVE", 0, 0


def _log_gateway_request(
    db: Session,
    *,
    user_id: Optional[str],
    api_key_id: Optional[str],
    subscription_id: Optional[str],
    method: str,
    path: str,
    query_string: str,
    status_code: int,
    upstream_status_code: Optional[int],
    latency_ms: float,
    client_ip: str,
    gateway_mode: str,
    error_code: Optional[str] = None,
) -> None:
    db.add(
        ApiRequestLog(
            user_id=user_id,
            api_key_id=api_key_id,
            subscription_id=subscription_id,
            method=method[:12],
            path=path[:300],
            query_string=query_string[:500],
            status_code=status_code,
            upstream_status_code=upstream_status_code,
            latency_ms=round(latency_ms, 2),
            client_ip=client_ip[:64],
            gateway_mode=gateway_mode,
            error_code=error_code,
        )
    )
    db.commit()


def _execute_builtin_endpoint(
    sub_path: str,
    method: str,
    query_params: Dict[str, str],
    body_bytes: bytes,
    headers: Dict[str, str],
    client_ip: str,
    plan: SubscriptionPlan,
    api_key: ApiKey,
    branding: Optional[Dict[str, str]] = None,
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """Built-in deterministic gateway utility APIs under /v1/*."""
    normalized = "/" + sub_path.strip("/")

    try:
        body_json = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
    except Exception:
        body_json = None

    if normalized == "/status" and method == "GET":
        b = branding or get_effective_branding(None)
        return 200, {
            "service": f"{b['app_name']} Gateway",
            "provider": b["company_name"],
            "status": "operational",
            "timestamp_utc": utc_now().isoformat(),
            "master_link_tag": api_key.master_link_tag,
            "plan": {
                "name": plan.name,
                "slug": plan.slug,
                "daily_limit": plan.daily_request_limit,
                "monthly_limit": plan.monthly_request_limit,
                "rate_limit_per_minute": plan.rate_limit_per_minute,
            },
        }

    if normalized == "/network/echo":
        safe_headers = {
            k: v
            for k, v in headers.items()
            if k.lower() not in ("x-api-key", "authorization", "cookie")
        }
        return 200, {
            "method": method,
            "path": f"/v1{normalized}",
            "client_ip": client_ip,
            "query": query_params,
            "headers": safe_headers,
            "json_body": body_json,
            "received_at_utc": utc_now().isoformat(),
        }

    if normalized == "/crypto/uuid" and method == "GET":
        count = min(25, max(1, int(query_params.get("count", "1") or 1)))
        return 200, {
            "count": count,
            "uuids": [str(uuid.uuid4()) for _ in range(count)],
        }

    if normalized == "/crypto/hash":
        payload_text = query_params.get("text")
        algo = (query_params.get("algorithm") or "sha256").lower()
        secret_key = None
        if isinstance(body_json, dict):
            payload_text = body_json.get("text", payload_text)
            algo = str(body_json.get("algorithm", algo)).lower()
            secret_key = body_json.get("hmac_secret")
        if payload_text is None:
            return 400, {"error": "VALIDATION_ERROR", "message": "Provide 'text' in query parameter or JSON body."}
        raw = str(payload_text).encode("utf-8")
        supported = {"sha256": hashlib.sha256, "sha512": hashlib.sha512, "blake2b": hashlib.blake2b}
        if algo not in supported:
            return 400, {"error": "UNSUPPORTED_ALGORITHM", "supported": list(supported.keys())}
        if secret_key:
            digest = hmac.new(str(secret_key).encode("utf-8"), raw, supported[algo]).hexdigest()
        else:
            digest = supported[algo](raw).hexdigest()
        return 200, {"algorithm": algo, "hmac": bool(secret_key), "digest_hex": digest, "input_bytes": len(raw)}

    if normalized == "/geo/ip-parse" and method == "GET":
        target_ip = (query_params.get("ip") or client_ip).strip()
        try:
            ip_obj = ipaddress.ip_address(target_ip)
        except ValueError:
            return 400, {"error": "INVALID_IP", "message": f"'{target_ip}' is not a valid IPv4/IPv6 address."}
        return 200, {
            "ip": str(ip_obj),
            "version": ip_obj.version,
            "is_private": ip_obj.is_private,
            "is_global": ip_obj.is_global,
            "is_loopback": ip_obj.is_loopback,
            "is_multicast": ip_obj.is_multicast,
            "reverse_pointer": ip_obj.reverse_pointer,
        }

    if normalized == "/network/dns" and method == "GET":
        domain = (query_params.get("domain") or "").strip().lower()
        if not domain or len(domain) > 253 or " " in domain:
            return 400, {"error": "INVALID_DOMAIN", "message": "Provide a valid 'domain' query parameter."}
        try:
            infos = socket.getaddrinfo(domain, None)
            ipv4 = sorted({info[4][0] for info in infos if info[0] == socket.AF_INET})
            ipv6 = sorted({info[4][0] for info in infos if info[0] == socket.AF_INET6})
            return 200, {"domain": domain, "ipv4": ipv4, "ipv6": ipv6, "resolved": bool(ipv4 or ipv6)}
        except socket.gaierror as exc:
            return 200, {"domain": domain, "ipv4": [], "ipv6": [], "resolved": False, "detail": str(exc)}

    if normalized == "/utils/timestamp" and method == "GET":
        now = utc_now()
        return 200, {
            "iso_utc": now.isoformat(),
            "unix_seconds": int(now.timestamp()),
            "unix_milliseconds": int(now.timestamp() * 1000),
            "date_utc": now.strftime("%Y-%m-%d"),
        }

    if normalized == "/utils/json-validate" and method == "POST":
        if body_json is None:
            return 422, {"valid": False, "error": "Request body is not valid JSON."}
        top_type = type(body_json).__name__
        key_count = len(body_json) if isinstance(body_json, (dict, list)) else 1
        return 200, {
            "valid": True,
            "root_type": top_type,
            "item_count": key_count,
            "byte_length": len(body_bytes),
        }

    return None


def _json_gateway_result(
    status_code: int,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, Dict[str, str], bytes, str]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return status_code, dict(headers or {}), body, "application/json"


async def _best_effort_gateway_alert(
    db: Session,
    *,
    user_id: str,
    full_path: str,
    status_code: int,
    error_code: Optional[str],
    plan_name: str,
    daily_limit: int,
    daily_rem: int,
    monthly_limit: int,
    monthly_rem: int,
) -> None:
    try:
        from app.services.telegram_service import notify_gateway_alerts

        await notify_gateway_alerts(
            db,
            user_id=user_id,
            full_path=full_path,
            status_code=status_code,
            error_code=error_code,
            plan_name=plan_name,
            daily_limit=daily_limit,
            daily_rem=daily_rem,
            monthly_limit=monthly_limit,
            monthly_rem=monthly_rem,
        )
    except Exception:
        pass


async def execute_gateway_core(
    db: Session,
    *,
    method: str,
    subpath: str,
    query_dict: Optional[Dict[str, str]] = None,
    query_str: str = "",
    body_bytes: bytes = b"",
    req_headers: Optional[Dict[str, str]] = None,
    client_ip: str = "127.0.0.1",
    raw_api_key: Optional[str] = None,
) -> Tuple[int, Dict[str, str], bytes, str]:
    """Core gateway pipeline reusable by HTTP /v1/* routes and internal Telegram Bot runners."""
    started = time.perf_counter()
    upper_method = method.upper()
    full_path = f"/v1/{subpath.lstrip('/')}"
    query_map = dict(query_dict or {})
    headers_map = dict(req_headers or {})

    gw = db.get(MasterGatewayConfig, 1)
    gw_mode = gw.gateway_mode if gw else "hybrid"

    raw_key = raw_api_key or extract_api_key_from_headers(headers_map, db)
    if not raw_key:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=None,
            api_key_id=None,
            subscription_id=None,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=401,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="MISSING_API_KEY",
        )
        return _json_gateway_result(
            401,
            {"error": "MISSING_API_KEY", "message": "Provide X-API-Key or Authorization: Bearer <api_key>."},
        )

    api_key = db.query(ApiKey).filter(ApiKey.key_hash == sha256_hex(raw_key)).first()
    if not api_key:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=None,
            api_key_id=None,
            subscription_id=None,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=401,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="INVALID_API_KEY",
        )
        return _json_gateway_result(401, {"error": "INVALID_API_KEY", "message": "API key is invalid."})

    if api_key.status != "active":
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=api_key.user_id,
            api_key_id=api_key.id,
            subscription_id=api_key.subscription_id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=403,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="KEY_REVOKED",
        )
        return _json_gateway_result(403, {"error": "KEY_REVOKED", "message": "This API key has been revoked."})

    user = db.get(User, api_key.user_id)
    if not user or not user.is_active or user.is_suspended:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=api_key.user_id,
            api_key_id=api_key.id,
            subscription_id=api_key.subscription_id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=403,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="ACCOUNT_SUSPENDED",
        )
        return _json_gateway_result(
            403,
            {"error": "ACCOUNT_SUSPENDED", "message": "Account is suspended or inactive."},
        )

    sub = db.get(Subscription, api_key.subscription_id)
    plan = db.get(SubscriptionPlan, sub.plan_id) if sub else None
    now = utc_now()
    if not sub or not plan:
        return _json_gateway_result(403, {"error": "NO_SUBSCRIPTION", "message": "Subscription missing."})

    if sub.status == "active" and as_utc(sub.expires_at) <= now:
        sub.status = "expired"
        db.commit()

    if sub.status != "active":
        latency = (time.perf_counter() - started) * 1000
        err_code = "SUBSCRIPTION_EXPIRED" if sub.status == "expired" else "SUBSCRIPTION_INACTIVE"
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=403,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code=err_code,
        )
        return _json_gateway_result(
            403,
            {"error": err_code, "message": f"Your {plan.name} subscription is {sub.status}. Renew to continue."},
        )

    allowed_methods = {m.strip().upper() for m in plan.allowed_methods.split(",") if m.strip()}
    if upper_method not in allowed_methods:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=403,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="METHOD_NOT_ALLOWED_FOR_PLAN",
        )
        return _json_gateway_result(
            403,
            {
                "error": "METHOD_NOT_ALLOWED_FOR_PLAN",
                "message": f"Method {upper_method} is not permitted on {plan.name}. Allowed: {sorted(allowed_methods)}",
            },
        )

    if not _is_endpoint_allowed(plan.allowed_endpoints, full_path):
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=403,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="ENDPOINT_NOT_ALLOWED",
        )
        return _json_gateway_result(
            403,
            {"error": "ENDPOINT_NOT_ALLOWED", "message": f"Endpoint {full_path} is not enabled on your plan."},
        )

    allowed_rate, rate_rem, retry_after = rate_limiter.check_and_record(api_key.id, plan.rate_limit_per_minute)
    if not allowed_rate:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=429,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="RATE_LIMIT_EXCEEDED",
        )
        return _json_gateway_result(
            429,
            {
                "error": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit of {plan.rate_limit_per_minute} req/min exceeded. Retry in {retry_after}s.",
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(plan.rate_limit_per_minute),
                "X-RateLimit-Remaining": "0",
            },
        )

    quota_ok, quota_err, daily_rem, monthly_rem = _atomic_consume_quota(
        db, sub.id, plan.daily_request_limit, plan.monthly_request_limit
    )
    if not quota_ok:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=429,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code=quota_err,
        )
        await _best_effort_gateway_alert(
            db,
            user_id=user.id,
            full_path=full_path,
            status_code=429,
            error_code=quota_err,
            plan_name=plan.name,
            daily_limit=plan.daily_request_limit,
            daily_rem=daily_rem,
            monthly_limit=plan.monthly_request_limit,
            monthly_rem=monthly_rem,
        )
        return _json_gateway_result(
            429,
            {
                "error": quota_err,
                "message": f"Plan quota reached ({quota_err}). Upgrade or wait for quota reset.",
            },
            headers={
                "X-Quota-Daily-Remaining": str(daily_rem),
                "X-Quota-Monthly-Remaining": str(monthly_rem),
            },
        )

    api_key.total_requests += 1
    api_key.last_used_at = now
    db.flush()

    common_headers = {
        "X-Request-Id": str(uuid.uuid4()),
        "X-RateLimit-Limit": str(plan.rate_limit_per_minute),
        "X-RateLimit-Remaining": str(rate_rem),
        "X-Quota-Daily-Remaining": str(daily_rem),
        "X-Quota-Monthly-Remaining": str(monthly_rem),
        "X-Beta-Plan": plan.slug,
    }

    if gw_mode in ("builtin", "hybrid"):
        builtin_result = _execute_builtin_endpoint(
            subpath,
            upper_method,
            query_map,
            body_bytes,
            headers_map,
            client_ip,
            plan,
            api_key,
            branding=get_effective_branding(db),
        )
        if builtin_result is not None:
            resp_status, resp_payload = builtin_result
            latency = (time.perf_counter() - started) * 1000
            _log_gateway_request(
                db,
                user_id=user.id,
                api_key_id=api_key.id,
                subscription_id=sub.id,
                method=upper_method,
                path=full_path,
                query_string=query_str,
                status_code=resp_status,
                upstream_status_code=None,
                latency_ms=latency,
                client_ip=client_ip,
                gateway_mode="builtin",
            )
            common_headers["X-Gateway-Mode"] = "builtin"
            await _best_effort_gateway_alert(
                db,
                user_id=user.id,
                full_path=full_path,
                status_code=resp_status,
                error_code=None,
                plan_name=plan.name,
                daily_limit=plan.daily_request_limit,
                daily_rem=daily_rem,
                monthly_limit=plan.monthly_request_limit,
                monthly_rem=monthly_rem,
            )
            return _json_gateway_result(resp_status, resp_payload, headers=common_headers)

    upstream_base = (gw.upstream_base_url if gw else "").strip().rstrip("/")
    if not upstream_base or gw_mode == "builtin":
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=404,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode=gw_mode,
            error_code="ENDPOINT_NOT_FOUND",
        )
        return _json_gateway_result(
            404,
            {
                "error": "ENDPOINT_NOT_FOUND",
                "message": f"No built-in endpoint at {full_path} and no external Upstream Master API URL is configured.",
                "builtin_endpoints": [
                    "/v1/status",
                    "/v1/network/echo",
                    "/v1/network/dns",
                    "/v1/crypto/hash",
                    "/v1/crypto/uuid",
                    "/v1/geo/ip-parse",
                    "/v1/utils/timestamp",
                    "/v1/utils/json-validate",
                ],
            },
            headers=common_headers,
        )

    cfg = get_settings()
    master_key = decrypt_secret(gw.encrypted_master_api_key, cfg) if gw else None
    if not master_key and cfg.MASTER_API_KEY:
        master_key = cfg.MASTER_API_KEY.strip()

    target_url = f"{upstream_base}/{subpath.lstrip('/')}"
    if query_str:
        target_url = f"{target_url}?{query_str}"

    forward_headers = {
        k: v
        for k, v in headers_map.items()
        if k.lower() not in ("host", "content-length", "x-api-key", "authorization", "cookie", "connection")
    }
    if master_key:
        header_name = (gw.auth_header_name or "Authorization").strip()
        scheme = (gw.auth_scheme or "").strip()
        forward_headers[header_name] = f"{scheme} {master_key}".strip() if scheme else master_key

    if gw and gw.forward_user_context_headers:
        forward_headers["X-Beta-User-Id"] = user.id
        forward_headers["X-Beta-Plan-Slug"] = plan.slug
        forward_headers["X-Beta-Key-Id"] = api_key.id

    timeout_sec = max(1.0, (gw.timeout_ms if gw else 10000) / 1000.0)
    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            upstream_resp = await client.request(
                method=upper_method,
                url=target_url,
                headers=forward_headers,
                content=body_bytes if body_bytes else None,
            )
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=upstream_resp.status_code,
            upstream_status_code=upstream_resp.status_code,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode="proxy",
        )
        resp_headers = {
            k: v
            for k, v in upstream_resp.headers.items()
            if k.lower() not in ("content-encoding", "transfer-encoding", "connection", "content-length")
        }
        resp_headers.update(common_headers)
        resp_headers["X-Gateway-Mode"] = "proxy"
        await _best_effort_gateway_alert(
            db,
            user_id=user.id,
            full_path=full_path,
            status_code=upstream_resp.status_code,
            error_code="UPSTREAM_5XX" if upstream_resp.status_code >= 500 else None,
            plan_name=plan.name,
            daily_limit=plan.daily_request_limit,
            daily_rem=daily_rem,
            monthly_limit=plan.monthly_request_limit,
            monthly_rem=monthly_rem,
        )
        return (
            upstream_resp.status_code,
            resp_headers,
            upstream_resp.content,
            upstream_resp.headers.get("content-type", "application/json"),
        )
    except httpx.RequestError as exc:
        latency = (time.perf_counter() - started) * 1000
        _log_gateway_request(
            db,
            user_id=user.id,
            api_key_id=api_key.id,
            subscription_id=sub.id,
            method=upper_method,
            path=full_path,
            query_string=query_str,
            status_code=502,
            upstream_status_code=None,
            latency_ms=latency,
            client_ip=client_ip,
            gateway_mode="proxy",
            error_code="UPSTREAM_UNREACHABLE",
        )
        await _best_effort_gateway_alert(
            db,
            user_id=user.id,
            full_path=full_path,
            status_code=502,
            error_code="UPSTREAM_UNREACHABLE",
            plan_name=plan.name,
            daily_limit=plan.daily_request_limit,
            daily_rem=daily_rem,
            monthly_limit=plan.monthly_request_limit,
            monthly_rem=monthly_rem,
        )
        return _json_gateway_result(
            502,
            {"error": "UPSTREAM_UNREACHABLE", "message": f"Upstream API connection failed: {type(exc).__name__}"},
            headers=common_headers,
        )


async def handle_gateway_request(request: Request, subpath: str, db: Session) -> Response:
    body_bytes = await request.body()
    status_code, resp_headers, content, media_type = await execute_gateway_core(
        db,
        method=request.method,
        subpath=subpath,
        query_dict=dict(request.query_params),
        query_str=request.url.query or "",
        body_bytes=body_bytes,
        req_headers=dict(request.headers),
        client_ip=get_client_ip(request),
    )
    return Response(
        content=content,
        status_code=status_code,
        headers=resp_headers,
        media_type=media_type,
    )
