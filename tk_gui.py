import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

from tiktok_download import download_tiktok_video, download_from_profile

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

    # ── Left panel (inputs) ───────────────────────────────────────────────────
    def _build_left(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        # Mode notebook
        nb = ttk.Notebook(left)
        nb.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
        self.notebook = nb

        # ── Tab: Single ───────────────────────────────────────────────────────
        t1 = ttk.Frame(nb, padding=12, style='TFrame')
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

        # ── Tab: Profile ──────────────────────────────────────────────────────
        t2 = ttk.Frame(nb, padding=12, style='TFrame')
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

        # ── Tab: Multiple ─────────────────────────────────────────────────────
        t3 = ttk.Frame(nb, padding=12, style='TFrame')
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

        # ── Output folder ─────────────────────────────────────────────────────
        out_lf = ttk.LabelFrame(left, text='Output Folder',
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

        # ── Download button ───────────────────────────────────────────────────
        self.download_btn = ttk.Button(left, text='▶   Start Download',
                                       command=self.start_download,
                                       style='Accent.TButton')
        self.download_btn.grid(row=2, column=0, sticky='ew', ipady=4)

        # ── Progress bar ──────────────────────────────────────────────────────
        self.progress = ttk.Progressbar(left, mode='indeterminate')
        self.progress.grid(row=3, column=0, sticky='ew', pady=(8, 0))

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


if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
