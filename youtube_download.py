"""
youtube_download.py
───────────────────
YouTube download helpers using yt-dlp.

Supports:
  - Single video URL
  - Playlist URL
  - Multiple URLs (list)

Quality options: best, 1080p, 720p, 480p, 360p, audio-only
"""

from __future__ import annotations
import os
import re
import yt_dlp


# ── Quality presets ────────────────────────────────────────────────────────────
QUALITY_FORMATS: dict[str, str] = {
    "Best quality":   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "1080p (MP4)":    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
    "720p (MP4)":     "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
    "480p (MP4)":     "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
    "360p (MP4)":     "best[height<=360]",
    "Audio only (MP3)": "bestaudio/best",
}

# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_ydl_opts(out_dir: str, quality: str, progress_hook=None) -> dict:
    fmt = QUALITY_FORMATS.get(quality, QUALITY_FORMATS["Best quality"])
    is_audio = "Audio only" in quality

    opts: dict = {
        "format":          fmt,
        "outtmpl":         os.path.join(out_dir, "%(title)s.%(ext)s"),
        "quiet":           True,
        "no_warnings":     True,
        "ignoreerrors":    True,    # skip unavailable videos in playlist
        "merge_output_format": "mp4",
        "postprocessors":  [],
    }

    if is_audio:
        opts["postprocessors"].append({
            "key":            "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })
        opts["outtmpl"] = os.path.join(out_dir, "%(title)s.%(ext)s")

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ── Public API ─────────────────────────────────────────────────────────────────

def download_youtube_video(
    url: str,
    out_dir: str,
    quality: str = "Best quality",
    progress_hook=None,
) -> str | None:
    """Download a single YouTube video.

    Returns: output filename on success, None on failure.
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
    quality: str = "Best quality",
    max_videos: int | None = None,
    progress_hook=None,
    log_fn=None,
) -> tuple[int, int]:
    """Download all (or up to max_videos) videos from a playlist.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_ydl_opts(out_dir, quality, progress_hook)
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
    quality: str = "Best quality",
    progress_hook=None,
    log_fn=None,
) -> tuple[int, int]:
    """Download multiple individual YouTube URLs.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    ok = err = 0
    for url in urls:
        result = download_youtube_video(url, out_dir, quality, progress_hook)
        if result:
            ok += 1
            if log_fn:
                log_fn(f"Hoàn thành: {os.path.basename(result)}", "ok")
        else:
            err += 1
            if log_fn:
                log_fn(f"Thất bại: {url}", "err")
    return ok, len(urls)
