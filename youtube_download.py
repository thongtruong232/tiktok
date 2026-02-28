"""
youtube_download.py
───────────────────
Optimized YouTube download helpers using yt-dlp.

Supports:
  - Single video URL
  - Playlist URL
  - Multiple URLs (list / concurrent)
  - Full channel download

Quality options: best, 2160p, 1440p, 1080p, 720p, 480p, 360p, audio-only

Performance features:
  ✓ Concurrent fragment downloads (N=8 internal threads)
  ✓ aria2c external downloader (auto-detected, 16 connections)
  ✓ Download resume for interrupted transfers
  ✓ Concurrent multi-URL downloading (ThreadPoolExecutor)
  ✓ Optimized format sorting: resolution → HDR → fps → codec → bitrate
  ✓ Auto cookie detection (file → browser fallback)
  ✓ Robust retry & timeout handling
"""

from __future__ import annotations
import os
import re
import shutil
import concurrent.futures
from typing import Callable

import yt_dlp


# ── Quality presets ────────────────────────────────────────────────────────────
QUALITY_OPTIONS: list[str] = [
    "best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "audio",
]

_QUALITY_FORMATS: dict[str, str] = {
    "best":  "bestvideo*+bestaudio*/best*",
    "2160p": "bestvideo*[height<=2160]+bestaudio*/best*[height<=2160]",
    "1440p": "bestvideo*[height<=1440]+bestaudio*/best*[height<=1440]",
    "1080p": "bestvideo*[height<=1080]+bestaudio*/best*[height<=1080]",
    "720p":  "bestvideo*[height<=720]+bestaudio*/best*[height<=720]",
    "480p":  "bestvideo*[height<=480]+bestaudio*/best*[height<=480]",
    "360p":  "bestvideo*[height<=360]+bestaudio*/best*[height<=360]",
    "audio": "bestaudio[ext=m4a]/bestaudio*/best*",
}

# Max concurrent video downloads for multi-URL / playlist modes
MAX_CONCURRENT_DOWNLOADS = 3


# ── Cookies auto-detection ─────────────────────────────────────────────────────
_COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

# Cache cookie option so browser DB is probed only once per session
_cached_cookies: dict | None = None


def _cookies_opt() -> dict:
    """Return the best available cookies option.

    Priority:
      1. cookies.txt in the project folder (Netscape format, exported manually
         via browser extension such as 'Get cookies.txt LOCALLY')
      2. Try live browser cookie extraction (only works when browser is closed)
      3. No cookies — web_creator client works for most public videos
    """
    global _cached_cookies
    if _cached_cookies is not None:
        return _cached_cookies

    if os.path.exists(_COOKIE_FILE) and os.path.getsize(_COOKIE_FILE) > 0:
        _cached_cookies = {"cookiefile": _COOKIE_FILE}
        return _cached_cookies

    for browser in ("chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi"):
        try:
            test_opts = {
                "quiet": True,
                "no_warnings": True,
                "cookiesfrombrowser": (browser,),
                "skip_download": True,
                "extract_flat": True,
                "playlist_items": "1",
            }
            with yt_dlp.YoutubeDL(test_opts) as ydl:
                ydl.cookiejar  # trigger cookie DB load — raises on failure
            _cached_cookies = {"cookiesfrombrowser": (browser,)}
            return _cached_cookies
        except Exception:
            continue

    _cached_cookies = {}
    return _cached_cookies


# ── aria2c auto-detection ──────────────────────────────────────────────────────
_aria2c_available: bool | None = None


def _has_aria2c() -> bool:
    """Check if aria2c is available on PATH (cached)."""
    global _aria2c_available
    if _aria2c_available is None:
        _aria2c_available = shutil.which("aria2c") is not None
    return _aria2c_available


# ── Internal helpers ─────────────────────────────────────────────────────────


def _build_ydl_opts(
    out_dir: str,
    quality: str = "best",
    progress_hook: Callable | None = None,
) -> dict:
    """Construct yt-dlp options dict optimized for maximum quality & speed."""
    fmt = _QUALITY_FORMATS.get(quality, _QUALITY_FORMATS["best"])
    is_audio = (quality == "audio")

    opts: dict = {
        "format":              fmt,
        "outtmpl":             os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet":               True,
        "no_warnings":         True,
        "ignoreerrors":        True,
        "merge_output_format": None if is_audio else "mp4",
        "postprocessors":      [],

        # ── SSL / network robustness ───────────────────────────────────────
        "nocheckcertificate":  True,
        "retries":             10,
        "fragment_retries":    10,
        "http_chunk_size":     10 * 1024 * 1024,   # 10 MB
        "socket_timeout":      30,
        "continuedl":          True,   # resume interrupted downloads

        # ── Concurrent fragment downloads (yt-dlp -N) ─────────────────────
        "concurrent_fragment_downloads": 8,

        # ── Optimized format sorting for maximum quality ───────────────────
        # Resolution → HDR (12-bit) → FPS → Codec quality → Bitrate → Size
        "format_sort": [
            "res",
            "hdr:12",
            "fps",
            "vcodec:vp9.2",
            "vcodec:av01",
            "vcodec:vp9",
            "vcodec:h265",
            "vcodec:h264",
            "channels",
            "acodec:opus",
            "acodec:aac",
            "br",
            "asr",
            "size",
        ],

        # ── Player clients (no PO Token / JS runtime required) ────────────
        "extractor_args": {
            "youtube": {
                "player_client": ["web_creator", "ios", "android"],
            }
        },
    }

    # Remove keys with None values
    opts = {k: v for k, v in opts.items() if v is not None}

    # ── Audio-only post-processing ────────────────────────────────────────────
    if is_audio:
        opts["postprocessors"].append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "0",   # best quality
        })

    # ── aria2c external downloader (16 connections, auto-split) ───────────────
    if _has_aria2c():
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = {
            "aria2c": [
                "--min-split-size=1M",
                "--max-connection-per-server=16",
                "--max-concurrent-downloads=16",
                "--split=16",
            ]
        }

    # ── Inject cookies if available ───────────────────────────────────────────
    opts.update(_cookies_opt())

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ── Public API ─────────────────────────────────────────────────────────────────

