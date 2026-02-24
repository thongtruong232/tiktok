# TikTok Downloader (Tkinter GUI)

Files added in this workspace:

- [tiktok_download.py](tiktok_download.py) — module with `download_tiktok_video` and `download_from_profile` functions.
- [tk_gui.py](tk_gui.py) — Tkinter GUI wrapper that calls the module functions.
- [requirements.txt](requirements.txt) — dependencies (yt-dlp).

Quick start (Windows):

1. Install dependencies:

````markdown
# TikTok Downloader (Tkinter GUI)

Files added in this workspace:

- [tiktok_download.py](tiktok_download.py) — module with `download_tiktok_video` and `download_from_profile` functions.
- [tk_gui.py](tk_gui.py) — Tkinter GUI wrapper that calls the module functions.
- [requirements.txt](requirements.txt) — dependencies (yt-dlp).

Quick start (Windows):

1. Install dependencies:

```powershell
pip install -r requirements.txt
```

2. Run the GUI:

```powershell
python "tk_gui.py"
```

Notes:

- If your original file is `tiktok-download.py` (contains a hyphen), keep it for reference but the GUI imports `tiktok_download.py` (underscore) which is safe to import as a module.
- `yt-dlp` may require additional system codecs or ffmpeg for post-processing.

Virtual environment (recommended):

1. Create the venv (already created in this project as `.venv`):

```powershell
python -m venv .venv
```

2. Use the venv Python to install requirements and run the app without activating (Windows):

```powershell
.venv\\Scripts\\python -m pip install --upgrade pip
.venv\\Scripts\\python -m pip install -r requirements.txt
.venv\\Scripts\\python tk_gui.py
```

Or activate the venv (PowerShell):

```powershell
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python tk_gui.py
```
````
# tiktok
