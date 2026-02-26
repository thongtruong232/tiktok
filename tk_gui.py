import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

from tiktok_download import download_tiktok_video, download_from_profile
import video_edit

# ── Global theme ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

_ACCENT        = "#EE1D52"
_ACCENT_HOVER  = "#c41644"
_SIDEBAR_BG    = "#0d0d0d"
_MAIN_BG       = "#181818"
_CARD_BG       = "#212121"
_CARD2_BG      = "#2a2a2a"
_BORDER        = "#333333"
_FG            = "#ffffff"
_FG_DIM        = "#888888"
_FG_HINT       = "#666666"
_NAV_ACTIVE    = "#2a2a2a"
_BTN_BG        = "#2e2e2e"
_BTN_HOVER     = "#3a3a3a"
_ENTRY_BG      = "#2a2a2a"
_LOG_BG        = "#141414"
_LOG_OK        = "#4caf50"
_LOG_ERR       = "#ef5350"
_LOG_INFO      = "#42a5f5"
_LOG_TS        = "#555555"


def _card(parent, **kwargs):
    return ctk.CTkFrame(parent, fg_color=_CARD_BG, corner_radius=10,
                        border_width=1, border_color=_BORDER, **kwargs)

def _label(parent, text="", size=13, bold=False, color=_FG, **kwargs):
    weight = "bold" if bold else "normal"
    return ctk.CTkLabel(parent, text=text, font=("Segoe UI", size, weight),
                        text_color=color, **kwargs)

def _entry(parent, placeholder="", width=0, **kwargs):
    kw = dict(fg_color=_ENTRY_BG, border_color=_BORDER, border_width=1,
              corner_radius=8, font=("Segoe UI", 12), placeholder_text=placeholder)
    if width:
        kw["width"] = width
    kw.update(kwargs)
    return ctk.CTkEntry(parent, **kw)

def _btn(parent, text, command=None, accent=False, width=0, **kwargs):
    if accent:
        kw = dict(fg_color=_ACCENT, hover_color=_ACCENT_HOVER, text_color=_FG,
                  corner_radius=8, font=("Segoe UI", 13, "bold"))
    else:
        kw = dict(fg_color=_BTN_BG, hover_color=_BTN_HOVER, text_color=_FG,
                  corner_radius=8, font=("Segoe UI", 12))
    if width:
        kw["width"] = width
    kw.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **kw)

def _section_title(parent, text):
    return _label(parent, text, size=11, color=_FG_DIM)


