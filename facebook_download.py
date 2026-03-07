"""
facebook_download.py
────────────────────
Facebook video download helpers using yt-dlp.

Supports:
  - Single video / reel / watch URL
  - Profile / reels / videos page (scrapes video URLs from HTML)
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

import requests
from http.cookiejar import MozillaCookieJar
import yt_dlp


# ── URL validation ──────────────────────────────────────────────────────────────
_FB_URL_RE = re.compile(
    r'https?://(www\.|m\.|web\.|l\.)?(facebook\.com|fb\.watch|fb\.com)/',
    re.IGNORECASE,
)

# Patterns that indicate a profile / reels / videos page (not a single video)
_FB_PROFILE_RE = re.compile(
    r'https?://(www\.|m\.)?facebook\.com/'
    r'(?:'
    r'profile\.php\?id=\d+'                     # /profile.php?id=12345
    r'|(?!reel/|watch|video|photo|story|share|groups|events|pages|marketplace)'
    r'[a-zA-Z0-9.]+(?:/(?:reels|videos)/?)?'    # /username  /username/reels/  /username/videos/
    r')$',
    re.IGNORECASE,
)


def is_facebook_url(url: str) -> bool:
    """Return True if *url* looks like a valid Facebook link."""
    return bool(_FB_URL_RE.match(url.strip()))


def _is_fb_profile_or_listing(url: str) -> bool:
    """Return True if the URL is a profile / reels / videos page."""
    clean = url.strip().rstrip('/')
    # Also match profile.php with extra params
    if re.match(r'https?://(www\.|m\.)?facebook\.com/profile\.php\?id=\d+', clean, re.I):
        return True
    return bool(_FB_PROFILE_RE.match(clean))


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
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_FB_COOKIE_CANDIDATES = [
    os.path.join(_BASE_DIR, 'facebook_cookies.txt'),
    os.path.join(_BASE_DIR, 'facebook.com_cookies.txt'),
]


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
    for path in _FB_COOKIE_CANDIDATES:
        if _validate_cookies_file(path):
            return {'cookiefile': path}
    return {}


def _get_cookie_file() -> str | None:
    """Return the first valid cookie file path, or None."""
    for path in _FB_COOKIE_CANDIDATES:
        if _validate_cookies_file(path):
            return path
    return None


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


def download_facebook_profile(
    profile_url: str,
    out_dir: str = 'downloads',
    quality: str = 'best',
    max_videos: int | None = None,
    progress_hook: Callable | None = None,
    log_fn: Callable | None = None,
) -> tuple[int, int]:
    """Download videos from a Facebook profile / reels / videos page.

    Scrapes video URLs from the page HTML, then downloads each one.

    Returns: (success_count, total_count)
    """
    os.makedirs(out_dir, exist_ok=True)
    video_urls = _scrape_video_urls(profile_url, max_videos)
    if not video_urls:
        if log_fn:
            log_fn('[Facebook] Không tìm thấy video trên trang này.', 'err')
        return 0, 0

    if log_fn:
        log_fn(f'[Facebook] Tìm thấy {len(video_urls)} video, đang tải...', 'info')

    ok = 0
    for url in video_urls:
        fn = download_facebook_video(url, out_dir, quality, progress_hook, log_fn)
        if fn:
            ok += 1
            if log_fn:
                log_fn(f'Hoàn thành: {os.path.basename(fn)}', 'ok')
        else:
            if log_fn:
                log_fn(f'Thất bại: {url}', 'err')
    return ok, len(video_urls)


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


def fetch_facebook_video_list(url: str, max_videos: int | None = None) -> list[dict]:
    """Fetch video metadata from a Facebook URL.

    Handles:
      - Single video / reel URLs → yt-dlp direct extraction
      - Profile / reels / videos pages → scrapes HTML for video URLs,
        then extracts metadata for each via yt-dlp

    Returns list of dicts: {url, title, thumbnail, view_count, duration, uploader,
                            like_count, comment_count}
    """
    # If it's a profile / reels / videos page, scrape URLs first
    if _is_fb_profile_or_listing(url):
        video_urls = _scrape_video_urls(url, max_videos)
        if not video_urls:
            return []
        return _extract_info_batch(video_urls)

    # Single video URL — extract directly
    return _extract_single_info(url)


# ── Internal: scrape video URLs from a Facebook page ─────────────────────────────

_SCRAPE_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}


def _scrape_video_urls(page_url: str, max_videos: int | None = None) -> list[str]:
    """Scrape individual video/reel URLs from a Facebook profile-like page.

    Strategy:
      1. Fetch the page HTML with cookies
      2. Extract reel IDs from /reel/ID and escaped \\/reel\\/ID patterns
      3. Extract video IDs from /videos/ID patterns
      4. Build full URLs and deduplicate
      5. For bare username profiles (no /reels or /videos), try /reels/ then /videos/ pages
    """
    cookie_file = _get_cookie_file()
    session = requests.Session()

    if cookie_file:
        try:
            cj = MozillaCookieJar(cookie_file)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
        except Exception:
            pass

    def _extract_ids_from_html(html: str) -> list[str]:
        """Extract video URLs from Facebook page HTML."""
        found_urls: list[str] = []
        seen_ids: set[str] = set()

        # Reel IDs: /reel/12345 and escaped \/reel\/12345
        for reel_id in re.findall(r'(?:/|\\/)reel(?:/|\\/)(\d+)', html):
            if reel_id not in seen_ids:
                seen_ids.add(reel_id)
                found_urls.append(f'https://www.facebook.com/reel/{reel_id}')

        # Video IDs: /videos/12345
        for vid_id in re.findall(r'/videos/(\d+)', html):
            if vid_id not in seen_ids:
                seen_ids.add(vid_id)
                found_urls.append(f'https://www.facebook.com/watch/?v={vid_id}')

        # video_id in JSON: "video_id":"12345"
        for vid_id in re.findall(r'"video_id":"(\d+)"', html):
            if vid_id not in seen_ids:
                seen_ids.add(vid_id)
                found_urls.append(f'https://www.facebook.com/watch/?v={vid_id}')

        return found_urls

    def _fetch_page(target_url: str) -> list[str]:
        try:
            resp = session.get(
                target_url, headers=_SCRAPE_HEADERS,
                timeout=20, allow_redirects=True)
            if resp.status_code != 200:
                return []
            return _extract_ids_from_html(resp.text)
        except Exception:
            return []

    clean_url = page_url.strip().rstrip('/')
    all_urls: list[str] = []

    # Check if the URL already specifies /reels/ or /videos/
    if '/reels' in clean_url or '/videos' in clean_url:
        all_urls = _fetch_page(clean_url)
    elif '/profile.php' in clean_url:
        # For profile.php, fetch the main page
        all_urls = _fetch_page(clean_url)
    else:
        # Bare username — try /reels/ first, then /videos/
        reels_url = clean_url + '/reels/'
        all_urls = _fetch_page(reels_url)
        if not all_urls:
            videos_url = clean_url + '/videos/'
            all_urls = _fetch_page(videos_url)
        if not all_urls:
            # Fallback: try the bare profile page itself
            all_urls = _fetch_page(clean_url)

    if max_videos and len(all_urls) > max_videos:
        all_urls = all_urls[:max_videos]

    return all_urls


def _extract_single_info(url: str) -> list[dict]:
    """Extract metadata for a single Facebook video URL via yt-dlp."""
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


def _extract_info_batch(video_urls: list[str]) -> list[dict]:
    """Extract metadata for multiple Facebook video URLs via yt-dlp."""
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
    with _suppress_stderr():
        with yt_dlp.YoutubeDL(opts) as ydl:
            for url in video_urls:
                try:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        continue
                    thumb = ''
                    if info.get('thumbnails'):
                        thumb = info['thumbnails'][-1].get('url', '')
                    elif info.get('thumbnail'):
                        thumb = info['thumbnail']

                    results.append({
                        'url':           info.get('webpage_url')
                                         or info.get('url') or url,
                        'title':         info.get('title') or 'Không rõ',
                        'thumbnail':     thumb,
                        'view_count':    info.get('view_count') or 0,
                        'duration':      info.get('duration') or 0,
                        'uploader':      info.get('uploader') or '',
                        'like_count':    info.get('like_count') or 0,
                        'comment_count': info.get('comment_count') or 0,
                    })
                except Exception:
                    continue

    return results
