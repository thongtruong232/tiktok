import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

from tiktok_download import download_tiktok_video, download_from_profile
import video_edit

# ── Colour palette (TikTok-inspired) ──────────────────────────────────────────
_ACCENT      = "#EE1D52"   # TikTok red
_ACCENT_DARK = "#c41644"
_HDR_BG      = "#010101"   # TikTok near-black
_HDR_FG      = "#ffffff"
_BG          = "#f4f4f6"
_CARD_BG     = "#ffffff"
_CARD_BORDER = "#e0e0e0"
_FG          = "#222222"
_FG_DIM      = "#888888"
_LOG_BG      = "#fafafa"
_STATUS_BG   = "#ececec"


def _apply_style(root: tk.Tk) -> None:
    s = ttk.Style(root)
    s.theme_use('clam')

    s.configure('TFrame',            background=_BG)
    s.configure('TLabel',            background=_BG, foreground=_FG,
                                     font=('Segoe UI', 10))
    s.configure('TButton',           font=('Segoe UI', 10), padding=(8, 5))
    s.configure('TEntry',            fieldbackground=_CARD_BG,
                                     font=('Segoe UI', 10))
    s.configure('TNotebook',         background=_BG, borderwidth=0)
    s.configure('TNotebook.Tab',     font=('Segoe UI', 10), padding=(14, 6))
    s.map('TNotebook.Tab',
          foreground=[('selected', _ACCENT)],
          background=[('selected', _CARD_BG), ('!selected', _BG)])
    s.configure('TProgressbar',      troughcolor='#e0e0e0', background=_ACCENT)

    # Header
    s.configure('Header.TFrame',     background=_HDR_BG)
    s.configure('Header.TLabel',     background=_HDR_BG, foreground=_HDR_FG,
                                     font=('Segoe UI', 17, 'bold'))
    s.configure('Sub.TLabel',        background=_HDR_BG, foreground='#888888',
                                     font=('Segoe UI', 9))

    # Accent download button
    s.configure('Accent.TButton',    background=_ACCENT, foreground='white',
                                     font=('Segoe UI', 11, 'bold'), padding=(14, 8))
    s.map('Accent.TButton',
          background=[('active', _ACCENT_DARK), ('disabled', '#cccccc')],
          foreground=[('disabled', '#888888')])

    # Card LabelFrame
    s.configure('Card.TLabelframe',  background=_CARD_BG, relief='flat',
                                     bordercolor=_CARD_BORDER, borderwidth=1)
    s.configure('Card.TLabelframe.Label',
                                     background=_CARD_BG, foreground='#555555',
                                     font=('Segoe UI', 9, 'bold'))

    # Status bar
    s.configure('Status.TLabel',     background=_STATUS_BG, foreground='#555555',
                                     font=('Segoe UI', 9))

    # Hint text (small grey)
    s.configure('Hint.TLabel',       background=_CARD_BG, foreground=_FG_DIM,
                                     font=('Segoe UI', 8))

    root.configure(bg=_BG)


