import yt_dlp
import os


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
                          progress_hook=None):
    """
    Tải tất cả video từ một profile TikTok

    Args:
        profile_url: Link profile TikTok (vd: https://www.tiktok.com/@username)
        output_path: Thư mục lưu video
        max_videos: Số lượng video tối đa tải (None = tất cả)
        progress_hook: callback yt-dlp progress (optional)
    """
    os.makedirs(output_path, exist_ok=True)

    extra: dict = {
        'outtmpl': os.path.join(output_path, '%(uploader)s', '%(title)s.%(ext)s'),
        'ignoreerrors': True,   # skip unavailable videos in profile
    }
    if max_videos:
        extra['playlistend'] = max_videos

    opts = _build_tt_opts(output_path, extra=extra, progress_hook=progress_hook)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(profile_url, download=True)
            return info is not None
    except Exception:
        pass
    return False
