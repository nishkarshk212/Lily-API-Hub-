"""Built-in Media & YouTube search, full metadata extractor, and audio/video streaming engine."""

import asyncio
import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import mimetypes
import os
from pathlib import Path
import re
import shutil
import socket
import tempfile
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode, urlparse

from fastapi.responses import Response, StreamingResponse
import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decrypt_secret
from app.models.gateway import MediaGatewayConfig

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_URL_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
ISO_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")

MEDIA_ROUTE_MAP = {
    "/media/search": "search",
    "/yt/search": "search",
    "/media/info": "info",
    "/media/details": "info",
    "/yt/info": "info",
    "/yt/details": "info",
    "/media/audio": "audio",
    "/media/song": "audio",
    "/yt/audio": "audio",
    "/yt/song": "audio",
    "/media/video": "video",
    "/yt/video": "video",
    "/media/download": "download",
    "/yt/download": "download",
    "/media/file": "file",
    "/yt/file": "file",
}

AUDIO_EXT_MIME = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "opus": "audio/opus",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
    "wav": "audio/wav",
    "flac": "audio/flac",
}

VIDEO_EXT_MIME = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "mov": "video/quicktime",
}

QUALITY_HEIGHT_MAP = {
    "best": None,
    "2160p": 2160,
    "4k": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
    "240p": 240,
    "144p": 144,
}


class MediaServiceError(Exception):
    """Structured domain error raised during media search, inspection, or download."""

    def __init__(self, status_code: int, error_code: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.extra = extra or {}

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"error": self.error_code, "message": self.message}
        if self.extra:
            payload.update(self.extra)
        return payload


@dataclass
class MediaRuntimeConfig:
    """Resolved runtime settings for built-in media endpoints."""

    media_enabled: bool
    youtube_cookies: str
    youtube_api_key: str
    max_duration_seconds: int
    max_file_size_mb: int
    default_audio_format: str
    default_video_quality: str


@dataclass
class PreparedMediaStream:
    """Descriptor returned when streaming binary media or returning metadata JSON."""

    mode: str  # "json" | "stream"
    status_code: int
    json_payload: Optional[Dict[str, Any]] = None
    stream_url: Optional[str] = None
    stream_headers: Optional[Dict[str, str]] = None
    local_dir: Optional[str] = None
    local_file: Optional[str] = None
    filename: str = "media.bin"
    mime_type: str = "application/octet-stream"
    content_length: Optional[int] = None
    disposition: str = "attachment"
    range_header: Optional[str] = None


def parse_media_action(sub_path: str) -> Optional[str]:
    """Return canonical media route action for /v1/media/* or /v1/yt/* paths."""
    normalized = "/" + sub_path.strip("/").lower()
    return MEDIA_ROUTE_MAP.get(normalized)


def _import_yt_dlp():
    try:
        import yt_dlp  # type: ignore

        return yt_dlp
    except ImportError as exc:
        raise MediaServiceError(
            503,
            "MEDIA_EXTRACTOR_UNAVAILABLE",
            "Media extractor library (yt-dlp) is not installed on this server.",
        ) from exc


def _require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise MediaServiceError(
            503,
            "FFMPEG_UNAVAILABLE",
            "FFmpeg is required for audio conversion or HD video muxing on this server.",
        )
    return path


def load_media_runtime_config(db: Session, settings: Optional[Settings] = None) -> MediaRuntimeConfig:
    """Load effective Media API configuration from DB + encrypted secrets + env fallback."""
    cfg = settings or get_settings()
    row = db.get(MediaGatewayConfig, 1)

    cookies_txt = ""
    if row and row.encrypted_youtube_cookies:
        cookies_txt = decrypt_secret(row.encrypted_youtube_cookies, cfg) or ""
    elif cfg.YOUTUBE_COOKIES_B64.strip():
        try:
            cookies_txt = base64.b64decode(cfg.YOUTUBE_COOKIES_B64.strip()).decode("utf-8", errors="replace")
        except Exception:
            cookies_txt = ""

    yt_api_key = ""
    if row and row.encrypted_youtube_api_key:
        yt_api_key = decrypt_secret(row.encrypted_youtube_api_key, cfg) or ""
    elif cfg.YOUTUBE_API_KEY.strip():
        yt_api_key = cfg.YOUTUBE_API_KEY.strip()

    return MediaRuntimeConfig(
        media_enabled=row.media_enabled if row is not None else cfg.MEDIA_API_ENABLED,
        youtube_cookies=cookies_txt.strip(),
        youtube_api_key=yt_api_key.strip(),
        max_duration_seconds=row.max_duration_seconds if row is not None else cfg.MEDIA_MAX_DURATION_SECONDS,
        max_file_size_mb=row.max_file_size_mb if row is not None else cfg.MEDIA_MAX_FILE_SIZE_MB,
        default_audio_format=(row.default_audio_format if row is not None else "mp3") or "mp3",
        default_video_quality=(row.default_video_quality if row is not None else "720p") or "720p",
    )


@contextmanager
def _cookies_temp_file(cookies_txt: str):
    """Write cookies to an isolated 0600 temp file only for the active yt-dlp call."""
    if not cookies_txt:
        yield None
        return
    fd, tmp_path = tempfile.mkstemp(prefix="beta_ytc_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(cookies_txt + ("\n" if not cookies_txt.endswith("\n") else ""))
        os.chmod(tmp_path, 0o600)
        yield tmp_path
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def format_duration_hms(seconds: Optional[Any]) -> str:
    """Convert numeric seconds into HH:MM:SS or MM:SS display string."""
    if seconds is None:
        return ""
    try:
        total = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return ""
    hours, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def _parse_iso_duration(iso_val: str) -> Optional[int]:
    m = ISO_DURATION_RE.match((iso_val or "").strip())
    if not m:
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return h * 3600 + mins * 60 + s


def _sanitize_ascii_filename(title: str, ext: str) -> Tuple[str, str]:
    """Return (ascii_fallback_filename, original_unicode_filename) without path chars."""
    clean_ext = re.sub(r"[^a-zA-Z0-9]", "", ext or "bin").lower() or "bin"
    raw = (title or "beta_media").strip()
    raw = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", raw).strip(" ._") or "beta_media"
    unicode_base = raw[:120]
    ascii_base = re.sub(r"[^A-Za-z0-9._\-() ]+", "_", unicode_base).strip(" ._") or "beta_media"
    return f"{ascii_base[:100]}.{clean_ext}", f"{unicode_base}.{clean_ext}"


def build_content_disposition(disposition_type: str, title: str, ext: str) -> str:
    """Build RFC 6266 / 5987 Content-Disposition header safe for Unicode (Hindi/non-ASCII) titles."""
    kind = "inline" if disposition_type == "inline" else "attachment"
    ascii_name, unicode_name = _sanitize_ascii_filename(title, ext)
    return f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(unicode_name)}'


def _is_ip_public(ip_str: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip_str.split("%", 1)[0])
        return (
            ip_obj.is_global
            and not ip_obj.is_private
            and not ip_obj.is_loopback
            and not ip_obj.is_link_local
            and not ip_obj.is_multicast
            and not ip_obj.is_reserved
            and not ip_obj.is_unspecified
        )
    except ValueError:
        return False


