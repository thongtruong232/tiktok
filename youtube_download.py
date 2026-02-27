"""
youtube_download.py
───────────────────
YouTube download helpers using yt-dlp.

Supports:
  - Single video URL
  - Playlist URL
  - Multiple URLs (list)
  - Full channel download

Quality options: best, 1080p, 720p, 480p, 360p, audio-only
"""

from __future__ import annotations
import os
import re
import yt_dlp


# ── Cookies auto-detection ─────────────────────────────────────────────────────
_COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")


def _cookies_opt() -> dict:
    """Return the best available cookies option.

    Priority:
      1. cookies.txt in the project folder (Netscape format, exported manually
         via browser extension such as 'Get cookies.txt LOCALLY')
      2. Try live browser cookie extraction (only works when browser is closed)
      3. No cookies — web_creator client works for most public videos
    """
    if os.path.exists(_COOKIE_FILE) and os.path.getsize(_COOKIE_FILE) > 0:
        return {"cookiefile": _COOKIE_FILE}
    for browser in ("chrome", "edge", "brave", "chromium", "opera", "vivaldi"):
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
            return {"cookiesfrombrowser": (browser,)}
        except Exception:
            continue
    return {}


# ── Internal helpers ─────────────────────────────────────────────────────────
# Always download the best available quality — separate video+audio streams
# merged to MP4.  The * wildcard accepts any codec/container so the selector
# never fails, even when only a combined stream (e.g. format 18) is available.
_BEST_FORMAT = "bestvideo*+bestaudio*/best*"


def _build_ydl_opts(out_dir: str, progress_hook=None) -> dict:
    opts: dict = {
        "format":          _BEST_FORMAT,
        "outtmpl":         os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet":           True,
        "no_warnings":     True,
        "ignoreerrors":    True,
        "merge_output_format": "mp4",
        "postprocessors":  [],
        # ── SSL / network robustness ───────────────────────────────────────
        "nocheckcertificate": True,
        "retries":            10,
        "fragment_retries":   10,
        "http_chunk_size":    10 * 1024 * 1024,
        "socket_timeout":     30,
        # ── Prioritise resolution → fps → bitrate ─────────────────────────
        "format_sort": ["res", "fps", "hdr:12", "vcodec:vp9.2", "acodec:opus",
                        "vcodec", "acodec", "br", "size"],
        # ── Player clients (no PO Token / JS runtime required) ────────────
        "extractor_args": {
            "youtube": {
                "player_client": ["web_creator", "ios", "android"],
            }
        },
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
    progress_hook=None,
) -> str | None:
    """Download a single YouTube video at the best available quality.

    Returns: output filename on success, None on failure.
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_ydl_opts(out_dir, progress_hook)
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
    max_videos: int | None = None,
    progress_hook=None,
    log_fn=None,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a playlist at best quality.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_ydl_opts(out_dir, progress_hook)
    if max_videos:
        opts["playlistend"] = max_videos

    ok = err = 0
    def _hook(d):
        nonlocal ok, err
        if d.get("status") == "finished":
            ok += 1
        elif d.get("status") == "error":
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
    progress_hook=None,
    log_fn=None,
) -> tuple[int, int]:
    """Download multiple individual YouTube URLs at best quality.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    ok = err = 0
    for url in urls:
        result = download_youtube_video(url, out_dir, progress_hook)
        if result:
            ok += 1
            if log_fn:
                log_fn(f"Hoàn thành: {os.path.basename(result)}", "ok")
        else:
            err += 1
            if log_fn:
                log_fn(f"Thất bại: {url}", "err")
    return ok, len(urls)


def download_youtube_channel(
    url: str,
    out_dir: str,
    max_videos: int | None = None,
    use_channel_subfolder: bool = True,
    progress_hook=None,
    log_fn=None,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a YouTube channel at best quality.

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
            "quiet":        True,
            "no_warnings":  True,
            "extract_flat": True,
            "playlist_items": "1",
        }
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
    opts = _build_ydl_opts(final_out, progress_hook)
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
