"""Media API tests: search, full details, audio/video streaming, signed URLs, SSRF guard, and Admin config."""

import base64
from pathlib import Path
import socket

from app.models.gateway import ApiRequestLog
from app.models.user import User
from app.services import media_service


def _register_and_get_key(client):
    client.post(
        "/api/auth/register",
        json={"email": "mediauser@example.com", "password": "Password123", "full_name": "Media User"},
    )
    plans = client.get("/api/plans").json()
    free_plan = next(p for p in plans if p["price_paise"] == 0)
    act = client.post(f"/api/subscriptions/activate-free?plan_id={free_plan['id']}")
    assert act.status_code == 200
    key_id = act.json()["api_key"]["id"]
    raw_key = client.get(f"/api/keys/{key_id}/reveal").json()["api_key"]
    return key_id, raw_key


def _sample_video_info():
    return {
        "_type": "video",
        "id": "BddP6PYo2gs",
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": "https://www.youtube.com/watch?v=BddP6PYo2gs",
        "webpage_url_domain": "youtube.com",
        "title": "केसरिया - Kesariya (Brahmāstra) | Arijit Singh",
        "fulltitle": "केसरिया - Kesariya (Brahmāstra) | Pritam | Arijit Singh",
        "description": "Official Hindi song from Brahmastra.",
        "language": "hi",
        "categories": ["Music"],
        "tags": ["hindi song", "arijit singh", "kesariya"],
        "upload_date": "20220717",
        "release_date": "20220717",
        "timestamp": 1658059200,
        "duration": 268,
        "duration_string": "4:28",
        "track": "Kesariya",
        "artist": "Arijit Singh",
        "artists": ["Pritam", "Arijit Singh", "Amitabh Bhattacharya"],
        "album": "Brahmāstra",
        "release_year": 2022,
        "channel": "Sony Music India",
        "channel_id": "UC56gTxNs4f9xZ7Pa2i5xNzg",
        "channel_url": "https://www.youtube.com/channel/UC56gTxNs4f9xZ7Pa2i5xNzg",
        "channel_follower_count": 62000000,
        "channel_is_verified": True,
        "uploader": "Sony Music India",
        "uploader_id": "@SonyMusicIndia",
        "uploader_url": "https://www.youtube.com/@SonyMusicIndia",
        "view_count": 510000000,
        "like_count": 6200000,
        "comment_count": 210000,
        "age_limit": 0,
        "availability": "public",
        "live_status": "not_live",
        "is_live": False,
        "was_live": False,
        "thumbnail": "https://i.ytimg.com/vi/BddP6PYo2gs/maxresdefault.jpg",
        "thumbnails": [
            {"id": "0", "url": "https://i.ytimg.com/vi/BddP6PYo2gs/hqdefault.jpg", "width": 480, "height": 360},
            {"id": "max", "url": "https://i.ytimg.com/vi/BddP6PYo2gs/maxresdefault.jpg", "width": 1280, "height": 720},
        ],
        "chapters": [{"start_time": 0.0, "end_time": 268.0, "title": "Full Song"}],
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/sub.vtt"}]},
        "automatic_captions": {"hi": [{"ext": "vtt", "url": "https://example.com/auto.vtt"}]},
        "formats": [
            {
                "format_id": "140",
                "format_note": "medium",
                "ext": "m4a",
                "protocol": "https",
                "acodec": "mp4a.40.2",
                "vcodec": "none",
                "abr": 129.0,
                "asr": 44100,
                "audio_channels": 2,
                "filesize": 4321000,
                "url": "https://rr5---sn.googlevideo.com/videoplayback?ip=13.54.201.131&itag=140",
            },
            {
                "format_id": "18",
                "format_note": "360p",
                "ext": "mp4",
                "protocol": "https",
                "acodec": "mp4a.40.2",
                "vcodec": "avc1.42001E",
                "width": 640,
                "height": 360,
                "fps": 24,
                "tbr": 550.0,
                "filesize": 18000000,
                "url": "https://rr5---sn.googlevideo.com/videoplayback?ip=13.54.201.131&itag=18",
            },
            {
                "format_id": "137",
                "format_note": "1080p",
                "ext": "mp4",
                "protocol": "https",
                "acodec": "none",
                "vcodec": "avc1.640028",
                "width": 1920,
                "height": 1080,
                "fps": 24,
                "vbr": 2400.0,
                "filesize": 82000000,
                "url": "https://rr5---sn.googlevideo.com/videoplayback?ip=13.54.201.131&itag=137",
            },
        ],
    }