def browse_dir(entry: ttk.Entry) -> None:
    d = filedialog.askdirectory()
    if d:
        entry.delete(0, tk.END)
        entry.insert(0, d)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("TikTok Downloader")
        root.geometry("980x620")
        root.minsize(840, 500)
        root.resizable(True, True)

        _apply_style(root)

        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)   # main content expands

        self._build_header(root)
        self._build_main(root)
        self._build_statusbar(root)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self, root: tk.Tk) -> None:
        hdr = ttk.Frame(root, style='Header.TFrame', height=68)
        hdr.grid(row=0, column=0, sticky='ew')
        hdr.columnconfigure(0, weight=1)
        hdr.grid_propagate(False)
        ttk.Label(hdr, text='\u25cf  TikTok Downloader',
                  style='Header.TLabel').grid(row=0, column=0,
                                              padx=20, pady=(14, 1), sticky='w')
        ttk.Label(hdr, text='Created by thongtruong',
                  style='Sub.TLabel').grid(row=1, column=0,
                                           padx=22, pady=(0, 10), sticky='w')

    # ── Main two-column layout ────────────────────────────────────────────────
    def _build_main(self, root: tk.Tk) -> None:
        main = ttk.Frame(root, padding=(14, 12, 14, 8))
        main.grid(row=1, column=0, sticky='nsew')
        main.columnconfigure(0, minsize=340, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        self._build_left(main)
        self._build_right(main)

    # ── Left panel (Download + Edit Video pages) ─────────────────────────────
    def _build_left(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        # Top-level page notebook
        outer_nb = ttk.Notebook(left)
        outer_nb.grid(row=0, column=0, sticky='nsew')

        # ─── Download page ─────────────────────────────────────────────────
        dl_page = ttk.Frame(outer_nb, padding=(0, 8, 0, 0))
        dl_page.columnconfigure(0, weight=1)
        dl_page.rowconfigure(0, weight=1)
        outer_nb.add(dl_page, text='  ⬇  Download  ')

        # Mode notebook
        nb = ttk.Notebook(dl_page)
        nb.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.notebook = nb

        # Tab: Single
        t1 = ttk.Frame(nb, padding=12)
        nb.add(t1, text='  Single URL  ')
        t1.columnconfigure(0, weight=1)
        ttk.Label(t1, text='Video URL',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 4))
        self.url_single = ttk.Entry(t1)
        self.url_single.grid(row=1, column=0, sticky='ew')
        ttk.Label(t1, text='Dán link video TikTok vào ô trên.',
                  style='Hint.TLabel').grid(
            row=2, column=0, sticky='w', pady=(4, 0))

        # Tab: Profile
        t2 = ttk.Frame(nb, padding=12)
        nb.add(t2, text='  Profile  ')
        t2.columnconfigure(0, weight=1)
        ttk.Label(t2, text='Profile URL',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 4))
        self.url_profile = ttk.Entry(t2)
        self.url_profile.insert(0, 'https://www.tiktok.com/@username')
        self.url_profile.grid(row=1, column=0, sticky='ew')
        ttk.Label(t2, text='Số video tối đa (để trống = tất cả)',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=2, column=0, sticky='w', pady=(12, 4))
        self.max_videos = ttk.Entry(t2, width=10)
        self.max_videos.grid(row=3, column=0, sticky='w')

        # Tab: Multiple URLs
        t3 = ttk.Frame(nb, padding=12)
        nb.add(t3, text='  URLs  ')
        t3.columnconfigure(0, weight=1)
        t3.rowconfigure(1, weight=1)
        ttk.Label(t3, text='Danh sách URL (mỗi dòng một link)',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 4))
        self.multi_text = scrolledtext.ScrolledText(
            t3, width=36, height=8, wrap='none',
            font=('Consolas', 9), relief='flat',
            bg=_CARD_BG, borderwidth=1,
            highlightthickness=1,
            highlightcolor=_CARD_BORDER,
            highlightbackground=_CARD_BORDER)
        self.multi_text.grid(row=1, column=0, sticky='nsew')

        # Output folder
        out_lf = ttk.LabelFrame(dl_page, text='Output Folder',
                                padding=(10, 8), style='Card.TLabelframe')
        out_lf.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        out_lf.columnconfigure(0, weight=1)
        self.out_entry = ttk.Entry(out_lf)
        self.out_entry.insert(0, 'downloads')
        self.out_entry.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        btn_out = ttk.Frame(out_lf)
        btn_out.grid(row=1, column=0, sticky='w')
        ttk.Button(btn_out, text='Browse…',
                   command=lambda: browse_dir(self.out_entry)).pack(side='left')
        ttk.Button(btn_out, text='Open Folder',
                   command=self._open_output).pack(side='left', padx=(8, 0))

        # Download button + progress
        self.download_btn = ttk.Button(dl_page, text='▶   Start Download',
                                       command=self.start_download,
                                       style='Accent.TButton')
        self.download_btn.grid(row=2, column=0, sticky='ew', ipady=4)
        self.progress = ttk.Progressbar(dl_page, mode='indeterminate')
        self.progress.grid(row=3, column=0, sticky='ew', pady=(8, 0))

        # ─── Edit Video page ───────────────────────────────────────────────
        edit_page = ttk.Frame(outer_nb, padding=(0, 8, 0, 0))
        edit_page.columnconfigure(0, weight=1)
        edit_page.rowconfigure(1, weight=1)
        outer_nb.add(edit_page, text='  ✂  Edit Video  ')
        self._build_edit_tab(edit_page)

    # ── Edit Video tab ────────────────────────────────────────────────────────
    def _build_edit_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        # Input file
        in_lf = ttk.LabelFrame(parent, text='Input File',
                               padding=(10, 8), style='Card.TLabelframe')
        in_lf.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        in_lf.columnconfigure(0, weight=1)
        self.edit_in = ttk.Entry(in_lf)
        self.edit_in.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        ttk.Button(in_lf, text='Browse…',
                   command=self._browse_edit_in).grid(row=0, column=1)

        # Operation sub-notebook
        op_nb = ttk.Notebook(parent)
        op_nb.grid(row=1, column=0, sticky='nsew', pady=(0, 8))
        self.op_nb = op_nb
        self._build_resize_tab(op_nb)
        self._build_audio_tab(op_nb)
        self._build_convert_tab(op_nb)
        self._build_speed_tab(op_nb)
        self._build_rotate_tab(op_nb)
        self._build_merge_tab(op_nb)
        self._build_logo_tab(op_nb)

        # Output file
        out_lf = ttk.LabelFrame(parent, text='Output File  (để trống = tự động)',
                                padding=(10, 8), style='Card.TLabelframe')
        out_lf.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        out_lf.columnconfigure(0, weight=1)
        self.edit_out = ttk.Entry(out_lf)
        self.edit_out.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        ttk.Button(out_lf, text='Browse…',
                   command=self._browse_edit_out).grid(row=0, column=1)

        # Apply button + progress
        self.edit_btn = ttk.Button(parent, text='▶   Apply Edit',
                                   command=self._apply_edit,
                                   style='Accent.TButton')
        self.edit_btn.grid(row=3, column=0, sticky='ew', ipady=4)
        self.edit_progress = ttk.Progressbar(parent, mode='indeterminate')
        self.edit_progress.grid(row=4, column=0, sticky='ew', pady=(8, 0))

    # ── Edit sub-tab builders ─────────────────────────────────────────────────
    def _build_speed_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  ⚡ Speed  ')
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Speed multiplier').grid(row=0, column=0, sticky='w', pady=4)
        self.spd_value = ttk.Spinbox(f, from_=0.25, to=4.0, increment=0.25, width=8,
                                     format='%.2f')
        self.spd_value.set('2.00')
        self.spd_value.grid(row=0, column=1, sticky='w', padx=(8, 0))
        examples = [
            ('0.50×', '0.50'), ('0.75×', '0.75'), ('1.00×  (gốc)', '1.00'),
            ('1.50×', '1.50'), ('2.00×', '2.00'), ('4.00×', '4.00'),
        ]
        ttk.Label(f, text='Ví dụ nhanh:').grid(row=1, column=0, sticky='w', pady=(10, 2))
        btn_row = ttk.Frame(f)
        btn_row.grid(row=2, column=0, columnspan=2, sticky='w')
        for label, val in examples:
            ttk.Button(btn_row, text=label, width=9,
                       command=lambda v=val: (self.spd_value.delete(0, tk.END),
                                             self.spd_value.insert(0, v))
                       ).pack(side='left', padx=2)
        ttk.Label(f, text='< 1.0 = chậm hơn  |  > 1.0 = nhanh hơn  |  phạm vi: 0.25 – 4.0',
                  style='Hint.TLabel').grid(row=3, column=0, columnspan=2, sticky='w', pady=(10, 0))

    def _build_rotate_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  🔄 Rotate  ')
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Rotation / Flip').grid(row=0, column=0, sticky='w', pady=4)
        self.rot_choice = ttk.Combobox(f, state='readonly', width=26,
                                       values=list(video_edit.ROTATIONS.keys()))
        self.rot_choice.set('90°  clockwise')
        self.rot_choice.grid(row=0, column=1, sticky='w', padx=(8, 0))
        ttk.Label(f, text='Áp dụng bộ lọc vf của FFmpeg, video được re-encode.',
                  style='Hint.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(10, 0))

    def _build_merge_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  🎬 Merge  ')
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        ttk.Label(f, text='Danh sách file video (kéo thả hoặc dùng nút Add):',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        self.merge_list = tk.Listbox(f, selectmode='extended', height=6,
                                     font=('Consolas', 9), relief='flat',
                                     bg=_CARD_BG,
                                     highlightthickness=1,
                                     highlightbackground=_CARD_BORDER)
        self.merge_list.grid(row=1, column=0, sticky='nsew')
        sb = ttk.Scrollbar(f, orient='vertical', command=self.merge_list.yview)
        sb.grid(row=1, column=1, sticky='ns')
        self.merge_list.configure(yscrollcommand=sb.set)
        btn_bar = ttk.Frame(f)
        btn_bar.grid(row=2, column=0, sticky='w', pady=(6, 0))
        ttk.Button(btn_bar, text='Add…',    command=self._merge_add).pack(side='left')
        ttk.Button(btn_bar, text='Remove',  command=self._merge_remove).pack(side='left', padx=(6, 0))
        ttk.Button(btn_bar, text='Up ↑',    command=lambda: self._merge_move(-1)).pack(side='left', padx=(6, 0))
        ttk.Button(btn_bar, text='Down ↓',  command=lambda: self._merge_move(1)).pack(side='left', padx=(6, 0))
        ttk.Button(btn_bar, text='Clear',   command=lambda: self.merge_list.delete(0, tk.END)).pack(side='left', padx=(12, 0))
        ttk.Label(f, text='Stream-copy — cực nhanh, không mất chất lượng. Định dạng các file phải giống nhau.',
                  style='Hint.TLabel').grid(row=3, column=0, columnspan=2, sticky='w', pady=(6, 0))

    def _merge_add(self) -> None:
        files = filedialog.askopenfilenames(
            title='Chọn file video',
            filetypes=[('Video files', '*.mp4 *.mkv *.avi *.mov *.webm *.flv'),
                       ('All files', '*.*')])
        for f in files:
            self.merge_list.insert(tk.END, f)

    def _merge_remove(self) -> None:
        for idx in reversed(self.merge_list.curselection()):
            self.merge_list.delete(idx)

    def _merge_move(self, direction: int) -> None:
        sel = list(self.merge_list.curselection())
        if not sel:
            return
        if direction == -1 and sel[0] == 0:
            return
        if direction == 1 and sel[-1] == self.merge_list.size() - 1:
            return
        for idx in (sel if direction == 1 else reversed(sel)):
            neighbour = idx + direction
            val = self.merge_list.get(idx)
            self.merge_list.delete(idx)
            self.merge_list.insert(neighbour, val)
            self.merge_list.selection_set(neighbour)

    def _build_logo_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  🖼 Logo  ')
        f.columnconfigure(1, weight=1)

        # Logo file
        ttk.Label(f, text='File logo (PNG/JPG):',
                  font=('Segoe UI', 9, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 4))
        logo_row = ttk.Frame(f)
        logo_row.grid(row=1, column=0, columnspan=2, sticky='ew')
        logo_row.columnconfigure(0, weight=1)
        self.logo_path = ttk.Entry(logo_row)
        self.logo_path.grid(row=0, column=0, sticky='ew', padx=(0, 6))
        ttk.Button(logo_row, text='Browse…',
                   command=self._browse_logo).grid(row=0, column=1)

        # Position
        ttk.Label(f, text='Vị trí:').grid(row=2, column=0, sticky='w', pady=(10, 4))
        self.logo_pos = ttk.Combobox(f, state='readonly', width=18,
                                     values=list(video_edit.LOGO_POSITIONS.keys()))
        self.logo_pos.set('Bottom-Right')
        self.logo_pos.grid(row=2, column=1, sticky='w', padx=(8, 0))
        self.logo_pos.bind('<<ComboboxSelected>>', self._on_logo_pos_change)

        # Custom x/y (hidden by default)
        self._logo_custom_frame = ttk.Frame(f)
        self._logo_custom_frame.grid(row=3, column=0, columnspan=2, sticky='ew')
        ttk.Label(self._logo_custom_frame, text='X expr:').grid(
            row=0, column=0, sticky='w', pady=2)
        self.logo_x = ttk.Entry(self._logo_custom_frame, width=14)
        self.logo_x.insert(0, 'W-w-10')
        self.logo_x.grid(row=0, column=1, sticky='w', padx=(6, 20))
        ttk.Label(self._logo_custom_frame, text='Y expr:').grid(
            row=0, column=2, sticky='w', pady=2)
        self.logo_y = ttk.Entry(self._logo_custom_frame, width=14)
        self.logo_y.insert(0, 'H-h-20')
        self.logo_y.grid(row=0, column=3, sticky='w', padx=(6, 0))
        self._logo_custom_frame.grid_remove()   # hide initially

        # Scale
        ttk.Label(f, text='Scale (px rộng, 0=gốc):').grid(
            row=4, column=0, sticky='w', pady=(10, 4))
        self.logo_scale = ttk.Spinbox(f, from_=0, to=1920, increment=10, width=8)
        self.logo_scale.set('150')
        self.logo_scale.grid(row=4, column=1, sticky='w', padx=(8, 0))

        # Opacity
        ttk.Label(f, text='Opacity (0.0 – 1.0):').grid(
            row=5, column=0, sticky='w', pady=(6, 4))
        self.logo_opacity = ttk.Spinbox(f, from_=0.0, to=1.0, increment=0.05,
                                        width=8, format='%.2f')
        self.logo_opacity.set('1.00')
        self.logo_opacity.grid(row=5, column=1, sticky='w', padx=(8, 0))

        ttk.Label(f,
                  text='Dùng PNG có nền trong suốt để logo đẹp nhất.',
                  style='Hint.TLabel').grid(
            row=6, column=0, columnspan=2, sticky='w', pady=(10, 0))

    def _browse_logo(self) -> None:
        f = filedialog.askopenfilename(
            title='Chọn file logo',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.gif *.bmp *.webp'),
                       ('All files', '*.*')])
        if f:
            self.logo_path.delete(0, tk.END)
            self.logo_path.insert(0, f)

    def _on_logo_pos_change(self, _event=None) -> None:
        if self.logo_pos.get() == 'Custom':
            self._logo_custom_frame.grid()
        else:
            self._logo_custom_frame.grid_remove()

    def _build_resize_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  📐 Resize  ')
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Preset').grid(row=0, column=0, sticky='w', pady=4)
        self.res_preset = ttk.Combobox(f, state='readonly', width=22,
                                       values=list(video_edit.PRESETS.keys()))
        self.res_preset.set('720p  (1280×720)')
        self.res_preset.grid(row=0, column=1, sticky='w', padx=(8, 0))
        self.res_preset.bind('<<ComboboxSelected>>', self._on_preset_change)
        ttk.Label(f, text='Width').grid(row=1, column=0, sticky='w', pady=4)
        self.res_w = ttk.Entry(f, width=8)
        self.res_w.insert(0, '1280')
        self.res_w.grid(row=1, column=1, sticky='w', padx=(8, 0))
        ttk.Label(f, text='Height').grid(row=2, column=0, sticky='w', pady=4)
        self.res_h = ttk.Entry(f, width=8)
        self.res_h.insert(0, '720')
        self.res_h.grid(row=2, column=1, sticky='w', padx=(8, 0))
        ttk.Label(f, text='Dùng -1 cho một chiều để giữ tỉ lệ khung hình.',
                  style='Hint.TLabel').grid(row=3, column=0, columnspan=2, sticky='w', pady=(10, 0))

    def _build_audio_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  🎵 Audio  ')
        f.columnconfigure(1, weight=1)
        self.audio_mode = tk.StringVar(value='extract')
        ttk.Radiobutton(f, text='Extract audio  (lấy âm thanh ra file riêng)',
                        variable=self.audio_mode, value='extract').grid(
            row=0, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Radiobutton(f, text='Remove audio  (tắt tiếng video)',
                        variable=self.audio_mode, value='remove').grid(
            row=1, column=0, columnspan=2, sticky='w', pady=4)
        ttk.Label(f, text='Format').grid(row=2, column=0, sticky='w', pady=(14, 4))
        self.audio_fmt = ttk.Combobox(f, state='readonly', width=8,
                                      values=['mp3', 'aac', 'wav', 'ogg', 'm4a'])
        self.audio_fmt.set('mp3')
        self.audio_fmt.grid(row=2, column=1, sticky='w', padx=(8, 0))
        ttk.Label(f, text='(áp dụng khi extract)',
                  style='Hint.TLabel').grid(row=3, column=0, columnspan=2, sticky='w')

    def _build_convert_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=12)
        nb.add(f, text='  🔄 Convert  ')
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text='Output format').grid(row=0, column=0, sticky='w', pady=4)
        self.conv_fmt = ttk.Combobox(f, state='readonly', width=10,
                                     values=video_edit.FORMATS)
        self.conv_fmt.set('mp4')
        self.conv_fmt.grid(row=0, column=1, sticky='w', padx=(8, 0))
        ttk.Label(f, text='FFmpeg tự chọn codec phù hợp cho container.',
                  style='Hint.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=(10, 0))

    # ── Right panel (log) ─────────────────────────────────────────────────────
    def _build_right(self, parent: ttk.Frame) -> None:
        right = ttk.LabelFrame(parent, text='Activity Log',
                               padding=(10, 8), style='Card.TLabelframe')
        right.grid(row=0, column=1, sticky='nsew')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.log_box = scrolledtext.ScrolledText(
            right, state='disabled', wrap='word',
            font=('Consolas', 9), relief='flat',
            bg=_LOG_BG, borderwidth=0,
            highlightthickness=1,
            highlightcolor=_CARD_BORDER,
            highlightbackground=_CARD_BORDER)
        self.log_box.grid(row=0, column=0, sticky='nsew')

        # Colour tags
        self.log_box.tag_configure('ok',   foreground='#2e7d32')  # green
        self.log_box.tag_configure('err',  foreground='#c62828')  # red
        self.log_box.tag_configure('info', foreground='#1565c0')  # blue
        self.log_box.tag_configure('ts',   foreground='#aaaaaa')  # grey

        ttk.Button(right, text='Clear Log',
                   command=self._clear_log).grid(
            row=1, column=0, sticky='e', pady=(8, 0))

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self, root: tk.Tk) -> None:
        self.status_var = tk.StringVar(value='Ready')
        ttk.Label(root, textvariable=self.status_var,
                  style='Status.TLabel', anchor='w',
                  padding=(12, 4)).grid(row=2, column=0, sticky='ew')

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _open_output(self) -> None:
        path = self.out_entry.get().strip() or 'downloads'
        if not os.path.exists(path):
            messagebox.showinfo('Info', 'Output folder does not exist yet.')
            return
        try:
            os.startfile(path)
        except Exception:
            messagebox.showerror('Error', 'Cannot open folder on this platform.')

    def _log(self, text: str, tag: str = 'info') -> None:
        ts = datetime.now().strftime('%H:%M:%S')
        self.log_box.configure(state='normal')
        self.log_box.insert(tk.END, f'[{ts}] ', 'ts')
        self.log_box.insert(tk.END, text + '\n', tag)
        self.log_box.see(tk.END)
        self.log_box.configure(state='disabled')
        self.status_var.set(text)

    def _clear_log(self) -> None:
        self.log_box.configure(state='normal')
        self.log_box.delete('1.0', tk.END)
        self.log_box.configure(state='disabled')
        self.status_var.set('Ready')

    # ── Download logic ────────────────────────────────────────────────────────
    def start_download(self) -> None:
        tab_idx = self.notebook.index(self.notebook.select())
        out = self.out_entry.get().strip() or 'downloads'

        if tab_idx == 0:
            url = self.url_single.get().strip()
            if not url:
                messagebox.showwarning('Warning', 'Vui lòng nhập URL video.')
                return
            targets = [('single', url)]

        elif tab_idx == 1:
            url = self.url_profile.get().strip()
            if not url or url == 'https://www.tiktok.com/@username':
                messagebox.showwarning('Warning', 'Vui lòng nhập URL profile.')
                return
            mv = self.max_videos.get().strip()
            max_v = int(mv) if mv.isdigit() else None
            targets = [('profile', (url, max_v))]

        else:
            lines = self.multi_text.get('1.0', tk.END).splitlines()
            urls = [ln.strip() for ln in lines if ln.strip()]
            if not urls:
                messagebox.showwarning('Warning', 'Vui lòng nhập ít nhất một URL.')
                return
            targets = [('multi', urls)]

        if not os.path.exists(out):
            try:
                os.makedirs(out)
            except Exception as e:
                messagebox.showerror('Error', f'Không thể tạo thư mục:\n{e}')
                return

        self.download_btn.state(['disabled'])
        self.progress.start(10)
        threading.Thread(target=self._worker,
                         args=(targets, out), daemon=True).start()

    def _worker(self, targets: list, out: str) -> None:
        try:
            for kind, payload in targets:
                if kind == 'single':
                    self._log(f'Đang tải: {payload}', 'info')
                    fn = download_tiktok_video(payload, out)
                    if fn:
                        self._log(f'Hoàn thành: {fn}', 'ok')
                    else:
                        self._log(f'Thất bại: {payload}', 'err')

                elif kind == 'profile':
                    url, max_v = payload
                    self._log(f'Đang tải profile: {url}', 'info')
                    ok = download_from_profile(url, out, max_v)
                    if ok:
                        self._log('Tải profile hoàn thành.', 'ok')
                    else:
                        self._log('Tải profile thất bại.', 'err')

                else:   # multiple
                    for url in payload:
                        self._log(f'Đang tải: {url}', 'info')
                        fn = download_tiktok_video(url, out)
                        if fn:
                            self._log(f'Hoàn thành: {fn}', 'ok')
                        else:
                            self._log(f'Thất bại: {url}', 'err')

        except Exception as e:
            self._log(f'Lỗi: {e}', 'err')
        finally:
            try:
                self.download_btn.state(['!disabled'])
            except Exception:
                self.download_btn.config(state='normal')
            try:
                self.progress.stop()
            except Exception:
                pass

    # ── Edit helpers ──────────────────────────────────────────────────────────
    def _browse_edit_in(self) -> None:
        f = filedialog.askopenfilename(
            title='Chọn video input',
            filetypes=[('Video files', '*.mp4 *.mkv *.avi *.mov *.webm *.flv'),
                       ('All files', '*.*')])
        if f:
            self.edit_in.delete(0, tk.END)
            self.edit_in.insert(0, f)

    def _browse_edit_out(self) -> None:
        f = filedialog.asksaveasfilename(
            title='Lưu file output',
            filetypes=[('Video files', '*.mp4 *.mkv *.avi *.mov *.webm'),
                       ('Audio files', '*.mp3 *.aac *.wav *.ogg *.m4a'),
                       ('All files', '*.*')])
        if f:
            self.edit_out.delete(0, tk.END)
            self.edit_out.insert(0, f)

    def _on_preset_change(self, _event=None) -> None:
        key = self.res_preset.get()
        w, h = video_edit.PRESETS.get(key, (None, None))
        if w is not None:
            self.res_w.delete(0, tk.END); self.res_w.insert(0, str(w))
            self.res_h.delete(0, tk.END); self.res_h.insert(0, str(h))

    def _apply_edit(self) -> None:
        inp = self.edit_in.get().strip()
        if not inp or not os.path.isfile(inp):
            messagebox.showwarning('Warning', 'Vui lòng chọn file video hợp lệ.')
            return
        out = self.edit_out.get().strip() or None
        op_idx = self.op_nb.index(self.op_nb.select())
        self.edit_btn.state(['disabled'])
        self.edit_progress.start(10)
        threading.Thread(target=self._edit_worker,
                         args=(op_idx, inp, out), daemon=True).start()

    def _edit_worker(self, op_idx: int, inp: str, out) -> None:
        try:
            if op_idx == 0:       # Resize
                w = int(self.res_w.get())
                h = int(self.res_h.get())
                self._log(f'📐 Đang resize {w}×{h}: {os.path.basename(inp)}', 'info')
                result = video_edit.resize_video(inp, w, h, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            elif op_idx == 1:     # Audio
                mode = self.audio_mode.get()
                if mode == 'extract':
                    fmt = self.audio_fmt.get()
                    self._log(f'🎵 Đang extract audio ({fmt}): {os.path.basename(inp)}', 'info')
                    result = video_edit.extract_audio(inp, fmt, out)
                else:
                    self._log(f'🔇 Đang xóa audio: {os.path.basename(inp)}', 'info')
                    result = video_edit.remove_audio(inp, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            elif op_idx == 2:     # Convert
                fmt = self.conv_fmt.get()
                self._log(f'🔄 Đang convert → {fmt}: {os.path.basename(inp)}', 'info')
                result = video_edit.convert_format(inp, fmt, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            elif op_idx == 3:     # Speed
                try:
                    speed = float(self.spd_value.get())
                except ValueError:
                    speed = 1.0
                self._log(f'⚡ Đang đổi tốc độ {speed}×: {os.path.basename(inp)}', 'info')
                result = video_edit.speed_video(inp, speed, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            elif op_idx == 4:     # Rotate
                rotation = self.rot_choice.get()
                self._log(f'🔄 Đang rotate ({rotation}): {os.path.basename(inp)}', 'info')
                result = video_edit.rotate_video(inp, rotation, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            elif op_idx == 5:       # Merge
                paths = list(self.merge_list.get(0, tk.END))
                if not paths:
                    self._log('Merge: chưa có file nào trong danh sách.', 'err')
                    return
                self._log(f'🎬 Đang ghép {len(paths)} file...', 'info')
                result = video_edit.merge_videos(paths, out)
                self._log(f'Hoàn thành: {result}', 'ok')

            else:                   # Logo
                logo = self.logo_path.get().strip()
                if not logo or not os.path.isfile(logo):
                    self._log('Logo: chưa chọn file logo hợp lệ.', 'err')
                    return
                pos  = self.logo_pos.get()
                cx   = self.logo_x.get().strip()   or 'W-w-10'
                cy   = self.logo_y.get().strip()   or 'H-h-20'
                try:
                    scale = int(self.logo_scale.get())
                except ValueError:
                    scale = 150
                try:
                    opacity = float(self.logo_opacity.get())
                    opacity = max(0.0, min(1.0, opacity))
                except ValueError:
                    opacity = 1.0
                self._log(f'🖼 Đang thêm logo ({pos}): {os.path.basename(inp)}', 'info')
                result = video_edit.add_logo(inp, logo, pos, cx, cy,
                                             scale, opacity, out)
                self._log(f'Hoàn thành: {result}', 'ok')

        except Exception as e:
            self._log(f'Lỗi edit: {e}', 'err')
        finally:
            try:
                self.edit_btn.state(['!disabled'])
            except Exception:
                self.edit_btn.config(state='normal')
            try:
                self.edit_progress.stop()
            except Exception:
                pass


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    # Start maximized (full-window) where supported. Falls back safely.
    try:
        root.state('zoomed')
    except Exception:
        try:
            root.attributes('-zoomed', True)
        except Exception:
            pass
    root.mainloop()
