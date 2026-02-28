import yt_dlp
import os
import re
import requests


# ── Shared yt-dlp options for TikTok (applied to all functions) ───────────────
def _build_tt_opts(output_path: str, extra: dict | None = None,
                   progress_hook=None) -> dict:
    cookies = 'cookies.txt' if os.path.exists('cookies.txt') else None
    opts: dict = {
        'format':       'bestvideo+bestaudio/best',  # prefer separate streams → higher quality
        'outtmpl':      os.path.join(output_path, '%(title)s.%(ext)s'),
        'quiet':        True,           # suppress yt-dlp stdout noise
        'no_warnings':  True,
        'ignoreerrors': False,
        'merge_output_format': 'mp4',
        'postprocessors': [],
        # ── SSL / network robustness ─────────────────────────────────────
        'nocheckcertificate': True,
        'retries':            10,
        'fragment_retries':   10,
        'http_chunk_size':    10 * 1024 * 1024,  # 10 MB chunks
        'socket_timeout':     30,
    }
    if cookies:
        opts['cookiefile'] = cookies
    if progress_hook:
        opts['progress_hooks'] = [progress_hook]
    if extra:
        opts.update(extra)
    return opts


# ── Fallback: extract channel_id when secUid extraction fails ─────────────────
class _NullLogger:
    """Swallow all yt-dlp console output (including ERROR lines)."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _resolve_channel_id(profile_url: str) -> str | None:
    """Try to obtain a TikTok channel_id so we can use 'tiktokuser:<id>'.

    Strategy:
      1. Fetch the profile HTML and look for secUid in embedded JSON.
      2. If not found, try each video URL on the page until one yields a
         channel_id (some videos may be login-gated).
    """
    cookies_file = 'cookies.txt' if os.path.exists('cookies.txt') else None

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'en-US,en;q=0.9',
    }

    session = requests.Session()
    if cookies_file:
        try:
            from http.cookiejar import MozillaCookieJar
            cj = MozillaCookieJar(cookies_file)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
        except Exception:
            pass

    try:
        resp = session.get(profile_url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # ── 1. Look for secUid directly in JSON payload ──────────────────
        m = re.search(r'"secUid"\s*:\s*"([^"]+)"', html)
        if m:
            return m.group(1)

        # ── 2. Try video links → extract channel_id via yt-dlp ──────────
        vids = re.findall(r'/@[\w.]+/video/(\d+)', html)
        # deduplicate while preserving order
        seen = set()
        unique_vids = []
        for v in vids:
            if v not in seen:
                seen.add(v)
                unique_vids.append(v)

        opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'logger': _NullLogger(),        # suppress ERROR lines on console
        }
        if cookies_file:
            opts['cookiefile'] = cookies_file

        # Try up to 10 videos — some may be age-gated / login-required
        for vid_id in unique_vids[:10]:
            video_url = f'https://www.tiktok.com/@_/video/{vid_id}'
            try:
                # Redirect stderr to suppress any ERROR lines yt-dlp
                # prints directly (bypassing the logger in some cases)
                import io, sys
                old_stderr = sys.stderr
                sys.stderr = io.StringIO()
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        if info:
                            cid = info.get('channel_id') or info.get('uploader_id')
                            if cid:
                                return cid
                finally:
                    sys.stderr = old_stderr
            except Exception:
                continue
    except Exception:
        pass

    return None


def download_tiktok_video(url, output_path='downloads', progress_hook=None):
    """
    Tải video từ TikTok

    Args:
        url: Link video TikTok
        output_path: Thư mục lưu video (mặc định: 'downloads')
        progress_hook: callback yt-dlp progress (optional)
    """
    os.makedirs(output_path, exist_ok=True)
    opts = _build_tt_opts(output_path, progress_hook=progress_hook)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                filename = ydl.prepare_filename(info)
                return filename
    except Exception:
        pass
    return None


def download_from_profile(profile_url, output_path='downloads', max_videos=None,
                          progress_hook=None, log_fn=None):
    """
    Tải tất cả video từ một profile TikTok

    Args:
        profile_url: Link profile TikTok (vd: https://www.tiktok.com/@username)
        output_path: Thư mục lưu video
        max_videos: Số lượng video tối đa tải (None = tất cả)
        progress_hook: callback yt-dlp progress (optional)
        log_fn: optional logging callback (text, tag) – for UI feedback
    """
    def _info(msg):
        if log_fn:
            log_fn(msg, "info")

    def _do_download(url, suppress_stderr=False):
        extra: dict = {
            'outtmpl': os.path.join(output_path, '%(uploader)s', '%(title)s.%(ext)s'),
            'ignoreerrors': True,   # skip unavailable videos in profile
        }
        if max_videos:
            extra['playlistend'] = max_videos
        if suppress_stderr:
            extra['logger'] = _NullLogger()
        opts = _build_tt_opts(output_path, extra=extra, progress_hook=progress_hook)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info is not None

    os.makedirs(output_path, exist_ok=True)

    # ── 1. Normal attempt (suppress stderr to avoid ERROR leaking) ───────
    try:
        import io, sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            return _do_download(profile_url, suppress_stderr=True)
        finally:
            sys.stderr = old_stderr
    except Exception as e:
        err_msg = str(e)
        if 'Unable to extract secondary user ID' not in err_msg:
            # Unrelated error – give up
            return False

    # ── 2. Fallback: resolve channel_id ──────────────────────────────────
    _info("[TikTok] secUid không trích xuất được — đang thử lấy channel_id…")
    channel_id = _resolve_channel_id(profile_url)
    if not channel_id:
        _info("[TikTok] Không tìm được channel_id. Hãy thử dùng link video thay vì profile.")
        return False

    alt_url = f"tiktokuser:{channel_id}"
    _info(f"[TikTok] Dùng channel_id fallback: {alt_url}")

    try:
        return _do_download(alt_url)
    except Exception:
        pass
    return False