def _sample_search_result():
    return {
        "_type": "playlist",
        "id": "kesariya hindi song",
        "entries": [
            {
                "id": "BddP6PYo2gs",
                "url": "https://www.youtube.com/watch?v=BddP6PYo2gs",
                "title": "Kesariya - Brahmāstra | Arijit Singh",
                "description": "Hindi hit song",
                "channel": "Sony Music India",
                "channel_id": "UC56gTxNs4f9xZ7Pa2i5xNzg",
                "channel_url": "https://www.youtube.com/channel/UC56gTxNs4f9xZ7Pa2i5xNzg",
                "channel_is_verified": True,
                "uploader": "Sony Music India",
                "duration": 268,
                "view_count": 510000000,
                "live_status": "not_live",
                "availability": "public",
                "thumbnails": [{"url": "https://i.ytimg.com/vi/BddP6PYo2gs/hqdefault.jpg", "width": 480, "height": 360}],
            }
        ],
    }


def test_media_validation_and_ssrf_blocks(client, test_env):
    _, raw_key = _register_and_get_key(client)
    hdr = {"X-API-Key": raw_key}

    # Public overview lists the new media endpoints
    overview = client.get("/api/public/overview").json()
    paths = [e["path"] for e in overview["endpoints"]]
    assert "/v1/media/search" in paths
    assert "/v1/media/info" in paths
    assert "/v1/media/audio" in paths
    assert "/v1/media/video" in paths

    assert client.get("/v1/media/info", headers=hdr).status_code == 400
    assert client.get("/v1/media/info?id=bad", headers=hdr).status_code == 400
    assert client.get("/v1/media/file", headers=hdr).status_code == 400
    assert client.get("/v1/media/file?token=invalid_tok").status_code == 401

    for bad_url in [
        "file:///etc/passwd",
        "http://127.0.0.1:8000/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:5432/",
        "http://db:5432/",
    ]:
        resp = client.get("/v1/media/info", params={"url": bad_url}, headers=hdr)
        assert resp.status_code in (400, 403), f"{bad_url} returned {resp.status_code}"


