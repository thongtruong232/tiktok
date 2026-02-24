import yt_dlp
import os


def download_tiktok_video(url, output_path='downloads'):
    """
    Tải video từ TikTok

    Args:
        url: Link video TikTok
        output_path: Thư mục lưu video (mặc định: 'downloads')
    """
    # Tạo thư mục nếu chưa tồn tại
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # Cấu hình yt-dlp
    ydl_opts = {
        'format': 'best',  # Tải chất lượng tốt nhất
        'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),  # Tên file output
        'quiet': False,  # Hiển thị thông tin tải
        'no_warnings': False,
        'ignoreerrors': False,
        'cookiefile': 'cookies.txt',  # Sử dụng cookies để bypass hạn chế
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Đang tải video từ: {url}")
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            print(f"✓ Tải thành công: {filename}")
            return filename
    except Exception as e:
        print(f"✗ Lỗi khi tải video: {str(e)}")
        return None


def download_from_profile(profile_url, output_path='downloads', max_videos=None):
    """
    Tải tất cả video từ một profile TikTok

    Args:
        profile_url: Link profile TikTok (vd: https://www.tiktok.com/@username)
        output_path: Thư mục lưu video
        max_videos: Số lượng video tối đa tải (None = tất cả)
    """
    # Tạo thư mục nếu chưa tồn tại
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # Cấu hình yt-dlp cho playlist
    ydl_opts = {
        'format': 'best',
        'outtmpl': os.path.join(output_path, '%(uploader)s/%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': False,
        'cookiefile': 'cookies.txt',
        'playlistend': max_videos,  # Giới hạn số video
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Đang tải video từ profile: {profile_url}")
            if max_videos:
                print(f"Giới hạn: {max_videos} video")
            info = ydl.extract_info(profile_url, download=True)
            print(f"✓ Hoàn thành tải từ profile: {profile_url}")
            return True
    except Exception as e:
        print(f"✗ Lỗi khi tải từ profile: {str(e)}")
        return False