def validate_public_http_url(raw_url: str) -> str:
    """Validate URL scheme and resolved IPs against private/loopback/metadata SSRF targets."""
    cleaned = (raw_url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise MediaServiceError(400, "INVALID_MEDIA_URL", "Provide a valid http:// or https:// media URL.")

    host = (parsed.hostname or "").strip().lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")) or ("." not in host and ":" not in host):
        raise MediaServiceError(403, "UNSAFE_MEDIA_URL", "Internal, loopback, or non-public hostnames are blocked.")

    try:
        ipaddress.ip_address(host)
        if not _is_ip_public(host):
            raise MediaServiceError(403, "UNSAFE_MEDIA_URL", "Private or reserved IP targets are blocked.")
        return cleaned
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise MediaServiceError(400, "UNRESOLVABLE_MEDIA_HOST", f"Unable to resolve media host '{host}'.") from exc

    resolved_ips = [info[4][0] for info in infos if info and len(info) >= 5 and info[4]]
    if not resolved_ips or any(not _is_ip_public(ip) for ip in resolved_ips):
        raise MediaServiceError(403, "UNSAFE_MEDIA_URL", "Target resolves to a non-public IP address.")
    return cleaned


def _extract_yt_id(value: str) -> Optional[str]:
    v = (value or "").strip()
    if YOUTUBE_ID_RE.match(v):
        return v
    m = YOUTUBE_URL_ID_RE.search(v)
    return m.group(1) if m else None


def resolve_media_params(query_params: Dict[str, str], body_json: Optional[Any]) -> Dict[str, Any]:
    """Merge query parameters and optional JSON POST body uniformly."""
    merged: Dict[str, Any] = {str(k).lower(): v for k, v in query_params.items()}
    if isinstance(body_json, dict):
        for k, v in body_json.items():
            if v is not None and v != "":
                merged[str(k).lower()] = v
    return merged


def _extract_target_spec(params: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Return (public_url_or_none, search_query_or_none) from request parameters."""
    raw_url = str(params.get("url") or "").strip()
    raw_id = str(params.get("id") or params.get("video_id") or "").strip()
    raw_q = str(params.get("q") or params.get("query") or params.get("song") or params.get("title") or "").strip()

    if raw_url:
        if YOUTUBE_ID_RE.match(raw_url):
            return f"https://www.youtube.com/watch?v={raw_url}", None
        return validate_public_http_url(raw_url), None

    if raw_id:
        yt_id = _extract_yt_id(raw_id)
        if yt_id:
            return f"https://www.youtube.com/watch?v={yt_id}", None
        if raw_id.startswith(("http://", "https://")):
            return validate_public_http_url(raw_id), None
        raise MediaServiceError(400, "INVALID_MEDIA_ID", "Invalid media 'id'. Supply an 11-character YouTube video ID or a full URL.")

    if raw_q:
        if raw_q.startswith(("http://", "https://")):
            return validate_public_http_url(raw_q), None
        return None, raw_q

    raise MediaServiceError(
        400,
        "MISSING_MEDIA_TARGET",
        "Provide 'url', 'id' (YouTube video ID), or 'q' (song/video search query).",
    )


def create_media_file_token(
    *,
    api_key_id: str,
    target: str,
    media_type: str,
    fmt: str,
    quality: str,
    bitrate: str,
    settings: Optional[Settings] = None,
) -> str:
    """Create a short-lived HMAC token authorizing /v1/media/file without exposing raw API keys."""
    cfg = settings or get_settings()
    serializer = URLSafeTimedSerializer(cfg.SECRET_KEY, salt="beta-media-download")
    return serializer.dumps(
        {
            "k": api_key_id,
            "u": target,
            "t": media_type,
            "f": fmt,
            "q": quality,
            "b": bitrate,
        }
    )


def verify_media_file_token(
    token: str,
    *,
    max_age_seconds: int = 900,
    settings: Optional[Settings] = None,
) -> Dict[str, str]:
    """Verify signed ephemeral download token returned by /v1/media/* metadata responses."""
    cfg = settings or get_settings()
    serializer = URLSafeTimedSerializer(cfg.SECRET_KEY, salt="beta-media-download")
    try:
        data = serializer.loads(token, max_age=max_age_seconds)
        if not isinstance(data, dict) or not data.get("k") or not data.get("u"):
            raise MediaServiceError(401, "INVALID_MEDIA_TOKEN", "Invalid media download token.")
        return {str(k): str(v) for k, v in data.items()}
    except SignatureExpired as exc:
        raise MediaServiceError(401, "EXPIRED_MEDIA_TOKEN", "Signed media download link expired (15m TTL). Request a fresh link.") from exc
    except BadSignature as exc:
        raise MediaServiceError(401, "INVALID_MEDIA_TOKEN", "Signed media download token is invalid.") from exc


def _build_download_links(
    *,
    public_base_url: str,
    api_key_id: str,
    canonical_target: str,
    yt_id: Optional[str],
    settings: Settings,
) -> Dict[str, Any]:
    """Generate both header-auth /v1/media/* URLs and signed ephemeral /v1/media/file URLs."""
    base = public_base_url.rstrip("/")
    ref_param = {"id": yt_id} if yt_id else {"url": canonical_target}

    def _entry(media_type: str, fmt: str, quality: str, bitrate: str = "192") -> Dict[str, str]:
        route = "/v1/media/audio" if media_type == "audio" else "/v1/media/video"
        qdict = dict(ref_param)
        if media_type == "audio":
            qdict["format"] = fmt
            if fmt == "mp3":
                qdict["bitrate"] = bitrate
            mime = AUDIO_EXT_MIME.get(fmt, "audio/mpeg")
        else:
            qdict["quality"] = quality
            qdict["format"] = fmt
            mime = VIDEO_EXT_MIME.get(fmt, "video/mp4")
        token = create_media_file_token(
            api_key_id=api_key_id,
            target=canonical_target,
            media_type=media_type,
            fmt=fmt,
            quality=quality,
            bitrate=bitrate,
            settings=settings,
        )
        return {
            "gateway_url": f"{base}{route}?{urlencode(qdict)}",
            "signed_url": f"{base}/v1/media/file?{urlencode({'token': token})}",
            "mime_type": mime,
        }

    return {
        "signed_ttl_seconds": 900,
        "auth_note": "Use signed_url directly in browsers/players/bots (15m TTL), or call gateway_url with X-API-Key header.",
        "audio": {
            "mp3_192kbps": _entry("audio", "mp3", "best", "192"),
            "mp3_320kbps": _entry("audio", "mp3", "best", "320"),
            "m4a": _entry("audio", "m4a", "best", "192"),
            "original": _entry("audio", "original", "best", "192"),
        },
        "video": {
            "best": _entry("video", "mp4", "best"),
            "1080p": _entry("video", "mp4", "1080p"),
            "720p": _entry("video", "mp4", "720p"),
            "480p": _entry("video", "mp4", "480p"),
            "360p": _entry("video", "mp4", "360p"),
        },
    }


async def _fetch_youtube_oembed(target_url: str) -> Optional[Dict[str, Any]]:
    if not _extract_yt_id(target_url):
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("https://www.youtube.com/oembed", params={"url": target_url, "format": "json"})
        if resp.status_code == 200:
            data = resp.json()
            return {
                "title": data.get("title"),
                "author_name": data.get("author_name"),
                "author_url": data.get("author_url"),
                "thumbnail_url": data.get("thumbnail_url"),
                "provider_name": data.get("provider_name"),
            }
    except Exception:
        pass
    return None


def _base_ydl_opts(cookies_file: Optional[str], runtime_cfg: MediaRuntimeConfig, *, flat: bool = False) -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreconfig": True,
        "noplaylist": not flat,
        "socket_timeout": 20,
        "retries": 1,
        "max_filesize": int(runtime_cfg.max_file_size_mb) * 1024 * 1024,
        "js_runtimes": {"deno": {}},
        "remote_components": ["ejs:github"],
    }
    if flat:
        opts["extract_flat"] = "in_playlist"
    if cookies_file:
        opts["cookiefile"] = cookies_file
    return opts


async def _raise_classified_extractor_error(exc: Exception, target_url: str) -> None:
    msg = str(exc or "").strip()
    lower = msg.lower()
    if "sign in to confirm" in lower and ("not a bot" in lower or "bot" in lower or "cookies" in lower):
        oembed = await _fetch_youtube_oembed(target_url)
        raise MediaServiceError(
            503,
            "YOUTUBE_BOT_VERIFICATION_REQUIRED",
            "YouTube requested account/bot verification from this server IP. Upload authorized Netscape cookies.txt in Admin -> Master Gateway & Media Config, or configure an authorized upstream resolver.",
            extra={"oembed_fallback": oembed} if oembed else None,
        ) from exc
    if "sign in to confirm your age" in lower or "age-restricted" in lower or "authentication" in lower:
        raise MediaServiceError(
            403,
            "MEDIA_AUTH_REQUIRED",
            "Target media requires authenticated cookies (age-restricted or member-only).",
        ) from exc
    if "private video" in lower or "video unavailable" in lower or "unavailable" in lower or "copyright" in lower or "does not exist" in lower:
        raise MediaServiceError(
            404,
            "MEDIA_UNAVAILABLE",
            f"Requested media is unavailable or private: {msg[:240]}",
        ) from exc
    if "unsupported url" in lower:
        raise MediaServiceError(400, "UNSUPPORTED_MEDIA_URL", f"Unsupported media URL: {msg[:200]}") from exc
    raise MediaServiceError(502, "MEDIA_EXTRACTION_FAILED", f"Failed to extract media metadata: {msg[:280]}") from exc


async def _extract_info_async(
    target: str,
    runtime_cfg: MediaRuntimeConfig,
    *,
    flat: bool = False,
) -> Dict[str, Any]:
    yt_dlp = _import_yt_dlp()

    def _run() -> Dict[str, Any]:
        with _cookies_temp_file(runtime_cfg.youtube_cookies) as cfile:
            opts = _base_ydl_opts(cfile, runtime_cfg, flat=flat)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False)
                return ydl.sanitize_info(info)

    try:
        return await asyncio.to_thread(_run)
    except MediaServiceError:
        raise
    except Exception as exc:
        await _raise_classified_extractor_error(exc, target)
        raise


async def _search_via_youtube_data_api(
    query: str,
    limit: int,
    api_key: str,
) -> Optional[List[Dict[str, Any]]]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            sr = await client.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "type": "video",
                    "q": query,
                    "maxResults": limit,
                    "key": api_key,
                },
            )
            if sr.status_code != 200:
                return None
            items = sr.json().get("items") or []
            ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]
            if not ids:
                return []

            vr = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(ids),
                    "key": api_key,
                },
            )
            details_by_id: Dict[str, Dict[str, Any]] = {}
            if vr.status_code == 200:
                for vid in vr.json().get("items") or []:
                    details_by_id[vid.get("id", "")] = vid

        out: List[Dict[str, Any]] = []
        for item in items:
            vid_id = item.get("id", {}).get("videoId")
            if not vid_id:
                continue
            detail = details_by_id.get(vid_id, {})
            sn = detail.get("snippet") or item.get("snippet") or {}
            cd = detail.get("contentDetails") or {}
            st = detail.get("statistics") or {}
            dur_s = _parse_iso_duration(cd.get("duration", ""))
            thumbs_obj = sn.get("thumbnails") or {}
            thumbs = [
                {
                    "id": k,
                    "url": v.get("url"),
                    "width": v.get("width"),
                    "height": v.get("height"),
                }
                for k, v in thumbs_obj.items()
                if isinstance(v, dict) and v.get("url")
            ]
            best_thumb = (
                (thumbs_obj.get("maxres") or thumbs_obj.get("high") or thumbs_obj.get("medium") or thumbs_obj.get("default") or {}).get("url")
            )
            out.append(
                {
                    "id": vid_id,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "title": sn.get("title") or "",
                    "description": sn.get("description") or "",
                    "channel": sn.get("channelTitle") or "",
                    "channel_id": sn.get("channelId") or "",
                    "channel_url": f"https://www.youtube.com/channel/{sn.get('channelId')}" if sn.get("channelId") else "",
                    "channel_is_verified": None,
                    "uploader": sn.get("channelTitle") or "",
                    "duration_seconds": dur_s,
                    "duration_string": format_duration_hms(dur_s),
                    "view_count": int(st["viewCount"]) if st.get("viewCount") and str(st["viewCount"]).isdigit() else None,
                    "like_count": int(st["likeCount"]) if st.get("likeCount") and str(st["likeCount"]).isdigit() else None,
                    "published_at": sn.get("publishedAt"),
                    "live_status": sn.get("liveBroadcastContent"),
                    "thumbnail": best_thumb,
                    "thumbnails": thumbs,
                    "tags": sn.get("tags") or [],
                }
            )
        return out
    except Exception:
        return None


async def search_media(
    db: Session,
    *,
    query: str,
    limit: int = 5,
    api_key_id: str,
    public_base_url: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Search YouTube songs/videos and attach ready-to-call info + download URLs."""
    cfg = settings or get_settings()
    rt = load_media_runtime_config(db, cfg)
    if not rt.media_enabled:
        raise MediaServiceError(503, "MEDIA_API_DISABLED", "Built-in Media API is currently disabled by the administrator.")

    cleaned_q = (query or "").strip()
    if not cleaned_q:
        raise MediaServiceError(400, "VALIDATION_ERROR", "Provide a non-empty search query parameter 'q'.")
    clamped_limit = max(1, min(20, int(limit or 5)))

    source_engine = "yt-dlp"
    results: Optional[List[Dict[str, Any]]] = None
    if rt.youtube_api_key:
        results = await _search_via_youtube_data_api(cleaned_q, clamped_limit, rt.youtube_api_key)
        if results is not None:
            source_engine = "youtube_data_api_v3"

    if results is None:
        raw = await _extract_info_async(f"ytsearch{clamped_limit}:{cleaned_q}", rt, flat=True)
        entries = raw.get("entries") or []
        results = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vid_id = entry.get("id") or _extract_yt_id(entry.get("url") or "")
            canon_url = entry.get("url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "")
            if vid_id and not str(canon_url).startswith("http"):
                canon_url = f"https://www.youtube.com/watch?v={vid_id}"
            thumbs = entry.get("thumbnails") or []
            best_thumb = entry.get("thumbnail") or (thumbs[-1].get("url") if thumbs and isinstance(thumbs[-1], dict) else None)
            dur = entry.get("duration")
            results.append(
                {
                    "id": vid_id,
                    "url": canon_url,
                    "title": entry.get("title") or "",
                    "description": entry.get("description") or "",
                    "channel": entry.get("channel") or entry.get("uploader") or "",
                    "channel_id": entry.get("channel_id") or "",
                    "channel_url": entry.get("channel_url") or "",
                    "channel_is_verified": entry.get("channel_is_verified"),
                    "uploader": entry.get("uploader") or "",
                    "duration_seconds": int(dur) if dur is not None else None,
                    "duration_string": format_duration_hms(dur),
                    "view_count": entry.get("view_count"),
                    "live_status": entry.get("live_status"),
                    "availability": entry.get("availability"),
                    "thumbnail": best_thumb,
                    "thumbnails": thumbs,
                }
            )

    base = public_base_url.rstrip("/")
    enriched: List[Dict[str, Any]] = []
    for item in results:
        canon_url = item.get("url") or ""
        yt_id = item.get("id") if YOUTUBE_ID_RE.match(str(item.get("id") or "")) else _extract_yt_id(canon_url)
        ref = {"id": yt_id} if yt_id else {"url": canon_url}
        enriched.append(
            {
                **item,
                "api_actions": {
                    "info": f"{base}/v1/media/info?{urlencode(ref)}",
                    "audio_mp3": f"{base}/v1/media/audio?{urlencode({**ref, 'format': 'mp3'})}",
                    "audio_m4a": f"{base}/v1/media/audio?{urlencode({**ref, 'format': 'm4a'})}",
                    "video_720p": f"{base}/v1/media/video?{urlencode({**ref, 'quality': '720p'})}",
                    "video_1080p": f"{base}/v1/media/video?{urlencode({**ref, 'quality': '1080p'})}",
                },
                "downloads": _build_download_links(
                    public_base_url=public_base_url,
                    api_key_id=api_key_id,
                    canonical_target=canon_url,
                    yt_id=yt_id,
                    settings=cfg,
                )
                if canon_url
                else None,
            }
        )

    return {
        "query": cleaned_q,
        "engine": source_engine,
        "count": len(enriched),
        "results": enriched,
    }


def _simplify_formats(raw_formats: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    audio_only: List[Dict[str, Any]] = []
    video_only: List[Dict[str, Any]] = []
    combined: List[Dict[str, Any]] = []

    for f in raw_formats:
        if not isinstance(f, dict):
            continue
        protocol = (f.get("protocol") or "").lower()
        ext = (f.get("ext") or "").lower()
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        if ext in ("mhtml", "none") or protocol == "mhtml":
            continue

        item: Dict[str, Any] = {
            "format_id": f.get("format_id"),
            "format_note": f.get("format_note"),
            "ext": ext,
            "protocol": protocol,
            "filesize_bytes": f.get("filesize") or f.get("filesize_approx"),
            "tbr_kbps": f.get("tbr"),
            "url": f.get("url"),
        }
        has_v = vcodec != "none"
        has_a = acodec != "none"
        if has_a and not has_v:
            item.update(
                {
                    "acodec": acodec,
                    "abr_kbps": f.get("abr"),
                    "asr_hz": f.get("asr"),
                    "audio_channels": f.get("audio_channels"),
                    "mime_type": AUDIO_EXT_MIME.get(ext, f"audio/{ext}"),
                }
            )
            audio_only.append(item)
        elif has_v and not has_a:
            item.update(
                {
                    "vcodec": vcodec,
                    "width": f.get("width"),
                    "height": f.get("height"),
                    "resolution": f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("height") else None),
                    "fps": f.get("fps"),
                    "vbr_kbps": f.get("vbr"),
                    "dynamic_range": f.get("dynamic_range"),
                    "mime_type": VIDEO_EXT_MIME.get(ext, f"video/{ext}"),
                }
            )
            video_only.append(item)
        elif has_v and has_a:
            item.update(
                {
                    "vcodec": vcodec,
                    "acodec": acodec,
                    "width": f.get("width"),
                    "height": f.get("height"),
                    "resolution": f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("height") else None),
                    "fps": f.get("fps"),
                    "abr_kbps": f.get("abr"),
                    "mime_type": VIDEO_EXT_MIME.get(ext, f"video/{ext}"),
                }
            )
            combined.append(item)

    audio_only.sort(key=lambda x: float(x.get("abr_kbps") or x.get("tbr_kbps") or 0), reverse=True)
    video_only.sort(key=lambda x: (int(x.get("height") or 0), float(x.get("fps") or 0), float(x.get("tbr_kbps") or 0)), reverse=True)
    combined.sort(key=lambda x: (int(x.get("height") or 0), float(x.get("tbr_kbps") or 0)), reverse=True)
    return audio_only, video_only, combined


def _normalize_media_details(
    info: Dict[str, Any],
    *,
    api_key_id: str,
    public_base_url: str,
    settings: Settings,
) -> Dict[str, Any]:
    canon_url = info.get("webpage_url") or info.get("original_url") or ""
    vid_id = info.get("id")
    yt_id = vid_id if YOUTUBE_ID_RE.match(str(vid_id or "")) else _extract_yt_id(canon_url)

    raw_formats = info.get("formats") or []
    audio_only, video_only, combined = _simplify_formats(raw_formats)

    best_audio = audio_only[0] if audio_only else (combined[0] if combined else None)
    best_video = video_only[0] if video_only else (combined[0] if combined else None)

    thumbs = [
        {
            "id": t.get("id"),
            "url": t.get("url"),
            "width": t.get("width"),
            "height": t.get("height"),
            "resolution": t.get("resolution"),
        }
        for t in (info.get("thumbnails") or [])
        if isinstance(t, dict) and t.get("url")
    ]
    thumbs.sort(key=lambda t: (int(t.get("width") or 0) * int(t.get("height") or 0)), reverse=True)
    best_thumb = info.get("thumbnail") or (thumbs[0]["url"] if thumbs else None)

    chapters = [
        {
            "start_time": c.get("start_time"),
            "end_time": c.get("end_time"),
            "title": c.get("title"),
        }
        for c in (info.get("chapters") or [])
        if isinstance(c, dict)
    ]

    subtitles = info.get("subtitles") or {}
    auto_caps = info.get("automatic_captions") or {}

    direct_audio_url = best_audio.get("url") if best_audio else None
    direct_video_url = (combined[0].get("url") if combined else None) or (best_video.get("url") if best_video else None)

    dur = info.get("duration")
    ts = info.get("timestamp")
    published_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if isinstance(ts, (int, float)) else None

    return {
        "source": {
            "extractor": info.get("extractor_key") or info.get("extractor") or "",
            "id": vid_id,
            "url": canon_url,
            "domain": info.get("webpage_url_domain") or urlparse(canon_url).netloc,
            "live_status": info.get("live_status"),
            "availability": info.get("availability"),
            "is_live": bool(info.get("is_live")),
            "was_live": bool(info.get("was_live")),
            "age_limit": info.get("age_limit"),
        },
        "metadata": {
            "title": info.get("title") or "",
            "fulltitle": info.get("fulltitle") or info.get("title") or "",
            "description": info.get("description") or "",
            "language": info.get("language"),
            "categories": info.get("categories") or [],
            "tags": info.get("tags") or [],
            "upload_date": info.get("upload_date"),
            "release_date": info.get("release_date"),
            "published_at_utc": published_iso,
            "duration_seconds": int(dur) if dur is not None else None,
            "duration_string": info.get("duration_string") or format_duration_hms(dur),
        },
        "music": {
            "track": info.get("track"),
            "artist": info.get("artist"),
            "artists": info.get("artists") or [],
            "album": info.get("album"),
            "album_artist": info.get("album_artist"),
            "creator": info.get("creator"),
            "release_year": info.get("release_year"),
        },
        "channel": {
            "id": info.get("channel_id"),
            "name": info.get("channel") or info.get("uploader"),
            "url": info.get("channel_url"),
            "follower_count": info.get("channel_follower_count"),
            "is_verified": info.get("channel_is_verified"),
            "uploader": info.get("uploader"),
            "uploader_id": info.get("uploader_id"),
            "uploader_url": info.get("uploader_url"),
        },
        "statistics": {
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
        },
        "thumbnails": {
            "best": best_thumb,
            "all": thumbs,
        },
        "chapters": chapters,
        "captions": {
            "subtitles": subtitles,
            "subtitle_languages": sorted(subtitles.keys()),
            "automatic_captions_languages": sorted(auto_caps.keys()),
        },
        "best_audio": best_audio,
        "best_video": best_video,
        "formats": {
            "audio_only": audio_only,
            "video_only": video_only,
            "combined": combined,
            "total_count": len(audio_only) + len(video_only) + len(combined),
        },
        "downloads": _build_download_links(
            public_base_url=public_base_url,
            api_key_id=api_key_id,
            canonical_target=canon_url,
            yt_id=yt_id,
            settings=settings,
        ),
        "direct_cdn": {
            "audio_url": direct_audio_url,
            "video_url": direct_video_url,
            "ip_bound": bool(direct_audio_url and "ip=" in direct_audio_url),
            "note": "GoogleVideo CDN URLs are often IP-locked to the extracting server IP; use the gateway downloads.* URLs for reliable client downloads.",
        },
        "raw_extra": {
            "license": info.get("license"),
            "series": info.get("series"),
            "season_number": info.get("season_number"),
            "episode_number": info.get("episode_number"),
            "media_type": info.get("media_type"),
        },
    }


async def _resolve_target_url(
    params: Dict[str, Any],
    runtime_cfg: MediaRuntimeConfig,
) -> str:
    url_target, search_query = _extract_target_spec(params)
    if url_target:
        return url_target

    flat_res = await _extract_info_async(f"ytsearch1:{search_query}", runtime_cfg, flat=True)
    entries = flat_res.get("entries") or []
    first = next((e for e in entries if isinstance(e, dict)), None)
    if not first:
        raise MediaServiceError(404, "SEARCH_NO_RESULTS", f"No media found matching '{search_query}'.")
    resolved = first.get("url") or (f"https://www.youtube.com/watch?v={first.get('id')}" if first.get("id") else "")
    if first.get("id") and not str(resolved).startswith("http"):
        resolved = f"https://www.youtube.com/watch?v={first['id']}"
    if not resolved:
        raise MediaServiceError(404, "SEARCH_NO_RESULTS", f"Search returned an entry without a resolvable URL for '{search_query}'.")
    return validate_public_http_url(resolved)


async def get_media_info(
    db: Session,
    *,
    params: Dict[str, Any],
    api_key_id: str,
    public_base_url: str,
    settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Fetch complete video/song metadata, formats, chapters, captions, thumbnails & download links."""
    cfg = settings or get_settings()
    rt = load_media_runtime_config(db, cfg)
    if not rt.media_enabled:
        raise MediaServiceError(503, "MEDIA_API_DISABLED", "Built-in Media API is currently disabled by the administrator.")

    target_url = await _resolve_target_url(params, rt)
    info = await _extract_info_async(target_url, rt, flat=False)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        if not entries:
            raise MediaServiceError(404, "MEDIA_UNAVAILABLE", "No playable item found for target.")
        info = entries[0]

    return _normalize_media_details(
        info,
        api_key_id=api_key_id,
        public_base_url=public_base_url,
        settings=cfg,
    )


def _pick_direct_stream(
    info: Dict[str, Any],
    *,
    media_type: str,
    requested_fmt: str,
    max_height: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Find a direct HTTP progressive stream when transcoding/muxing is unnecessary."""
    raw_formats = [
        f
        for f in (info.get("formats") or [])
        if isinstance(f, dict)
        and (f.get("protocol") or "").lower() in ("http", "https")
        and str(f.get("url") or "").startswith(("http://", "https://"))
    ]

    if media_type == "audio":
        audio_streams = [
            f
            for f in raw_formats
            if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") == "none"
        ]
        if not audio_streams:
            return None
        audio_streams.sort(key=lambda f: float(f.get("abr") or f.get("tbr") or 0), reverse=True)
        if requested_fmt in ("original", "best"):
            return audio_streams[0]
        if requested_fmt in ("m4a", "webm", "opus"):
            wanted_exts = {"opus": ("opus", "webm"), "webm": ("webm",), "m4a": ("m4a",)}[requested_fmt]
            matched = [f for f in audio_streams if (f.get("ext") or "").lower() in wanted_exts]
            if matched:
                return matched[0]
        return None

    # Video: only direct-stream if a single combined (video+audio) progressive stream matches cleanly
    combined = [
        f
        for f in raw_formats
        if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") != "none"
    ]
    if not combined:
        return None
    if requested_fmt in ("mp4", "webm"):
        combined = [f for f in combined if (f.get("ext") or "").lower() == requested_fmt]
    if max_height is not None:
        combined = [f for f in combined if int(f.get("height") or 0) <= max_height]
    if not combined:
        return None
    combined.sort(key=lambda f: (int(f.get("height") or 0), float(f.get("tbr") or 0)), reverse=True)

    # Ensure we don't settle for a tiny 360p combined stream if HD (e.g. 720p/1080p) separate video exists and matches target
    best_combined_h = int(combined[0].get("height") or 0)
    max_avail_video_h = max(
        [int(f.get("height") or 0) for f in raw_formats if (f.get("vcodec") or "none") != "none" and (max_height is None or int(f.get("height") or 0) <= max_height)],
        default=best_combined_h,
    )
    if max_avail_video_h > best_combined_h and (max_height is None or max_height >= 480):
        return None
    return combined[0]


def _pick_mux_or_audio_sources(
    info: Dict[str, Any],
    *,
    media_type: str,
    fmt: str,
    max_height: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Select already-extracted HTTP progressive streams to avoid re-invoking yt-dlp extract_info."""
    http_formats = [
        f
        for f in (info.get("formats") or [])
        if isinstance(f, dict)
        and (f.get("protocol") or "").lower() in ("http", "https")
        and str(f.get("url") or "").startswith(("http://", "https://"))
    ]
    audio_streams = [
        f
        for f in http_formats
        if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") == "none"
    ]
    combined_streams = [
        f
        for f in http_formats
        if (f.get("acodec") or "none") != "none" and (f.get("vcodec") or "none") != "none"
    ]
    if media_type == "audio":
        audio_streams.sort(key=lambda f: float(f.get("abr") or f.get("tbr") or 0), reverse=True)
        if audio_streams:
            return None, audio_streams[0]
        combined_streams.sort(key=lambda f: float(f.get("abr") or f.get("tbr") or 0), reverse=True)
        return None, (combined_streams[0] if combined_streams else None)

    video_streams = [
        f
        for f in http_formats
        if (f.get("vcodec") or "none") != "none"
        and (f.get("acodec") or "none") == "none"
        and (max_height is None or int(f.get("height") or 0) <= max_height)
    ]
    if not video_streams or not audio_streams:
        return None, None
    target_vext = "webm" if fmt == "webm" else "mp4"
    target_aext = "webm" if fmt == "webm" else "m4a"
    video_streams.sort(
        key=lambda f: (
            1 if (f.get("ext") or "").lower() == target_vext else 0,
            int(f.get("height") or 0),
            float(f.get("fps") or 0),
            float(f.get("tbr") or 0),
        ),
        reverse=True,
    )
    audio_streams.sort(
        key=lambda f: (
            1 if (f.get("ext") or "").lower() == target_aext else 0,
            float(f.get("abr") or f.get("tbr") or 0),
        ),
        reverse=True,
    )
    return video_streams[0], audio_streams[0]


async def _fetch_cdn_file(
    url: str,
    headers: Dict[str, str],
    dest_path: Path,
    max_bytes: int,
) -> None:
    safe_url = validate_public_http_url(url)
    client = _build_cdn_http_client()
    written = 0
    try:
        async with client.stream("GET", safe_url, headers=headers) as resp:
            if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                redir = validate_public_http_url(resp.headers["location"])
                async with client.stream("GET", redir, headers=headers) as r2:
                    if r2.status_code >= 400:
                        raise MediaServiceError(502, "MEDIA_CDN_ERROR", f"Upstream CDN returned HTTP {r2.status_code}.")
                    with open(dest_path, "wb") as fh:
                        async for chunk in r2.aiter_bytes(65536):
                            written += len(chunk)
                            if written > max_bytes:
                                raise MediaServiceError(413, "MEDIA_FILE_TOO_LARGE", "Stream exceeds maximum configured file size.")
                            await asyncio.to_thread(fh.write, chunk)
                return
            if resp.status_code >= 400:
                raise MediaServiceError(502, "MEDIA_CDN_ERROR", f"Upstream CDN returned HTTP {resp.status_code}.")
            with open(dest_path, "wb") as fh:
                async for chunk in resp.aiter_bytes(65536):
                    written += len(chunk)
                    if written > max_bytes:
                        raise MediaServiceError(413, "MEDIA_FILE_TOO_LARGE", "Stream exceeds maximum configured file size.")
                    await asyncio.to_thread(fh.write, chunk)
    finally:
        await client.aclose()


async def _run_ffmpeg_cmd(args: List[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr_bytes = await proc.communicate()
    if proc.returncode != 0:
        err_snip = stderr_bytes.decode("utf-8", errors="replace")[-300:]
        raise MediaServiceError(502, "FFMPEG_FAILED", f"FFmpeg processing failed: {err_snip}")


async def _transcode_or_mux_extracted_info(
    info: Dict[str, Any],
    runtime_cfg: MediaRuntimeConfig,
    *,
    media_type: str,
    fmt: str,
    max_height: Optional[int],
    bitrate: str,
    out_dir: str,
) -> Optional[Path]:
    """Transcode audio or mux video+audio from already-extracted stream URLs cleanly."""
    vid_stream, aud_stream = _pick_mux_or_audio_sources(info, media_type=media_type, fmt=fmt, max_height=max_height)
    if media_type == "audio" and not aud_stream:
        return None
    if media_type == "video" and (not vid_stream or not aud_stream):
        return None

    ffmpeg_bin = _require_ffmpeg()
    max_bytes = int(runtime_cfg.max_file_size_mb) * 1024 * 1024
    default_hdrs = {str(k): str(v) for k, v in (info.get("http_headers") or {}).items()}
    safe_title = str(info.get("title") or "")[:150]
    safe_artist = str(info.get("artist") or info.get("channel") or info.get("uploader") or "")[:120]

    if media_type == "audio" and aud_stream is not None:
        aext = (aud_stream.get("ext") or "m4a").lower()
        src_path = Path(out_dir) / f"src_audio.{aext}"
        ahdrs = {**default_hdrs, **{str(k): str(v) for k, v in (aud_stream.get("http_headers") or {}).items()}}
        await _fetch_cdn_file(str(aud_stream["url"]), ahdrs, src_path, max_bytes)
        out_ext = fmt if fmt in ("mp3", "m4a", "opus", "wav", "flac") else "mp3"
        out_path = Path(out_dir) / f"out.{out_ext}"
        codec_args = {
            "mp3": ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"],
            "m4a": ["-c:a", "aac", "-b:a", f"{bitrate}k"],
            "opus": ["-c:a", "libopus", "-b:a", f"{bitrate}k"],
            "wav": ["-c:a", "pcm_s16le"],
            "flac": ["-c:a", "flac"],
        }[out_ext]
        cmd = [
            ffmpeg_bin,
            "-y",
            "-v",
            "error",
            "-i",
            str(src_path),
            "-vn",
            *codec_args,
            "-metadata",
            f"title={safe_title}",
            "-metadata",
            f"artist={safe_artist}",
            str(out_path),
        ]
        await _run_ffmpeg_cmd(cmd)
        src_path.unlink(missing_ok=True)
        return out_path

    assert vid_stream is not None and aud_stream is not None
    vext = (vid_stream.get("ext") or "mp4").lower()
    aext = (aud_stream.get("ext") or "m4a").lower()
    vid_path = Path(out_dir) / f"src_video.{vext}"
    aud_path = Path(out_dir) / f"src_audio.{aext}"
    vhdrs = {**default_hdrs, **{str(k): str(v) for k, v in (vid_stream.get("http_headers") or {}).items()}}
    ahdrs = {**default_hdrs, **{str(k): str(v) for k, v in (aud_stream.get("http_headers") or {}).items()}}
    await asyncio.gather(
        _fetch_cdn_file(str(vid_stream["url"]), vhdrs, vid_path, max_bytes),
        _fetch_cdn_file(str(aud_stream["url"]), ahdrs, aud_path, max_bytes),
    )
    out_ext = "webm" if fmt == "webm" else "mp4"
    out_path = Path(out_dir) / f"out.{out_ext}"
    acodec_arg = "copy" if ((out_ext == "mp4" and aext in ("m4a", "aac", "mp4")) or (out_ext == "webm" and aext in ("webm", "opus"))) else ("aac" if out_ext == "mp4" else "libopus")
    vcodec_arg = "copy" if ((out_ext == "mp4" and vext == "mp4") or (out_ext == "webm" and vext == "webm")) else ("libx264" if out_ext == "mp4" else "copy")
    extra_flags = ["-movflags", "+faststart"] if out_ext == "mp4" else []
    cmd = [
        ffmpeg_bin,
        "-y",
        "-v",
        "error",
        "-i",
        str(vid_path),
        "-i",
        str(aud_path),
        "-c:v",
        vcodec_arg,
        "-c:a",
        acodec_arg,
        *extra_flags,
        str(out_path),
    ]
    await _run_ffmpeg_cmd(cmd)
    vid_path.unlink(missing_ok=True)
    aud_path.unlink(missing_ok=True)
    return out_path


async def _download_with_ytdlp_to_dir(
    target_url: str,
    runtime_cfg: MediaRuntimeConfig,
    *,
    media_type: str,
    fmt: str,
    max_height: Optional[int],
    bitrate: str,
    out_dir: str,
    extracted_info: Optional[Dict[str, Any]] = None,
) -> Path:
    """Download/transcode audio or muxed video into an isolated directory cleanly."""
    if extracted_info is not None:
        try:
            fast_path = await _transcode_or_mux_extracted_info(
                extracted_info,
                runtime_cfg,
                media_type=media_type,
                fmt=fmt,
                max_height=max_height,
                bitrate=bitrate,
                out_dir=out_dir,
            )
            if fast_path is not None and fast_path.is_file():
                max_bytes = int(runtime_cfg.max_file_size_mb) * 1024 * 1024
                if fast_path.stat().st_size > max_bytes:
                    raise MediaServiceError(
                        413,
                        "MEDIA_FILE_TOO_LARGE",
                        f"Processed file exceeds maximum size limit ({runtime_cfg.max_file_size_mb} MB).",
                    )
                return fast_path
        except MediaServiceError as exc:
            if exc.error_code == "MEDIA_FILE_TOO_LARGE" or exc.error_code == "FFMPEG_UNAVAILABLE":
                raise

    yt_dlp = _import_yt_dlp()
    ffmpeg_bin = _require_ffmpeg()

    def _run() -> str:
        with _cookies_temp_file(runtime_cfg.youtube_cookies) as cfile:
            opts = _base_ydl_opts(cfile, runtime_cfg, flat=False)
            opts.update(
                {
                    "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
                    "ffmpeg_location": ffmpeg_bin,
                    "restrictfilenames": True,
                }
            )
            if media_type == "audio":
                opts["format"] = "bestaudio/best"
                if fmt in ("mp3", "m4a", "opus", "wav", "flac"):
                    opts["postprocessors"] = [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": fmt,
                            "preferredquality": bitrate,
                        },
                        {"key": "FFmpegMetadata"},
                    ]
            else:
                h_filter = f"[height<={max_height}]" if max_height else ""
                if fmt == "mp4":
                    opts["format"] = f"bestvideo{h_filter}[ext=mp4]+bestaudio[ext=m4a]/bestvideo{h_filter}+bestaudio/best{h_filter}/best"
                    opts["merge_output_format"] = "mp4"
                    opts["postprocessor_args"] = {"merger": ["-movflags", "+faststart"]}
                elif fmt == "webm":
                    opts["format"] = f"bestvideo{h_filter}[ext=webm]+bestaudio[ext=webm]/bestvideo{h_filter}+bestaudio/best{h_filter}/best"
                    opts["merge_output_format"] = "webm"
                else:
                    opts["format"] = f"bestvideo{h_filter}+bestaudio/best{h_filter}/best"
                    opts["merge_output_format"] = "mp4"

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target_url, download=True)
                if info.get("_type") == "playlist" and info.get("entries"):
                    info = info["entries"][0]
                requested = info.get("requested_downloads") or []
                for req in requested:
                    fp = req.get("filepath")
                    if fp and os.path.isfile(fp):
                        return fp
                prepared = ydl.prepare_filename(info)
                if media_type == "audio" and fmt in ("mp3", "m4a", "opus", "wav", "flac"):
                    alt = str(Path(prepared).with_suffix(f".{fmt}"))
                    if os.path.isfile(alt):
                        return alt
                if media_type == "video":
                    target_ext = fmt if fmt in ("mp4", "webm") else "mp4"
                    alt = str(Path(prepared).with_suffix(f".{target_ext}"))
                    if os.path.isfile(alt):
                        return alt
                if os.path.isfile(prepared):
                    return prepared

        files = [str(p) for p in Path(out_dir).iterdir() if p.is_file() and not p.name.endswith(".part")]
        if not files:
            raise FileNotFoundError("Media postprocessing produced no output file.")
        return max(files, key=lambda p: os.path.getsize(p))

    try:
        out_path = Path(await asyncio.to_thread(_run))
    except MediaServiceError:
        raise
    except Exception as exc:
        await _raise_classified_extractor_error(exc, target_url)
        raise

    max_bytes = int(runtime_cfg.max_file_size_mb) * 1024 * 1024
    if out_path.stat().st_size > max_bytes:
        raise MediaServiceError(
            413,
            "MEDIA_FILE_TOO_LARGE",
            f"Processed file exceeds maximum size limit ({runtime_cfg.max_file_size_mb} MB).",
        )
    return out_path


async def prepare_media_download(
    db: Session,
    *,
    action: str,
    params: Dict[str, Any],
    api_key_id: str,
    public_base_url: str,
    range_header: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> PreparedMediaStream:
    """Prepare either JSON download metadata or a live binary audio/video stream."""
    cfg = settings or get_settings()
    rt = load_media_runtime_config(db, cfg)
    if not rt.media_enabled:
        raise MediaServiceError(503, "MEDIA_API_DISABLED", "Built-in Media API is currently disabled by the administrator.")

    media_type = action
    if action == "download":
        req_type = str(params.get("type") or params.get("media_type") or "audio").strip().lower()
        if req_type == "info":
            payload = await get_media_info(
                db, params=params, api_key_id=api_key_id, public_base_url=public_base_url, settings=cfg
            )
            return PreparedMediaStream(mode="json", status_code=200, json_payload=payload)
        media_type = "video" if req_type == "video" else "audio"

    mode = str(params.get("mode") or "stream").strip().lower()
    if mode not in ("stream", "inline", "json"):
        mode = "stream"

    raw_fmt = str(params.get("format") or "").strip().lower()
    if media_type == "audio":
        fmt = raw_fmt or rt.default_audio_format or "mp3"
        if fmt not in ("mp3", "m4a", "opus", "webm", "original", "best"):
            raise MediaServiceError(
                400, "UNSUPPORTED_AUDIO_FORMAT", "Supported audio formats: mp3, m4a, opus, webm, original."
            )
        quality = "best"
        max_height = None
    else:
        fmt = raw_fmt or "mp4"
        if fmt not in ("mp4", "webm", "best"):
            raise MediaServiceError(400, "UNSUPPORTED_VIDEO_FORMAT", "Supported video formats: mp4, webm, best.")
        quality = str(params.get("quality") or rt.default_video_quality or "720p").strip().lower()
        if quality not in QUALITY_HEIGHT_MAP:
            raise MediaServiceError(
                400, "UNSUPPORTED_VIDEO_QUALITY", "Supported video qualities: best, 1080p, 720p, 480p, 360p, 240p."
            )
        max_height = QUALITY_HEIGHT_MAP[quality]

    bitrate = str(params.get("bitrate") or "192").strip()
    if bitrate not in ("128", "192", "256", "320"):
        bitrate = "192"

    target_url = await _resolve_target_url(params, rt)
    info = await _extract_info_async(target_url, rt, flat=False)
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        if not entries:
            raise MediaServiceError(404, "MEDIA_UNAVAILABLE", "No playable item found for target.")
        info = entries[0]

    if info.get("is_live"):
        raise MediaServiceError(422, "LIVE_STREAM_UNSUPPORTED", "Downloading active live streams is not supported.")

    dur = info.get("duration")
    if dur is not None and float(dur) > float(rt.max_duration_seconds):
        raise MediaServiceError(
            413,
            "MEDIA_DURATION_LIMIT_EXCEEDED",
            f"Media duration ({int(float(dur))}s) exceeds configured limit ({rt.max_duration_seconds}s).",
        )

    title = info.get("title") or info.get("id") or "beta_media"
    canon_url = info.get("webpage_url") or target_url
    yt_id = _extract_yt_id(canon_url) or (info.get("id") if YOUTUBE_ID_RE.match(str(info.get("id") or "")) else None)
    direct = _pick_direct_stream(info, media_type=media_type, requested_fmt=fmt, max_height=max_height)

    resolved_ext = (
        (direct.get("ext") or ("m4a" if media_type == "audio" else "mp4"))
        if direct
        else ("mp3" if media_type == "audio" and fmt in ("best", "original") else (fmt if fmt not in ("best", "original") else "mp4"))
    )
    mime_type = (
        AUDIO_EXT_MIME.get(resolved_ext, mimetypes.guess_type(f"x.{resolved_ext}")[0] or "application/octet-stream")
        if media_type == "audio"
        else VIDEO_EXT_MIME.get(resolved_ext, mimetypes.guess_type(f"x.{resolved_ext}")[0] or "video/mp4")
    )
    _, unicode_filename = _sanitize_ascii_filename(title, resolved_ext)

    if mode == "json":
        token = create_media_file_token(
            api_key_id=api_key_id,
            target=canon_url,
            media_type=media_type,
            fmt=fmt,
            quality=quality,
            bitrate=bitrate,
            settings=cfg,
        )
        base = public_base_url.rstrip("/")
        route = "/v1/media/audio" if media_type == "audio" else "/v1/media/video"
        ref = {"id": yt_id} if yt_id else {"url": canon_url}
        qmeta = {**ref, "format": fmt}
        if media_type == "audio":
            qmeta["bitrate"] = bitrate
        else:
            qmeta["quality"] = quality
        return PreparedMediaStream(
            mode="json",
            status_code=200,
            json_payload={
                "status": "ready",
                "type": media_type,
                "id": info.get("id"),
                "title": title,
                "channel": info.get("channel") or info.get("uploader"),
                "duration_seconds": int(dur) if dur is not None else None,
                "duration_string": format_duration_hms(dur),
                "thumbnail": info.get("thumbnail"),
                "format": resolved_ext,
                "quality": quality if media_type == "video" else f"{bitrate}kbps",
                "mime_type": mime_type,
                "filename": unicode_filename,
                "filesize_bytes": (direct.get("filesize") or direct.get("filesize_approx")) if direct else None,
                "delivery": "direct_cdn_proxy" if direct else "ffmpeg_transcode_stream",
                "download_url": f"{base}/v1/media/file?{urlencode({'token': token})}",
                "gateway_url": f"{base}{route}?{urlencode(qmeta)}",
                "signed_ttl_seconds": 900,
            },
        )

    if direct:
        cdn_url = validate_public_http_url(str(direct["url"]))
        req_headers = {str(k): str(v) for k, v in (direct.get("http_headers") or info.get("http_headers") or {}).items()}
        return PreparedMediaStream(
            mode="stream",
            status_code=206 if range_header else 200,
            stream_url=cdn_url,
            stream_headers=req_headers,
            filename=title,
            mime_type=mime_type,
            content_length=direct.get("filesize") or direct.get("filesize_approx"),
            disposition="inline" if mode == "inline" else "attachment",
            range_header=range_header,
        )

    # FFmpeg transcoding / muxing path into an isolated temporary directory
    tmp_dir = tempfile.mkdtemp(prefix="beta_dl_")
    try:
        out_path = await _download_with_ytdlp_to_dir(
            canon_url,
            rt,
            media_type=media_type,
            fmt=fmt,
            max_height=max_height,
            bitrate=bitrate,
            out_dir=tmp_dir,
            extracted_info=info,
        )
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    final_ext = out_path.suffix.lstrip(".").lower() or resolved_ext
    final_mime = (
        AUDIO_EXT_MIME.get(final_ext, mime_type) if media_type == "audio" else VIDEO_EXT_MIME.get(final_ext, mime_type)
    )
    return PreparedMediaStream(
        mode="stream",
        status_code=200,
        local_dir=tmp_dir,
        local_file=str(out_path),
        filename=title,
        mime_type=final_mime,
        content_length=out_path.stat().st_size,
        disposition="inline" if mode == "inline" else "attachment",
    )


def _build_cdn_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False)


async def build_media_streaming_response(
    prepared: PreparedMediaStream,
    *,
    headers: Dict[str, str],
    resolve_ext_hint: Callable[[str], str] = lambda m: m.split("/")[-1].split(";")[0],
) -> Response:
    """Turn a PreparedMediaStream into an async FastAPI StreamingResponse with guaranteed cleanup."""
    if prepared.local_file and prepared.local_dir:
        ext = Path(prepared.local_file).suffix.lstrip(".") or resolve_ext_hint(prepared.mime_type)
        out_headers = dict(headers)
        out_headers["Content-Disposition"] = build_content_disposition(prepared.disposition, prepared.filename, ext)
        if prepared.content_length is not None:
            out_headers["Content-Length"] = str(prepared.content_length)

        async def _file_chunks() -> AsyncIterator[bytes]:
            try:
                with open(prepared.local_file, "rb") as fh:
                    while True:
                        chunk = await asyncio.to_thread(fh.read, 65536)
                        if not chunk:
                            break
                        yield chunk
            finally:
                shutil.rmtree(prepared.local_dir, ignore_errors=True)

        return StreamingResponse(
            _file_chunks(),
            status_code=prepared.status_code,
            headers=out_headers,
            media_type=prepared.mime_type,
        )

    if prepared.stream_url:
        ext = "m4a" if prepared.mime_type == "audio/mp4" else resolve_ext_hint(prepared.mime_type)
        if ext == "mpeg":
            ext = "mp3"
        out_headers = dict(headers)
        out_headers["Content-Disposition"] = build_content_disposition(prepared.disposition, prepared.filename, ext)

        cdn_headers = dict(prepared.stream_headers or {})
        if prepared.range_header:
            cdn_headers["Range"] = prepared.range_header

        client = _build_cdn_http_client()
        try:
            ctx = client.stream("GET", prepared.stream_url, headers=cdn_headers)
            upstream_resp = await ctx.__aenter__()
        except Exception as exc:
            await client.aclose()
            raise MediaServiceError(502, "MEDIA_STREAM_FAILED", f"Failed to stream upstream CDN media: {type(exc).__name__}") from exc

        # Validate redirect targets once safely if CDN issues a location redirect
        if upstream_resp.status_code in (301, 302, 303, 307, 308) and upstream_resp.headers.get("location"):
            redir_url = validate_public_http_url(upstream_resp.headers["location"])
            await ctx.__aexit__(None, None, None)
            try:
                ctx = client.stream("GET", redir_url, headers=cdn_headers)
                upstream_resp = await ctx.__aenter__()
            except Exception as exc:
                await client.aclose()
                raise MediaServiceError(502, "MEDIA_STREAM_FAILED", f"Failed to follow media redirect: {type(exc).__name__}") from exc

        if upstream_resp.status_code >= 400:
            code = upstream_resp.status_code
            await ctx.__aexit__(None, None, None)
            await client.aclose()
            raise MediaServiceError(502, "MEDIA_CDN_ERROR", f"Upstream CDN refused media stream (HTTP {code}).")

        for copy_hdr in ("content-length", "content-range", "accept-ranges"):
            if copy_hdr in upstream_resp.headers:
                out_headers[copy_hdr.title()] = upstream_resp.headers[copy_hdr]

        status_out = upstream_resp.status_code
        raw_ct = (upstream_resp.headers.get("content-type") or "").strip()
        media_t = prepared.mime_type if (not raw_ct or raw_ct == "application/octet-stream") else raw_ct

        async def _cdn_chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream_resp.aiter_bytes(65536):
                    yield chunk
            finally:
                try:
                    await ctx.__aexit__(None, None, None)
                finally:
                    await client.aclose()

        return StreamingResponse(
            _cdn_chunks(),
            status_code=status_out,
            headers=out_headers,
            media_type=media_t,
        )

    raise MediaServiceError(500, "MEDIA_STREAM_UNINITIALIZED", "No media stream source prepared.")
