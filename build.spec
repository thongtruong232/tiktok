# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

_datas = collect_data_files('dearpygui')

# Thêm fonts nếu có
if os.path.exists('fonts'):
    _datas.append(('fonts', 'fonts'))

# Thêm icon nếu có
if os.path.exists('icon.ico'):
    _datas.append(('icon.ico', '.'))

# Thêm file cookies nếu muốn bundle kèm
if os.path.exists('youtube_cookies.txt'):
    _datas.append(('youtube_cookies.txt', '.'))
if os.path.exists('tiktok_cookies.txt'):
    _datas.append(('tiktok_cookies.txt', '.'))

# Thêm window_config.json
if os.path.exists('window_config.json'):
    _datas.append(('window_config.json', '.'))

a = Analysis(
    ['tk_gui.py'],
    pathex=['.'],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        *collect_submodules('yt_dlp'),
        *collect_submodules('dearpygui'),
        'tiktok_download',
        'youtube_download',   # ← thêm module này
        'video_edit',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.simpledialog',
        'screeninfo',         # ← dùng trong App.run()
        'PIL',
        'PIL.Image',
        'numpy',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy.testing', 'pytest'],
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
    name='TTTools',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # Không hiện cửa sổ console đen
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll'],  # Không nén DLL hệ thống
    name='TTTools',
)