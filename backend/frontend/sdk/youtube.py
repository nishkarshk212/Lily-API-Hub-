"""
Beta API Hub — YouTube Client for Telegram Music Bots (youtube.py)
------------------------------------------------------------------
High-throughput music extraction & streaming module designed for Telegram
music bots (Yukki, PyTgCalls, AnonX, Pyrogram, Telethon, python-telegram-bot).

Powered by Beta API Gateway:
API Base URL : https://lily-api-hub-production.up.railway.app/v1
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple, Union

DEFAULT_API_BASE_URL = "https://lily-api-hub-production.up.railway.app/v1"
DEFAULT_USER_AGENT = "TelegramMusicBot/2.0 (SonicNetwork)"

_executor = ThreadPoolExecutor(max_workers=8)


class YouTubeError(Exception):
    """Raised when an API error or network failure occurs during media operations."""

    def __init__(self, message: str, status_code: int = 500, error_code: str = "ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code

    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message} (HTTP {self.status_code})"


class YouTubeClient:
    """Production-grade Telegram Music Bot client for searching, streaming, and downloading songs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 45.0,
    ):
        self.api_key = (
            api_key
            or os.getenv("BETA_API_KEY")
            or os.getenv("LILY_API_KEY")
            or os.getenv("API_KEY")
            or ""
        ).strip()
        self.base_url = (base_url or os.getenv("BETA_API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")
        self.timeout = timeout

        if not self.api_key:
            # Fallback warning — key can still be passed dynamically
            pass

    def _headers(self, custom_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _request_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous JSON request helper using standard library urllib."""
        query_str = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{self.base_url}{path}"
        if query_str:
            url = f"{url}?{query_str}"

        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw_data = response.read().decode(charset)
                return json.loads(raw_data)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("message") or err_json.get("detail") or str(exc)
                code = err_json.get("error") or f"HTTP_{exc.code}"
            except Exception:
                msg = err_body or str(exc)
                code = f"HTTP_{exc.code}"
            raise YouTubeError(msg, status_code=exc.code, error_code=code) from exc
        except Exception as exc:
            raise YouTubeError(f"Network error while connecting to API Hub: {exc}", status_code=500) from exc

    # -------------------------------------------------------------------------
    # Synchronous Core Methods
    # -------------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube for songs or videos by name or keywords."""
        cleaned_query = (query or "").strip()
        if not cleaned_query:
            return []
        data = self._request_json("/media/search", {"q": cleaned_query, "limit": limit})
        return data.get("results") or []

    def get_track(self, query_or_url: str) -> Dict[str, Any]:
        """Resolve a query or YouTube URL to a single top track with streamable metadata."""
        cleaned = (query_or_url or "").strip()
        if not cleaned:
            raise YouTubeError("Empty query provided to get_track()", status_code=400)

        # Check if URL or 11-char ID
        yt_id_match = re.search(r"(?:v=|\/|youtu\.be\/)([A-Za-z0-9_-]{11})", cleaned)
        video_id = yt_id_match.group(1) if yt_id_match else None

        if video_id:
            info = self._request_json("/media/info", {"id": video_id})
            return info

        results = self.search(cleaned, limit=1)
        if not results:
            raise YouTubeError(f"No tracks found matching query: '{query_or_url}'", status_code=404)
        return results[0]

    def get_stream_url(self, query_or_url: str, bitrate: int = 192) -> str:
        """Get direct streaming URL suitable for Telegram Voice Chat (PyTgCalls)."""
        track = self.get_track(query_or_url)
        video_id = track.get("id")
        if not video_id:
            raise YouTubeError("Failed to extract video ID from track result", status_code=500)

        # Check signed pre-authenticated URL if available
        downloads = track.get("downloads", {}).get("audio", {})
        signed = downloads.get(f"mp3_{bitrate}kbps", {}).get("signed_url") or downloads.get("m4a", {}).get("signed_url")
        if signed:
            return signed

        # Direct gateway streaming endpoint with API Key
        return f"{self.base_url}/media/audio?id={video_id}&format=mp3&bitrate={bitrate}"

    def download_audio(
        self,
        query_or_url: str,
        output_dir: str = "downloads",
        filename: Optional[str] = None,
        bitrate: int = 320,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Download high-quality MP3 audio file to disk for Telegram bot send_audio().

        Returns:
            (file_path, track_metadata)
        """
        track = self.get_track(query_or_url)
        video_id = track.get("id")
        title = track.get("title") or "song"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        clean_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()[:80] or f"track_{video_id}"
        dest_filename = filename or f"{clean_title}.mp3"
        dest_file = out_path / dest_filename

        download_url = f"{self.base_url}/media/audio?id={video_id}&format=mp3&bitrate={bitrate}"
        req = urllib.request.Request(download_url, headers=self._headers({"Accept": "*/*"}))

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp, open(dest_file, "wb") as out_fh:
                chunk_size = 64 * 1024
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_fh.write(chunk)
        except Exception as exc:
            if dest_file.exists():
                dest_file.unlink(missing_ok=True)
            raise YouTubeError(f"Failed to download audio for '{title}': {exc}") from exc

        return str(dest_file.resolve()), track

    def download_video(
        self,
        query_or_url: str,
        output_dir: str = "downloads",
        quality: str = "720p",
    ) -> Tuple[str, Dict[str, Any]]:
        """Download MP4 video file to disk for Telegram bot send_video()."""
        track = self.get_track(query_or_url)
        video_id = track.get("id")
        title = track.get("title") or "video"

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        clean_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip()[:80] or f"video_{video_id}"
        dest_file = out_path / f"{clean_title}_{quality}.mp4"

        download_url = f"{self.base_url}/media/video?id={video_id}&quality={quality}&format=mp4"
        req = urllib.request.Request(download_url, headers=self._headers({"Accept": "*/*"}))

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp, open(dest_file, "wb") as out_fh:
                chunk_size = 64 * 1024
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_fh.write(chunk)
        except Exception as exc:
            if dest_file.exists():
                dest_file.unlink(missing_ok=True)
            raise YouTubeError(f"Failed to download video for '{title}': {exc}") from exc

        return str(dest_file.resolve()), track

    # -------------------------------------------------------------------------
    # Async Methods for Pyrogram, Telethon & Asyncio Music Bots
    # -------------------------------------------------------------------------

    async def search_async(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self.search, query, limit)

    async def get_track_async(self, query_or_url: str) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self.get_track, query_or_url)

    async def get_stream_url_async(self, query_or_url: str, bitrate: int = 192) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self.get_stream_url, query_or_url, bitrate)

    async def download_audio_async(
        self,
        query_or_url: str,
        output_dir: str = "downloads",
        filename: Optional[str] = None,
        bitrate: int = 320,
    ) -> Tuple[str, Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self.download_audio, query_or_url, output_dir, filename, bitrate)

    async def download_video_async(
        self,
        query_or_url: str,
        output_dir: str = "downloads",
        quality: str = "720p",
    ) -> Tuple[str, Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self.download_video, query_or_url, output_dir, quality)


# Global default instance
_default_client = YouTubeClient()

search = _default_client.search
get_track = _default_client.get_track
get_stream_url = _default_client.get_stream_url
download_audio = _default_client.download_audio
download_video = _default_client.download_video

search_async = _default_client.search_async
get_track_async = _default_client.get_track_async
get_stream_url_async = _default_client.get_stream_url_async
download_audio_async = _default_client.download_audio_async
download_video_async = _default_client.download_video_async


if __name__ == "__main__":
    test_query = sys.argv[1] if len(sys.argv) > 1 else "Kesariya Brahmastra"
    print(f"🎵 Searching YouTube for: '{test_query}'...")
    try:
        results = search(test_query, limit=1)
        if not results:
            print("No tracks found.")
            sys.exit(1)

        track = results[0]
        print(f"✅ Found: {track.get('title')} ({track.get('id')})")
        print(f"⏱  Duration: {track.get('duration_string')}")
        print(f"📺 Channel: {track.get('channel')}")
        print("\n⬇ Downloading 320kbps MP3 preview...")
        file_path, _ = download_audio(test_query, output_dir="./downloads", bitrate=192)
        print(f"🎉 Saved to: {file_path}")
        print(f"📦 File size: {os.path.getsize(file_path):,} bytes")
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

