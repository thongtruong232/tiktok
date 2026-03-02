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


# ── URL validation ──────────────────────────────────────────────────────────────
_YT_URL_RE = re.compile(
    r'https?://(www\.|m\.|music\.)?youtu(\.be|be\.com)/', re.IGNORECASE
)


def is_youtube_url(url: str) -> bool:
    """Return True if *url* looks like a valid YouTube link."""
    return bool(_YT_URL_RE.match(url.strip()))


# ── Quality presets ────────────────────────────────────────────────────────────
QUALITY_OPTIONS: list[str] = [
    "best", "2160p", "1440p", "1080p", "720p", "480p", "360p", "audio",
]

_QUALITY_FORMATS: dict[str, str] = {
    # tv_embedded client provides full DASH streams without PO-token requirement.
    # Fallback chain per quality level (5 levels):
    #   1. bestvideo[ext=mp4]+bestaudio[ext=m4a]  — DASH streams, prefer mp4/m4a
    #   2. bestvideo+bestaudio                    — DASH streams, any container
    #   3. bestvideo[ext=mp4]+bestaudio           — mixed container fallback
    #   4. b[ext=mp4][height<=N]                  — combined progressive MP4
    #   5. best[height<=N] / best                 — absolute fallback, any format
    "best":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/bestvideo[ext=mp4]+bestaudio/b[ext=mp4]/best",
    "2160p": "bestvideo[ext=mp4][height<=2160]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/bestvideo[ext=mp4][height<=2160]+bestaudio/b[ext=mp4][height<=2160]/best[height<=2160]/best",
    "1440p": "bestvideo[ext=mp4][height<=1440]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/bestvideo[ext=mp4][height<=1440]+bestaudio/b[ext=mp4][height<=1440]/best[height<=1440]/best",
    "1080p": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/bestvideo[ext=mp4][height<=1080]+bestaudio/b[ext=mp4][height<=1080]/best[height<=1080]/best",
    "720p":  "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/bestvideo[ext=mp4][height<=720]+bestaudio/b[ext=mp4][height<=720]/best[height<=720]/best",
    "480p":  "bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/bestvideo[ext=mp4][height<=480]+bestaudio/b[ext=mp4][height<=480]/best[height<=480]/best",
    "360p":  "bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/bestvideo[ext=mp4][height<=360]+bestaudio/b[ext=mp4][height<=360]/best[height<=360]/best",
    "audio": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
}

# Max concurrent video downloads for multi-URL / playlist modes
MAX_CONCURRENT_DOWNLOADS = 3


# ── Cookies auto-detection ─────────────────────────────────────────────────────
_COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_cookies.txt")

# Cache cookie option so browser DB is probed only once per session
_cached_cookies: dict | None = None
_cached_cookies_mtime: float = 0.0   # track file changes to invalidate cache


def _cookie_status_text() -> str:
    """Return human-readable cookie usage status."""
    opt = _cookies_opt()
    if "cookiefile" in opt:
        return "youtube_cookies.txt"
    if "cookiesfrombrowser" in opt:
        browser = opt["cookiesfrombrowser"][0] if opt["cookiesfrombrowser"] else "browser"
        return f"browser:{browser}"
    return "không sử dụng"


def get_youtube_runtime_context(quality: str = "best", use_cookies: bool = True) -> dict:
    """Return current runtime context used for YouTube downloads."""
    cookie_status = _cookie_status_text()
    cookies_opt = _cookies_opt()
    return {
        "quality": quality,
        "cookies": cookie_status,
        "using_cookies": bool(cookies_opt),
        "using_aria2c": _has_aria2c(),
        "concurrent_fragments": 8,
    }


