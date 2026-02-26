import os
import queue
import threading
import tkinter as _tk               # used ONLY for file dialogs
from datetime import datetime
from tkinter import filedialog as _fdlg

import dearpygui.dearpygui as dpg

from tiktok_download import download_tiktok_video, download_from_profile
import video_edit

# ── Hidden Tk root (file dialogs only) ────────────────────────────────────────
_tk_root = _tk.Tk()
_tk_root.withdraw()

# ── Layout constants ───────────────────────────────────────────────────────────
_SIDEBAR_W = 90
_LOG_W     = 340
_HDR_H     = 62
_MAX_LOG   = 300   # max log lines kept in panel

# ── Color palette  (R, G, B, A  —  0-255) ─────────────────────────────────────
_CA      = (238,  29,  82, 255)   # accent
_CA_H    = (196,  22,  68, 255)   # accent hover
_CA_ACT  = (160,  10,  48, 255)   # accent active/pressed
_CS      = ( 13,  13,  13, 255)   # sidebar / log panel bg
_CM      = ( 24,  24,  24, 255)   # main bg
_CC      = ( 33,  33,  33, 255)   # card bg
_CC2     = ( 42,  42,  42, 255)   # card2 bg
_CB      = ( 51,  51,  51, 255)   # border
_CF      = (255, 255, 255, 255)   # foreground
_CF2     = (136, 136, 136, 255)   # dim foreground
_CF3     = (102, 102, 102, 255)   # hint foreground
_CBTN    = ( 46,  46,  46, 255)   # button bg
_CBTN_H  = ( 58,  58,  58, 255)   # button hover
_CL      = ( 20,  20,  20, 255)   # log bg
_CL_OK   = ( 76, 175,  80, 255)
_CL_ERR  = (239,  83,  80, 255)
_CL_INFO = ( 66, 165, 245, 255)
_CL_TS   = ( 85,  85,  85, 255)
_CTRANS  = (  0,   0,   0,   0)