class App:
    def __init__(self, root):
        self.root = root
        root.title("TikTok Downloader")
        root.geometry("1280x760")
        root.minsize(980, 580)
        root.configure(fg_color=_MAIN_BG)

        root.columnconfigure(0, minsize=80,  weight=0)
        root.columnconfigure(1, weight=1)
        root.columnconfigure(2, minsize=340, weight=0)
        root.rowconfigure(0, weight=1)

        self._pages = {}
        self._nav_btns = {}

        self._build_sidebar(root)
        self._build_content_host(root)
        self._build_log_panel(root)
        self._switch_page("download")

    # ── Sidebar ────────────────────────────────────────────────────────────────
    def _build_sidebar(self, root):
        sb = ctk.CTkFrame(root, fg_color=_SIDEBAR_BG, corner_radius=0, width=80)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)

        logo_box = ctk.CTkFrame(sb, fg_color=_ACCENT, corner_radius=12, width=46, height=46)
        logo_box.grid(row=0, column=0, pady=(20, 0))
        logo_box.grid_propagate(False)
        ctk.CTkLabel(logo_box, text="▶", font=("Segoe UI", 20), text_color=_FG
                     ).place(relx=0.5, rely=0.5, anchor="center")
        _label(sb, "DowRen", size=8, color=_FG_DIM).grid(row=1, column=0, pady=(4, 20))

        nav_items = [("download", "⬇", "Tải"), ("edit", "✂", "Edit"), ("batch", "📦", "Batch")]
        for row_idx, (page_id, icon, label) in enumerate(nav_items, start=2):
            frame = ctk.CTkFrame(sb, fg_color="transparent", corner_radius=10, width=68, height=64)
            frame.grid(row=row_idx, column=0, padx=6, pady=3)
            frame.grid_propagate(False)
            btn = ctk.CTkButton(frame, text=f"{icon}\n{label}",
                                command=lambda p=page_id: self._switch_page(p),
                                fg_color="transparent", hover_color=_NAV_ACTIVE,
                                text_color=_FG_DIM, corner_radius=10,
                                font=("Segoe UI", 10), width=68, height=64)
            btn.place(relx=0.5, rely=0.5, anchor="center")
            self._nav_btns[page_id] = btn
        sb.rowconfigure(10, weight=1)

    def _switch_page(self, page_id):
        for pid, frame in self._pages.items():
            if pid == page_id:
                frame.grid()
            else:
                frame.grid_remove()
        for pid, btn in self._nav_btns.items():
            if pid == page_id:
                btn.configure(fg_color=_NAV_ACTIVE, text_color=_FG)
            else:
                btn.configure(fg_color="transparent", text_color=_FG_DIM)

    # ── Content host ───────────────────────────────────────────────────────────
    def _build_content_host(self, root):
        host = ctk.CTkFrame(root, fg_color=_MAIN_BG, corner_radius=0)
        host.grid(row=0, column=1, sticky="nsew")
        host.columnconfigure(0, weight=1)
        host.rowconfigure(0, weight=1)
        self._build_download_page(host)
        self._build_edit_page(host)
        self._build_batch_page(host)

    # ── Download page ──────────────────────────────────────────────────────────
    def _build_download_page(self, host):
        page = ctk.CTkFrame(host, fg_color=_MAIN_BG, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        self._pages["download"] = page

        hdr = ctk.CTkFrame(page, fg_color=_SIDEBAR_BG, corner_radius=0, height=68)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        _label(hdr, "TikTok Downloader", size=18, bold=True
               ).grid(row=0, column=0, padx=24, pady=(14, 1), sticky="w")
        _label(hdr, "Created by thongtruong", size=9, color=_FG_DIM
               ).grid(row=1, column=0, padx=26, pady=(0, 12), sticky="w")

        scroll = ctk.CTkScrollableFrame(page, fg_color=_MAIN_BG,
                                        scrollbar_button_color=_CARD_BG)
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        scroll.columnconfigure(0, weight=1)

        _label(scroll, "Chọn loại link để tải video", size=16, bold=True
               ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        _label(scroll, "Hỗ trợ: Single video  •  Profile  •  Nhiều URLs",
               size=11, color=_FG_DIM).grid(row=1, column=0, sticky="w", pady=(0, 18))

        self._dl_mode_bar = ctk.CTkSegmentedButton(
            scroll,
            values=["  Single Video  ", "  Profile  ", "  Nhiều URLs  "],
            command=self._on_dl_mode_change,
            fg_color=_CARD_BG, selected_color=_ACCENT,
            selected_hover_color=_ACCENT_HOVER,
            unselected_color=_CARD_BG, unselected_hover_color=_BTN_HOVER,
            text_color=_FG, font=("Segoe UI", 12), corner_radius=8)
        self._dl_mode_bar.set("  Single Video  ")
        self._dl_mode_bar.grid(row=2, column=0, sticky="w", pady=(0, 14))

        input_card = _card(scroll)
        input_card.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        input_card.columnconfigure(0, weight=1)

        # Single URL frame
        self._dl_single_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        self._dl_single_frame.columnconfigure(0, weight=1)
        _section_title(self._dl_single_frame, "VIDEO URL").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        url_row = ctk.CTkFrame(self._dl_single_frame, fg_color="transparent")
        url_row.grid(row=1, column=0, sticky="ew")
        url_row.columnconfigure(0, weight=1)
        self.url_single = _entry(url_row, placeholder="https://www.tiktok.com/@user/video/...", height=42)
        self.url_single.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(url_row, "📋 Dán", command=self._paste_single, width=90).grid(row=0, column=1)

        # Profile frame
        self._dl_profile_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        self._dl_profile_frame.columnconfigure(0, weight=1)
        _section_title(self._dl_profile_frame, "PROFILE URL").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        self.url_profile = _entry(self._dl_profile_frame,
                                  placeholder="https://www.tiktok.com/@username", height=42)
        self.url_profile.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        max_row = ctk.CTkFrame(self._dl_profile_frame, fg_color="transparent")
        max_row.grid(row=2, column=0, sticky="w")
        _label(max_row, "Số video tối đa:", size=12).grid(row=0, column=0, padx=(0, 10))
        self.max_videos = _entry(max_row, placeholder="để trống = tất cả", width=180, height=38)
        self.max_videos.grid(row=0, column=1)

        # Multi URLs frame
        self._dl_multi_frame = ctk.CTkFrame(input_card, fg_color="transparent")
        self._dl_multi_frame.columnconfigure(0, weight=1)
        _section_title(self._dl_multi_frame, "DANH SÁCH URL  (mỗi dòng 1 link)").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        self.multi_text = ctk.CTkTextbox(
            self._dl_multi_frame, height=160, fg_color=_ENTRY_BG,
            border_color=_BORDER, border_width=1, corner_radius=8,
            font=("Consolas", 11), text_color=_FG)
        self.multi_text.grid(row=1, column=0, sticky="ew")

        self._dl_single_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=14)

        # Output folder
        out_card = _card(scroll)
        out_card.grid(row=4, column=0, sticky="ew", pady=(0, 14))
        out_card.columnconfigure(0, weight=1)
        oi = ctk.CTkFrame(out_card, fg_color="transparent")
        oi.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        oi.columnconfigure(0, weight=1)
        _section_title(oi, "THƯ MỤC LƯU VIDEO").grid(row=0, column=0, sticky="w", pady=(0, 6))
        or_ = ctk.CTkFrame(oi, fg_color="transparent")
        or_.grid(row=1, column=0, sticky="ew")
        or_.columnconfigure(0, weight=1)
        self.out_entry = _entry(or_, placeholder="downloads", height=42)
        self.out_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.out_entry.insert(0, "downloads")
        btn_row = ctk.CTkFrame(or_, fg_color="transparent")
        btn_row.grid(row=0, column=1)
        _btn(btn_row, "📂", command=lambda: self._browse_dir(self.out_entry), width=46).pack(side="left")
        _btn(btn_row, "📁 Mở", command=self._open_output, width=80).pack(side="left", padx=(6, 0))

        self.download_btn = _btn(scroll, "▶   Bắt đầu tải",
                                 command=self.start_download, accent=True, height=48)
        self.download_btn.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        self.dl_progress = ctk.CTkProgressBar(scroll, mode="indeterminate", height=6,
                                              corner_radius=3, progress_color=_ACCENT,
                                              fg_color=_CARD_BG)
        self.dl_progress.grid(row=6, column=0, sticky="ew")
        self.dl_progress.set(0)

    def _on_dl_mode_change(self, value):
        for fr in [self._dl_single_frame, self._dl_profile_frame, self._dl_multi_frame]:
            fr.grid_remove()
        if value == "  Single Video  ":
            self._dl_single_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        elif value == "  Profile  ":
            self._dl_profile_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        else:
            self._dl_multi_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=14)

    def _paste_single(self):
        try:
            text = self.root.clipboard_get()
            self.url_single.delete(0, tk.END)
            self.url_single.insert(0, text.strip())
        except Exception:
            pass

    def _browse_dir(self, entry):
        d = filedialog.askdirectory()
        if d:
            entry.delete(0, tk.END)
            entry.insert(0, d)

    # ── Edit page ──────────────────────────────────────────────────────────────
    def _build_edit_page(self, host):
        page = ctk.CTkFrame(host, fg_color=_MAIN_BG, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        self._pages["edit"] = page

        hdr = ctk.CTkFrame(page, fg_color=_SIDEBAR_BG, corner_radius=0, height=68)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        _label(hdr, "✂  Edit Video", size=18, bold=True
               ).grid(row=0, column=0, padx=24, pady=(14, 1), sticky="w")
        _label(hdr, "Chỉnh sửa video đơn lẻ với các thao tác FFmpeg",
               size=9, color=_FG_DIM).grid(row=1, column=0, padx=26, pady=(0, 12), sticky="w")

        scroll = ctk.CTkScrollableFrame(page, fg_color=_MAIN_BG,
                                        scrollbar_button_color=_CARD_BG)
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        scroll.columnconfigure(0, weight=1)

        # Input
        in_card = _card(scroll)
        in_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        in_card.columnconfigure(0, weight=1)
        ii = ctk.CTkFrame(in_card, fg_color="transparent")
        ii.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        ii.columnconfigure(0, weight=1)
        _section_title(ii, "FILE INPUT").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ir = ctk.CTkFrame(ii, fg_color="transparent")
        ir.grid(row=1, column=0, sticky="ew")
        ir.columnconfigure(0, weight=1)
        self.edit_in = _entry(ir, placeholder="Chọn file video...", height=42)
        self.edit_in.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(ir, "📂 Browse", command=self._browse_edit_in, width=110).grid(row=0, column=1)

        # Operations tabview
        self.op_tabview = ctk.CTkTabview(
            scroll, fg_color=_CARD_BG, corner_radius=10,
            segmented_button_fg_color=_CARD2_BG,
            segmented_button_selected_color=_ACCENT,
            segmented_button_selected_hover_color=_ACCENT_HOVER,
            segmented_button_unselected_color=_CARD2_BG,
            segmented_button_unselected_hover_color=_BTN_HOVER,
            border_color=_BORDER, border_width=1, text_color=_FG)
        self.op_tabview.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for t in ["📐 Resize", "🎵 Audio", "🔄 Convert", "⚡ Speed", "🔁 Rotate", "🎬 Merge", "🖼 Logo"]:
            self.op_tabview.add(t)

        self._build_edit_resize(self.op_tabview.tab("📐 Resize"))
        self._build_edit_audio(self.op_tabview.tab("🎵 Audio"))
        self._build_edit_convert(self.op_tabview.tab("🔄 Convert"))
        self._build_edit_speed(self.op_tabview.tab("⚡ Speed"))
        self._build_edit_rotate(self.op_tabview.tab("🔁 Rotate"))
        self._build_edit_merge(self.op_tabview.tab("🎬 Merge"))
        self._build_edit_logo(self.op_tabview.tab("🖼 Logo"))

        # Output
        out_card = _card(scroll)
        out_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        out_card.columnconfigure(0, weight=1)
        oi2 = ctk.CTkFrame(out_card, fg_color="transparent")
        oi2.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        oi2.columnconfigure(0, weight=1)
        _section_title(oi2, "FILE OUTPUT  (để trống = tự động đặt tên)").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        or2 = ctk.CTkFrame(oi2, fg_color="transparent")
        or2.grid(row=1, column=0, sticky="ew")
        or2.columnconfigure(0, weight=1)
        self.edit_out = _entry(or2, placeholder="Lưu tại...", height=42)
        self.edit_out.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(or2, "💾 Save As", command=self._browse_edit_out, width=110).grid(row=0, column=1)

        self.edit_btn = _btn(scroll, "▶   Apply Edit",
                             command=self._apply_edit, accent=True, height=48)
        self.edit_btn.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        self.edit_progress = ctk.CTkProgressBar(scroll, mode="indeterminate", height=6,
                                                corner_radius=3, progress_color=_ACCENT,
                                                fg_color=_CARD_BG)
        self.edit_progress.grid(row=4, column=0, sticky="ew")
        self.edit_progress.set(0)

    def _tf(self, tab):
        f = ctk.CTkFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=12, pady=10)
        f.columnconfigure(1, weight=1)
        return f

    def _build_edit_resize(self, tab):
        f = self._tf(tab)
        _label(f, "Preset:", size=12).grid(row=0, column=0, sticky="w", pady=4)
        self.res_preset = ctk.CTkComboBox(f, values=list(video_edit.PRESETS.keys()),
                                          state="readonly", width=220, fg_color=_ENTRY_BG,
                                          border_color=_BORDER, button_color=_ACCENT,
                                          command=self._on_preset_change, font=("Segoe UI", 12))
        self.res_preset.set("720p  (1280×720)")
        self.res_preset.grid(row=0, column=1, sticky="w", padx=(10, 0))
        _label(f, "Width:", size=12).grid(row=1, column=0, sticky="w", pady=4)
        self.res_w = _entry(f, width=100, height=36)
        self.res_w.insert(0, "1280")
        self.res_w.grid(row=1, column=1, sticky="w", padx=(10, 0))
        _label(f, "Height:", size=12).grid(row=2, column=0, sticky="w", pady=4)
        self.res_h = _entry(f, width=100, height=36)
        self.res_h.insert(0, "720")
        self.res_h.grid(row=2, column=1, sticky="w", padx=(10, 0))
        _label(f, "Dùng -1 cho một chiều để giữ tỉ lệ.", size=10, color=_FG_HINT
               ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_edit_audio(self, tab):
        f = self._tf(tab)
        self.audio_mode = ctk.StringVar(value="extract")
        ctk.CTkRadioButton(f, text="Extract audio  (lấy âm thanh ra file riêng)",
                           variable=self.audio_mode, value="extract",
                           fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
                           font=("Segoe UI", 12)).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        ctk.CTkRadioButton(f, text="Remove audio  (tắt tiếng video)",
                           variable=self.audio_mode, value="remove",
                           fg_color=_ACCENT, hover_color=_ACCENT_HOVER,
                           font=("Segoe UI", 12)).grid(row=1, column=0, columnspan=2, sticky="w", pady=4)
        _label(f, "Format:", size=12).grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.audio_fmt = ctk.CTkComboBox(f, values=["mp3", "aac", "wav", "ogg", "m4a"],
                                         state="readonly", width=120, fg_color=_ENTRY_BG,
                                         border_color=_BORDER, button_color=_ACCENT,
                                         font=("Segoe UI", 12))
        self.audio_fmt.set("mp3")
        self.audio_fmt.grid(row=2, column=1, sticky="w", padx=(10, 0))
        _label(f, "(áp dụng khi extract)", size=10, color=_FG_HINT
               ).grid(row=3, column=0, columnspan=2, sticky="w")

    def _build_edit_convert(self, tab):
        f = self._tf(tab)
        _label(f, "Output format:", size=12).grid(row=0, column=0, sticky="w", pady=4)
        self.conv_fmt = ctk.CTkComboBox(f, values=video_edit.FORMATS, state="readonly",
                                        width=120, fg_color=_ENTRY_BG, border_color=_BORDER,
                                        button_color=_ACCENT, font=("Segoe UI", 12))
        self.conv_fmt.set("mp4")
        self.conv_fmt.grid(row=0, column=1, sticky="w", padx=(10, 0))
        _label(f, "FFmpeg tự chọn codec phù hợp cho container.", size=10, color=_FG_HINT
               ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_edit_speed(self, tab):
        f = self._tf(tab)
        _label(f, "Speed multiplier:", size=12).grid(row=0, column=0, sticky="w", pady=4)
        self.spd_value = _entry(f, width=100, height=36)
        self.spd_value.insert(0, "2.00")
        self.spd_value.grid(row=0, column=1, sticky="w", padx=(10, 0))
        _label(f, "Ví dụ nhanh:", size=12).grid(row=1, column=0, sticky="w", pady=(12, 4))
        br = ctk.CTkFrame(f, fg_color="transparent")
        br.grid(row=2, column=0, columnspan=2, sticky="w")
        for lbl, val in [("0.5×","0.50"),("0.75×","0.75"),("1×","1.00"),
                          ("1.5×","1.50"),("2×","2.00"),("4×","4.00")]:
            _btn(br, lbl, width=58,
                 command=lambda v=val: (self.spd_value.delete(0, tk.END),
                                       self.spd_value.insert(0, v))).pack(side="left", padx=3)
        _label(f, "< 1.0 = chậm  |  > 1.0 = nhanh  |  phạm vi 0.25–4.0", size=10, color=_FG_HINT
               ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_edit_rotate(self, tab):
        f = self._tf(tab)
        _label(f, "Rotation / Flip:", size=12).grid(row=0, column=0, sticky="w", pady=4)
        self.rot_choice = ctk.CTkComboBox(f, values=list(video_edit.ROTATIONS.keys()),
                                          state="readonly", width=280, fg_color=_ENTRY_BG,
                                          border_color=_BORDER, button_color=_ACCENT,
                                          font=("Segoe UI", 12))
        self.rot_choice.set(list(video_edit.ROTATIONS.keys())[0])
        self.rot_choice.grid(row=0, column=1, sticky="w", padx=(10, 0))
        _label(f, "Áp dụng bộ lọc vf của FFmpeg, video được re-encode.", size=10, color=_FG_HINT
               ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_edit_merge(self, tab):
        f = ctk.CTkFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=12, pady=10)
        f.columnconfigure(0, weight=1)
        _label(f, "Danh sách file video:", size=12, bold=True).grid(row=0, column=0, sticky="w", pady=(0, 6))
        list_bg = ctk.CTkFrame(f, fg_color=_ENTRY_BG, corner_radius=8,
                               border_color=_BORDER, border_width=1)
        list_bg.grid(row=1, column=0, sticky="ew")
        list_bg.columnconfigure(0, weight=1)
        self.merge_list = tk.Listbox(list_bg, height=6, font=("Consolas", 10),
                                     bg=_ENTRY_BG, fg=_FG, selectbackground=_ACCENT,
                                     relief="flat", borderwidth=0, highlightthickness=0,
                                     activestyle="none")
        self.merge_list.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        sb = tk.Scrollbar(list_bg, orient="vertical", command=self.merge_list.yview, bg=_CARD_BG)
        sb.grid(row=0, column=1, sticky="ns", pady=4)
        self.merge_list.configure(yscrollcommand=sb.set)
        bb = ctk.CTkFrame(f, fg_color="transparent")
        bb.grid(row=2, column=0, sticky="w", pady=(8, 0))
        for text, cmd in [("Add…", self._merge_add), ("Remove", self._merge_remove),
                          ("↑ Up", lambda: self._merge_move(-1)),
                          ("↓ Down", lambda: self._merge_move(1)),
                          ("Clear", lambda: self.merge_list.delete(0, tk.END))]:
            _btn(bb, text, command=cmd, width=72).pack(side="left", padx=3)
        _label(f, "Stream-copy — cực nhanh, không mất chất lượng.", size=10, color=_FG_HINT
               ).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _build_edit_logo(self, tab):
        f = self._tf(tab)
        _label(f, "File logo (PNG/JPG):", size=12).grid(row=0, column=0, sticky="w", pady=(0, 6))
        lr = ctk.CTkFrame(f, fg_color="transparent")
        lr.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        lr.columnconfigure(0, weight=1)
        self.logo_path = _entry(lr, placeholder="Chọn file logo...", height=38)
        self.logo_path.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(lr, "📂 Browse", command=self._browse_logo, width=110).grid(row=0, column=1)
        _label(f, "Vị trí:", size=12).grid(row=2, column=0, sticky="w", pady=4)
        self.logo_pos = ctk.CTkComboBox(f, values=list(video_edit.LOGO_POSITIONS.keys()),
                                        state="readonly", width=180, fg_color=_ENTRY_BG,
                                        border_color=_BORDER, button_color=_ACCENT,
                                        font=("Segoe UI", 12), command=self._on_logo_pos_change)
        self.logo_pos.set("Bottom-Right")
        self.logo_pos.grid(row=2, column=1, sticky="w", padx=(10, 0))
        self._logo_custom_frame = ctk.CTkFrame(f, fg_color="transparent")
        self._logo_custom_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        _label(self._logo_custom_frame, "X:", size=12).grid(row=0, column=0, padx=(0, 4))
        self.logo_x = _entry(self._logo_custom_frame, width=110, height=34)
        self.logo_x.insert(0, "W-w-10")
        self.logo_x.grid(row=0, column=1, padx=(0, 16))
        _label(self._logo_custom_frame, "Y:", size=12).grid(row=0, column=2, padx=(0, 4))
        self.logo_y = _entry(self._logo_custom_frame, width=110, height=34)
        self.logo_y.insert(0, "H-h-20")
        self.logo_y.grid(row=0, column=3)
        self._logo_custom_frame.grid_remove()
        _label(f, "Scale (px rộng, 0=gốc):", size=12).grid(row=4, column=0, sticky="w", pady=4)
        self.logo_scale = _entry(f, width=100, height=36)
        self.logo_scale.insert(0, "150")
        self.logo_scale.grid(row=4, column=1, sticky="w", padx=(10, 0))
        _label(f, "Opacity (0.0–1.0):", size=12).grid(row=5, column=0, sticky="w", pady=4)
        self.logo_opacity = _entry(f, width=100, height=36)
        self.logo_opacity.insert(0, "1.00")
        self.logo_opacity.grid(row=5, column=1, sticky="w", padx=(10, 0))
        _label(f, "Dùng PNG có nền trong suốt để logo đẹp nhất.", size=10, color=_FG_HINT
               ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # ── Batch page ──────────────────────────────────────────────────────────────
    def _build_batch_page(self, host):
        page = ctk.CTkFrame(host, fg_color=_MAIN_BG, corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)
        self._pages["batch"] = page

        hdr = ctk.CTkFrame(page, fg_color=_SIDEBAR_BG, corner_radius=0, height=68)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        _label(hdr, "📦  Batch Edit", size=18, bold=True
               ).grid(row=0, column=0, padx=24, pady=(14, 1), sticky="w")
        _label(hdr, "Áp dụng cùng một thao tác cho nhiều video cùng lúc",
               size=9, color=_FG_DIM).grid(row=1, column=0, padx=26, pady=(0, 12), sticky="w")

        scroll = ctk.CTkScrollableFrame(page, fg_color=_MAIN_BG,
                                        scrollbar_button_color=_CARD_BG)
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        scroll.columnconfigure(0, weight=1)

        # File list card
        fc = _card(scroll)
        fc.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        fc.columnconfigure(0, weight=1)
        fi = ctk.CTkFrame(fc, fg_color="transparent")
        fi.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        fi.columnconfigure(0, weight=1)
        _section_title(fi, "DANH SÁCH FILE INPUT").grid(row=0, column=0, sticky="w", pady=(0, 8))
        lb_bg = ctk.CTkFrame(fi, fg_color=_ENTRY_BG, corner_radius=8,
                             border_color=_BORDER, border_width=1)
        lb_bg.grid(row=1, column=0, sticky="ew")
        lb_bg.columnconfigure(0, weight=1)
        self.batch_list = tk.Listbox(lb_bg, height=7, font=("Consolas", 10),
                                     bg=_ENTRY_BG, fg=_FG, selectbackground=_ACCENT,
                                     relief="flat", borderwidth=0, highlightthickness=0,
                                     activestyle="none")
        self.batch_list.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        sb2 = tk.Scrollbar(lb_bg, orient="vertical", command=self.batch_list.yview, bg=_CARD_BG)
        sb2.grid(row=0, column=1, sticky="ns", pady=4)
        self.batch_list.configure(yscrollcommand=sb2.set)
        bb2 = ctk.CTkFrame(fi, fg_color="transparent")
        bb2.grid(row=2, column=0, sticky="w", pady=(8, 0))
        for text, cmd in [("Add…", self._batch_add_files),
                          ("Remove", self._batch_remove_files),
                          ("Clear", lambda: self.batch_list.delete(0, tk.END))]:
            _btn(bb2, text, command=cmd, width=80).pack(side="left", padx=3)

        # Output dir card
        oc = _card(scroll)
        oc.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        oc.columnconfigure(0, weight=1)
        oi = ctk.CTkFrame(oc, fg_color="transparent")
        oi.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        oi.columnconfigure(0, weight=1)
        _section_title(oi, "THƯ MỤC OUTPUT  (để trống = cùng thư mục gốc)").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        or3 = ctk.CTkFrame(oi, fg_color="transparent")
        or3.grid(row=1, column=0, sticky="ew")
        or3.columnconfigure(0, weight=1)
        self.batch_out_dir = _entry(or3, placeholder="Chọn thư mục...", height=42)
        self.batch_out_dir.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(or3, "📂 Browse", command=self._batch_browse_out, width=110).grid(row=0, column=1)

        # Operation card
        opc = _card(scroll)
        opc.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        opc.columnconfigure(0, weight=1)
        opi = ctk.CTkFrame(opc, fg_color="transparent")
        opi.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        opi.columnconfigure(0, weight=1)
        _section_title(opi, "THAO TÁC ÁP DỤNG CHO TẤT CẢ FILE").grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        op_row = ctk.CTkFrame(opi, fg_color="transparent")
        op_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        _label(op_row, "Chọn thao tác:", size=12).pack(side="left", padx=(0, 10))
        _BATCH_OPS = ["📐 Resize", "🎵 Extract Audio", "🔇 Remove Audio",
                      "🔄 Convert", "⚡ Speed", "🔁 Rotate", "🖼 Logo"]
        self.batch_op = ctk.CTkComboBox(op_row, values=_BATCH_OPS, state="readonly",
                                        width=220, fg_color=_ENTRY_BG, border_color=_BORDER,
                                        button_color=_ACCENT, font=("Segoe UI", 12),
                                        command=self._on_batch_op_change)
        self.batch_op.set("📐 Resize")
        self.batch_op.pack(side="left")

        sh = ctk.CTkFrame(opi, fg_color="transparent")
        sh.grid(row=2, column=0, sticky="ew")
        sh.columnconfigure(0, weight=1)
        sh.columnconfigure(1, weight=1)
        self._batch_sf = {}

        def _r(parent, lbl, widget, row):
            _label(parent, lbl, size=12).grid(row=row, column=0, sticky="w", pady=3)
            widget.grid(row=row, column=1, sticky="w", padx=(10, 0))

        # Resize settings
        f1 = ctk.CTkFrame(sh, fg_color="transparent")
        f1.columnconfigure(1, weight=1)
        self.b_res_preset = ctk.CTkComboBox(f1, values=list(video_edit.PRESETS.keys()),
                                            state="readonly", width=220, fg_color=_ENTRY_BG,
                                            border_color=_BORDER, button_color=_ACCENT,
                                            font=("Segoe UI", 12), command=self._on_b_preset_change)
        self.b_res_preset.set("720p  (1280×720)")
        self.b_res_w = _entry(f1, width=100, height=34); self.b_res_w.insert(0, "1280")
        self.b_res_h = _entry(f1, width=100, height=34); self.b_res_h.insert(0, "720")
        _r(f1, "Preset:", self.b_res_preset, 0)
        _r(f1, "Width:", self.b_res_w, 1)
        _r(f1, "Height:", self.b_res_h, 2)
        self._batch_sf["📐 Resize"] = f1

        f2 = ctk.CTkFrame(sh, fg_color="transparent"); f2.columnconfigure(1, weight=1)
        self.b_audio_fmt = ctk.CTkComboBox(f2, values=["mp3","aac","wav","ogg","m4a"],
                                           state="readonly", width=120, fg_color=_ENTRY_BG,
                                           border_color=_BORDER, button_color=_ACCENT,
                                           font=("Segoe UI", 12))
        self.b_audio_fmt.set("mp3")
        _r(f2, "Định dạng:", self.b_audio_fmt, 0)
        self._batch_sf["🎵 Extract Audio"] = f2

        f3 = ctk.CTkFrame(sh, fg_color="transparent")
        _label(f3, "Xóa hoàn toàn âm thanh khỏi tất cả video đã chọn.", size=11, color=_FG_HINT
               ).pack(anchor="w", pady=4)
        self._batch_sf["🔇 Remove Audio"] = f3

        f4 = ctk.CTkFrame(sh, fg_color="transparent"); f4.columnconfigure(1, weight=1)
        self.b_conv_fmt = ctk.CTkComboBox(f4, values=video_edit.FORMATS, state="readonly",
                                          width=120, fg_color=_ENTRY_BG, border_color=_BORDER,
                                          button_color=_ACCENT, font=("Segoe UI", 12))
        self.b_conv_fmt.set("mp4")
        _r(f4, "Định dạng:", self.b_conv_fmt, 0)
        self._batch_sf["🔄 Convert"] = f4

        f5 = ctk.CTkFrame(sh, fg_color="transparent"); f5.columnconfigure(1, weight=1)
        self.b_speed = _entry(f5, width=100, height=34); self.b_speed.insert(0, "2.00")
        _r(f5, "Tốc độ (0.25–4.0):", self.b_speed, 0)
        self._batch_sf["⚡ Speed"] = f5

        f6 = ctk.CTkFrame(sh, fg_color="transparent"); f6.columnconfigure(1, weight=1)
        self.b_rotate = ctk.CTkComboBox(f6, values=list(video_edit.ROTATIONS.keys()),
                                        state="readonly", width=280, fg_color=_ENTRY_BG,
                                        border_color=_BORDER, button_color=_ACCENT,
                                        font=("Segoe UI", 12))
        self.b_rotate.set(list(video_edit.ROTATIONS.keys())[0])
        _r(f6, "Rotation:", self.b_rotate, 0)
        self._batch_sf["🔁 Rotate"] = f6

        f7 = ctk.CTkFrame(sh, fg_color="transparent"); f7.columnconfigure(1, weight=1)
        lr7 = ctk.CTkFrame(f7, fg_color="transparent"); lr7.columnconfigure(0, weight=1)
        lr7.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        _label(lr7, "File logo:", size=12).grid(row=0, column=0, sticky="w")
        lr7b = ctk.CTkFrame(lr7, fg_color="transparent"); lr7b.columnconfigure(0, weight=1)
        lr7b.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.b_logo_path = _entry(lr7b, placeholder="Chọn file logo...", height=36)
        self.b_logo_path.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        _btn(lr7b, "📂 Browse", command=self._b_browse_logo, width=100).grid(row=0, column=1)
        self.b_logo_pos = ctk.CTkComboBox(f7, values=list(video_edit.LOGO_POSITIONS.keys()),
                                          state="readonly", width=180, fg_color=_ENTRY_BG,
                                          border_color=_BORDER, button_color=_ACCENT,
                                          font=("Segoe UI", 12))
        self.b_logo_pos.set("Bottom-Right")
        self.b_logo_scale = _entry(f7, width=100, height=34); self.b_logo_scale.insert(0, "150")
        self.b_logo_opacity = _entry(f7, width=100, height=34); self.b_logo_opacity.insert(0, "1.00")
        _r(f7, "Vị trí:", self.b_logo_pos, 1)
        _r(f7, "Scale (px):", self.b_logo_scale, 2)
        _r(f7, "Opacity:", self.b_logo_opacity, 3)
        self._batch_sf["🖼 Logo"] = f7

        self._show_batch_sf("📐 Resize")

        self.batch_btn = _btn(scroll, "▶   Apply to All",
                              command=self._apply_batch, accent=True, height=48)
        self.batch_btn.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.batch_progress = ctk.CTkProgressBar(scroll, mode="determinate", height=6,
                                                 corner_radius=3, progress_color=_ACCENT,
                                                 fg_color=_CARD_BG)
        self.batch_progress.grid(row=4, column=0, sticky="ew", pady=(0, 4))
        self.batch_progress.set(0)
        self.batch_status_lbl = _label(scroll, "", size=11, color=_FG_DIM)
        self.batch_status_lbl.grid(row=5, column=0, sticky="w")

    # ── Log panel ──────────────────────────────────────────────────────────────
    def _build_log_panel(self, root):
        panel = ctk.CTkFrame(root, fg_color=_SIDEBAR_BG, corner_radius=0)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(panel, fg_color=_SIDEBAR_BG, corner_radius=0, height=68)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        _label(hdr, "📋  Activity Log", size=14, bold=True
               ).grid(row=0, column=0, padx=16, pady=(18, 0), sticky="w")

        log_frame = ctk.CTkFrame(panel, fg_color=_LOG_BG, corner_radius=0)
        log_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(6, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_box = tk.Text(log_frame, state="disabled", wrap="word",
                               font=("Consolas", 9), bg=_LOG_BG, fg=_FG,
                               relief="flat", borderwidth=0, highlightthickness=0,
                               padx=8, pady=6, insertbackground=_FG)
        self.log_box.grid(row=0, column=0, sticky="nsew")
        sb3 = tk.Scrollbar(log_frame, orient="vertical", command=self.log_box.yview, bg=_CARD_BG)
        sb3.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=sb3.set)
        self.log_box.tag_configure("ok",   foreground=_LOG_OK)
        self.log_box.tag_configure("err",  foreground=_LOG_ERR)
        self.log_box.tag_configure("info", foreground=_LOG_INFO)
        self.log_box.tag_configure("ts",   foreground=_LOG_TS)

        btm = ctk.CTkFrame(panel, fg_color=_SIDEBAR_BG, corner_radius=0, height=44)
        btm.grid(row=2, column=0, sticky="ew")
        btm.grid_propagate(False)
        btm.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        _label(btm, "", size=9, color=_FG_DIM, textvariable=self.status_var
               ).grid(row=0, column=0, sticky="w", padx=14, pady=12)
        _btn(btm, "🗑 Clear", command=self._clear_log, width=80
             ).grid(row=0, column=1, padx=10, pady=8)

    def _log(self, text, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, f"[{ts}] ", "ts")
        self.log_box.insert(tk.END, text + "\n", tag)
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")
        self.status_var.set(text[:80])

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        self.status_var.set("Ready")

    # ── Shared helpers ─────────────────────────────────────────────────────────
    def _open_output(self):
        path = self.out_entry.get().strip() or "downloads"
        if not os.path.exists(path):
            messagebox.showinfo("Info", "Thư mục output chưa tồn tại.")
            return
        try:
            os.startfile(path)
        except Exception:
            messagebox.showerror("Error", "Không thể mở thư mục.")

    def _on_preset_change(self, value):
        w, h = video_edit.PRESETS.get(value, (None, None))
        if w is not None:
            self.res_w.delete(0, tk.END); self.res_w.insert(0, str(w))
            self.res_h.delete(0, tk.END); self.res_h.insert(0, str(h))

    def _browse_edit_in(self):
        f = filedialog.askopenfilename(title="Chọn video input",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                       ("All files", "*.*")])
        if f:
            self.edit_in.delete(0, tk.END); self.edit_in.insert(0, f)

    def _browse_edit_out(self):
        f = filedialog.asksaveasfilename(title="Lưu file output",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm"),
                       ("Audio files", "*.mp3 *.aac *.wav *.ogg *.m4a"),
                       ("All files", "*.*")])
        if f:
            self.edit_out.delete(0, tk.END); self.edit_out.insert(0, f)

    def _browse_logo(self):
        f = filedialog.askopenfilename(title="Chọn file logo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if f:
            self.logo_path.delete(0, tk.END); self.logo_path.insert(0, f)

    def _on_logo_pos_change(self, value):
        if value == "Custom":
            self._logo_custom_frame.grid(row=3, column=0, columnspan=2, sticky="ew")
        else:
            self._logo_custom_frame.grid_remove()

    def _merge_add(self):
        files = filedialog.askopenfilenames(title="Chọn file video",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                       ("All files", "*.*")])
        for f in files:
            self.merge_list.insert(tk.END, f)

    def _merge_remove(self):
        for idx in reversed(self.merge_list.curselection()):
            self.merge_list.delete(idx)

    def _merge_move(self, direction):
        sel = list(self.merge_list.curselection())
        if not sel:
            return
        if direction == -1 and sel[0] == 0:
            return
        if direction == 1 and sel[-1] == self.merge_list.size() - 1:
            return
        for idx in (sel if direction == 1 else reversed(sel)):
            nb = idx + direction
            val = self.merge_list.get(idx)
            self.merge_list.delete(idx)
            self.merge_list.insert(nb, val)
            self.merge_list.selection_set(nb)

    def _show_batch_sf(self, op):
        for key, frame in self._batch_sf.items():
            frame.grid_remove()
        if op in self._batch_sf:
            self._batch_sf[op].grid(row=0, column=0, columnspan=2, sticky="ew")

    def _on_batch_op_change(self, value):
        self._show_batch_sf(value)

    def _on_b_preset_change(self, value):
        w, h = video_edit.PRESETS.get(value, (None, None))
        if w is not None:
            self.b_res_w.delete(0, tk.END); self.b_res_w.insert(0, str(w))
            self.b_res_h.delete(0, tk.END); self.b_res_h.insert(0, str(h))

    def _batch_add_files(self):
        files = filedialog.askopenfilenames(title="Chọn file video",
            filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                       ("All files", "*.*")])
        for f in files:
            self.batch_list.insert(tk.END, f)

    def _batch_remove_files(self):
        for idx in reversed(self.batch_list.curselection()):
            self.batch_list.delete(idx)

    def _batch_browse_out(self):
        folder = filedialog.askdirectory(title="Chọn thư mục output")
        if folder:
            self.batch_out_dir.delete(0, tk.END); self.batch_out_dir.insert(0, folder)

    def _b_browse_logo(self):
        f = filedialog.askopenfilename(title="Chọn file logo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                       ("All files", "*.*")])
        if f:
            self.b_logo_path.delete(0, tk.END); self.b_logo_path.insert(0, f)

    # ── Download logic ─────────────────────────────────────────────────────────
    def start_download(self):
        mode = self._dl_mode_bar.get()
        out = self.out_entry.get().strip() or "downloads"
        if mode == "  Single Video  ":
            url = self.url_single.get().strip()
            if not url:
                messagebox.showwarning("Warning", "Vui lòng nhập URL video.")
                return
            targets = [("single", url)]
        elif mode == "  Profile  ":
            url = self.url_profile.get().strip()
            if not url or url == "https://www.tiktok.com/@username":
                messagebox.showwarning("Warning", "Vui lòng nhập URL profile.")
                return
            mv = self.max_videos.get().strip()
            max_v = int(mv) if mv.isdigit() else None
            targets = [("profile", (url, max_v))]
        else:
            raw = self.multi_text.get("1.0", tk.END)
            urls = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if not urls:
                messagebox.showwarning("Warning", "Vui lòng nhập ít nhất một URL.")
                return
            targets = [("multi", urls)]
        if not os.path.exists(out):
            try:
                os.makedirs(out)
            except Exception as e:
                messagebox.showerror("Error", f"Không thể tạo thư mục:\n{e}")
                return
        self.download_btn.configure(state="disabled")
        self.dl_progress.configure(mode="indeterminate")
        self.dl_progress.start()
        threading.Thread(target=self._worker, args=(targets, out), daemon=True).start()

    def _worker(self, targets, out):
        try:
            for kind, payload in targets:
                if kind == "single":
                    self._log(f"Đang tải: {payload}", "info")
                    fn = download_tiktok_video(payload, out)
                    self._log(f"Hoàn thành: {fn}" if fn else f"Thất bại: {payload}",
                              "ok" if fn else "err")
                elif kind == "profile":
                    url, max_v = payload
                    self._log(f"Đang tải profile: {url}", "info")
                    ok = download_from_profile(url, out, max_v)
                    self._log("Tải profile hoàn thành." if ok else "Tải profile thất bại.",
                              "ok" if ok else "err")
                else:
                    for url in payload:
                        self._log(f"Đang tải: {url}", "info")
                        fn = download_tiktok_video(url, out)
                        self._log(f"Hoàn thành: {fn}" if fn else f"Thất bại: {url}",
                                  "ok" if fn else "err")
        except Exception as e:
            self._log(f"Lỗi: {e}", "err")
        finally:
            self.download_btn.configure(state="normal")
            self.dl_progress.stop()
            self.dl_progress.set(0)

    # ── Edit logic ─────────────────────────────────────────────────────────────
    def _apply_edit(self):
        inp = self.edit_in.get().strip()
        if not inp or not os.path.isfile(inp):
            messagebox.showwarning("Warning", "Vui lòng chọn file video hợp lệ.")
            return
        out = self.edit_out.get().strip() or None
        tab = self.op_tabview.get()
        self.edit_btn.configure(state="disabled")
        self.edit_progress.configure(mode="indeterminate")
        self.edit_progress.start()
        threading.Thread(target=self._edit_worker, args=(tab, inp, out), daemon=True).start()

    def _edit_worker(self, tab, inp, out):
        try:
            if tab == "📐 Resize":
                w, h = int(self.res_w.get()), int(self.res_h.get())
                self._log(f"📐 Resize {w}×{h}: {os.path.basename(inp)}", "info")
                result = video_edit.resize_video(inp, w, h, out)
            elif tab == "🎵 Audio":
                if self.audio_mode.get() == "extract":
                    fmt = self.audio_fmt.get()
                    self._log(f"🎵 Extract audio ({fmt}): {os.path.basename(inp)}", "info")
                    result = video_edit.extract_audio(inp, fmt, out)
                else:
                    self._log(f"🔇 Remove audio: {os.path.basename(inp)}", "info")
                    result = video_edit.remove_audio(inp, out)
            elif tab == "🔄 Convert":
                fmt = self.conv_fmt.get()
                self._log(f"🔄 Convert → {fmt}: {os.path.basename(inp)}", "info")
                result = video_edit.convert_format(inp, fmt, out)
            elif tab == "⚡ Speed":
                try:
                    speed = float(self.spd_value.get())
                except ValueError:
                    speed = 1.0
                self._log(f"⚡ Speed {speed}×: {os.path.basename(inp)}", "info")
                result = video_edit.speed_video(inp, speed, out)
            elif tab == "🔁 Rotate":
                rotation = self.rot_choice.get()
                self._log(f"🔁 Rotate ({rotation}): {os.path.basename(inp)}", "info")
                result = video_edit.rotate_video(inp, rotation, out)
            elif tab == "🎬 Merge":
                paths = list(self.merge_list.get(0, tk.END))
                if not paths:
                    self._log("Merge: chưa có file nào trong danh sách.", "err")
                    return
                self._log(f"🎬 Ghép {len(paths)} file...", "info")
                result = video_edit.merge_videos(paths, out)
            else:  # Logo
                logo = self.logo_path.get().strip()
                if not logo or not os.path.isfile(logo):
                    self._log("Logo: chưa chọn file logo hợp lệ.", "err")
                    return
                pos = self.logo_pos.get()
                cx  = self.logo_x.get().strip()  or "W-w-10"
                cy  = self.logo_y.get().strip()  or "H-h-20"
                try:
                    scale = int(self.logo_scale.get())
                except ValueError:
                    scale = 150
                try:
                    opacity = float(self.logo_opacity.get())
                    opacity = max(0.0, min(1.0, opacity))
                except ValueError:
                    opacity = 1.0
                self._log(f"🖼 Logo ({pos}): {os.path.basename(inp)}", "info")
                result = video_edit.add_logo(inp, logo, pos, cx, cy, scale, opacity, out)
            self._log(f"Hoàn thành: {result}", "ok")
        except Exception as e:
            self._log(f"Lỗi edit: {e}", "err")
        finally:
            self.edit_btn.configure(state="normal")
            self.edit_progress.stop()
            self.edit_progress.set(0)

    # ── Batch logic ────────────────────────────────────────────────────────────
    def _apply_batch(self):
        files = list(self.batch_list.get(0, tk.END))
        if not files:
            messagebox.showwarning("Warning", "Chưa có file nào trong danh sách.")
            return
        op = self.batch_op.get()
        out_dir = self.batch_out_dir.get().strip()
        if out_dir and not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Không thể tạo thư mục:\n{e}")
                return
        self.batch_btn.configure(state="disabled")
        self.batch_progress.set(0)
        self.batch_status_lbl.configure(text="")
        threading.Thread(target=self._batch_worker, args=(files, op, out_dir), daemon=True).start()

    def _batch_worker(self, files, op, out_dir):
        ok_count = err_count = 0
        total = len(files)
        try:
            for i, inp in enumerate(files):
                name = os.path.basename(inp)
                base, orig_ext = os.path.splitext(name)
                src_dir = os.path.dirname(inp)

                def _out(suffix, ext=""):
                    fname = f"{base}_{suffix}{ext or orig_ext}"
                    return os.path.join(out_dir or src_dir, fname)

                try:
                    self._log(f"[{i+1}/{total}] {op}: {name}", "info")
                    if op == "📐 Resize":
                        w, h = int(self.b_res_w.get()), int(self.b_res_h.get())
                        result = video_edit.resize_video(inp, w, h, _out(f"{w}x{h}"))
                    elif op == "🎵 Extract Audio":
                        fmt = self.b_audio_fmt.get()
                        result = video_edit.extract_audio(inp, fmt, _out("audio", f".{fmt}"))
                    elif op == "🔇 Remove Audio":
                        result = video_edit.remove_audio(inp, _out("noaudio"))
                    elif op == "🔄 Convert":
                        fmt = self.b_conv_fmt.get()
                        result = video_edit.convert_format(inp, fmt, _out("converted", f".{fmt}"))
                    elif op == "⚡ Speed":
                        try:
                            speed = float(self.b_speed.get())
                        except ValueError:
                            speed = 1.0
                        result = video_edit.speed_video(inp, speed, _out(f"speed{speed}"))
                    elif op == "🔁 Rotate":
                        result = video_edit.rotate_video(inp, self.b_rotate.get(), _out("rotated"))
                    elif op == "🖼 Logo":
                        logo = self.b_logo_path.get().strip()
                        if not logo or not os.path.isfile(logo):
                            self._log(f"  ✗ Logo không hợp lệ, bỏ qua: {name}", "err")
                            err_count += 1
                            continue
                        pos = self.b_logo_pos.get()
                        try:
                            scale = int(self.b_logo_scale.get())
                        except ValueError:
                            scale = 150
                        try:
                            opacity = float(self.b_logo_opacity.get())
                            opacity = max(0.0, min(1.0, opacity))
                        except ValueError:
                            opacity = 1.0
                        result = video_edit.add_logo(inp, logo, pos, "W-w-10", "H-h-20",
                                                     scale, opacity, _out("logo"))
                    else:
                        result = inp
                    self._log(f"  ✓ → {os.path.basename(result)}", "ok")
                    ok_count += 1
                except Exception as e:
                    self._log(f"  ✗ Lỗi: {e}", "err")
                    err_count += 1
                finally:
                    self.batch_progress.set((i + 1) / total)
                    self.batch_status_lbl.configure(
                        text=f"{i+1}/{total}  —  ✓ {ok_count}   ✗ {err_count}")
        finally:
            self.batch_btn.configure(state="normal")
            tag = "ok" if err_count == 0 else "err"
            self._log(f"Batch xong: {ok_count}/{total} thành công, {err_count} lỗi.", tag)
            self.batch_status_lbl.configure(
                text=f"Xong — ✓ {ok_count}   ✗ {err_count}   / {total} file")


if __name__ == "__main__":
    root = ctk.CTk()
    app = App(root)
    try:
        root.state("zoomed")
    except Exception:
        try:
            root.attributes("-zoomed", True)
        except Exception:
            pass
    root.mainloop()
