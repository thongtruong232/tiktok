# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Chỉ thêm ffmpeg.exe nếu file thực sự tồn tại
_datas = collect_data_files('dearpygui')
if os.path.exists('ffmpeg.exe'):
    _datas.append(('ffmpeg.exe', '.'))

a = Analysis(
    ['tk_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        *collect_submodules('yt_dlp'),
        *collect_submodules('dearpygui'),
        'tiktok_download',
        'video_edit',
        'tkinter',
        'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy.testing'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TikTokDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TikTokDownloader',
)