class App:
    def __init__(self):
        self._current_page: str | None = None
        self._pages: dict[str, str]    = {}    # page_id → child_window tag
        self._nav_btns: dict[str, str] = {}    # page_id → button tag
        self._log_queue: queue.Queue   = queue.Queue()
        self._log_items: list[str]     = []
        self._log_counter: int         = 0

    # ─────────────────────────────────────────────────────────────────────────
    def run(self):
        dpg.create_context()
        self._setup_fonts()
        self._setup_themes()
        dpg.create_viewport(title="TikTok Downloader", width=1280, height=760,
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
        with dpg.font_registry():
            if os.path.exists(reg):
                with dpg.font(reg, 14, tag="f_reg"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)
                    dpg.add_font_range(0x2190, 0x21FF)   # arrows ←→↑↓
                    dpg.add_font_range(0x2700, 0x27BF)   # dingbats ✂
                dpg.bind_font("f_reg")
            if os.path.exists(bold):
                with dpg.font(bold, 16, tag="f_title"):
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                    dpg.add_font_range_hint(dpg.mvFontRangeHint_Vietnamese)
                with dpg.font(bold, 13, tag="f_bold"):
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
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive,      _CA)
                dpg.add_theme_color(dpg.mvThemeCol_Button,             _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,      _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,       _CA_ACT)
                dpg.add_theme_color(dpg.mvThemeCol_Text,               _CF)
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled,       _CF2)
                dpg.add_theme_color(dpg.mvThemeCol_Border,             _CB)
                dpg.add_theme_color(dpg.mvThemeCol_BorderShadow,       _CTRANS)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,        _CM)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,      _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, _CA)
                dpg.add_theme_color(dpg.mvThemeCol_Header,             _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered,      _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive,       _CA)
                dpg.add_theme_color(dpg.mvThemeCol_Tab,                _CBTN)
                dpg.add_theme_color(dpg.mvThemeCol_TabHovered,         _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_TabActive,          _CA)
                dpg.add_theme_color(dpg.mvThemeCol_TabUnfocusedActive, _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBg,            _CS)
                dpg.add_theme_color(dpg.mvThemeCol_TitleBgActive,      _CS)
                dpg.add_theme_color(dpg.mvThemeCol_PopupBg,            _CC)
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark,          _CA)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab,         _CA)
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive,   _CA_H)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding,    0)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding,      8)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding,      6)
                dpg.add_theme_style(dpg.mvStyleVar_GrabRounding,       4)
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding,  4)
                dpg.add_theme_style(dpg.mvStyleVar_TabRounding,        6)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding,      0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,       8, 5)
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

        # ── accent button ────────────────────────────────────────────────────
        with dpg.theme(tag="th_accent"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CA_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CA_ACT)

        # ── nav button: active ───────────────────────────────────────────────
        with dpg.theme(tag="th_nav_on"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CC2)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CC2)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CC2)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          _CF)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)

        # ── nav button: inactive ─────────────────────────────────────────────
        with dpg.theme(tag="th_nav_off"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CTRANS)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CBTN_H)
                dpg.add_theme_color(dpg.mvThemeCol_Text,          _CF2)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)

        # ── logo box ─────────────────────────────────────────────────────────
        with dpg.theme(tag="th_logo"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button,        _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _CA)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,  _CA)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding,  12, 10)

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
            dpg.add_spacer(height=14)
            logo = dpg.add_button(label="▶", width=46, height=46, enabled=False,
                                  indent=(_SIDEBAR_W - 46) // 2)
            dpg.bind_item_theme(logo, "th_logo")
            if dpg.does_item_exist("f_bold"):
                dpg.bind_item_font(logo, "f_bold")
            dpg.add_text("DowRen", color=_CF2, indent=27)
            dpg.add_spacer(height=10)
            dpg.add_separator()
            dpg.add_spacer(height=10)

            for page_id, icon, label in [
                ("download", "↓",  "Tai"),
                ("edit",     "✂",  "Edit"),
                ("batch",    "☰",  "Batch"),
            ]:
                btn = dpg.add_button(
                    label=f"{icon}\n{label}", tag=f"nav_{page_id}",
                    width=_SIDEBAR_W - 12, height=58,
                    callback=lambda s, a, u: self._switch_page(u),
                    user_data=page_id, indent=6)
                dpg.bind_item_theme(btn, "th_nav_off")
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
            self._build_edit_page(w, h)
            self._build_batch_page(w, h)

    # ── Shared: page header bar ────────────────────────────────────────────────
    def _hdr(self, title: str, subtitle: str):
        with dpg.child_window(height=_HDR_H, border=False, no_scrollbar=True) as c:
            dpg.bind_item_theme(c, "th_sidebar")
            dpg.add_spacer(height=8)
            t = dpg.add_text(title, indent=20)
            if dpg.does_item_exist("f_title"):
                dpg.bind_item_font(t, "f_title")
            dpg.add_text(subtitle, color=_CF2, indent=22)

    # ── Download page ──────────────────────────────────────────────────────────
    def _build_download_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_dl", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_dl", "th_main")
            self._pages["download"] = "pg_dl"
            self._hdr("TikTok Downloader", "Created by thongtruong")

            with dpg.child_window(tag="dl_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("dl_scroll", "th_main")
                dpg.add_spacer(height=10)

                t = dpg.add_text("Chon loai link de tai video", indent=16)
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(t, "f_bold")
                dpg.add_text("Ho tro: Single Video  •  Profile  •  Nhieu URLs",
                             color=_CF2, indent=16)
                dpg.add_spacer(height=10)

                # Mode selector (radio buttons styled as segmented control)
                dpg.add_radio_button(
                    tag="dl_mode",
                    items=["Single Video", "Profile", "Nhieu URLs"],
                    default_value="Single Video", horizontal=True, indent=16,
                    callback=self._on_dl_mode_change)
                dpg.add_spacer(height=10)

                # ── Single URL card ──────────────────────────────────────────
                with dpg.child_window(tag="dl_card_single", height=88,
                                      border=True, indent=12):
                    dpg.add_text("VIDEO URL", color=_CF2)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="url_single", width=-76,
                                           hint="https://www.tiktok.com/@user/video/...")
                        dpg.add_button(label="Dan", width=68,
                                       callback=self._paste_single)

                # ── Profile card ──────────────────────────────────────────────
                with dpg.child_window(tag="dl_card_profile", height=116,
                                      border=True, indent=12):
                    dpg.add_text("PROFILE URL", color=_CF2)
                    dpg.add_spacer(height=4)
                    dpg.add_input_text(tag="url_profile", width=-4,
                                       hint="https://www.tiktok.com/@username")
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_text("So video toi da:", color=_CF2)
                        dpg.add_spacer(width=8)
                        dpg.add_input_text(tag="max_videos", width=160,
                                           hint="de trong = tat ca")
                dpg.hide_item("dl_card_profile")

                # ── Multi URL card ────────────────────────────────────────────
                with dpg.child_window(tag="dl_card_multi", height=190,
                                      border=True, indent=12):
                    dpg.add_text("DANH SACH URL  (moi dong 1 link)", color=_CF2)
                    dpg.add_spacer(height=4)
                    dpg.add_input_text(tag="multi_text", multiline=True,
                                       width=-4, height=140)
                dpg.hide_item("dl_card_multi")

                dpg.add_spacer(height=12)

                # ── Output folder card ────────────────────────────────────────
                with dpg.child_window(height=78, border=True, indent=12):
                    dpg.add_text("THU MUC LUU VIDEO", color=_CF2)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="dl_out", default_value="downloads",
                                           width=-164)
                        dpg.add_button(label="Browse", width=76,
                                       callback=lambda: self._browse_dir("dl_out"))
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="Mo thu muc", width=80,
                                       callback=self._open_output)

                dpg.add_spacer(height=12)
                dl_btn = dpg.add_button(label="  ▶   Bat dau tai  ", tag="dl_btn",
                                        width=-12, height=46, indent=12,
                                        callback=self.start_download)
                dpg.bind_item_theme(dl_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(dl_btn, "f_bold")
                dpg.add_spacer(height=6)
                dpg.add_progress_bar(tag="dl_prog", width=-12, height=6,
                                     indent=12, default_value=0.0)

    def _on_dl_mode_change(self, sender, app_data):
        for card in ["dl_card_single", "dl_card_profile", "dl_card_multi"]:
            dpg.hide_item(card)
        if app_data == "Single Video":
            dpg.show_item("dl_card_single")
        elif app_data == "Profile":
            dpg.show_item("dl_card_profile")
        else:
            dpg.show_item("dl_card_multi")

    def _paste_single(self):
        try:
            _tk_root.update()
            dpg.set_value("url_single", _tk_root.clipboard_get().strip())
        except Exception:
            pass

    # ── Edit page ──────────────────────────────────────────────────────────────
    def _build_edit_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_edit", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_edit", "th_main")
            dpg.hide_item("pg_edit")
            self._pages["edit"] = "pg_edit"
            self._hdr("✂  Edit Video",
                      "Chinh sua video don le voi cac thao tac FFmpeg")

            with dpg.child_window(tag="edit_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("edit_scroll", "th_main")
                dpg.add_spacer(height=10)

                # Input
                with dpg.child_window(height=78, border=True, indent=12):
                    dpg.add_text("FILE INPUT", color=_CF2)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="edit_in", width=-120,
                                           hint="Chon file video...")
                        dpg.add_button(label="Browse...", width=112,
                                       callback=self._browse_edit_in)
                dpg.add_spacer(height=8)

                # Op tabs
                with dpg.tab_bar(tag="op_tabs", indent=12):
                    with dpg.tab(label="Resize"):
                        self._tab_resize()
                    with dpg.tab(label="Audio"):
                        self._tab_audio()
                    with dpg.tab(label="Convert"):
                        self._tab_convert()
                    with dpg.tab(label="Speed"):
                        self._tab_speed()
                    with dpg.tab(label="Rotate"):
                        self._tab_rotate()
                    with dpg.tab(label="Merge"):
                        self._tab_merge()
                    with dpg.tab(label="Logo"):
                        self._tab_logo()

                dpg.add_spacer(height=8)

                # Output
                with dpg.child_window(height=78, border=True, indent=12):
                    dpg.add_text("FILE OUTPUT  (de trong = tu dong dat ten)", color=_CF2)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="edit_out", width=-120,
                                           hint="Luu tai...")
                        dpg.add_button(label="Save As...", width=112,
                                       callback=self._browse_edit_out)

                dpg.add_spacer(height=12)
                edit_btn = dpg.add_button(label="  ▶   Apply Edit  ", tag="edit_btn",
                                          width=-12, height=46, indent=12,
                                          callback=self._apply_edit)
                dpg.bind_item_theme(edit_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(edit_btn, "f_bold")
                dpg.add_spacer(height=6)
                dpg.add_progress_bar(tag="edit_prog", width=-12, height=6,
                                     indent=12, default_value=0.0)

    def _tab_resize(self):
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Preset:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="res_preset", items=list(video_edit.PRESETS.keys()),
                          default_value="720p  (1280x720)", width=220,
                          callback=self._on_preset_change)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Width: ", color=_CF2)
            dpg.add_input_text(tag="res_w", default_value="1280", width=100)
            dpg.add_spacer(width=16)
            dpg.add_text("Height:", color=_CF2)
            dpg.add_input_text(tag="res_h", default_value="720", width=100)
        dpg.add_spacer(height=4)
        dpg.add_text("Dung -1 cho mot chieu de giu ti le khung hinh.",
                     color=_CF3, indent=16)

    def _tab_audio(self):
        dpg.add_spacer(height=8)
        dpg.add_radio_button(tag="audio_mode",
                             items=["Extract audio  (lay am thanh ra file rieng)",
                                    "Remove audio   (tat tieng video)"],
                             default_value="Extract audio  (lay am thanh ra file rieng)",
                             indent=16)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Format:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="audio_fmt",
                          items=["mp3", "aac", "wav", "ogg", "m4a"],
                          default_value="mp3", width=120)
        dpg.add_text("(ap dung khi extract audio)", color=_CF3, indent=16)

    def _tab_convert(self):
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Output format:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="conv_fmt", items=video_edit.FORMATS,
                          default_value="mp4", width=120)
        dpg.add_spacer(height=4)
        dpg.add_text("FFmpeg tu chon codec phu hop cho container.",
                     color=_CF3, indent=16)

    def _tab_speed(self):
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Speed multiplier:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="spd_val", default_value="2.00", width=100)
        dpg.add_spacer(height=10)
        dpg.add_text("Nhanh chon:", color=_CF2, indent=16)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True, indent=16):
            for lbl, val in [("0.5x", "0.50"), ("0.75x", "0.75"), ("1x", "1.00"),
                              ("1.5x", "1.50"), ("2x", "2.00"), ("4x", "4.00")]:
                dpg.add_button(label=lbl, width=56,
                               callback=lambda s, a, u: dpg.set_value("spd_val", u),
                               user_data=val)
                dpg.add_spacer(width=4)
        dpg.add_spacer(height=4)
        dpg.add_text("< 1.0 = cham  |  > 1.0 = nhanh  |  pham vi 0.25-4.0",
                     color=_CF3, indent=16)

    def _tab_rotate(self):
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Rotation / Flip:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="rot_choice",
                          items=list(video_edit.ROTATIONS.keys()),
                          default_value=list(video_edit.ROTATIONS.keys())[0],
                          width=280)
        dpg.add_spacer(height=4)
        dpg.add_text("Ap dung bo loc vf cua FFmpeg — video duoc re-encode.",
                     color=_CF3, indent=16)

    def _tab_merge(self):
        dpg.add_spacer(height=8)
        dpg.add_text("Danh sach file video:", color=_CF2, indent=16)
        dpg.add_spacer(height=4)
        dpg.add_listbox(tag="merge_list", items=[], width=-16, num_items=5, indent=12)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True, indent=12):
            for lbl, cb in [("Add...",  self._merge_add),
                             ("Remove", self._merge_remove),
                             ("Up",     lambda: self._merge_move(-1)),
                             ("Down",   lambda: self._merge_move(1)),
                             ("Clear",  lambda: dpg.configure_item("merge_list", items=[]))]:
                dpg.add_button(label=lbl, width=68, callback=cb)
                dpg.add_spacer(width=4)
        dpg.add_spacer(height=4)
        dpg.add_text("Stream-copy — cuc nhanh, khong mat chat luong.",
                     color=_CF3, indent=16)

    def _tab_logo(self):
        dpg.add_spacer(height=8)
        dpg.add_text("File logo (PNG/JPG):", color=_CF2, indent=16)
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True, indent=12):
            dpg.add_input_text(tag="logo_path", width=-120, hint="Chon file logo...")
            dpg.add_button(label="Browse...", width=112, callback=self._browse_logo)
        dpg.add_spacer(height=8)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Vi tri:", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_combo(tag="logo_pos",
                          items=list(video_edit.LOGO_POSITIONS.keys()),
                          default_value="Bottom-Right", width=180,
                          callback=self._on_logo_pos_change)
        with dpg.group(tag="logo_custom", horizontal=False, indent=16):
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_text("X:", color=_CF2)
                dpg.add_input_text(tag="logo_x", default_value="W-w-10", width=110)
                dpg.add_spacer(width=12)
                dpg.add_text("Y:", color=_CF2)
                dpg.add_input_text(tag="logo_y", default_value="H-h-20", width=110)
        dpg.hide_item("logo_custom")
        dpg.add_spacer(height=4)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Scale (px):", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="logo_scale", default_value="150", width=100)
        with dpg.group(horizontal=True, indent=16):
            dpg.add_text("Opacity:  ", color=_CF2)
            dpg.add_spacer(width=8)
            dpg.add_input_text(tag="logo_opacity", default_value="1.00", width=100)
        dpg.add_spacer(height=4)
        dpg.add_text("Dung PNG co nen trong suot de logo dep nhat.",
                     color=_CF3, indent=16)

    # ── Batch page ─────────────────────────────────────────────────────────────
    def _build_batch_page(self, w: int, h: int):
        with dpg.child_window(tag="pg_batch", width=w, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("pg_batch", "th_main")
            dpg.hide_item("pg_batch")
            self._pages["batch"] = "pg_batch"
            self._hdr("☰  Batch Edit",
                      "Ap dung cung mot thao tac cho nhieu video cung luc")

            with dpg.child_window(tag="batch_scroll", width=w, height=h - _HDR_H,
                                  border=False):
                dpg.bind_item_theme("batch_scroll", "th_main")
                dpg.add_spacer(height=10)

                # File list
                with dpg.child_window(height=186, border=True, indent=12):
                    dpg.add_text("DANH SACH FILE INPUT", color=_CF2)
                    dpg.add_spacer(height=4)
                    dpg.add_listbox(tag="batch_list", items=[], width=-8, num_items=5)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Add...",  width=82,
                                       callback=self._batch_add_files)
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="Remove",  width=82,
                                       callback=self._batch_remove_files)
                        dpg.add_spacer(width=4)
                        dpg.add_button(label="Clear",   width=82,
                                       callback=lambda: dpg.configure_item(
                                           "batch_list", items=[]))

                dpg.add_spacer(height=8)

                # Output dir
                with dpg.child_window(height=78, border=True, indent=12):
                    dpg.add_text("THU MUC OUTPUT  (de trong = cung thu muc goc)",
                                 color=_CF2)
                    dpg.add_spacer(height=4)
                    with dpg.group(horizontal=True):
                        dpg.add_input_text(tag="batch_out", width=-120,
                                           hint="Chon thu muc...")
                        dpg.add_button(label="Browse...", width=112,
                                       callback=lambda: self._browse_dir("batch_out"))

                dpg.add_spacer(height=8)

                # Operation selector
                _BOPS = ["Resize", "Extract Audio", "Remove Audio",
                         "Convert", "Speed", "Rotate", "Logo"]
                with dpg.child_window(height=190, border=True, indent=12):
                    dpg.add_text("THAO TAC AP DUNG CHO TAT CA FILE", color=_CF2)
                    dpg.add_spacer(height=6)
                    with dpg.group(horizontal=True):
                        dpg.add_text("Chon thao tac:", color=_CF2)
                        dpg.add_spacer(width=8)
                        dpg.add_combo(tag="batch_op", items=_BOPS,
                                      default_value="Resize", width=200,
                                      callback=self._on_batch_op_change)
                    dpg.add_spacer(height=8)

                    # Per-operation sub-panels (only "Resize" visible initially)
                    with dpg.group(tag="bop_resize"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Preset:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_res_preset",
                                          items=list(video_edit.PRESETS.keys()),
                                          default_value="720p  (1280x720)", width=220,
                                          callback=self._on_b_preset_change)
                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            dpg.add_text("W:", color=_CF2)
                            dpg.add_input_text(tag="b_res_w",
                                               default_value="1280", width=100)
                            dpg.add_spacer(width=12)
                            dpg.add_text("H:", color=_CF2)
                            dpg.add_input_text(tag="b_res_h",
                                               default_value="720",  width=100)

                    with dpg.group(tag="bop_extract_audio"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Dinh dang:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_audio_fmt",
                                          items=["mp3","aac","wav","ogg","m4a"],
                                          default_value="mp3", width=120)
                    dpg.hide_item("bop_extract_audio")

                    with dpg.group(tag="bop_remove_audio"):
                        dpg.add_text("Xoa hoan toan am thanh khoi tat ca video.",
                                     color=_CF3)
                    dpg.hide_item("bop_remove_audio")

                    with dpg.group(tag="bop_convert"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Dinh dang:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_conv_fmt", items=video_edit.FORMATS,
                                          default_value="mp4", width=120)
                    dpg.hide_item("bop_convert")

                    with dpg.group(tag="bop_speed"):
                        with dpg.group(horizontal=True):
                            dpg.add_text("Toc do (0.25-4.0):", color=_CF2)
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
                                               hint="Chon file logo...")
                            dpg.add_button(label="Browse...", width=112,
                                           callback=self._b_browse_logo)
                        dpg.add_spacer(height=4)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Vi tri:", color=_CF2)
                            dpg.add_spacer(width=8)
                            dpg.add_combo(tag="b_logo_pos",
                                          items=list(video_edit.LOGO_POSITIONS.keys()),
                                          default_value="Bottom-Right", width=180)
                        with dpg.group(horizontal=True):
                            dpg.add_text("Scale:", color=_CF2)
                            dpg.add_input_text(tag="b_logo_scale",
                                               default_value="150", width=90)
                            dpg.add_spacer(width=8)
                            dpg.add_text("Opacity:", color=_CF2)
                            dpg.add_input_text(tag="b_logo_opacity",
                                               default_value="1.00", width=90)
                    dpg.hide_item("bop_logo")

                dpg.add_spacer(height=10)
                batch_btn = dpg.add_button(label="  ▶   Apply to All  ",
                                           tag="batch_btn",
                                           width=-12, height=46, indent=12,
                                           callback=self._apply_batch)
                dpg.bind_item_theme(batch_btn, "th_accent")
                if dpg.does_item_exist("f_bold"):
                    dpg.bind_item_font(batch_btn, "f_bold")
                dpg.add_spacer(height=6)
                dpg.add_progress_bar(tag="batch_prog", width=-12, height=6,
                                     indent=12, default_value=0.0)
                dpg.add_spacer(height=4)
                dpg.add_text("", tag="batch_status", color=_CF2, indent=12)

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log_panel(self, h: int):
        with dpg.child_window(tag="log_panel", width=_LOG_W, height=h,
                              border=False, no_scrollbar=True):
            dpg.bind_item_theme("log_panel", "th_sidebar")
            dpg.add_spacer(height=8)
            t = dpg.add_text("  Activity Log", indent=8)
            if dpg.does_item_exist("f_bold"):
                dpg.bind_item_font(t, "f_bold")
            dpg.add_separator()
            dpg.add_spacer(height=4)
            with dpg.child_window(tag="log_content", width=_LOG_W - 16,
                                  height=h - 82, border=False, indent=8):
                dpg.bind_item_theme("log_content", "th_log")
            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True, indent=8):
                dpg.add_text("", tag="status_txt", color=_CF2)
                dpg.add_spacer(width=-72)
                clr = dpg.add_button(label="Clear", width=64,
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
        self._log_queue.put((f"[{ts}] {text}", colors.get(tag, _CF)))
        try:
            dpg.set_value("status_txt", text[:55])
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
        dpg.set_item_height("log_content",  vh - 82)

        for pg in ["pg_dl", "pg_edit", "pg_batch"]:
            dpg.set_item_width(pg, cw)
            dpg.set_item_height(pg, vh)
        for sc in ["dl_scroll", "edit_scroll", "batch_scroll"]:
            dpg.set_item_width(sc, cw)
            dpg.set_item_height(sc, vh - _HDR_H)

    # ── File dialog helpers ────────────────────────────────────────────────────
    def _browse_dir(self, target: str):
        _tk_root.update()
        d = _fdlg.askdirectory()
        if d:
            dpg.set_value(target, d)

    def _browse_file_single(self, target: str, filetypes):
        _tk_root.update()
        f = _fdlg.askopenfilename(filetypes=filetypes)
        if f:
            dpg.set_value(target, f)

    def _browse_files_to_list(self, listbox: str, filetypes):
        _tk_root.update()
        files = _fdlg.askopenfilenames(filetypes=filetypes)
        if files:
            cur = list(dpg.get_item_configuration(listbox).get("items", []))
            dpg.configure_item(listbox, items=cur + list(files))

    def _browse_edit_in(self):
        self._browse_file_single("edit_in",
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _browse_edit_out(self):
        _tk_root.update()
        f = _fdlg.asksaveasfilename(
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"),
                       ("Audio files", "*.mp3 *.aac *.wav *.ogg *.m4a"),
                       ("All files",   "*.*")])
        if f:
            dpg.set_value("edit_out", f)

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
        self._browse_files_to_list("merge_list",
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _merge_remove(self):
        items    = list(dpg.get_item_configuration("merge_list").get("items", []))
        selected = dpg.get_value("merge_list")
        if selected in items:
            items.remove(selected)
            dpg.configure_item("merge_list", items=items)

    def _merge_move(self, direction: int):
        items    = list(dpg.get_item_configuration("merge_list").get("items", []))
        selected = dpg.get_value("merge_list")
        if selected not in items:
            return
        idx = items.index(selected)
        nb  = idx + direction
        if 0 <= nb < len(items):
            items[idx], items[nb] = items[nb], items[idx]
            dpg.configure_item("merge_list", items=items)
            dpg.set_value("merge_list", items[nb])

    def _batch_add_files(self):
        self._browse_files_to_list("batch_list",
            [("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
             ("All files",   "*.*")])

    def _batch_remove_files(self):
        items    = list(dpg.get_item_configuration("batch_list").get("items", []))
        selected = dpg.get_value("batch_list")
        if selected in items:
            items.remove(selected)
            dpg.configure_item("batch_list", items=items)

    # ── Download logic ─────────────────────────────────────────────────────────
    def start_download(self):
        mode = dpg.get_value("dl_mode")
        out  = dpg.get_value("dl_out").strip() or "downloads"

        if mode == "Single Video":
            url = dpg.get_value("url_single").strip()
            if not url:
                self._log("Vui long nhap URL video.", "err"); return
            targets = [("single", url)]
        elif mode == "Profile":
            url = dpg.get_value("url_profile").strip()
            if not url:
                self._log("Vui long nhap URL profile.", "err"); return
            mv    = dpg.get_value("max_videos").strip()
            max_v = int(mv) if mv.isdigit() else None
            targets = [("profile", (url, max_v))]
        else:
            raw  = dpg.get_value("multi_text")
            urls = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if not urls:
                self._log("Vui long nhap it nhat mot URL.", "err"); return
            targets = [("multi", urls)]

        if not os.path.exists(out):
            try:
                os.makedirs(out)
            except Exception as e:
                self._log(f"Khong the tao thu muc: {e}", "err"); return

        dpg.configure_item("dl_btn", enabled=False)
        dpg.set_value("dl_prog", 0.0)
        threading.Thread(target=self._worker, args=(targets, out), daemon=True).start()

    def _worker(self, targets, out):
        try:
            for kind, payload in targets:
                if kind == "single":
                    self._log(f"Dang tai: {payload}", "info")
                    fn = download_tiktok_video(payload, out)
                    self._log(f"Hoan thanh: {fn}" if fn else f"That bai: {payload}",
                              "ok" if fn else "err")
                elif kind == "profile":
                    url, max_v = payload
                    self._log(f"Dang tai profile: {url}", "info")
                    ok = download_from_profile(url, out, max_v)
                    self._log("Tai profile hoan thanh." if ok else "Tai profile that bai.",
                              "ok" if ok else "err")
                else:
                    for url in payload:
                        self._log(f"Dang tai: {url}", "info")
                        fn = download_tiktok_video(url, out)
                        self._log(f"Hoan thanh: {fn}" if fn else f"That bai: {url}",
                                  "ok" if fn else "err")
        except Exception as e:
            self._log(f"Loi: {e}", "err")
        finally:
            try:
                dpg.configure_item("dl_btn", enabled=True)
                dpg.set_value("dl_prog", 0.0)
            except Exception:
                pass

    # ── Edit logic ─────────────────────────────────────────────────────────────
    def _apply_edit(self):
        inp = dpg.get_value("edit_in").strip()
        if not inp or not os.path.isfile(inp):
            self._log("Vui long chon file video hop le.", "err"); return
        out      = dpg.get_value("edit_out").strip() or None
        tab_uuid = dpg.get_value("op_tabs")
        tab      = dpg.get_item_label(tab_uuid) if dpg.does_item_exist(tab_uuid) else ""

        dpg.configure_item("edit_btn", enabled=False)
        dpg.set_value("edit_prog", 0.0)
        threading.Thread(target=self._edit_worker,
                         args=(tab, inp, out), daemon=True).start()

    def _edit_worker(self, tab: str, inp: str, out):
        try:
            if "Resize" in tab:
                w, h = int(dpg.get_value("res_w")), int(dpg.get_value("res_h"))
                self._log(f"Resize {w}x{h}: {os.path.basename(inp)}", "info")
                result = video_edit.resize_video(inp, w, h, out)
            elif "Audio" in tab:
                mode = dpg.get_value("audio_mode")
                if "Extract" in mode:
                    fmt = dpg.get_value("audio_fmt")
                    self._log(f"Extract audio ({fmt}): {os.path.basename(inp)}", "info")
                    result = video_edit.extract_audio(inp, fmt, out)
                else:
                    self._log(f"Remove audio: {os.path.basename(inp)}", "info")
                    result = video_edit.remove_audio(inp, out)
            elif "Convert" in tab:
                fmt = dpg.get_value("conv_fmt")
                self._log(f"Convert -> {fmt}: {os.path.basename(inp)}", "info")
                result = video_edit.convert_format(inp, fmt, out)
            elif "Speed" in tab:
                try:   speed = float(dpg.get_value("spd_val"))
                except ValueError: speed = 1.0
                self._log(f"Speed {speed}x: {os.path.basename(inp)}", "info")
                result = video_edit.speed_video(inp, speed, out)
            elif "Rotate" in tab:
                rot = dpg.get_value("rot_choice")
                self._log(f"Rotate ({rot}): {os.path.basename(inp)}", "info")
                result = video_edit.rotate_video(inp, rot, out)
            elif "Merge" in tab:
                paths = list(dpg.get_item_configuration("merge_list").get("items", []))
                if not paths:
                    self._log("Merge: chua co file nao.", "err"); return
                self._log(f"Ghep {len(paths)} file...", "info")
                result = video_edit.merge_videos(paths, out)
            else:  # Logo
                logo = dpg.get_value("logo_path").strip()
                if not logo or not os.path.isfile(logo):
                    self._log("Logo: chua chon file logo hop le.", "err"); return
                pos = dpg.get_value("logo_pos")
                cx  = dpg.get_value("logo_x").strip()  or "W-w-10"
                cy  = dpg.get_value("logo_y").strip()  or "H-h-20"
                try:   scale = int(dpg.get_value("logo_scale"))
                except ValueError: scale = 150
                try:
                    opacity = float(dpg.get_value("logo_opacity"))
                    opacity = max(0.0, min(1.0, opacity))
                except ValueError: opacity = 1.0
                self._log(f"Logo ({pos}): {os.path.basename(inp)}", "info")
                result = video_edit.add_logo(inp, logo, pos, cx, cy,
                                             scale, opacity, out)
            self._log(f"Hoan thanh: {result}", "ok")
        except Exception as e:
            self._log(f"Loi edit: {e}", "err")
        finally:
            try:
                dpg.configure_item("edit_btn", enabled=True)
                dpg.set_value("edit_prog", 0.0)
            except Exception:
                pass

    # ── Batch logic ────────────────────────────────────────────────────────────
    def _apply_batch(self):
        files = list(dpg.get_item_configuration("batch_list").get("items", []))
        if not files:
            self._log("Chua co file nao trong danh sach.", "err"); return
        op      = dpg.get_value("batch_op")
        out_dir = dpg.get_value("batch_out").strip()
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                self._log(f"Khong the tao thu muc: {e}", "err"); return
        dpg.configure_item("batch_btn", enabled=False)
        dpg.set_value("batch_prog", 0.0)
        threading.Thread(target=self._batch_worker,
                         args=(list(files), op, out_dir), daemon=True).start()

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
                    return os.path.join(out_dir or _s, f"{_b}_{suffix}{ext or _e}")

                try:
                    self._log(f"[{i+1}/{total}] {op}: {name}", "info")
                    if op == "Resize":
                        w, h = (int(dpg.get_value("b_res_w")),
                                int(dpg.get_value("b_res_h")))
                        result = video_edit.resize_video(inp, w, h, _out(f"{w}x{h}"))
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
                        try:   speed = float(dpg.get_value("b_speed"))
                        except ValueError: speed = 1.0
                        result = video_edit.speed_video(inp, speed,
                                                         _out(f"speed{speed}"))
                    elif op == "Rotate":
                        result = video_edit.rotate_video(
                            inp, dpg.get_value("b_rotate"), _out("rotated"))
                    elif op == "Logo":
                        logo = dpg.get_value("b_logo_path").strip()
                        if not logo or not os.path.isfile(logo):
                            self._log(f"  X Logo khong hop le: {name}", "err")
                            err_count += 1; continue
                        pos = dpg.get_value("b_logo_pos")
                        try:   scale = int(dpg.get_value("b_logo_scale"))
                        except ValueError: scale = 150
                        try:
                            opacity = float(dpg.get_value("b_logo_opacity"))
                            opacity = max(0.0, min(1.0, opacity))
                        except ValueError: opacity = 1.0
                        result = video_edit.add_logo(
                            inp, logo, pos, "W-w-10", "H-h-20",
                            scale, opacity, _out("logo"))
                    else:
                        result = inp
                    self._log(f"  OK -> {os.path.basename(result)}", "ok")
                    ok_count += 1
                except Exception as e:
                    self._log(f"  X Loi: {e}", "err")
                    err_count += 1
                finally:
                    try:
                        dpg.set_value("batch_prog", (i + 1) / total)
                        dpg.set_value("batch_status",
                                      f"{i+1}/{total}  —  OK {ok_count}"
                                      f"   X {err_count}")
                    except Exception:
                        pass
        finally:
            try:
                dpg.configure_item("batch_btn", enabled=True)
                self._log(
                    f"Batch xong: {ok_count}/{total} thanh cong,"
                    f" {err_count} loi.",
                    "ok" if err_count == 0 else "err")
                dpg.set_value("batch_status",
                              f"Xong — OK {ok_count}   X {err_count}"
                              f"   / {total} file")
            except Exception:
                pass


if __name__ == "__main__":
    App().run()
