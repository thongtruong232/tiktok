import os
import json
import queue
import time
import threading
from datetime import datetime

import numpy as np
from PIL import Image
import dearpygui.dearpygui as dpg

from tiktok_download import download_tiktok_video, download_from_profile, is_tiktok_url
from youtube_download import (download_youtube_video, download_youtube_playlist,
                               download_youtube_multi, download_youtube_channel,
                               QUALITY_OPTIONS, get_youtube_runtime_context,
                               is_youtube_url)
import video_edit

# ── Layout constants ───────────────────────────────────────────────────────────
_SIDEBAR_W = 145
_LOG_W     = 310
_HDR_H     = 68
_MAX_LOG   = 300   # max log lines kept in panel

# ── Navigation items (page_id, label with icon) ───────────────────────────────
_NAV_ITEMS = [
    ("download", "Tải Video"),
    ("library",  "Thư Viện"),
    ("edit",     "Chỉnh Sửa"),
    ("batch",    "Batch Edit"),
]

# ── Color palette  (R, G, B, A  —  0‑255) ─────────────────────────────────────
_CA      = (238,  29,  82, 255)   # accent (TikTok pink-red)
_CA_H    = (200,  24,  70, 255)   # accent hover
_CA_ACT  = (165,  15,  55, 255)   # accent pressed
_CS      = ( 18,  18,  18, 255)   # sidebar / header / log panel bg
_CM      = ( 22,  22,  22, 255)   # main content bg
_CC      = ( 32,  32,  32, 255)   # card bg
_CC2     = ( 40,  40,  40, 255)   # frame / input bg
_CB      = ( 50,  50,  50, 255)   # border
_CF      = (240, 240, 240, 255)   # primary text
_CF2     = (160, 160, 160, 255)   # secondary text
_CF3     = (110, 110, 110, 255)   # hint / placeholder
_CBTN    = ( 48,  48,  48, 255)   # button bg
_CBTN_H  = ( 62,  62,  62, 255)   # button hover
_CL      = ( 14,  14,  14, 255)   # log content bg
_CL_OK   = ( 76, 175,  80, 255)
_CL_ERR  = (239,  83,  80, 255)
_CL_INFO = ( 66, 165, 245, 255)
_CTRANS  = (  0,   0,   0,   0)
_CNAV    = ( 38,  38,  38, 255)   # nav button active bg
_CNAV_H  = ( 30,  30,  30, 255)   # nav button hover (inactive)