def download_youtube_video(
    url: str,
    out_dir: str,
    quality: str = "best",
    progress_hook: Callable | None = None,
) -> str | None:
    """Download a single YouTube video.

    Args:
        url:           YouTube video URL.
        out_dir:       Output directory.
        quality:       One of QUALITY_OPTIONS (default "best").
        progress_hook: Optional yt-dlp progress callback.

    Returns: output filepath on success, None on failure.
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_ydl_opts(out_dir, quality, progress_hook)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info)
    except Exception:
        pass
    return None


def download_youtube_playlist(
    url: str,
    out_dir: str,
    quality: str = "best",
    max_videos: int | None = None,
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a playlist.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_ydl_opts(out_dir, quality, progress_hook)
    if max_videos:
        opts["playlistend"] = max_videos

    ok = err = 0

    def _hook(d: dict) -> None:
        nonlocal ok, err
        status = d.get("status")
        if status == "finished":
            ok += 1
            if log_fn:
                fname = d.get("filename", "")
                if fname:
                    log_fn(f"✓ {os.path.basename(fname)}", "ok")
        elif status == "error":
            err += 1
        if progress_hook:
            progress_hook(d)

    opts["progress_hooks"] = [_hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            total = len(info.get("entries", [])) if info else 0
    except Exception:
        total = 0

    return ok, total


def download_youtube_multi(
    urls: list[str],
    out_dir: str,
    quality: str = "best",
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
    max_workers: int = MAX_CONCURRENT_DOWNLOADS,
) -> tuple[int, int]:
    """Download multiple individual YouTube URLs concurrently.

    Uses ThreadPoolExecutor for parallel downloads (default 3 workers).

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)

    def _download_one(single_url: str) -> bool:
        result = download_youtube_video(single_url, out_dir, quality, progress_hook)
        if result:
            if log_fn:
                log_fn(f"Hoàn thành: {os.path.basename(result)}", "ok")
            return True
        else:
            if log_fn:
                log_fn(f"Thất bại: {single_url}", "err")
            return False

    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_one, u): u for u in urls}
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    ok += 1
            except Exception:
                pass

    return ok, len(urls)


def download_youtube_channel(
    url: str,
    out_dir: str,
    quality: str = "best",
    max_videos: int | None = None,
    use_channel_subfolder: bool = True,
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a YouTube channel.

    Supports channel URLs:
      https://www.youtube.com/@handle
      https://www.youtube.com/channel/UCxxx
      https://www.youtube.com/c/name
      https://www.youtube.com/user/name

    If use_channel_subfolder is True, videos are saved in a sub-folder
    named after the channel inside out_dir.

    Returns: (success_count, total_attempted)
    """
    os.makedirs(out_dir, exist_ok=True)
    final_out = out_dir

    # ── Resolve channel name for sub-folder ──────────────────────────────────
    if use_channel_subfolder:
        opts_info: dict = {
            "quiet":          True,
            "no_warnings":    True,
            "extract_flat":   True,
            "playlist_items": "1",
        }
        opts_info.update(_cookies_opt())
        try:
            with yt_dlp.YoutubeDL(opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                channel_name = (
                    info.get("channel")
                    or info.get("uploader")
                    or info.get("id")
                    or "channel"
                )
                # Sanitize for use as a directory name
                channel_name = re.sub(r'[\\/:*?"<>|]', "_", channel_name).strip()
                final_out = os.path.join(out_dir, channel_name)
                os.makedirs(final_out, exist_ok=True)
                if log_fn:
                    log_fn(f"Kênh: {channel_name}  →  {final_out}", "info")
        except Exception:
            pass  # fallback to out_dir on any error

    # ── Build download options ────────────────────────────────────────────────
    opts = _build_ydl_opts(final_out, quality, progress_hook)
    if max_videos:
        opts["playlistend"] = max_videos

    ok = err = 0

    def _hook(d: dict) -> None:
        nonlocal ok, err
        status = d.get("status")
        if status == "finished":
            ok += 1
            if log_fn:
                fname = d.get("filename", "")
                if fname:
                    log_fn(f"✓ {os.path.basename(fname)}", "ok")
        elif status == "error":
            err += 1
        if progress_hook:
            progress_hook(d)

    opts["progress_hooks"] = [_hook]

    total = 0
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            entries = info.get("entries") if info else None
            if entries is not None:
                total = len(list(entries))   # entries may be a generator
    except Exception:
        pass

    return ok, total


# ── Utility: get video info without downloading ───────────────────────────────

def get_video_info(url: str) -> dict | None:
    """Fetch video metadata without downloading.

    Useful for previewing title, duration, available formats, thumbnail, etc.
    """
    opts: dict = {
        "quiet":           True,
        "no_warnings":     True,
        "skip_download":   True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["web_creator", "ios", "android"],
            }
        },
    }
    opts.update(_cookies_opt())
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None