def _validate_cookies_file(path: str) -> bool:
    """Check if a cookies.txt file is valid Netscape format with content."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Valid Netscape cookie line has >=7 tab-separated fields
                if len(line.split("\t")) >= 7:
                    return True
        return False
    except Exception:
        return False


def _cookies_opt() -> dict:
    """Return the best available cookies option.

    Priority:
      1. cookies.txt in the project folder (valid Netscape format)
      2. Try live browser cookie extraction (only works when browser is closed)
      3. No cookies  — yt-dlp default extraction still works for public videos
    """
    global _cached_cookies, _cached_cookies_mtime

    # Invalidate cache if cookies.txt was modified/created/removed
    try:
        current_mtime = os.path.getmtime(_COOKIE_FILE) if os.path.exists(_COOKIE_FILE) else 0.0
    except OSError:
        current_mtime = 0.0
    if current_mtime != _cached_cookies_mtime:
        _cached_cookies = None
        _cached_cookies_mtime = current_mtime

    if _cached_cookies is not None:
        return _cached_cookies

    if _validate_cookies_file(_COOKIE_FILE):
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
    use_cookies: bool = True,
) -> dict:
    """Construct yt-dlp options dict optimized for maximum quality & speed."""
    fmt = _QUALITY_FORMATS.get(quality, _QUALITY_FORMATS["best"])
    is_audio = (quality == "audio")

    opts: dict = {
        "format":              fmt,
        "outtmpl":             os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet":               True,
        "no_warnings":         True,
        # ignoreerrors intentionally omitted for single-video — errors must surface
        # For playlist/multi, callers set it explicitly via opts update
        "merge_output_format": None if is_audio else "mp4",
        "postprocessors":      [],

        # ── Ensure ffmpeg is used for merging separate video+audio streams ─
        "prefer_ffmpeg":        True,

        # ── JS runtime: use Node.js for YouTube signature/challenge solving ─
        # yt-dlp defaults to deno which may not be installed.
        # Node.js is widely available and yt-dlp-ejs supports it.
        "js_runtimes":         {"node": {}},

        # ── SSL / network robustness ───────────────────────────────────────
        "nocheckcertificate":  True,
        "retries":             10,
        "fragment_retries":    10,
        "http_chunk_size":     10 * 1024 * 1024,   # 10 MB
        "socket_timeout":      30,

        # ── Concurrent fragment downloads (yt-dlp -N) ─────────────────────
        "concurrent_fragment_downloads": 8,
        # format_sort intentionally omitted — it conflicts with explicit format
        # strings and causes "Requested format is not available" errors.
        # The format string above already encodes all quality/fallback logic.
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

    # ── Cookies: always use youtube_cookies.txt (web client, full DASH access) ─
    # Cookies file is always present → web client path → no PO-token issue.
    # Full DASH streams available: bestvideo+bestaudio up to 4K works correctly.
    cookie_opts: dict = _cookies_opt()
    if cookie_opts:
        opts.update(cookie_opts)
    else:
        # Cookies file missing/invalid — fall back to tv_embedded (no PO-token)
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["tv_embedded", "ios", "android"],
            }
        }

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ── Public API ─────────────────────────────────────────────────────────────────

def download_youtube_video(
    url: str,
    out_dir: str,
    quality: str = "best",
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
    use_cookies: bool = True,
) -> str | None:
    """Download a single YouTube video.

    Args:
        url:           YouTube video URL.
        out_dir:       Output directory.
        quality:       One of QUALITY_OPTIONS (default "best").
        progress_hook: Optional yt-dlp progress callback.
        log_fn:        Optional logging callback (text, tag).
        use_cookies:   Whether to inject cookies.txt (default False).

    Returns: output filepath on success, None on failure.
    """
    if not is_youtube_url(url):
        if log_fn:
            log_fn(f"URL không hợp lệ: {url}", "err")
        return None
    os.makedirs(out_dir, exist_ok=True)
    if log_fn:
        ctx = get_youtube_runtime_context(quality, use_cookies)
        log_fn(
            "[YouTube] cấu hình tải: "
            f"quality={ctx['quality']} | cookies={ctx['cookies']} | "
            f"aria2c={'bật' if ctx['using_aria2c'] else 'tắt'} | "
            f"N={ctx['concurrent_fragments']}",
            "info",
        )
    opts = _build_ydl_opts(out_dir, quality, progress_hook, use_cookies)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError as e:
        err_msg = str(e)
        if "Requested format is not available" in err_msg or "format" in err_msg.lower():
            # Retry with absolute fallback: accept any available format
            if log_fn:
                log_fn("[YouTube] format yêu cầu không có sẵn, thử lại với format tự động...", "warn")
            fallback_opts = _build_ydl_opts(out_dir, "best", progress_hook, use_cookies)
            fallback_opts["format"] = "best/bestvideo+bestaudio"
            fallback_opts["js_runtimes"] = {"node": {}}
            # Ensure tv_embedded client is used if no cookies
            if "extractor_args" in fallback_opts:
                fallback_opts["extractor_args"] = {
                    "youtube": {"player_client": ["tv_embedded", "ios", "android", "web"]}
                }
            try:
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        if log_fn:
                            log_fn("[YouTube] tải thành công với format fallback.", "info")
                        return ydl.prepare_filename(info)
            except Exception as e2:
                if log_fn:
                    log_fn(f"[YouTube] lỗi fallback: {e2}", "err")
        else:
            if log_fn:
                log_fn(f"[YouTube] lỗi tải: {e}", "err")
    except Exception as e:
        if log_fn:
            log_fn(f"[YouTube] lỗi không xác định: {e}", "err")
    return None


def download_youtube_playlist(
    url: str,
    out_dir: str,
    quality: str = "best",
    max_videos: int | None = None,
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
    use_cookies: bool = True,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a playlist.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    if log_fn:
        ctx = get_youtube_runtime_context(quality, use_cookies)
        log_fn(
            "[YouTube] cấu hình playlist: "
            f"quality={ctx['quality']} | cookies={ctx['cookies']} | "
            f"aria2c={'bật' if ctx['using_aria2c'] else 'tắt'} | "
            f"N={ctx['concurrent_fragments']}",
            "info",
        )
    opts = _build_ydl_opts(out_dir, quality, progress_hook, use_cookies)
    if max_videos:
        opts["playlistend"] = max_videos
    opts["ignoreerrors"] = True   # skip unavailable videos in playlist

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
    use_cookies: bool = True,
) -> tuple[int, int]:
    """Download multiple individual YouTube URLs concurrently.

    Uses ThreadPoolExecutor for parallel downloads (default 3 workers).

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    if log_fn:
        ctx = get_youtube_runtime_context(quality, use_cookies)
        log_fn(
            "[YouTube] cấu hình multi-url: "
            f"quality={ctx['quality']} | cookies={ctx['cookies']} | "
            f"aria2c={'bật' if ctx['using_aria2c'] else 'tắt'} | "
            f"N={ctx['concurrent_fragments']} | workers={max_workers}",
            "info",
        )

    def _download_one(single_url: str) -> bool:
        result = download_youtube_video(single_url, out_dir, quality, progress_hook, use_cookies=use_cookies)
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
    use_cookies: bool = True,
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
    if log_fn:
        ctx = get_youtube_runtime_context(quality, use_cookies)
        log_fn(
            "[YouTube] cấu hình channel: "
            f"quality={ctx['quality']} | cookies={ctx['cookies']} | "
            f"aria2c={'bật' if ctx['using_aria2c'] else 'tắt'} | "
            f"N={ctx['concurrent_fragments']}",
            "info",
        )
    final_out = out_dir

    # ── Resolve channel name for sub-folder ──────────────────────────────────
    if use_channel_subfolder:
        opts_info: dict = {
            "quiet":          True,
            "no_warnings":    True,
            "extract_flat":   True,
            "playlist_items": "1",
        }
        if use_cookies:
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
    opts = _build_ydl_opts(final_out, quality, progress_hook, use_cookies)
    if max_videos:
        opts["playlistend"] = max_videos
    opts["ignoreerrors"] = True   # skip unavailable videos in channel

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
        "js_runtimes":     {"node": {}},
    }
    # Use cookies if available for full format access
    cookie_opts = _cookies_opt()
    if cookie_opts:
        opts.update(cookie_opts)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        return None