def test_media_search_full_details_and_json_download(client, test_env, monkeypatch):
    _, raw_key = _register_and_get_key(client)
    hdr = {"X-API-Key": raw_key}

    async def fake_extract(target: str, runtime_cfg, *, flat: bool = False):
        if flat and target.startswith("ytsearch"):
            return _sample_search_result()
        return _sample_video_info()

    monkeypatch.setattr(media_service, "_extract_info_async", fake_extract)
    monkeypatch.setattr(
        media_service.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.78", 0))],
    )

    # Search
    sr = client.get("/v1/media/search", params={"q": "kesariya hindi song", "limit": "5"}, headers=hdr)
    assert sr.status_code == 200
    sdata = sr.json()
    assert sdata["count"] == 1
    assert sdata["results"][0]["id"] == "BddP6PYo2gs"
    assert sdata["results"][0]["duration_string"] == "4:28"
    assert "/v1/media/file?token=" in sdata["results"][0]["downloads"]["audio"]["mp3_192kbps"]["signed_url"]

    # Full details ("every details") via /v1/yt/info alias
    info_resp = client.get("/v1/yt/info", params={"q": "kesariya hindi song"}, headers=hdr)
    assert info_resp.status_code == 200
    idata = info_resp.json()
    assert idata["source"]["id"] == "BddP6PYo2gs"
    assert idata["music"]["track"] == "Kesariya"
    assert idata["music"]["artist"] == "Arijit Singh"
    assert idata["channel"]["follower_count"] == 62000000
    assert idata["statistics"]["view_count"] == 510000000
    assert len(idata["chapters"]) == 1
    assert idata["captions"]["subtitle_languages"] == ["en"]
    assert idata["captions"]["automatic_captions_languages"] == ["hi"]
    assert idata["formats"]["total_count"] == 3
    assert idata["direct_cdn"]["ip_bound"] is True
    assert "/v1/media/file?token=" in idata["downloads"]["video"]["1080p"]["signed_url"]

    # Audio & video JSON delivery mode
    aud_json = client.get(
        "/v1/media/audio", params={"id": "BddP6PYo2gs", "format": "mp3", "bitrate": "320", "mode": "json"}, headers=hdr
    )
    assert aud_json.status_code == 200
    assert aud_json.json()["type"] == "audio"
    assert aud_json.json()["mime_type"] == "audio/mpeg"
    assert "/v1/media/file?token=" in aud_json.json()["download_url"]

    vid_json = client.post(
        "/v1/media/download",
        json={"id": "BddP6PYo2gs", "type": "video", "quality": "1080p", "format": "mp4", "mode": "json"},
        headers=hdr,
    )
    assert vid_json.status_code == 200
    assert vid_json.json()["type"] == "video"
    assert vid_json.json()["quality"] == "1080p"


def test_media_streaming_signed_file_playground_and_revocation(client, test_env, monkeypatch):
    key_id, raw_key = _register_and_get_key(client)
    hdr = {"X-API-Key": raw_key}

    async def fake_extract(target: str, runtime_cfg, *, flat: bool = False):
        return _sample_video_info()

    monkeypatch.setattr(media_service, "_extract_info_async", fake_extract)
    monkeypatch.setattr(
        media_service.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.190.78", 0))],
    )
    monkeypatch.setattr(media_service, "validate_public_http_url", lambda u: u)

    class MockStreamResp:
        status_code = 200
        headers = {"content-type": "audio/mp4", "content-length": "12", "accept-ranges": "bytes"}

        async def aiter_bytes(self, chunk_size=65536):
            yield b"FAKE_M4A_123"

    class MockStreamCtx:
        async def __aenter__(self):
            return MockStreamResp()

        async def __aexit__(self, *args):
            return False

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass

        def stream(self, method, url, headers=None):
            return MockStreamCtx()

        async def aclose(self):
            pass

    monkeypatch.setattr(media_service, "_build_cdn_http_client", lambda: MockHttpxClient())

    # 1. Direct zero-disk M4A stream
    stream_resp = client.get("/v1/media/audio", params={"id": "BddP6PYo2gs", "format": "m4a"}, headers=hdr)
    assert stream_resp.status_code == 200
    assert stream_resp.content == b"FAKE_M4A_123"
    assert stream_resp.headers["content-type"].startswith("audio/mp4")
    assert "filename*=" in stream_resp.headers["content-disposition"]

    # 2. FFmpeg MP3 download + temp directory cleanup
    created_dirs = []

    async def fake_dl_dir(target_url, runtime_cfg, *, media_type, fmt, max_height, bitrate, out_dir):
        created_dirs.append(Path(out_dir))
        out = Path(out_dir) / f"song.{fmt}"
        out.write_bytes(b"ID3_FAKE_MP3_BYTES")
        return out

    monkeypatch.setattr(media_service, "_download_with_ytdlp_to_dir", fake_dl_dir)

    mp3_resp = client.get("/v1/media/song", params={"id": "BddP6PYo2gs", "format": "mp3"}, headers=hdr)
    assert mp3_resp.status_code == 200
    assert mp3_resp.content == b"ID3_FAKE_MP3_BYTES"
    assert mp3_resp.headers["content-type"].startswith("audio/mpeg")
    assert created_dirs and not created_dirs[0].exists()

    # 3. Signed /v1/media/file works cleanly WITHOUT X-API-Key header
    meta = client.get("/v1/media/audio", params={"id": "BddP6PYo2gs", "format": "m4a", "mode": "json"}, headers=hdr).json()
    signed_path = "/v1/" + meta["download_url"].split("/v1/", 1)[1]
    signed_resp = client.get(signed_path)
    assert signed_resp.status_code == 200
    assert signed_resp.content == b"FAKE_M4A_123"

    # Query string in log is sanitized cleanly
    with test_env() as db:
        last_log = db.query(ApiRequestLog).filter(ApiRequestLog.path == "/v1/media/file").first()
        assert last_log is not None
        assert last_log.query_string == "token=[signed]"

    # 4. Playground handles binary audio preview cleanly
    pg = client.post(
        "/api/playground/execute",
        json={
            "api_key_id": key_id,
            "method": "GET",
            "endpoint": "/v1/media/audio",
            "query_params": {"id": "BddP6PYo2gs", "format": "m4a"},
        },
    )
    assert pg.status_code == 200
    pg_body = pg.json()["body"]
    assert pg_body["binary"] is True
    assert base64.b64decode(pg_body["preview_base64"]) == b"FAKE_M4A_123"

    # 5. Revoking key blocks even existing signed URL immediately
    assert client.post(f"/api/keys/{key_id}/revoke").status_code == 200
    revoked_signed = client.get(signed_path)
    assert revoked_signed.status_code == 403
    assert revoked_signed.json()["error"] == "KEY_REVOKED"


