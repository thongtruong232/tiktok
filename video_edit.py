"""
video_edit.py – Video editing helpers using ffmpeg-python.

All functions accept an optional `output_path`.  If omitted, a sensible
default name is derived from the input file.
"""

import os

import ffmpeg


# ── Internal helper ───────────────────────────────────────────────────────────

def _derive(input_path: str, suffix: str, ext: str | None = None) -> str:
    """Return <base>_<suffix>.<ext> next to the original file."""
    base, orig_ext = os.path.splitext(input_path)
    return f"{base}_{suffix}{ext if ext else orig_ext}"


# ── 1. Resize ─────────────────────────────────────────────────────────────────

PRESETS = {
    '4K  (3840×2160)': (3840, 2160),
    '1080p (1920×1080)': (1920, 1080),
    '720p  (1280×720)':  (1280,  720),
    '480p  (854×480)':   ( 854,  480),
    '360p  (640×360)':   ( 640,  360),
    'Custom':            (None,  None),
}


def resize_video(input_path: str, width: int, height: int,
                 output_path: str | None = None) -> str:
    """Resize to *width*×*height*. Use -1 for either dimension to keep aspect."""
    output_path = output_path or _derive(input_path, f'{width}x{height}')
    (
        ffmpeg
        .input(input_path)
        .filter('scale', width, height)
        .output(output_path)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# ── 4. Audio ──────────────────────────────────────────────────────────────────

def extract_audio(input_path: str, output_format: str = 'mp3',
                  output_path: str | None = None) -> str:
    """Extract the audio stream to a standalone audio file."""
    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f'{base}_audio.{output_format}'
    (
        ffmpeg
        .input(input_path)
        .output(output_path, vn=None)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


def remove_audio(input_path: str, output_path: str | None = None) -> str:
    """Strip the audio track from a video (video-copy, no re-encode)."""
    output_path = output_path or _derive(input_path, 'noaudio')
    (
        ffmpeg
        .input(input_path)
        .output(output_path, an=None, vcodec='copy')
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# ── 5. Format conversion ──────────────────────────────────────────────────────

FORMATS = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'gif']


def convert_format(input_path: str, output_format: str,
                   output_path: str | None = None) -> str:
    """Re-mux / transcode to the given container format."""
    if not output_path:
        base = os.path.splitext(input_path)[0]
        output_path = f'{base}_converted.{output_format}'
    (
        ffmpeg
        .input(input_path)
        .output(output_path)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# ── 6. Speed control ─────────────────────────────────────────────────────────

def speed_video(input_path: str, speed: float,
               output_path: str | None = None) -> str:
    """
    Change playback speed.
    speed > 1  → faster (e.g. 2.0 = 2×).  speed < 1 → slower (e.g. 0.5 = ½×).
    Audio tempo is adjusted to match; supports 0.25×–4.0× range.
    """
    output_path = output_path or _derive(input_path, f'speed{speed}')
    pts = 1.0 / speed          # PTS factor (inverse of speed)
    # atempo filter only accepts 0.5–2.0 per node; chain nodes if needed
    tempo = speed
    atempo_chain = []
    while tempo > 2.0:
        atempo_chain.append('atempo=2.0')
        tempo /= 2.0
    while tempo < 0.5:
        atempo_chain.append('atempo=0.5')
        tempo *= 2.0
    atempo_chain.append(f'atempo={tempo:.4f}')
    audio_filter = ','.join(atempo_chain)

    (
        ffmpeg
        .input(input_path)
        .output(output_path,
                vf=f'setpts={pts:.4f}*PTS',
                af=audio_filter)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# ── 7. Rotate ────────────────────────────────────────────────────────────────

ROTATIONS = {
    '90°  theo chiều kim đồng hồ':         'transpose=1',
    '90°  ngược chiều kim đồng hồ': 'transpose=2',
    '180°':                   'transpose=1,transpose=1',
    'Lật ngang':        'hflip',
    'Lật dọc':          'vflip',
}


def rotate_video(input_path: str, rotation: str,
                output_path: str | None = None) -> str:
    """Apply a rotation/flip using FFmpeg vf filters."""
    output_path = output_path or _derive(input_path, 'rotated')
    vf = ROTATIONS.get(rotation, 'transpose=1')
    (
        ffmpeg
        .input(input_path)
        .output(output_path, vf=vf)
        .overwrite_output()
        .run(quiet=True)
    )
    return output_path


# ── 8. Merge videos ──────────────────────────────────────────────────────────

def merge_videos(input_paths: list[str],
                output_path: str | None = None) -> str:
    """
    Concatenate a list of video files into one using the FFmpeg concat demuxer
    (stream-copy — no re-encoding, very fast).
    A temporary file list is written next to the first input.
    """
    if not input_paths:
        raise ValueError('No input files provided.')
    if not output_path:
        base = os.path.splitext(input_paths[0])[0]
        output_path = f'{base}_merged.mp4'

    list_file = output_path + '.txt'
    try:
        with open(list_file, 'w', encoding='utf-8') as fh:
            for p in input_paths:
                fh.write(f"file '{p}'\n")
        (
            ffmpeg
            .input(list_file, format='concat', safe=0)
            .output(output_path, c='copy')
            .overwrite_output()
            .run(quiet=True)
        )
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)
    return output_path
