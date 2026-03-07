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
import json
from contextlib import contextmanager
from typing import Callable

import requests
from http.cookiejar import MozillaCookieJar
import base64
import yt_dlp


# ── Module-level cache for pagination query hash (refreshed per process) ─────
_cached_reels_doc_id: str | None = None
_REELS_PAGINATION_QUERY = 'ProfileCometAppCollectionReelsRendererPaginationQuery'


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
    """Scrape video/reel URLs from a Facebook profile page, with cursor pagination.

    Strategy:
      1. Fetch the profile/reels/videos page HTML with authentication cookies
      2. Extract reel and video IDs from the initial HTML (~10 items)
      3. Extract GraphQL pagination tokens (lsd, fb_dtsg, app_collection node ID)
      4. Discover the Relay pagination query hash from loaded JS bundles (cached)
      5. Paginate via Facebook's GraphQL API until all videos are retrieved
    """
    global _cached_reels_doc_id

    cookie_file = _get_cookie_file()
    session = requests.Session()

    cj: MozillaCookieJar | None = None
    if cookie_file:
        try:
            cj = MozillaCookieJar(cookie_file)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
        except Exception:
            pass

    seen_ids: set[str] = set()
    all_urls: list[str] = []

    def _add_url(url: str) -> None:
        """Add a video URL, deduplicating by numeric ID."""
        m = re.search(r'/reel/(\d+)|[?&]v=(\d+)', url)
        vid_id = (m.group(1) or m.group(2)) if m else url
        if vid_id not in seen_ids:
            seen_ids.add(vid_id)
            all_urls.append(url)

    def _extract_video_urls(text: str) -> list[str]:
        """Extract reel/video URLs from HTML or JSON text."""
        found: list[str] = []
        local_seen: set[str] = set()
        for reel_id in re.findall(r'(?:/|\\/)reel(?:/|\\/)(\d+)', text):
            if reel_id not in local_seen:
                local_seen.add(reel_id)
                found.append(f'https://www.facebook.com/reel/{reel_id}')
        for vid_id in re.findall(r'"video_id"\s*:\s*"(\d+)"', text):
            if vid_id not in local_seen:
                local_seen.add(vid_id)
                found.append(f'https://www.facebook.com/watch/?v={vid_id}')
        return found

    def _fetch_html(url: str) -> str:
        try:
            r = session.get(url, headers=_SCRAPE_HEADERS, timeout=20, allow_redirects=True)
            return r.text if r.status_code == 200 else ''
        except Exception:
            return ''

    # ── Determine which URL to fetch ──────────────────────────────────────────
    clean = page_url.strip().rstrip('/')
    if '/profile.php' in clean or '/reels' in clean or '/videos' in clean or 'sk=' in clean:
        primary_url = clean
        fallback_url = None
    else:
        primary_url = clean + '/reels/'
        fallback_url = clean + '/videos/'

    # ── Fetch initial page ────────────────────────────────────────────────────
    html = _fetch_html(primary_url)
    if not html and fallback_url:
        html = _fetch_html(fallback_url)
    if not html and clean != primary_url:
        html = _fetch_html(clean)
    if not html:
        return []

    for u in _extract_video_urls(html):
        _add_url(u)

    # ── Extract pagination metadata ───────────────────────────────────────────
    cursor_m = re.search(r'"end_cursor"\s*:\s*"([^"]+)"', html)
    has_next_m = re.search(r'"has_next_page"\s*:\s*(true|false)', html)
    cursor = cursor_m.group(1) if cursor_m else None
    has_next = (has_next_m.group(1) == 'true') if has_next_m else bool(cursor)

    if not (cursor and has_next):
        return all_urls[:max_videos] if max_videos else all_urls

    if max_videos and len(all_urls) >= max_videos:
        return all_urls[:max_videos]

    # Extract auth tokens needed for GraphQL
    lsd_m  = re.search(r'"LSD",\[\],\{"token":"([^"]+)"\}', html)
    dtsg_m = re.search(r'"DTSGInitData",\[\],\{"token":"([^"]+)"', html)
    lsd     = lsd_m.group(1) if lsd_m else None
    fb_dtsg = dtsg_m.group(1) if dtsg_m else None
    fb_c_user = next(
        (c.value for c in session.cookies if c.name == 'c_user'), None
    )
    jazoest = ('2' + ''.join(str(ord(c)) for c in lsd)) if lsd else None

    # Extract app_collection base64 node ID (identifies the reels feed node)
    collection_id: str | None = None
    for b64 in re.findall(r'"id"\s*:\s*"([A-Za-z0-9+/]{20,}={0,2})"', html):
        try:
            decoded = base64.b64decode(b64 + '==').decode('utf-8', errors='replace')
            if 'app_collection' in decoded:
                collection_id = b64
                break
        except Exception:
            pass

    if not (lsd and fb_dtsg and collection_id):
        return all_urls[:max_videos] if max_videos else all_urls

    # ── Discover Relay pagination query doc_id from JS bundles (cached) ───────
    if not _cached_reels_doc_id:
        js_urls = list(set(re.findall(
            r'"(https://static[^"]+rsrc\.php[^"]*\.js[^"]*)"', html)))
        for js_url in js_urls:
            try:
                rj = session.get(
                    js_url,
                    headers={'User-Agent': _SCRAPE_HEADERS['User-Agent']},
                    timeout=30,
                )
                if rj.status_code != 200 or _REELS_PAGINATION_QUERY not in rj.text:
                    continue
                js = rj.text
                for m in re.finditer(re.escape(_REELS_PAGINATION_QUERY), js):
                    ctx = js[max(0, m.start() - 500):m.start() + 500]
                    ids = re.findall(r'\b(\d{15,})\b', ctx)
                    if ids:
                        _cached_reels_doc_id = ids[0]
                        break
                if _cached_reels_doc_id:
                    break
            except Exception:
                continue

    if not _cached_reels_doc_id:
        return all_urls[:max_videos] if max_videos else all_urls

    # ── Paginate via Facebook's GraphQL endpoint ──────────────────────────────
    post_headers = {
        'User-Agent':      _SCRAPE_HEADERS['User-Agent'],
        'Accept-Language': _SCRAPE_HEADERS['Accept-Language'],
        'Content-Type':    'application/x-www-form-urlencoded',
        'X-FB-LSD':        lsd,
        'Origin':          'https://www.facebook.com',
        'Referer':         primary_url,
        'Sec-Fetch-Dest':  'empty',
        'Sec-Fetch-Mode':  'cors',
        'Sec-Fetch-Site':  'same-origin',
    }

    for _ in range(100):  # safety cap: max 100 extra pages (~2400 more videos)
        if max_videos and len(all_urls) >= max_videos:
            break
        try:
            payload = {
                'av':                      fb_c_user or '0',
                '__user':                  fb_c_user or '0',
                '__a':                     '1',
                'lsd':                     lsd,
                'jazoest':                 jazoest,
                'fb_dtsg':                 fb_dtsg,
                'server_timestamps':       'true',
                'fb_api_caller_class':     'RelayModern',
                'fb_api_req_friendly_name': _REELS_PAGINATION_QUERY,
                'variables': json.dumps({
                    'cursor': cursor,
                    'count':  24,
                    'id':     collection_id,
                    'scale':  2,
                }),
                'doc_id': _cached_reels_doc_id,
            }
            resp = session.post(
                'https://www.facebook.com/api/graphql/',
                data=payload, headers=post_headers, timeout=20,
            )
            if resp.status_code != 200:
                break
            text = resp.text
            if text.startswith('for (;;);'):
                text = text[9:]
            # Hard error: API rejected request (missing "data" key)
            if '"data"' not in text:
                break

            for u in _extract_video_urls(text):
                _add_url(u)

            next_cur_m  = re.search(r'"end_cursor"\s*:\s*"([^"]+)"', text)
            has_next_m2 = re.search(r'"has_next_page"\s*:\s*(true|false)', text)
            has_more    = has_next_m2.group(1) == 'true' if has_next_m2 else False
            cursor = (next_cur_m.group(1) if (next_cur_m and has_more) else None)
            if not cursor:
                break
        except Exception:
            break

    return all_urls[:max_videos] if max_videos else all_urls


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
