"""
facebook_download.py
────────────────────
Facebook video download helpers using yt-dlp.

Supports:
  - Single video / reel / watch URL
  - Video list fetching (metadata preview)

Quality: best available (bestvideo+bestaudio merged to mp4)
Authentication: cookies file for private / login-required videos
"""

from __future__ import annotations
import os
import re
import io
import sys
from contextlib import contextmanager
from typing import Callable

import yt_dlp


# ── URL validation ──────────────────────────────────────────────────────────────
_FB_URL_RE = re.compile(
    r'https?://(www\.|m\.|web\.|l\.)?(facebook\.com|fb\.watch|fb\.com)/',
    re.IGNORECASE,
)


def is_facebook_url(url: str) -> bool:
    """Return True if *url* looks like a valid Facebook link."""
    return bool(_FB_URL_RE.match(url.strip()))


# ── Helpers ──────────────────────────────────────────────────────────────────────
@contextmanager
def _suppress_stderr():
    """Temporarily redirect stderr to devnull."""
    old = sys.stderr
    sys.stderr = io.StringIO()
    try:
        yield
    finally:
        sys.stderr = old


class _NullLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


# ── Cookie file ──────────────────────────────────────────────────────────────────
_FB_COOKIE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'facebook_cookies.txt')


def _validate_cookies_file(path: str) -> bool:
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if len(line.split('\t')) >= 7:
                    return True
        return False
    except Exception:
        return False


def _cookies_opt() -> dict:
    if _validate_cookies_file(_FB_COOKIE_FILE):
        return {'cookiefile': _FB_COOKIE_FILE}
    return {}


# ── Quality formats ─────────────────────────────────────────────────────────────
QUALITY_OPTIONS: list[str] = [
    'best', '1080p', '720p', '480p', '360p',
]

_QUALITY_FORMATS: dict[str, str] = {
    'best':  'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
    '1080p': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[ext=mp4][height<=1080]/best[height<=1080]/best',
    '720p':  'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[ext=mp4][height<=720]/best[height<=720]/best',
    '480p':  'bestvideo[ext=mp4][height<=480]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[ext=mp4][height<=480]/best[height<=480]/best',
    '360p':  'bestvideo[ext=mp4][height<=360]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[ext=mp4][height<=360]/best[height<=360]/best',
}


# ── Build yt-dlp opts ────────────────────────────────────────────────────────────
def _build_fb_opts(
    out_dir: str,
    quality: str = 'best',
    progress_hook: Callable | None = None,
) -> dict:
    fmt = _QUALITY_FORMATS.get(quality, _QUALITY_FORMATS['best'])

    opts: dict = {
        'format':              fmt,
        'outtmpl':             os.path.join(out_dir, '%(title)s.%(ext)s'),
        'quiet':               True,
        'no_warnings':         True,
        'merge_output_format': 'mp4',
        'postprocessors':      [],
        'prefer_ffmpeg':       True,
        'nocheckcertificate':  True,
        'retries':             10,
        'fragment_retries':    10,
        'http_chunk_size':     10 * 1024 * 1024,
        'socket_timeout':      30,
        'concurrent_fragment_downloads': 8,
    }

    cookie_opts = _cookies_opt()
    if cookie_opts:
        opts.update(cookie_opts)

    if progress_hook:
        opts['progress_hooks'] = [progress_hook]

    return opts


# ── Public API ───────────────────────────────────────────────────────────────────

def download_facebook_video(
    url: str,
    out_dir: str = 'downloads',
    quality: str = 'best',
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
) -> str | None:
    """Download a single Facebook video.

    Returns: output filepath on success, None on failure.
    """
    os.makedirs(out_dir, exist_ok=True)
    opts = _build_fb_opts(out_dir, quality, progress_hook)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info)
    except Exception as e:
        if log_fn:
            log_fn(f'[Facebook] Lỗi tải: {e}', 'err')
    return None


def download_facebook_multi(
    urls: list[str],
    out_dir: str = 'downloads',
    quality: str = 'best',
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
) -> tuple[int, int]:
    """Download multiple Facebook video URLs sequentially.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    ok = 0
    for url in urls:
        fn = download_facebook_video(url, out_dir, quality, progress_hook, log_fn)
        if fn:
            ok += 1
            if log_fn:
                log_fn(f'Hoàn thành: {os.path.basename(fn)}', 'ok')
        else:
            if log_fn:
                log_fn(f'Thất bại: {url}', 'err')
    return ok, len(urls)


def fetch_facebook_video_list(url: str) -> list[dict]:
    """Fetch video metadata from a Facebook URL.

    Returns list of dicts: {url, title, thumbnail, view_count, duration, uploader,
                            like_count, comment_count}
    """
    opts: dict = {
        'quiet':              True,
        'no_warnings':        True,
        'skip_download':      True,
        'nocheckcertificate': True,
        'ignoreerrors':       True,
        'logger':             _NullLogger(),
    }
    cookie_opts = _cookies_opt()
    if cookie_opts:
        opts.update(cookie_opts)

    results: list[dict] = []
    try:
        with _suppress_stderr():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return results

                entries = info.get('entries')
                items = list(entries) if entries else [info]

                for entry in items:
                    if entry is None:
                        continue
                    thumb = ''
                    if entry.get('thumbnails'):
                        thumb = entry['thumbnails'][-1].get('url', '')
                    elif entry.get('thumbnail'):
                        thumb = entry['thumbnail']

                    results.append({
                        'url':           entry.get('webpage_url')
                                         or entry.get('url') or url,
                        'title':         entry.get('title') or 'Không rõ',
                        'thumbnail':     thumb,
                        'view_count':    entry.get('view_count') or 0,
                        'duration':      entry.get('duration') or 0,
                        'uploader':      entry.get('uploader') or '',
                        'like_count':    entry.get('like_count') or 0,
                        'comment_count': entry.get('comment_count') or 0,
                    })
    except Exception:
        pass

    return results