def test_bot_verification_classification_and_admin_media_config(client, test_env, monkeypatch):
    _, raw_key = _register_and_get_key(client)
    hdr = {"X-API-Key": raw_key}

    async def fake_bot_error(target: str, runtime_cfg, *, flat: bool = False):
        await media_service._raise_classified_extractor_error(
            RuntimeError("ERROR: [youtube] BddP6PYo2gs: Sign in to confirm you’re not a bot. Use --cookies for the authentication."),
            target,
        )

    async def fake_oembed(target_url: str):
        return {"title": "Kesariya", "author_name": "Sony Music India"}

    monkeypatch.setattr(media_service, "_extract_info_async", fake_bot_error)
    monkeypatch.setattr(media_service, "_fetch_youtube_oembed", fake_oembed)

    bot_resp = client.get("/v1/media/info", params={"id": "BddP6PYo2gs"}, headers=hdr)
    assert bot_resp.status_code == 503
    assert bot_resp.json()["error"] == "YOUTUBE_BOT_VERIFICATION_REQUIRED"
    assert bot_resp.json()["oembed_fallback"]["title"] == "Kesariya"

    # Non-admin blocked from media config
    assert client.get("/api/admin/media-config").status_code == 403

    # Log in as seeded admin
    with test_env() as db:
        admin_user = db.query(User).filter(User.role == "admin").first()
        assert admin_user is not None

    login = client.post("/api/admin/login", json={"email": "admin@sonicnetwork.dev", "password": "SonicAdmin!2026"})
    assert login.status_code == 200

    put = client.put(
        "/api/admin/media-config",
        json={
            "media_enabled": True,
            "youtube_cookies_txt": ".youtube.com\tTRUE\t/\tTRUE\t2147483647\tVISITOR_INFO1_LIVE\tsecret_cookie",
            "youtube_api_key": "AIzaSyTestKeyForAdminStorageOnly123",
            "max_duration_seconds": 900,
            "max_file_size_mb": 120,
            "default_audio_format": "mp3",
            "default_video_quality": "720p",
        },
    )
    assert put.status_code == 200
    assert put.json()["has_youtube_cookies"] is True

    get_cfg = client.get("/api/admin/media-config").json()
    assert get_cfg["has_youtube_cookies"] is True
    assert get_cfg["has_youtube_api_key"] is True
    assert "secret_cookie" not in str(get_cfg)
    assert "AIzaSyTestKeyForAdminStorageOnly123" not in str(get_cfg)