class App:
    def __init__(self):
        self._current_page: str | None     = None
        self._pages: dict[str, str]         = {}    # page_id → child_window tag
        self._nav_btns: dict[str, str]      = {}    # page_id → button tag
        self._log_queue: queue.Queue        = queue.Queue()
        self._dlg_queue: queue.Queue        = queue.Queue()
        self._log_items: list[str]          = []
        self._log_counter: int              = 0
        self._activity_id: int              = 0
        self._logo_texture: str | None      = None   # logo texture tag (if loaded)
        # ── Edit / Batch state ────────────────────────────────────────────
        self._current_edit_tab: str         = "Resize"   # tracks selected tab
        self._current_dl_platform: str      = "tiktok"   # tracks active download platform
        self._merge_items: list[str]        = []          # merge listbox items
        self._batch_items: list[str]        = []          # batch listbox items
        # ── Library state ─────────────────────────────────────────────────
        self._lib_root: str                 = os.path.abspath("downloads")
        self._lib_folders: list[str]        = []          # sub-folder names
        self._lib_current_folder: str       = ""          # currently selected folder
        self._lib_files: list[dict]         = []          # cached file info dicts
        self._lib_selected: set[int]        = set()       # indices of selected rows

    # ─────────────────────────────────────────────────────────────────────────
    def _load_window_config(self):
        """Load saved window dimensions from config file."""
        config_file = os.path.join(os.path.dirname(__file__), "window_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_window_config(self):
        """Save current window dimensions to config file."""
        try:
            vw = dpg.get_viewport_width()
            vh = dpg.get_viewport_height()
            config = {"width": vw, "height": vh}
            config_file = os.path.join(os.path.dirname(__file__), "window_config.json")
            with open(config_file, 'w') as f:
                json.dump(config, f)
        except Exception:
            pass  # Silent fail on save error

    def run(self):
        dpg.create_context()
        self._setup_fonts()
        self._setup_themes()
        self._load_logo_texture()

        # ── Check FFmpeg availability ─────────────────────────────────────
        if not video_edit.check_ffmpeg():
            self._log_queue.put((
                "[Cảnh báo] FFmpeg không tìm thấy trên PATH. "
                "Chức năng chỉnh sửa video sẽ không hoạt động.",
                (239, 190, 60, 255),
            ))

        # Load saved window config, or use primary monitor fullscreen
        win_config = self._load_window_config()
        if win_config and "width" in win_config and "height" in win_config:
            screen_w = win_config["width"]
            screen_h = win_config["height"]
        else:
            # Default to primary monitor fullscreen
            try:
                from screeninfo import get_monitors
                monitors = get_monitors()
                primary = monitors[0]  # Primary / main monitor
                screen_w = primary.width
                screen_h = primary.height
            except (ImportError, IndexError):
                # Fallback to Tkinter if screeninfo not available
                import tkinter as _tk_screen
                _screen = _tk_screen.Tk()
                _screen.withdraw()
                screen_w = _screen.winfo_screenwidth()
                screen_h = _screen.winfo_screenheight()
                # If multi-monitor detected (width >> 2560), use only half
                if screen_w > 2560:
                    screen_w = screen_w // 2
                _screen.destroy()
        
        dpg.create_viewport(title="TT Tools",
                            width=screen_w, height=screen_h,
                            min_width=980, min_height=580)
        dpg.setup_dearpygui()
        self._build_ui()
        dpg.set_primary_window("main_win", True)
        dpg.set_viewport_resize_callback(self._on_resize)
        dpg.show_viewport()
        dpg.set_frame_callback(2, self._process_log_queue)   # start log pump
        dpg.start_dearpygui()
        dpg.destroy_context()

    # ── Fonts ──────────────────────────────────────────────────────────────────
    def _setup_fonts(self):
        reg  = "C:/Windows/Fonts/segoeui.ttf"
        bold = "C:/Windows/Fonts/segoeuib.ttf"
        _xr = [                                # extra Unicode ranges
            (0x2000, 0x206F),  # General Punctuation
            (0x2190, 0x21FF),  # Arrows
            (0x2500, 0x257F),  # Box Drawing
            (0x25A0, 0x25FF),  # Geometric Shapes  (▶)
            (0x2600, 0x26FF),  # Misc Symbols
            (0x2700, 0x27BF),  # Dingbats
        ]
        with dpg.font_registry():
            if os.path.exists(reg):
                with dpg.font(reg, 15, tag="f_reg"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)
                    for lo, hi in _xr:
                        dpg.add_font_range(lo, hi)
                dpg.bind_font("f_reg")
            if os.path.exists(bold):
                with dpg.font(bold, 18, tag="f_title"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)
                    for lo, hi in _xr:
                        dpg.add_font_range(lo, hi)
                with dpg.font(bold, 14, tag="f_bold"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)
                    for lo, hi in _xr:
                        dpg.add_font_range(lo, hi)
                with dpg.font(bold, 13, tag="f_nav"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)

    # ── Themes ─────────────────────────────────────────────────────────────────
    def _setup_themes(self):
        # ── global ──────────────────────────────────────────────────────────
        with dpg.theme(tag="th_global"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg,           _CM)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg,            _CC)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg,            _CC2)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered,     _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,      _CB)
                dpg.add_theme_color(dpg.mvThemeCol_Button,             _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,      _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,       _CA_ACT)
                dpg.add_theme_color(dpg.mvThemeCol_Text,               _CF)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,       _CF3)
                dpg.add_theme_color(dpg.mvThemeCol_Border,             _CB)
                dpg.add_theme_color(dpg.mvThemeCol_BorderShadow,       _CTRANS)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,        _CM)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,      _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, _CA)
                dpg.add_theme_color(dpg.mvThemeCol_Header,             _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,      _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,       _CA)
                dpg.add_theme_color(dpg.mvThemeCol_Tab,                _CC2)
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered,         _CA_H)
                dpg.add_theme_color(dpg.mvThemeCol_TabActive,          _CA)
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, _CA_H)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg,            _CS)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,      _CS)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg,            _CC)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark,          _CA)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,         _CA)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive,   _CA_H)
                dpg.add_theme_color(dpg.mvThemeCol_Separator,          _CB)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,     0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,      6)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,      5)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,       3)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding,  4)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding,        5)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,      0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,       10, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,        8, 6)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize,      10)
        dpg.bind_theme("th_global")

        # ── sidebar / log panel bg ───────────────────────────────────────────
        with dpg.theme(tag="th_sidebar"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, _CS)

        # ── main content bg ──────────────────────────────────────────────────
        with dpg.theme(tag="th_main"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, _CM)

        # ── log text area ────────────────────────────────────────────────────
        with dpg.theme(tag="th_log"):
            with dpg.theme_component(dpg.mvChildWindow):
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, _CL)

        # ── accent button (red CTA) ─────────────────────────────────────────
        with dpg.theme(tag="th_accent"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CA_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CA_ACT)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 6)

        # ── nav button: active ───────────────────────────────────────────────
        with dpg.theme(tag="th_nav_on"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CNAV)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CNAV)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CNAV)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          _CF)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,  8, 10)

        # ── nav button: inactive ─────────────────────────────────────────────
        with dpg.theme(tag="th_nav_off"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CTRANS)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CNAV_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CNAV)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          _CF2)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,  8, 10)

        # ── logo box ─────────────────────────────────────────────────────────
        with dpg.theme(tag="th_logo"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CA)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 14)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,  14, 12)

    # ── Load logo texture ──────────────────────────────────────────────────────
    def _load_logo_texture(self):
        """Load logo image and create a DPG static texture."""
        self._logo_texture = None
        base = os.path.dirname(__file__)
        candidates = ["logo.png", "logo.jpg", "logo.jpeg", "logo.bmp", "logo.ico"]
        logo_path = None
        for fn in candidates:
            p = os.path.join(base, fn)
            if os.path.exists(p):
                logo_path = p
                break
        if not logo_path:
            return
        try:
            img = Image.open(logo_path).convert("RGBA")
            img = img.resize((50, 50), Image.Resampling.LANCZOS)
            # Flatten to float list [R,G,B,A, R,G,B,A, ...] in 0.0-1.0 range
            data = (np.array(img).astype(np.float32) / 255.0).flatten().tolist()
            w, h = img.size
            with dpg.texture_registry():
                dpg.add_static_texture(w, h, data, tag="logo_texture")
            self._logo_texture = "logo_texture"
            try:
                self._log(f"Loaded logo: {os.path.basename(logo_path)}", "info")
            except Exception:
                pass
        except Exception as e:
            self._logo_texture = None
            try:
                self._log(f"Logo load failed: {e}", "err")
            except Exception:
                pass

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        vp_w = dpg.get_viewport_width()
        vp_h = dpg.get_viewport_height()
        cw   = vp_w - _SIDEBAR_W - _LOG_W

        with dpg.window(tag="main_win", no_title_bar=True, no_move=True,
                        no_resize=True, no_scrollbar=True,
                        no_scroll_with_mouse=True,
                        width=vp_w, height=vp_h):
            with dpg.group(horizontal=True):
                self._build_sidebar(vp_h)
                self._build_content_host(cw, vp_h)
                self._build_log_panel(vp_h)

        self._switch_page("download")

    # ── Sidebar ────────────────────────────────────────────────────────────────
    def _build_sidebar(self, h: int):
        with dpg.child_window(tag="sidebar", width=_SIDEBAR_W, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("sidebar", "th_sidebar")

            # ── Logo area ────────────────────────────────────────────────────
            dpg.add_spacer(height=18)
            if self._logo_texture:
                dpg.add_image("logo_texture", width=50, height=50, indent=14)
            else:
                logo = dpg.add_button(label="TT", width=60, height=60,
                                      enabled=False, indent=14)
                dpg.bind_item_theme(logo, "th_logo")
                if dpg.does_item_exist("f_title"):
                    dpg.bind_item_font(logo, "f_title")
            dpg.add_spacer(height=6)
            # name_txt = dpg.add_text("Lạc trôi", color=_CF2, indent=28)
            # if dpg.does_item_exist("f_nav"):
            #     dpg.bind_item_font(name_txt, "f_nav")
            # dpg.add_spacer(height=16)
            # dpg.add_separator()
            # dpg.add_spacer(height=16)

            # ── Navigation buttons ───────────────────────────────────────────
            for page_id, label in _NAV_ITEMS:
                btn = dpg.add_button(
                    label=label, tag=f"nav_{page_id}",
                    width=_SIDEBAR_W - 16, height=38,
                    callback=lambda s, a, u: self._switch_page(u),
                    user_data=page_id, indent=8)
                dpg.bind_item_theme(btn, "th_nav_off")
                if dpg.does_item_exist("f_nav"):
                    dpg.bind_item_font(btn, "f_nav")
                self._nav_btns[page_id] = f"nav_{page_id}"
                dpg.add_spacer(height=4)

    def _switch_page(self, page_id: str):
        if page_id == self._current_page:
            return
        for pid, tag in self._pages.items():
            (dpg.show_item if pid == page_id else dpg.hide_item)(tag)
        if self._current_page:
            dpg.bind_item_theme(self._nav_btns[self._current_page], "th_nav_off")
        dpg.bind_item_theme(self._nav_btns[page_id], "th_nav_on")
        self._current_page = page_id

    # ── Content host ───────────────────────────────────────────────────────────
    def _build_content_host(self, w: int, h: int):
        with dpg.child_window(tag="content_host", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("content_host", "th_main")
            self._build_download_page(w, h)
            self._build_library_page(w, h)
            self._build_edit_page(w, h)
            self._build_batch_page(w, h)

    # ── Shared: page header bar ────────────────────────────────────────────────
    def _hdr(self, title: str, subtitle: str):
        with dpg.child_window(height=_HDR_H, border=False, no_scrollbar=True) as c:
            dpg.bind_item_theme(c, "th_sidebar")
            dpg.add_spacer(height=12)
            t = dpg.add_text(title, indent=24)
            if dpg.does_item_exist("f_title"):
                dpg.bind_item_font(t, "f_title")
            dpg.add_spacer(height=4)
            dpg.add_text(subtitle, color=_CF2, indent=24)

    # ── Download page ──────────────────────────────────────────────────────────
    def _build_download_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_dl", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_dl", "th_main")
            self._pages["download"] = "pg_dl"
            self._hdr("TT Tools",
                      "Tải video từ nhiều nền tảng")

            with dpg.child_window(tag="dl_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("dl_scroll", "th_main")
                dpg.add_spacer(height=12)

                # ── Platform tab bar ──────────────────────────────────────────
                with dpg.tab_bar(tag="dl_platform_tabs",
                                 callback=self._on_platform_tab_change):

                    # ── TikTok tab ────────────────────────────────────────────
                    with dpg.tab(label="  TikTok  ", tag="dl_tab_tiktok"):
                        dpg.add_spacer(height=10)
                        t = dpg.add_text("Chọn loại link để tải video", indent=20)
                        if dpg.does_item_exist("f_bold"):
                            dpg.bind_item_font(t, "f_bold")
                        # dpg.add_text("Hỗ trợ:  Single Video  |  Profile  |  Nhiều URLs",
                        #              color=_CF2, indent=20)
                        dpg.add_spacer(height=10)

                        dpg.add_radio_button(
                            tag="dl_mode",
                            items=["Single Video", "Profile", "Nhiều URLs"],
                            default_value="Single Video", horizontal=True, indent=20,
                            callback=self._on_dl_mode_change)
                        dpg.add_spacer(height=12)

                        with dpg.child_window(tag="dl_card_single", height=90,
                                              border=True, indent=16):
                            dpg.add_text("VIDEO URL", color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            with dpg.group(horizontal=True):
                                dpg.add_input_text(tag="url_single", width=-80,
                                                   hint="https://www.tiktok.com/@user/video/...")
                                dpg.add_button(label="Dán", width=70,
                                               callback=self._paste_single)

                        with dpg.child_window(tag="dl_card_profile", height=120,
                                              border=True, indent=16):
                            dpg.add_text("PROFILE URL", color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            dpg.add_input_text(tag="url_profile", width=-8,
                                               hint="https://www.tiktok.com/@username")
                            dpg.add_spacer(height=8)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Số video tối đa:", color=_CF2, indent=16)
                                dpg.add_spacer(width=8)
                                dpg.add_input_text(tag="max_videos", width=160,
                                                   hint="để trống = tất cả")
                        dpg.hide_item("dl_card_profile")

                        with dpg.child_window(tag="dl_card_multi", height=200,
                                              border=True, indent=16):
                            dpg.add_text("DANH SÁCH URL  (mỗi dòng 1 link)",
                                         color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            dpg.add_input_text(tag="multi_text", multiline=True,
                                               width=-8, height=148)
                        dpg.hide_item("dl_card_multi")
                        dpg.add_spacer(height=8)

                    # ── YouTube tab ───────────────────────────────────────────
                    with dpg.tab(label="  YouTube  ", tag="dl_tab_youtube"):
                        dpg.add_spacer(height=10)
                        t = dpg.add_text("Tải video từ YouTube", indent=20)
                        if dpg.does_item_exist("f_bold"):
                            dpg.bind_item_font(t, "f_bold")
                        # dpg.add_text("Hỗ trợ:  Video đơn  |  Playlist  |  Nhiều URLs",
                        #              color=_CF2, indent=20)
                        dpg.add_spacer(height=10)

                        dpg.add_radio_button(
                            tag="yt_mode",
                            items=["Video đơn", "Playlist", "Nhiều URLs", "Kênh"],
                            default_value="Video đơn", horizontal=True, indent=20,
                            callback=self._on_yt_mode_change)
                        dpg.add_spacer(height=12)

                        with dpg.child_window(tag="yt_card_single", height=90,
                                              border=True, indent=16):
                            dpg.add_text("VIDEO URL", color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            with dpg.group(horizontal=True):
                                dpg.add_input_text(
                                    tag="yt_url_single", width=-80,
                                    hint="https://www.youtube.com/watch?v=...")
                                dpg.add_button(
                                    label="Dán", width=70,
                                    callback=lambda: self._paste_to("yt_url_single"))

                        with dpg.child_window(tag="yt_card_playlist", height=120,
                                              border=True, indent=16):
                            dpg.add_text("PLAYLIST / CHANNEL URL", color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            dpg.add_input_text(
                                tag="yt_playlist_url", width=-8,
                                hint="https://www.youtube.com/playlist?list=...")
                            dpg.add_spacer(height=8)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Số video tối đa:", color=_CF2, indent=16)
                                dpg.add_spacer(width=8)
                                dpg.add_input_text(tag="yt_max_items", width=160,
                                                   hint="để trống = tất cả")
                        dpg.hide_item("yt_card_playlist")

                        with dpg.child_window(tag="yt_card_multi", height=200,
                                              border=True, indent=16):
                            dpg.add_text("DANH SÁCH URL  (mỗi dòng 1 link)",
                                         color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            dpg.add_input_text(tag="yt_multi_text", multiline=True,
                                               width=-8, height=148)
                        dpg.hide_item("yt_card_multi")

                        with dpg.child_window(tag="yt_card_channel", height=150,
                                              border=True, indent=16):
                            dpg.add_text("CHANNEL URL", color=_CF2, indent=16)
                            dpg.add_spacer(height=6)
                            with dpg.group(horizontal=True):
                                dpg.add_input_text(
                                    tag="yt_channel_url", width=-80,
                                    hint="https://www.youtube.com/@handle")
                                dpg.add_button(
                                    label="Dán", width=70,
                                    callback=lambda: self._paste_to("yt_channel_url"))
                            dpg.add_spacer(height=10)
                            with dpg.group(horizontal=True):
                                dpg.add_text("Số video tối đa:", color=_CF2, indent=16)
                                dpg.add_spacer(width=8)
                                dpg.add_input_text(tag="yt_ch_max", width=160,
                                                   hint="để trống = tất cả")
                            dpg.add_spacer(height=8)
                            dpg.add_checkbox(tag="yt_ch_subfolder",
                                             label="Lưu vào thư mục riêng theo tên kênh",
                                             default_value=True, indent=16)
                        dpg.hide_item("yt_card_channel")

                        dpg.add_spacer(height=10)
                        with dpg.child_window(height=52, border=True, indent=16):
                            with dpg.group(horizontal=True):
                                dpg.add_text("CHẤT LƯỢNG:", color=_CF2, indent=16)
                                dpg.add_spacer(width=8)
                                dpg.add_combo(
                                    tag="yt_quality",
                                    items=QUALITY_OPTIONS,
                                    default_value="best",
                                    width=160)

                        dpg.add_spacer(height=8)

                dpg.add_spacer(height=14)

                # ── Shared: Output folder ─────────────────────────────────────
                with dpg.child_window(height=82, border=True, indent=16):
                    dpg.add_text("THƯ MỤC LƯU VIDEO", color=_CF2, indent=16)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="dl_out", default_value="downloads",
                                           width=-230)
                        dpg.add_button(label="Duyệt...", width=84,
                                       callback=lambda: self._browse_dir("dl_out"))
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="Mở thư mục", width=90,
                                       callback=self._open_output)

                dpg.add_spacer(height=14)
                dl_btn = dpg.add_button(label="Bắt đầu tải", tag="dl_btn",
                                        width=-16, height=44, indent=16,
                                        callback=self.start_download)
                dpg.bind_item_theme(dl_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(dl_btn, "f_bold")
                dpg.add_spacer(height=8)
                dpg.add_progress_bar(tag="dl_prog", width=-16, height=5,
                                     indent=16, default_value=0.0)

    def _on_dl_mode_change(self, sender, app_data):
        for card in ["dl_card_single", "dl_card_profile", "dl_card_multi"]:
            dpg.hide_item(card)
        if app_data == "Single Video":
            dpg.show_item("dl_card_single")
        elif app_data == "Profile":
            dpg.show_item("dl_card_profile")
        else:
            dpg.show_item("dl_card_multi")

    def _on_yt_mode_change(self, sender, app_data):
        for card in ["yt_card_single", "yt_card_playlist", "yt_card_multi", "yt_card_channel"]:
            dpg.hide_item(card)
        if app_data == "Video đơn":
            dpg.show_item("yt_card_single")
        elif app_data == "Playlist":
            dpg.show_item("yt_card_playlist")
        elif app_data == "Nhiều URLs":
            dpg.show_item("yt_card_multi")
        else:  # Kênh
            dpg.show_item("yt_card_channel")

    def _on_platform_tab_change(self, sender, app_data):
        """Track the currently-selected download platform tab."""
        try:
            label = dpg.get_item_label(app_data)
        except Exception:
            label = ""
        if "YouTube" in label:
            self._current_dl_platform = "youtube"
        else:
            self._current_dl_platform = "tiktok"

    def _on_tab_change(self, sender, app_data):
        """Track currently-selected edit tab by its string tag."""
        # app_data is the UUID of the newly-selected tab
        label = ""
        try:
            label = dpg.get_item_label(app_data)
        except Exception:
            pass
        if label:
            self._current_edit_tab = label

    def _paste_single(self):
        """Paste clipboard text into the URL field."""
        self._paste_to("url_single")

    def _paste_to(self, tag: str):
        """Paste clipboard text into the field identified by `tag`."""
        try:
            import subprocess
            result = subprocess.run(
                ['powershell', '-command', 'Get-Clipboard'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            text = result.stdout.strip()
            if text:
                dpg.set_value(tag, text)
        except Exception:
            pass

    # ── Library page ───────────────────────────────────────────────────────────
    def _build_library_page(self, w: int, h: int):
        _FOLDER_PNL_W = 260   # left folder panel width

        with dpg.child_window(tag="pg_lib", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_lib", "th_main")
            dpg.hide_item("pg_lib")
            self._pages["library"] = "pg_lib"
            self._hdr("Thư Viện",
                      "Quản lý video đã tải về")

            with dpg.child_window(tag="lib_scroll", width=w, height=h - _HDR_H,
                                  border=False, no_scrollbar=True):
                dpg.bind_item_theme("lib_scroll", "th_main")
                dpg.add_spacer(height=8)

                # ── Top bar: path display + edit ──────────────────────────────
                with dpg.child_window(height=50, border=True, indent=12):
                    with dpg.group(horizontal=True):
                        dpg.add_text("ĐƯỜNG DẪN LƯU TRÊN MÁY TÍNH",
                                     color=_CF2, indent=8)
                        dpg.add_spacer(width=12)
                        dpg.add_input_text(tag="lib_root_input",
                                           default_value=self._lib_root,
                                           width=400, on_enter=True,
                                           callback=self._lib_set_root)
                        dpg.add_spacer(width=6)
                        dpg.add_button(label="Duyệt...", width=80,
                                       callback=self._lib_browse_root)
                        dpg.add_spacer(width=6)
                        dpg.add_button(label="Mở", width=50,
                                       callback=self._lib_open_root)

                dpg.add_spacer(height=8)

                # ── Main body: folder panel (left) + file table (right) ───────
                with dpg.group(horizontal=True):

                    # ── Left: Folder panel ────────────────────────────────────
                    with dpg.child_window(tag="lib_folder_panel",
                                          width=_FOLDER_PNL_W, height=-4,
                                          border=True):
                        dpg.add_spacer(height=6)
                        with dpg.group(horizontal=True, indent=8):
                            t = dpg.add_text("THƯ MỤC")
                            if dpg.does_item_exist("f_bold"):
                                dpg.bind_item_font(t, "f_bold")
                            dpg.add_spacer(width=40)
                            btn_new = dpg.add_button(
                                label="+ Thêm mới", width=110,
                                callback=self._lib_add_folder)
                            dpg.bind_item_theme(btn_new, "th_accent")
                        dpg.add_spacer(height=8)
                        dpg.add_separator()
                        dpg.add_spacer(height=6)

                        # Folder listbox (selectable list)
                        dpg.add_child_window(tag="lib_folder_list",
                                             height=-4, border=False)

                    # ── Right: File table ─────────────────────────────────────
                    with dpg.child_window(tag="lib_file_panel", height=-4,
                                          border=True):
                        dpg.add_spacer(height=6)

                        # Toolbar
                        with dpg.group(horizontal=True, indent=8):
                            dpg.add_text("", tag="lib_file_count", color=_CF2)
                            dpg.add_spacer(width=20)

                            # Spacer to push buttons right
                            dpg.add_spacer(width=200)

                            btn_del = dpg.add_button(
                                label="Xóa video", tag="lib_del_btn",
                                width=100,
                                callback=self._lib_delete_selected)
                            dpg.bind_item_theme(btn_del, "th_accent")
                            dpg.add_spacer(width=8)
                            btn_upl = dpg.add_button(
                                label="Upload", tag="lib_upload_btn",
                                width=90,
                                callback=self._lib_upload_files)

                        dpg.add_spacer(height=6)
                        dpg.add_separator()
                        dpg.add_spacer(height=4)

                        # File table
                        with dpg.table(tag="lib_file_table",
                                       header_row=True,
                                       borders_innerH=True,
                                       borders_outerH=True,
                                       borders_innerV=False,
                                       borders_outerV=False,
                                       resizable=True,
                                       scrollY=True,
                                       height=-4):
                            dpg.add_table_column(label="",       width_fixed=True,
                                                 init_width_or_weight=30)
                            dpg.add_table_column(label="Loại",   width_fixed=True,
                                                 init_width_or_weight=70)
                            dpg.add_table_column(label="Tên file")
                            dpg.add_table_column(label="Kích thước",
                                                 width_fixed=True,
                                                 init_width_or_weight=90)
                            dpg.add_table_column(label="Ngày tạo",
                                                 width_fixed=True,
                                                 init_width_or_weight=155)

        # Populate on first show
        self._lib_refresh_folders()

    # ── Library logic ──────────────────────────────────────────────────────────
    def _lib_set_root(self, sender=None, app_data=None):
        """Set library root from text input or external call."""
        new_root = dpg.get_value("lib_root_input").strip()
        if new_root and os.path.isdir(new_root):
            self._lib_root = os.path.abspath(new_root)
            dpg.set_value("lib_root_input", self._lib_root)
            self._lib_refresh_folders()
        else:
            self._log("Đường dẫn không hợp lệ hoặc không tồn tại.", "err")

    def _lib_browse_root(self):
        """Open a folder dialog to pick the library root."""
        def _worker():
            import tkinter as tk
            from tkinter import filedialog as fd
            root = tk.Tk()
            root.withdraw()
            try:
                d = fd.askdirectory(parent=root, initialdir=self._lib_root)
                if d:
                    self._dlg_queue.put(("lib_root_set", d))
            finally:
                root.destroy()
        threading.Thread(target=_worker, daemon=True).start()

    def _lib_open_root(self):
        if os.path.isdir(self._lib_root):
            try:
                os.startfile(self._lib_root)
            except Exception:
                pass

    def _lib_refresh_folders(self):
        """Scan _lib_root for sub-folders and rebuild the folder list panel."""
        os.makedirs(self._lib_root, exist_ok=True)
        self._lib_folders.clear()
        try:
            for entry in sorted(os.scandir(self._lib_root), key=lambda e: e.name.lower()):
                if entry.is_dir():
                    self._lib_folders.append(entry.name)
        except Exception:
            pass

        # Also add the root itself as a virtual item
        # Rebuild the UI list
        if dpg.does_item_exist("lib_folder_list"):
            children = dpg.get_item_children("lib_folder_list", slot=1)
            if children:
                for c in children:
                    dpg.delete_item(c)

            with dpg.item_handler_registry() as _:
                pass  # placeholder; we add buttons below

            parent = "lib_folder_list"
            # Root folder button (always first)
            self._lib_add_folder_btn(parent, ".", self._lib_root, is_root=True)
            for fname in self._lib_folders:
                fpath = os.path.join(self._lib_root, fname)
                self._lib_add_folder_btn(parent, fname, fpath)

        # Auto-select root
        self._lib_select_folder(".")

    def _lib_add_folder_btn(self, parent, name, path, is_root=False):
        """Create a selectable folder button inside the folder panel."""
        # Count files
        vcount = acount = icount = 0
        try:
            for f in os.scandir(path):
                if not f.is_file():
                    continue
                ext = os.path.splitext(f.name)[1].lower()
                if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"):
                    vcount += 1
                elif ext in (".mp3", ".aac", ".wav", ".ogg", ".m4a", ".flac"):
                    acount += 1
                elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"):
                    icount += 1
        except Exception:
            pass

        display_name = os.path.basename(path) if not is_root else os.path.basename(self._lib_root)
        label = f"{display_name}"
        sub = f"  {vcount} video  ·  {icount} ảnh  ·  {acount} audio"

        with dpg.group(parent=parent):
            btn = dpg.add_button(
                label=label, width=-4, height=30,
                callback=lambda s, a, u: self._lib_select_folder(u),
                user_data=name)
            if dpg.does_item_exist("f_bold"):
                dpg.bind_item_font(btn, "f_bold")
            dpg.add_text(sub, color=_CF3, indent=8)
            dpg.add_spacer(height=4)

    def _lib_select_folder(self, folder_name: str):
        """Select a folder and refresh the file table."""
        self._lib_current_folder = folder_name
        if folder_name == ".":
            scan_path = self._lib_root
        else:
            scan_path = os.path.join(self._lib_root, folder_name)

        self._lib_files.clear()
        self._lib_selected.clear()

        if os.path.isdir(scan_path):
            try:
                for entry in sorted(os.scandir(scan_path), key=lambda e: e.name.lower()):
                    if not entry.is_file():
                        continue
                    stat = entry.stat()
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"):
                        ftype = "VIDEO"
                    elif ext in (".mp3", ".aac", ".wav", ".ogg", ".m4a", ".flac"):
                        ftype = "AUDIO"
                    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"):
                        ftype = "IMAGE"
                    else:
                        ftype = "FILE"
                    self._lib_files.append({
                        "name": entry.name,
                        "path": entry.path,
                        "type": ftype,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
            except Exception:
                pass

        self._lib_rebuild_table()

    def _lib_rebuild_table(self):
        """Rebuild the file table rows from _lib_files."""
        # Clear existing rows
        if dpg.does_item_exist("lib_file_table"):
            children = dpg.get_item_children("lib_file_table", slot=1)
            if children:
                for c in children:
                    dpg.delete_item(c)

        folder_label = os.path.basename(self._lib_root) if self._lib_current_folder == "." \
            else self._lib_current_folder
        dpg.set_value("lib_file_count",
                      f"{len(self._lib_files)} file của  {folder_label}")

        _TYPE_COLORS = {
            "VIDEO": (238, 29, 82, 255),
            "AUDIO": (66, 165, 245, 255),
            "IMAGE": (76, 175, 80, 255),
            "FILE":  _CF2,
        }

        for idx, finfo in enumerate(self._lib_files):
            with dpg.table_row(parent="lib_file_table"):
                # Checkbox
                cb = dpg.add_checkbox(
                    callback=lambda s, a, u: self._lib_toggle_select(u, a),
                    user_data=idx)

                # Type badge
                dpg.add_text(finfo["type"],
                             color=_TYPE_COLORS.get(finfo["type"], _CF2))

                # Filename
                dpg.add_text(finfo["name"])

                # Size
                dpg.add_text(self._format_size(finfo["size"]), color=_CF2)

                # Date
                ts = datetime.fromtimestamp(finfo["mtime"]).strftime("%H:%M:%S %d/%m/%Y")
                dpg.add_text(ts, color=_CF2)

    def _lib_toggle_select(self, idx: int, checked: bool):
        if checked:
            self._lib_selected.add(idx)
        else:
            self._lib_selected.discard(idx)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024*1024):.2f} MB"
        else:
            return f"{size_bytes / (1024**3):.2f} GB"

    def _lib_add_folder(self):
        """Prompt user to create a new folder inside the library root."""
        def _worker():
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            try:
                name = simpledialog.askstring(
                    "Thêm thư mục", "Tên thư mục mới:",
                    parent=root)
                if name and name.strip():
                    self._dlg_queue.put(("lib_new_folder", name.strip()))
            finally:
                root.destroy()
        threading.Thread(target=_worker, daemon=True).start()

    def _lib_delete_selected(self):
        """Delete the selected files from disk and refresh."""
        if not self._lib_selected:
            self._log("Chưa chọn file nào để xóa.", "err")
            return
        count = len(self._lib_selected)
        self._log(f"Đang xóa {count} file...", "info")
        deleted = 0
        for idx in sorted(self._lib_selected, reverse=True):
            if 0 <= idx < len(self._lib_files):
                fpath = self._lib_files[idx]["path"]
                try:
                    os.remove(fpath)
                    deleted += 1
                except Exception as e:
                    self._log(f"Không thể xóa {os.path.basename(fpath)}: {e}", "err")
        self._log(f"Đã xóa {deleted} file.", "ok")
        # Refresh
        self._lib_select_folder(self._lib_current_folder)
        self._lib_refresh_folders()

    def _lib_upload_files(self):
        """Copy video files into the current library folder via file dialog."""
        def _worker():
            import tkinter as tk
            from tkinter import filedialog as fd
            root = tk.Tk()
            root.withdraw()
            try:
                files = fd.askopenfilenames(
                    parent=root,
                    filetypes=[
                        ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                        ("Audio files", "*.mp3 *.aac *.wav *.ogg *.m4a"),
                        ("All files", "*.*"),
                    ])
                if files:
                    self._dlg_queue.put(("lib_upload", list(files)))
            finally:
                root.destroy()
        threading.Thread(target=_worker, daemon=True).start()

    def _lib_process_upload(self, files: list[str]):
        """Copy files into the current library folder."""
        import shutil
        if self._lib_current_folder == ".":
            dest = self._lib_root
        else:
            dest = os.path.join(self._lib_root, self._lib_current_folder)
        os.makedirs(dest, exist_ok=True)
        copied = 0
        for src in files:
            try:
                shutil.copy2(src, dest)
                copied += 1
            except Exception as e:
                self._log(f"Lỗi copy {os.path.basename(src)}: {e}", "err")
        self._log(f"Đã thêm {copied} file vào {os.path.basename(dest)}.", "ok")
        self._lib_select_folder(self._lib_current_folder)
        self._lib_refresh_folders()

    # ── Edit page ──────────────────────────────────────────────────────────────
    def _build_edit_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_edit", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_edit", "th_main")
            dpg.hide_item("pg_edit")
            self._pages["edit"] = "pg_edit"
            self._hdr("Chỉnh Sửa Video",
                      "Chỉnh sửa video đơn lẻ với các thao tác FFmpeg")

            with dpg.child_window(tag="edit_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("edit_scroll", "th_main")
                dpg.add_spacer(height=10)

                # Input file
                with dpg.child_window(height=80, border=True, indent=16):
                    dpg.add_text("FILE ĐẦU VÀO", color=_CF2, indent=16)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="edit_in", width=-120,
                                           hint="Chọn file video...")
                        dpg.add_button(label="Duyệt...", width=110,
                                       callback=self._browse_edit_in)
                dpg.add_spacer(height=10)

                # Op tabs
                with dpg.tab_bar(tag="op_tabs", indent=16,
                                 callback=self._on_tab_change):
                    with dpg.tab(label="Resize",  tag="tab_resize"):
                        self._tab_resize()
                    with dpg.tab(label="Trim",    tag="tab_trim"):
                        self._tab_trim()
                    with dpg.tab(label="Crop",    tag="tab_crop"):
                        self._tab_crop()
                    with dpg.tab(label="Audio",   tag="tab_audio"):
                        self._tab_audio()
                    with dpg.tab(label="Convert", tag="tab_convert"):
                        self._tab_convert()
                    with dpg.tab(label="Speed",   tag="tab_speed"):
                        self._tab_speed()
                    with dpg.tab(label="Rotate",  tag="tab_rotate"):
                        self._tab_rotate()
                    with dpg.tab(label="Merge",   tag="tab_merge"):
                        self._tab_merge()
                    with dpg.tab(label="Logo",    tag="tab_logo"):
                        self._tab_logo()

                dpg.add_spacer(height=10)

                # Output file
                with dpg.child_window(height=80, border=True, indent=16):
                    dpg.add_text("FILE ĐẦU RA  (để trống = tự động đặt tên)",
                                 color=_CF2, indent=16)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="edit_out", width=-120,
                                           hint="Lưu tại...")
                        dpg.add_button(label="Lưu...", width=110,
                                       callback=self._browse_edit_out)

                dpg.add_spacer(height=14)
                edit_btn = dpg.add_button(label="Áp dụng chỉnh sửa",
                                          tag="edit_btn",
                                          width=-16, height=44, indent=16,
                                          callback=self._apply_edit)
                dpg.bind_item_theme(edit_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(edit_btn, "f_bold")
                dpg.add_spacer(height=8)
                dpg.add_progress_bar(tag="edit_prog", width=-16, height=5,
                                     indent=16, default_value=0.0)

    def _tab_resize(self):
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Preset:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="res_preset", items=list(video_edit.PRESETS.keys()),
                          default_value="720p  (1280×720)", width=220,
                          callback=self._on_preset_change)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Width:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="res_w", default_value="1280", width=100)
            dpg.add_spacer(width=16)
            dpg.add_text("Height:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="res_h", default_value="720", width=100)
        dpg.add_spacer(height=6)
        dpg.add_text("Dùng -1 cho một chiều để giữ tỉ lệ khung hình.",
                     color=_CF3, indent=20)

    def _tab_trim(self):
        dpg.add_spacer(height=10)
        dpg.add_text("Cắt video theo thời gian (stream-copy, không re-encode):",
                     color=_CF2, indent=20)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Bắt đầu:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="trim_start", default_value="00:00:00",
                               width=120, hint="HH:MM:SS")
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Kết thúc:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="trim_end", default_value="00:01:00",
                               width=120, hint="HH:MM:SS")
        dpg.add_spacer(height=6)
        dpg.add_text("Định dạng: HH:MM:SS hoặc số giây (vd: 90 = 1:30).",
                     color=_CF3, indent=20)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_button(label="Lấy thời lượng", width=130,
                           callback=self._get_video_duration)
            dpg.add_spacer(width=8)
            dpg.add_text("", tag="trim_duration_txt", color=_CF2)

    def _tab_crop(self):
        dpg.add_spacer(height=10)
        dpg.add_text("Cắt khung hình (crop):", color=_CF2, indent=20)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Width:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="crop_w", default_value="1280", width=100)
            dpg.add_spacer(width=16)
            dpg.add_text("Height:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="crop_h", default_value="720", width=100)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("X:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="crop_x", default_value="0", width=100)
            dpg.add_spacer(width=16)
            dpg.add_text("Y:", color=_CF2)
            dpg.add_spacer(width=4)
            dpg.add_input_text(tag="crop_y", default_value="0", width=100)
        dpg.add_spacer(height=6)
        dpg.add_text("Nhanh chọn:", color=_CF2, indent=20)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True, indent=20):
            for lbl, vals in [("16:9", ("1280", "720")),
                               ("9:16", ("720", "1280")),
                               ("1:1", ("720", "720")),
                               ("4:3", ("960", "720"))]:
                dpg.add_button(label=lbl, width=56,
                               callback=lambda s, a, u: self._set_crop_preset(u),
                               user_data=vals)
                dpg.add_spacer(width=4)
        dpg.add_spacer(height=6)
        dpg.add_text("X, Y = tọa độ góc trên-trái vùng cắt. Dùng 0,0 để cắt từ góc.",
                     color=_CF3, indent=20)

    def _set_crop_preset(self, vals):
        dpg.set_value("crop_w", vals[0])
        dpg.set_value("crop_h", vals[1])

    def _get_video_duration(self):
        """Show the duration of the selected input video."""
        inp = dpg.get_value("edit_in").strip()
        if not inp or not os.path.isfile(inp):
            self._log("Chọn file video trước để lấy thời lượng.", "err")
            return
        dur = video_edit.get_duration(inp)
        if dur > 0:
            mins, secs = divmod(int(dur), 60)
            hrs, mins = divmod(mins, 60)
            txt = f"{hrs:02d}:{mins:02d}:{secs:02d} ({dur:.1f}s)"
            dpg.set_value("trim_duration_txt", txt)
            dpg.set_value("trim_end", f"{hrs:02d}:{mins:02d}:{secs:02d}")
            self._log(f"Thời lượng: {txt}", "info")
        else:
            dpg.set_value("trim_duration_txt", "Không đọc được")
            self._log("Không đọc được thời lượng video.", "err")

    def _tab_audio(self):
        dpg.add_spacer(height=10)
        dpg.add_radio_button(tag="audio_mode",
                             items=["Extract audio  (lấy âm thanh ra file riêng)",
                                    "Remove audio   (tắt tiếng video)"],
                             default_value="Extract audio  (lấy âm thanh ra file riêng)",
                             indent=20)
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Format:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="audio_fmt",
                          items=["mp3", "aac", "wav", "ogg", "m4a"],
                          default_value="mp3", width=120)
        dpg.add_text("(áp dụng khi extract audio)", color=_CF3, indent=20)

    def _tab_convert(self):
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Output format:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="conv_fmt", items=video_edit.FORMATS,
                          default_value="mp4", width=120)
        dpg.add_spacer(height=6)
        dpg.add_text("FFmpeg tự chọn codec phù hợp cho container.",
                     color=_CF3, indent=20)

    def _tab_speed(self):
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Tốc độ:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="spd_val", default_value="2.00", width=100)
        dpg.add_spacer(height=10)
        dpg.add_text("Nhanh chọn:", color=_CF2, indent=20)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=20):
            for lbl, val in [("0.5x", "0.50"), ("0.75x", "0.75"), ("1x", "1.00"),
                              ("1.5x", "1.50"), ("2x", "2.00"), ("4x", "4.00")]:
                dpg.add_button(label=lbl, width=56,
                               callback=lambda s, a, u: dpg.set_value("spd_val", u),
                               user_data=val)
                dpg.add_spacer(width=4)
        dpg.add_spacer(height=6)
        dpg.add_text("< 1.0 = chậm  |  > 1.0 = nhanh  |  phạm vi 0.25 – 4.0",
                     color=_CF3, indent=20)

    def _tab_rotate(self):
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Rotation / Flip:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="rot_choice",
                          items=list(video_edit.ROTATIONS.keys()),
                          default_value=list(video_edit.ROTATIONS.keys())[0],
                          width=280)
        dpg.add_spacer(height=6)
        dpg.add_text("Áp dụng bộ lọc vf của FFmpeg — video được re-encode.",
                     color=_CF3, indent=20)

    def _tab_merge(self):
        dpg.add_spacer(height=10)
        dpg.add_text("Danh sách file video:", color=_CF2, indent=20)
        dpg.add_spacer(height=6)
        dpg.add_listbox(tag="merge_list", items=[], width=-20,
                        num_items=5, indent=16)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            for lbl, cb in [("Thêm...",  self._merge_add),
                             ("Xóa",     self._merge_remove),
                             ("Lên",     lambda: self._merge_move(-1)),
                             ("Xuống",   lambda: self._merge_move(1)),
                             ("Xóa hết", self._merge_clear)]:
                dpg.add_button(label=lbl, width=72, callback=cb)
                dpg.add_spacer(width=4)
        dpg.add_spacer(height=6)
        dpg.add_text("Stream-copy — cực nhanh, không mất chất lượng.",
                     color=_CF3, indent=20)

    def _tab_logo(self):
        dpg.add_spacer(height=10)
        dpg.add_text("File logo (PNG/JPG):", color=_CF2, indent=20)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_input_text(tag="logo_path", width=-120,
                               hint="Chọn file logo...")
            dpg.add_button(label="Duyệt...", width=110,
                           callback=self._browse_logo)
        dpg.add_spacer(height=10)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Vị trí:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="logo_pos",
                          items=list(video_edit.LOGO_POSITIONS.keys()),
                          default_value="Bottom-Right", width=180,
                          callback=self._on_logo_pos_change)
        with dpg.group(tag="logo_custom", horizontal=False, indent=20):
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_text("X:", color=_CF2)
                dpg.add_input_text(tag="logo_x", default_value="W-w-10", width=110)
                dpg.add_spacer(width=12)
                dpg.add_text("Y:", color=_CF2)
                dpg.add_input_text(tag="logo_y", default_value="H-h-20", width=110)
        dpg.hide_item("logo_custom")
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Scale (px):", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="logo_scale", default_value="150", width=100)
        with dpg.group(horizontal=True, indent=20):
            dpg.add_text("Opacity:   ", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="logo_opacity", default_value="1.00", width=100)
        dpg.add_spacer(height=6)
        dpg.add_text("Dùng PNG có nền trong suốt để logo đẹp nhất.",
                     color=_CF3, indent=20)

    # ── Batch page ─────────────────────────────────────────────────────────────
    def _build_batch_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_batch", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_batch", "th_main")
            dpg.hide_item("pg_batch")
            self._pages["batch"] = "pg_batch"
            self._hdr("Batch Edit",
                      "Áp dụng cùng thao tác cho nhiều video cùng lúc")

            with dpg.child_window(tag="batch_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("batch_scroll", "th_main")
                dpg.add_spacer(height=10)

                # File list
                dpg.add_text("DANH SÁCH FILE ĐẦU VÀO", color=_CF2, indent=16)
                dpg.add_spacer(height=6)
                dpg.add_input_text(tag="batch_list_display", multiline=True,
                                   width=-16, height=120, readonly=True,
                                   indent=16, hint="Chưa có file nào")
                dpg.add_spacer(height=6)
                with dpg.group(horizontal=True, indent=16):
                    dpg.add_button(label="Thêm...", width=84,
                                   callback=self._batch_add_files)
                    dpg.add_spacer(width=4)
                    dpg.add_combo(tag="batch_file_select", items=[], width=180,
                                  default_value="")
                    dpg.add_spacer(width=4)
                    dpg.add_button(label="Xóa", width=60,
                                   callback=self._batch_remove_file)
                    dpg.add_spacer(width=4)
                    dpg.add_button(label="Xóa hết", width=84,
                                   callback=self._batch_clear)

                dpg.add_spacer(height=10)

                # Output dir
                with dpg.child_window(height=80, border=True, indent=16):
                    dpg.add_text("THƯ MỤC ĐẦU RA  (để trống = cùng thư mục gốc)",
                                 color=_CF2, indent=16)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="batch_out", width=-120,
                                           hint="Chọn thư mục...")
                        dpg.add_button(label="Duyệt...", width=110,
                                       callback=lambda: self._browse_dir(
                                           "batch_out"))

                dpg.add_spacer(height=10)

                # Operation selector
                _BOPS = ["Resize", "Trim", "Crop", "Extract Audio",
                         "Remove Audio", "Convert", "Speed", "Rotate", "Logo"]
                with dpg.child_window(height=200, border=True, indent=16):
                    dpg.add_text("THAO TÁC ÁP DỤNG CHO TẤT CẢ FILE", color=_CF2, indent=16)
                    dpg.add_spacer(height=8)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Chọn thao tác:", color=_CF2, indent=16)
                        dpg.add_spacer(width=8)
                        dpg.add_combo(tag="batch_op", items=_BOPS,
                                      default_value="Resize", width=200,
                                      callback=self._on_batch_op_change)
                    dpg.add_spacer(height=10)

                    # Resize sub-panel
                    with dpg.group(tag="bop_resize"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Preset:", color=_CF2, indent=16)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_res_preset",
                                          items=list(video_edit.PRESETS.keys()),
                                          default_value="720p  (1280×720)",
                                          width=220,
                                          callback=self._on_b_preset_change)
                        dpg.add_spacer(height=6)
                        with dpg.group(horizontal=True):
                            dpg.add_text("W:", color=_CF2, indent=16)
                            dpg.add_input_text(tag="b_res_w",
                                               default_value="1280", width=100)
                            dpg.add_spacer(width=12)
                            dpg.add_text("H:", color=_CF2)
                            dpg.add_input_text(tag="b_res_h",
                                               default_value="720",  width=100)

                    with dpg.group(tag="bop_trim"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Bắt đầu:", color=_CF2, indent=16)
                            dpg.add_input_text(tag="b_trim_start",
                                               default_value="00:00:00", width=120)
                            dpg.add_spacer(width=12)
                            dpg.add_text("Kết thúc:", color=_CF2)
                            dpg.add_input_text(tag="b_trim_end",
                                               default_value="00:01:00", width=120)
                    dpg.hide_item("bop_trim")

                    with dpg.group(tag="bop_crop"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("W:", color=_CF2, indent=16)
                            dpg.add_input_text(tag="b_crop_w",
                                               default_value="1280", width=100)
                            dpg.add_spacer(width=12)
                            dpg.add_text("H:", color=_CF2)
                            dpg.add_input_text(tag="b_crop_h",
                                               default_value="720", width=100)
                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            dpg.add_text("X:", color=_CF2, indent=16)
                            dpg.add_input_text(tag="b_crop_x",
                                               default_value="0", width=100)
                            dpg.add_spacer(width=12)
                            dpg.add_text("Y:", color=_CF2)
                            dpg.add_input_text(tag="b_crop_y",
                                               default_value="0", width=100)
                    dpg.hide_item("bop_crop")

                    with dpg.group(tag="bop_extract_audio"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Định dạng:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_audio_fmt",
                                          items=["mp3","aac","wav","ogg","m4a"],
                                          default_value="mp3", width=120)
                    dpg.hide_item("bop_extract_audio")

                    with dpg.group(tag="bop_remove_audio"):
                        dpg.add_text("Xóa hoàn toàn âm thanh khỏi tất cả video.",
                                     color=_CF3)
                    dpg.hide_item("bop_remove_audio")

                    with dpg.group(tag="bop_convert"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Định dạng:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_conv_fmt",
                                          items=video_edit.FORMATS,
                                          default_value="mp4", width=120)
                    dpg.hide_item("bop_convert")

                    with dpg.group(tag="bop_speed"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Tốc độ (0.25–4.0):", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_input_text(tag="b_speed",
                                               default_value="2.00", width=100)
                    dpg.hide_item("bop_speed")

                    with dpg.group(tag="bop_rotate"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Rotation:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_rotate",
                                          items=list(video_edit.ROTATIONS.keys()),
                                          default_value=list(
                                              video_edit.ROTATIONS.keys())[0],
                                          width=280)
                    dpg.hide_item("bop_rotate")

                    with dpg.group(tag="bop_logo"):
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(tag="b_logo_path", width=-120,
                                               hint="Chọn file logo...")
                            dpg.add_button(label="Duyệt...", width=110,
                                           callback=self._b_browse_logo)
                        dpg.add_spacer(height=6)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Vị trí:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_logo_pos",
                                          items=list(
                                              video_edit.LOGO_POSITIONS.keys()),
                                          default_value="Bottom-Right", width=180)
                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Scale:", color=_CF2)
                            dpg.add_input_text(tag="b_logo_scale",
                                               default_value="150", width=90)
                            dpg.add_spacer(width=8)
                            dpg.add_text("Opacity:", color=_CF2)
                            dpg.add_input_text(tag="b_logo_opacity",
                                               default_value="1.00", width=90)
                    dpg.hide_item("bop_logo")

                dpg.add_spacer(height=12)
                batch_btn = dpg.add_button(label="Áp dụng tất cả",
                                           tag="batch_btn",
                                           width=-16, height=44, indent=16,
                                           callback=self._apply_batch)
                dpg.bind_item_theme(batch_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(batch_btn, "f_bold")
                dpg.add_spacer(height=8)
                dpg.add_progress_bar(tag="batch_prog", width=-16, height=5,
                                     indent=16, default_value=0.0)
                dpg.add_spacer(height=6)
                dpg.add_text("", tag="batch_status", color=_CF2, indent=16)

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log_panel(self, h: int):
        with dpg.child_window(tag="log_panel", width=_LOG_W, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("log_panel", "th_sidebar")
            dpg.add_spacer(height=12)
            t = dpg.add_text("Activity Log", indent=12)
            if dpg.does_item_exist("f_bold"):
                dpg.bind_item_font(t, "f_bold")
            dpg.add_spacer(height=6)
            dpg.add_separator()
            dpg.add_spacer(height=6)
            with dpg.child_window(tag="log_content", width=_LOG_W - 16,
                                  height=h - 60, border=False, indent=8):
                dpg.bind_item_theme("log_content", "th_log")
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True, indent=8):
                dpg.add_text("", tag="status_txt", color=_CF2,
                             wrap=_LOG_W - 100)
                clr = dpg.add_button(label="Xóa log", width=68,
                                     callback=self._clear_log)
                dpg.bind_item_theme(clr, "th_accent")

    # ── Log queue pump (called every frame from render thread) ─────────────────
    def _process_log_queue(self, *_):
        while not self._log_queue.empty():
            try:
                text, color = self._log_queue.get_nowait()
                self._add_log_entry(text, color)
            except queue.Empty:
                break
        # Process pending dialog results (from worker threads)
        while not self._dlg_queue.empty():
            try:
                item = self._dlg_queue.get_nowait()
                if not item:
                    continue

                # Library-specific 2-tuple messages
                if len(item) == 2:
                    cmd, payload = item
                    if cmd == "lib_root_set":
                        self._lib_root = os.path.abspath(payload)
                        dpg.set_value("lib_root_input", self._lib_root)
                        self._lib_refresh_folders()
                    elif cmd == "lib_new_folder":
                        new_path = os.path.join(self._lib_root, payload)
                        try:
                            os.makedirs(new_path, exist_ok=True)
                            self._log(f"Đã tạo thư mục: {payload}", "ok")
                            self._lib_refresh_folders()
                        except Exception as e:
                            self._log(f"Không thể tạo thư mục: {e}", "err")
                    elif cmd == "lib_upload":
                        self._lib_process_upload(payload)
                    continue

                mode, target, res = item
                if not res:
                    continue
                if mode in ('open', 'save', 'dir'):
                    try:
                        dpg.set_value(target, res)
                    except Exception:
                        pass
                elif mode == 'open_multi':
                    try:
                        new_files = list(res)
                        if target == '__merge__':
                            # add to app-side list, sync to listbox
                            for f in new_files:
                                if f not in self._merge_items:
                                    self._merge_items.append(f)
                            dpg.configure_item("merge_list",
                                               items=list(self._merge_items))
                        elif target == '__batch__':
                            for f in new_files:
                                if f not in self._batch_items:
                                    self._batch_items.append(f)
                            self._refresh_batch_list_display()
                        else:
                            # generic listbox fallback
                            dpg.configure_item(target, items=new_files)
                    except Exception:
                        pass
            except queue.Empty:
                break
        if dpg.is_dearpygui_running():
            dpg.set_frame_callback(dpg.get_frame_count() + 1,
                                   self._process_log_queue)

    def _add_log_entry(self, text: str, color: tuple):
        tag = f"ll_{self._log_counter}"
        self._log_counter += 1
        dpg.add_text(text, tag=tag, color=color,
                     parent="log_content", wrap=_LOG_W - 36)
        self._log_items.append(tag)
        while len(self._log_items) > _MAX_LOG:
            old = self._log_items.pop(0)
            if dpg.does_item_exist(old):
                dpg.delete_item(old)
        dpg.set_y_scroll("log_content", dpg.get_y_scroll_max("log_content"))

    def _log(self, text: str, tag: str = "info"):
        ts     = datetime.now().strftime("%H:%M:%S")
        colors = {"ok": _CL_OK, "err": _CL_ERR, "info": _CL_INFO}
        icon_map = {"ok": "✓", "err": "✗", "info": "•"}
        self._log_queue.put((f"[{ts}] {icon_map.get(tag, '•')} {text}", colors.get(tag, _CF)))
        try:
            dpg.set_value("status_txt", text[:80])
        except Exception:
            pass

    def _clear_log(self):
        for tag in self._log_items:
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)
        self._log_items.clear()
        dpg.set_value("status_txt", "Ready")

    # ── Viewport resize ────────────────────────────────────────────────────────
    def _on_resize(self):
        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()
        cw = vw - _SIDEBAR_W - _LOG_W

        dpg.set_item_width("main_win",      vw)
        dpg.set_item_height("main_win",     vh)
        dpg.set_item_height("sidebar",      vh)
        dpg.set_item_width("content_host",  cw)
        dpg.set_item_height("content_host", vh)
        dpg.set_item_height("log_panel",    vh)
        dpg.set_item_width("log_content",   _LOG_W - 16)
        dpg.set_item_height("log_content",  vh - 60)

        for pg in ["pg_dl", "pg_lib", "pg_edit", "pg_batch"]:
            dpg.set_item_width(pg, cw)
            dpg.set_item_height(pg, vh)
        for sc in ["dl_scroll", "lib_scroll", "edit_scroll", "batch_scroll"]:
            dpg.set_item_width(sc, cw)
            dpg.set_item_height(sc, vh - _HDR_H)
        
        # Save window dimensions for next session
        self._save_window_config()

    # ── File dialog helpers ────────────────────────────────────────────────────
    # ── File dialog helpers (run dialogs in worker threads and post results back)
    def _start_dialog_thread(self, mode: str, target: str, filetypes=None):
        """Start a thread that creates its own Tk root and runs a dialog.

        mode: 'open', 'open_multi', 'save', 'dir'
        target: the dpg item tag to set (or listbox tag)
        filetypes: optional filetypes for file dialogs
        """
        def _worker():
            import tkinter as tk
            from tkinter import filedialog as fd

            root = tk.Tk()
            root.withdraw()
            try:
                if mode == 'open':
                    res = fd.askopenfilename(parent=root, filetypes=filetypes)
                elif mode == 'open_multi':
                    res = fd.askopenfilenames(parent=root, filetypes=filetypes)
                elif mode == 'save':
                    res = fd.asksaveasfilename(parent=root, filetypes=filetypes)
                elif mode == 'dir':
                    res = fd.askdirectory(parent=root)
                else:
                    res = None
            except Exception:
                res = None
            finally:
                try:
                    root.destroy()
                except Exception:
                    pass

            # Push result to dlg queue for main thread to apply
            self._dlg_queue.put((mode, target, res))

        threading.Thread(target=_worker, daemon=True).start()

    def _browse_dir(self, target: str):
        self._start_dialog_thread('dir', target)

    def _browse_file_single(self, target: str, filetypes):
        self._start_dialog_thread('open', target, filetypes)

    def _browse_files_to_list(self, listbox: str, filetypes):
        self._start_dialog_thread('open_multi', listbox, filetypes)

    def _browse_edit_in(self):
        self._browse_file_single("edit_in",
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _browse_edit_out(self):
        self._start_dialog_thread('save', 'edit_out',
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"),
             ("Audio files", "*.mp3 *.aac *.wav *.ogg *.m4a"),
             ("All files",   "*.*")])

    def _browse_logo(self):
        self._browse_file_single("logo_path",
            [("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"),
             ("All files",   "*.*")])

    def _b_browse_logo(self):
        self._browse_file_single("b_logo_path",
            [("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"),
             ("All files",   "*.*")])

    def _open_output(self):
        path = dpg.get_value("dl_out").strip() or "downloads"
        if os.path.exists(path):
            try:
                os.startfile(path)
            except Exception:
                pass

    # ── Edit helpers ───────────────────────────────────────────────────────────
    def _on_preset_change(self, sender, app_data):
        w, h = video_edit.PRESETS.get(app_data, (None, None))
        if w:
            dpg.set_value("res_w", str(w))
            dpg.set_value("res_h", str(h))

    def _on_logo_pos_change(self, sender, app_data):
        if app_data == "Custom":
            dpg.show_item("logo_custom")
        else:
            dpg.hide_item("logo_custom")

    def _on_b_preset_change(self, sender, app_data):
        w, h = video_edit.PRESETS.get(app_data, (None, None))
        if w:
            dpg.set_value("b_res_w", str(w))
            dpg.set_value("b_res_h", str(h))

    def _on_batch_op_change(self, sender, app_data):
        op_to_group = {
            "Resize":        "bop_resize",
            "Trim":          "bop_trim",
            "Crop":          "bop_crop",
            "Extract Audio": "bop_extract_audio",
            "Remove Audio":  "bop_remove_audio",
            "Convert":       "bop_convert",
            "Speed":         "bop_speed",
            "Rotate":        "bop_rotate",
            "Logo":          "bop_logo",
        }
        for g in op_to_group.values():
            dpg.hide_item(g)
        if app_data in op_to_group:
            dpg.show_item(op_to_group[app_data])

    # ── Merge list helpers ─────────────────────────────────────────────────────
    def _merge_add(self):
        self._start_dialog_thread(
            'open_multi', '__merge__',
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _merge_remove(self):
        selected = dpg.get_value("merge_list")
        if selected in self._merge_items:
            self._merge_items.remove(selected)
            dpg.configure_item("merge_list", items=list(self._merge_items))

    def _merge_clear(self):
        self._merge_items.clear()
        dpg.configure_item("merge_list", items=[])

    def _merge_move(self, direction: int):
        selected = dpg.get_value("merge_list")
        if selected not in self._merge_items:
            return
        idx = self._merge_items.index(selected)
        nb  = idx + direction
        if 0 <= nb < len(self._merge_items):
            self._merge_items[idx], self._merge_items[nb] = \
                self._merge_items[nb], self._merge_items[idx]
            dpg.configure_item("merge_list", items=list(self._merge_items))
            dpg.set_value("merge_list", self._merge_items[nb])

    # ── Batch list helpers ─────────────────────────────────────────────────────
    def _refresh_batch_list_display(self):
        """Update batch_list_display text and batch_file_select combo."""
        text = "\n".join(self._batch_items) if self._batch_items else ""
        try:
            dpg.set_value("batch_list_display", text)
            dpg.configure_item("batch_file_select",
                               items=list(self._batch_items),
                               default_value=self._batch_items[0] if self._batch_items else "")
        except Exception:
            pass

    def _batch_add_files(self):
        self._start_dialog_thread(
            'open_multi', '__batch__',
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _batch_remove_file(self):
        selected = dpg.get_value("batch_file_select")
        if selected in self._batch_items:
            self._batch_items.remove(selected)
            self._refresh_batch_list_display()

    def _batch_clear(self):
        self._batch_items.clear()
        self._refresh_batch_list_display()

    # ── Download logic ─────────────────────────────────────────────────────────
    def start_download(self):
        platform = self._current_dl_platform   # "tiktok" | "youtube"
        out = dpg.get_value("dl_out").strip() or "downloads"

        self._activity_id += 1
        act = self._activity_id

        if platform == "tiktok":
            mode = dpg.get_value("dl_mode")
            self._log(f"[Activity #{act}] Bắt đầu tác vụ tải TikTok | mode={mode}", "info")
            if mode == "Single Video":
                url = dpg.get_value("url_single").strip()
                if not url:
                    self._log("Vui lòng nhập URL video.", "err"); return
                if not is_tiktok_url(url):
                    self._log("URL không phải TikTok hợp lệ. Hãy kiểm tra lại.", "err"); return
                targets = [("tt_single", url)]
            elif mode == "Profile":
                url = dpg.get_value("url_profile").strip()
                if not url:
                    self._log("Vui lòng nhập URL profile.", "err"); return
                if not is_tiktok_url(url):
                    self._log("URL không phải TikTok hợp lệ.", "err"); return
                mv    = dpg.get_value("max_videos").strip()
                max_v = int(mv) if mv.isdigit() else None
                targets = [("tt_profile", (url, max_v))]
            else:
                raw  = dpg.get_value("multi_text")
                urls = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                if not urls:
                    self._log("Vui lòng nhập ít nhất một URL.", "err"); return
                # Filter and warn about invalid URLs
                invalid = [u for u in urls if not is_tiktok_url(u)]
                if invalid:
                    self._log(f"Bỏ qua {len(invalid)} URL không hợp lệ.", "err")
                    urls = [u for u in urls if is_tiktok_url(u)]
                    if not urls:
                        self._log("Không có URL TikTok hợp lệ nào.", "err"); return
                targets = [("tt_multi", urls)]

        else:  # youtube
            yt_mode = dpg.get_value("yt_mode")
            quality = dpg.get_value("yt_quality") or "best"
            # Auto-detect cookies: use them if the cookies file exists and is valid
            from youtube_download import _validate_cookies_file
            _cf = os.path.join(os.path.dirname(__file__), "youtube_cookies.txt")
            use_cookies = _validate_cookies_file(_cf)
            yt_ctx = get_youtube_runtime_context(quality, use_cookies)
            self._log(
                f"[Activity #{act}] Bắt đầu tác vụ tải YouTube | mode={yt_mode}",
                "info",
            )
            self._log(
                f"[Activity #{act}] quality={quality} | cookies={yt_ctx['cookies']} | "
                f"aria2c={'bật' if yt_ctx['using_aria2c'] else 'tắt'}",
                "info",
            )
            if yt_mode == "Video đơn":
                url = dpg.get_value("yt_url_single").strip()
                if not url:
                    self._log("Vui lòng nhập URL video YouTube.", "err"); return
                if not is_youtube_url(url):
                    self._log("URL không phải YouTube hợp lệ.", "err"); return
                targets = [("yt_single", (url, quality, use_cookies))]
            elif yt_mode == "Playlist":
                url = dpg.get_value("yt_playlist_url").strip()
                if not url:
                    self._log("Vui lòng nhập URL playlist / channel.", "err"); return
                mv    = dpg.get_value("yt_max_items").strip()
                max_v = int(mv) if mv.isdigit() else None
                targets = [("yt_playlist", (url, quality, max_v, use_cookies))]
            elif yt_mode == "Nhiều URLs":
                raw  = dpg.get_value("yt_multi_text")
                urls = [ln.strip() for ln in raw.splitlines() if ln.strip()]
                if not urls:
                    self._log("Vui lòng nhập ít nhất một URL.", "err"); return
                targets = [("yt_multi", (urls, quality, use_cookies))]
            else:  # Kênh
                url = dpg.get_value("yt_channel_url").strip()
                if not url:
                    self._log("Vui lòng nhập URL kênh YouTube.", "err"); return
                mv          = dpg.get_value("yt_ch_max").strip()
                max_v       = int(mv) if mv.isdigit() else None
                use_subfol  = dpg.get_value("yt_ch_subfolder")
                targets = [("yt_channel", (url, quality, max_v, use_subfol, use_cookies))]

        if not os.path.exists(out):
            try:
                os.makedirs(out)
                self._log(f"[Activity #{act}] Tạo thư mục output: {out}", "ok")
            except Exception as e:
                self._log(f"Không thể tạo thư mục: {e}", "err"); return
        else:
            self._log(f"[Activity #{act}] Output: {os.path.abspath(out)}", "info")

        dpg.configure_item("dl_btn", enabled=False)
        dpg.set_value("dl_prog", 0.0)
        threading.Thread(target=self._worker, args=(targets, out, act),
                         daemon=True).start()

    def _worker(self, targets, out, act: int):
        started = time.perf_counter()
        last_pct = -1

        def _prog_hook(d):
            """yt-dlp progress callback → update progress bar."""
            nonlocal last_pct
            try:
                if d.get("status") == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    downloaded = d.get("downloaded_bytes", 0)
                    if total > 0:
                        progress = downloaded / total
                        dpg.set_value("dl_prog", progress)
                        pct = int(progress * 100)
                        if pct >= 0 and (pct // 10) > (last_pct // 10):
                            last_pct = pct
                            self._log(f"[Activity #{act}] Tiến độ tải: {pct}%", "info")
                elif d.get("status") == "finished":
                    dpg.set_value("dl_prog", 1.0)
            except Exception:
                pass

        try:
            for kind, payload in targets:
                # ── TikTok ────────────────────────────────────────────────────
                if kind == "tt_single":
                    self._log(f"[TikTok] Đang tải: {payload}", "info")
                    fn = download_tiktok_video(payload, out, _prog_hook)
                    self._log(
                        f"Hoàn thành: {os.path.basename(fn)}" if fn
                        else f"Thất bại: {payload}",
                        "ok" if fn else "err")

                elif kind == "tt_profile":
                    url, max_v = payload
                    self._log(f"[TikTok] Đang tải profile: {url}", "info")
                    ok = download_from_profile(url, out, max_v, _prog_hook, self._log)
                    self._log(
                        "Tải profile hoàn thành." if ok else "Tải profile thất bại.",
                        "ok" if ok else "err")

                elif kind == "tt_multi":
                    for url in payload:
                        self._log(f"[TikTok] Đang tải: {url}", "info")
                        fn = download_tiktok_video(url, out, _prog_hook)
                        self._log(
                            f"Hoàn thành: {os.path.basename(fn)}" if fn
                            else f"Thất bại: {url}",
                            "ok" if fn else "err")

                # ── YouTube ───────────────────────────────────────────────────
                elif kind == "yt_single":
                    url, quality, use_cookies = payload
                    self._log(f"[YouTube] Đang tải ({quality}): {url}", "info")
                    fn = download_youtube_video(url, out, quality, _prog_hook, self._log, use_cookies)
                    self._log(
                        f"Hoàn thành: {os.path.basename(fn)}" if fn
                        else f"Thất bại: {url}",
                        "ok" if fn else "err")

                elif kind == "yt_playlist":
                    url, quality, max_v, use_cookies = payload
                    self._log(f"[YouTube] Đang tải playlist ({quality}): {url}", "info")
                    ok_n, total = download_youtube_playlist(
                        url, out, quality, max_v, _prog_hook, self._log, use_cookies)
                    self._log(
                        f"Playlist hoàn thành: {ok_n}/{total} video.",
                        "ok" if ok_n > 0 else "err")

                elif kind == "yt_multi":
                    urls, quality, use_cookies = payload
                    self._log(f"[YouTube] Đang tải {len(urls)} URL ({quality})...", "info")
                    ok_n, total = download_youtube_multi(
                        urls, out, quality, _prog_hook, self._log, use_cookies=use_cookies)
                    self._log(
                        f"Hoàn thành: {ok_n}/{total} video.",
                        "ok" if ok_n > 0 else "err")

                elif kind == "yt_channel":
                    url, quality, max_v, use_subfol, use_cookies = payload
                    self._log(f"[YouTube] Đang tải kênh ({quality}): {url}", "info")
                    if max_v:
                        self._log(f"Giới hạn: {max_v} video đầu tiên.", "info")
                    ok_n, total = download_youtube_channel(
                        url, out, quality, max_v, use_subfol, _prog_hook, self._log, use_cookies)
                    self._log(
                        f"Kênh hoàn thành: {ok_n} video đã tải.",
                        "ok" if ok_n > 0 else "err")

        except Exception as e:
            self._log(f"Lỗi: {e}", "err")
        finally:
            elapsed = time.perf_counter() - started
            self._log(f"[Activity #{act}] Kết thúc tác vụ tải ({elapsed:.1f}s)", "ok")
            try:
                dpg.set_value("dl_prog", 1.0)
                time.sleep(1.5)  # show 100% briefly
                dpg.configure_item("dl_btn", enabled=True)
                dpg.set_value("dl_prog", 0.0)
            except Exception:
                pass

    # ── Edit logic ─────────────────────────────────────────────────────────────
    def _apply_edit(self):
        inp = dpg.get_value("edit_in").strip()
        if not inp or not os.path.isfile(inp):
            self._log("Vui lòng chọn file video hợp lệ.", "err"); return
        out = dpg.get_value("edit_out").strip() or None
        tab = self._current_edit_tab   # reliable — updated by tab_bar callback

        dpg.configure_item("edit_btn", enabled=False)
        dpg.set_value("edit_prog", 0.0)
        threading.Thread(target=self._edit_worker,
                         args=(tab, inp, out), daemon=True).start()

    def _edit_worker(self, tab: str, inp: str, out):
        started = time.perf_counter()
        try:
            dpg.set_value("edit_prog", 0.15)
            if "Resize" in tab:
                w, h = int(dpg.get_value("res_w")), int(dpg.get_value("res_h"))
                self._log(f"Resize {w}x{h}: {os.path.basename(inp)}", "info")
                result = video_edit.resize_video(inp, w, h, out)
            elif "Trim" in tab:
                start = dpg.get_value("trim_start").strip()
                end = dpg.get_value("trim_end").strip()
                if not start or not end:
                    self._log("Nhập thời gian bắt đầu và kết thúc.", "err"); return
                self._log(f"Trim {start}→{end}: {os.path.basename(inp)}", "info")
                result = video_edit.trim_video(inp, start, end, out)
            elif "Crop" in tab:
                cw = int(dpg.get_value("crop_w"))
                ch = int(dpg.get_value("crop_h"))
                cx = int(dpg.get_value("crop_x"))
                cy = int(dpg.get_value("crop_y"))
                self._log(f"Crop {cw}x{ch}+{cx}+{cy}: {os.path.basename(inp)}", "info")
                result = video_edit.crop_video(inp, cw, ch, cx, cy, out)
            elif "Audio" in tab:
                mode = dpg.get_value("audio_mode")
                if "Extract" in mode:
                    fmt = dpg.get_value("audio_fmt")
                    self._log(
                        f"Extract audio ({fmt}): {os.path.basename(inp)}",
                        "info")
                    result = video_edit.extract_audio(inp, fmt, out)
                else:
                    self._log(f"Remove audio: {os.path.basename(inp)}", "info")
                    result = video_edit.remove_audio(inp, out)
            elif "Convert" in tab:
                fmt = dpg.get_value("conv_fmt")
                self._log(
                    f"Convert -> {fmt}: {os.path.basename(inp)}", "info")
                result = video_edit.convert_format(inp, fmt, out)
            elif "Speed" in tab:
                try:
                    speed = float(dpg.get_value("spd_val"))
                except ValueError:
                    speed = 1.0
                self._log(f"Speed {speed}x: {os.path.basename(inp)}", "info")
                result = video_edit.speed_video(inp, speed, out)
            elif "Rotate" in tab:
                rot = dpg.get_value("rot_choice")
                self._log(
                    f"Rotate ({rot}): {os.path.basename(inp)}", "info")
                result = video_edit.rotate_video(inp, rot, out)
            elif "Merge" in tab:
                paths = list(self._merge_items)
                if not paths:
                    self._log("Merge: chưa có file nào.", "err"); return
                self._log(f"Ghép {len(paths)} file...", "info")
                result = video_edit.merge_videos(paths, out)
            else:  # Logo
                logo = dpg.get_value("logo_path").strip()
                if not logo or not os.path.isfile(logo):
                    self._log("Logo: chưa chọn file logo hợp lệ.", "err")
                    return
                pos = dpg.get_value("logo_pos")
                cx  = dpg.get_value("logo_x").strip()  or "W-w-10"
                cy  = dpg.get_value("logo_y").strip()  or "H-h-20"
                try:
                    scale = int(dpg.get_value("logo_scale"))
                except ValueError:
                    scale = 150
                try:
                    opacity = float(dpg.get_value("logo_opacity"))
                    opacity = max(0.0, min(1.0, opacity))
                except ValueError:
                    opacity = 1.0
                self._log(f"Logo ({pos}): {os.path.basename(inp)}", "info")
                result = video_edit.add_logo(inp, logo, pos, cx, cy,
                                             scale, opacity, out)
            dpg.set_value("edit_prog", 1.0)
            elapsed = time.perf_counter() - started
            self._log(f"Hoàn thành ({elapsed:.1f}s): {result}", "ok")
        except Exception as e:
            self._log(f"Lỗi edit: {e}", "err")
        finally:
            try:
                time.sleep(1.0)  # show completion briefly
                dpg.configure_item("edit_btn", enabled=True)
                dpg.set_value("edit_prog", 0.0)
            except Exception:
                pass

    # ── Batch logic ────────────────────────────────────────────────────────────
    def _apply_batch(self):
        files = list(self._batch_items)
        if not files:
            self._log("Chưa có file nào trong danh sách.", "err"); return
        op      = dpg.get_value("batch_op")
        out_dir = dpg.get_value("batch_out").strip()
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                self._log(f"Không thể tạo thư mục: {e}", "err"); return
        dpg.configure_item("batch_btn", enabled=False)
        dpg.set_value("batch_prog", 0.0)
        threading.Thread(target=self._batch_worker,
                         args=(list(files), op, out_dir),
                         daemon=True).start()

    def _batch_worker(self, files: list, op: str, out_dir: str):
        ok_count = err_count = 0
        total = len(files)
        try:
            for i, inp in enumerate(files):
                name     = os.path.basename(inp)
                base, ex = os.path.splitext(name)
                src_dir  = os.path.dirname(inp)

                def _out(suffix: str, ext: str = "",
                         _b=base, _e=ex, _s=src_dir) -> str:
                    return os.path.join(out_dir or _s,
                                        f"{_b}_{suffix}{ext or _e}")

                try:
                    self._log(f"[{i+1}/{total}] {op}: {name}", "info")
                    if op == "Resize":
                        w, h = (int(dpg.get_value("b_res_w")),
                                int(dpg.get_value("b_res_h")))
                        result = video_edit.resize_video(
                            inp, w, h, _out(f"{w}x{h}"))
                    elif op == "Trim":
                        start = dpg.get_value("b_trim_start").strip()
                        end = dpg.get_value("b_trim_end").strip()
                        result = video_edit.trim_video(
                            inp, start, end, _out("trimmed"))
                    elif op == "Crop":
                        cw = int(dpg.get_value("b_crop_w"))
                        ch = int(dpg.get_value("b_crop_h"))
                        cx = int(dpg.get_value("b_crop_x"))
                        cy = int(dpg.get_value("b_crop_y"))
                        result = video_edit.crop_video(
                            inp, cw, ch, cx, cy, _out(f"crop{cw}x{ch}"))
                    elif op == "Extract Audio":
                        fmt    = dpg.get_value("b_audio_fmt")
                        result = video_edit.extract_audio(
                            inp, fmt, _out("audio", f".{fmt}"))
                    elif op == "Remove Audio":
                        result = video_edit.remove_audio(inp, _out("noaudio"))
                    elif op == "Convert":
                        fmt    = dpg.get_value("b_conv_fmt")
                        result = video_edit.convert_format(
                            inp, fmt, _out("converted", f".{fmt}"))
                    elif op == "Speed":
                        try:
                            speed = float(dpg.get_value("b_speed"))
                        except ValueError:
                            speed = 1.0
                        result = video_edit.speed_video(
                            inp, speed, _out(f"speed{speed}"))
                    elif op == "Rotate":
                        result = video_edit.rotate_video(
                            inp, dpg.get_value("b_rotate"),
                            _out("rotated"))
                    elif op == "Logo":
                        logo = dpg.get_value("b_logo_path").strip()
                        if not logo or not os.path.isfile(logo):
                            self._log(
                                f"  ✗ Logo không hợp lệ: {name}", "err")
                            err_count += 1; continue
                        pos = dpg.get_value("b_logo_pos")
                        try:
                            scale = int(dpg.get_value("b_logo_scale"))
                        except ValueError:
                            scale = 150
                        try:
                            opacity = float(dpg.get_value("b_logo_opacity"))
                            opacity = max(0.0, min(1.0, opacity))
                        except ValueError:
                            opacity = 1.0
                        result = video_edit.add_logo(
                            inp, logo, pos, "W-w-10", "H-h-20",
                            scale, opacity, _out("logo"))
                    else:
                        result = inp
                    self._log(
                        f"  ✓ {os.path.basename(result)}", "ok")
                    ok_count += 1
                except Exception as e:
                    self._log(f"  ✗ Lỗi: {e}", "err")
                    err_count += 1
                finally:
                    try:
                        dpg.set_value("batch_prog", (i + 1) / total)
                        dpg.set_value("batch_status",
                                      f"{i+1}/{total}  —  OK {ok_count}"
                                      f"   ✗ {err_count}")
                    except Exception:
                        pass
        finally:
            try:
                dpg.configure_item("batch_btn", enabled=True)
                self._log(
                    f"Batch xong: {ok_count}/{total} thành công,"
                    f" {err_count} lỗi.",
                    "ok" if err_count == 0 else "err")
                dpg.set_value("batch_status",
                              f"Xong — OK {ok_count}   ✗ {err_count}"
                              f"   / {total} file")
            except Exception:
                pass


if __name__ == "__main__":
    App().run()
