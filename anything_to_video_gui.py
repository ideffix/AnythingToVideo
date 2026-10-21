import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import anything_to_video as atv


class AnythingToVideoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AnythingToVideo")
        self.root.geometry("880x790")
        self.root.minsize(800, 720)

        # Color palette (Modern Dark Mode)
        self.bg_main = "#181926"
        self.bg_card = "#24273a"
        self.bg_input = "#1e2030"
        self.fg_primary = "#cad3f5"
        self.fg_secondary = "#a5adcb"
        self.fg_accent = "#8aadf4"
        self.accent_btn = "#7dc4e4"
        self.success_color = "#a6da95"
        self.error_color = "#ed8796"
        self.warn_color = "#eed49f"

        self.root.configure(bg=self.bg_main)

        # Background worker state
        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.is_busy = False
        self.ffmpeg_path = atv.find_ffmpeg()
        self.current_dec_parts_info = None

        self._init_styles()
        self._build_ui()
        self._update_ffmpeg_badge()

    def _init_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.style.configure(".", background=self.bg_main, foreground=self.fg_primary, font=("Segoe UI", 10))

        # Notebook tabs
        self.style.configure("TNotebook", background=self.bg_main, borderwidth=0)
        self.style.configure("TNotebook.Tab",
                             background=self.bg_card,
                             foreground=self.fg_secondary,
                             padding=[18, 9],
                             font=("Segoe UI", 10, "bold"),
                             borderwidth=0)
        self.style.map("TNotebook.Tab",
                       background=[("selected", self.accent_btn)],
                       foreground=[("selected", "#181926")])

        # Progress bar
        self.style.configure("Horizontal.TProgressbar",
                             troughcolor=self.bg_input,
                             background=self.accent_btn,
                             thickness=14,
                             borderwidth=0)

    def _build_ui(self):
        # 1. Top Header
        header_frame = tk.Frame(self.root, bg=self.bg_main, padx=20, pady=8)
        header_frame.pack(fill=tk.X)

        title_lbl = tk.Label(header_frame, text="🎞️ AnythingToVideo",
                             font=("Segoe UI", 16, "bold"),
                             fg=self.fg_primary, bg=self.bg_main)
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(header_frame,
                                text="Lossless Data Storage in Video Frames | Configurable Resolution, FPS, Color Palette & Multipart",
                                font=("Segoe UI", 9),
                                fg=self.fg_secondary, bg=self.bg_main)
        subtitle_lbl.pack(anchor="w", pady=(1, 4))

        # FFmpeg status bar
        self.ffmpeg_bar = tk.Frame(header_frame, bg=self.bg_card, padx=10, pady=4)
        self.ffmpeg_bar.pack(fill=tk.X)

        self.ffmpeg_lbl = tk.Label(self.ffmpeg_bar, text="Checking FFmpeg...",
                                   font=("Segoe UI", 9), fg=self.fg_secondary, bg=self.bg_card)
        self.ffmpeg_lbl.pack(side=tk.LEFT)

        btn_ffmpeg = tk.Button(self.ffmpeg_bar, text="Locate FFmpeg...",
                               font=("Segoe UI", 8), bg=self.bg_input, fg=self.fg_primary,
                               activebackground=self.bg_card, activeforeground=self.fg_primary,
                               relief="flat", cursor="hand2", command=self._choose_ffmpeg)
        btn_ffmpeg.pack(side=tk.RIGHT)

        # 2. Main Notebook Tabs (Encode / Decode)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=(4, 6))

        self.tab_encode = tk.Frame(self.notebook, bg=self.bg_card, padx=16, pady=10)
        self.tab_decode = tk.Frame(self.notebook, bg=self.bg_card, padx=16, pady=10)

        self.notebook.add(self.tab_encode, text=" 📥 Encode (File ➔ Video) ")
        self.notebook.add(self.tab_decode, text=" 📤 Decode & Merge (Video ➔ File) ")

        self._build_encode_tab()
        self._build_decode_tab()

        # 3. Progress and Status Section
        progress_frame = tk.Frame(self.root, bg=self.bg_main, padx=20, pady=4)
        progress_frame.pack(fill=tk.X)

        self.status_lbl = tk.Label(progress_frame, text="Ready to proceed.",
                                   font=("Segoe UI", 9, "bold"), fg=self.fg_primary, bg=self.bg_main)
        self.status_lbl.pack(anchor="w", pady=(0, 3))

        self.progressbar = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL,
                                           style="Horizontal.TProgressbar", mode="determinate")
        self.progressbar.pack(fill=tk.X)

        # 4. Operation Log Console
        log_frame = tk.Frame(self.root, bg=self.bg_main, padx=20, pady=4)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        log_header = tk.Frame(log_frame, bg=self.bg_main)
        log_header.pack(fill=tk.X, pady=(0, 2))

        tk.Label(log_header, text="Operation Log:",
                 font=("Segoe UI", 9, "bold"), fg=self.fg_secondary, bg=self.bg_main).pack(side=tk.LEFT)

        tk.Button(log_header, text="Clear", font=("Segoe UI", 8),
                  bg=self.bg_card, fg=self.fg_secondary, relief="flat", cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        self.log_text = tk.Text(log_frame, height=5, bg=self.bg_input, fg=self.fg_primary,
                                insertbackground=self.fg_primary, relief="flat",
                                font=("Consolas", 9), padx=8, pady=4)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview, bg=self.bg_card)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def _build_encode_tab(self):
        # Section 1: Source File
        tk.Label(self.tab_encode, text="Source file to encode:",
                 font=("Segoe UI", 10, "bold"), fg=self.fg_primary, bg=self.bg_card).pack(anchor="w")

        f_input = tk.Frame(self.tab_encode, bg=self.bg_card)
        f_input.pack(fill=tk.X, pady=(2, 6))

        self.enc_input_var = tk.StringVar()
        self.enc_input_var.trace_add("write", lambda *args: self._on_enc_settings_changed())
        ent_input = tk.Entry(f_input, textvariable=self.enc_input_var, font=("Segoe UI", 10),
                             bg=self.bg_input, fg=self.fg_primary, insertbackground=self.fg_primary, relief="flat")
        ent_input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 8))

        btn_browse_in = tk.Button(f_input, text="Browse...", font=("Segoe UI", 9),
                                  bg=self.bg_input, fg=self.fg_primary, relief="flat", cursor="hand2",
                                  command=self._browse_enc_input)
        btn_browse_in.pack(side=tk.RIGHT)

        # Section 2: Video Configuration (Resolution, FPS, Color Palette)
        f_video_cfg = tk.LabelFrame(self.tab_encode, text=" Video Configuration (Resolution, FPS, Color Palette) ",
                                    font=("Segoe UI", 9, "bold"), fg=self.fg_accent, bg=self.bg_card, padx=10, pady=6)
        f_video_cfg.pack(fill=tk.X, pady=(0, 6))

        # Row: Resolution (Default: 1920x1080)
        f_res_row = tk.Frame(f_video_cfg, bg=self.bg_card)
        f_res_row.pack(fill=tk.X, pady=2)

        tk.Label(f_res_row, text="Resolution:", font=("Segoe UI", 9),
                 fg=self.fg_primary, bg=self.bg_card, width=14, anchor="w").pack(side=tk.LEFT)

        self.res_preset_var = tk.StringVar(value="1920x1080 (1080p FHD - Default)")
        self.res_cb = ttk.Combobox(f_res_row, textvariable=self.res_preset_var, state="readonly", width=28,
                                   values=[
                                       "1920x1080 (1080p FHD - Default)",
                                       "1280x720 (720p HD)",
                                       "2560x1440 (1440p 2K QHD)",
                                       "3840x2160 (2160p 4K UHD)",
                                       "854x480 (480p SD)",
                                       "640x360 (360p)",
                                       "Custom resolution..."
                                   ])
        self.res_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.res_cb.bind("<<ComboboxSelected>>", self._on_res_preset_selected)

        self.f_custom_res = tk.Frame(f_res_row, bg=self.bg_card)
        self.f_custom_res.pack(side=tk.LEFT)
        self.custom_w_var = tk.StringVar(value=str(atv.DEFAULT_WIDTH))
        self.custom_h_var = tk.StringVar(value=str(atv.DEFAULT_HEIGHT))
        self.custom_w_var.trace_add("write", lambda *args: self._on_enc_settings_changed())
        self.custom_h_var.trace_add("write", lambda *args: self._on_enc_settings_changed())

        ent_w = tk.Entry(self.f_custom_res, textvariable=self.custom_w_var, width=6,
                         font=("Segoe UI", 9), bg=self.bg_input, fg=self.fg_primary, relief="flat")
        ent_w.pack(side=tk.LEFT, ipady=1)
        tk.Label(self.f_custom_res, text="x", font=("Segoe UI", 9), fg=self.fg_secondary, bg=self.bg_card).pack(side=tk.LEFT, padx=3)
        ent_h = tk.Entry(self.f_custom_res, textvariable=self.custom_h_var, width=6,
                         font=("Segoe UI", 9), bg=self.bg_input, fg=self.fg_primary, relief="flat")
        ent_h.pack(side=tk.LEFT, ipady=1)
        self.f_custom_res.pack_forget()

        # Row: FPS (Default: 30 fps)
        f_fps_row = tk.Frame(f_video_cfg, bg=self.bg_card)
        f_fps_row.pack(fill=tk.X, pady=2)

        tk.Label(f_fps_row, text="Frame rate (FPS):", font=("Segoe UI", 9),
                 fg=self.fg_primary, bg=self.bg_card, width=14, anchor="w").pack(side=tk.LEFT)

        self.fps_preset_var = tk.StringVar(value="30 fps (Default)")
        self.fps_cb = ttk.Combobox(f_fps_row, textvariable=self.fps_preset_var, state="readonly", width=28,
                                   values=[
                                       "30 fps (Default)",
                                       "60 fps (Smooth)",
                                       "24 fps (Cinematic)",
                                       "15 fps (Compact)",
                                       "Custom FPS..."
                                   ])
        self.fps_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.fps_cb.bind("<<ComboboxSelected>>", self._on_fps_preset_selected)

        self.f_custom_fps = tk.Frame(f_fps_row, bg=self.bg_card)
        self.f_custom_fps.pack(side=tk.LEFT)
        self.custom_fps_var = tk.StringVar(value=str(atv.DEFAULT_FPS))
        self.custom_fps_var.trace_add("write", lambda *args: self._on_enc_settings_changed())
        ent_fps = tk.Entry(self.f_custom_fps, textvariable=self.custom_fps_var, width=6,
                           font=("Segoe UI", 9), bg=self.bg_input, fg=self.fg_primary, relief="flat")
        ent_fps.pack(side=tk.LEFT, ipady=1)
        self.f_custom_fps.pack_forget()

        # Row: Color Palette (Default: 24-bit RGB)
        f_col_row = tk.Frame(f_video_cfg, bg=self.bg_card)
        f_col_row.pack(fill=tk.X, pady=2)

        tk.Label(f_col_row, text="Color palette:", font=("Segoe UI", 9),
                 fg=self.fg_primary, bg=self.bg_card, width=14, anchor="w").pack(side=tk.LEFT)

        self.color_mode_var = tk.StringVar(value="Full Color (24-bit RGB - Default)")
        self.color_cb = ttk.Combobox(f_col_row, textvariable=self.color_mode_var, state="readonly", width=36,
                                     values=[
                                         "Full Color (24-bit RGB - Default)",
                                         "8 Colors (3-bit saturated RGB)",
                                         "Black & White (1-bit B&W - High resilience)"
                                     ])
        self.color_cb.pack(side=tk.LEFT)
        self.color_cb.bind("<<ComboboxSelected>>", lambda e: self._on_enc_settings_changed())

        # Section 3: Multipart Splitting
        f_split = tk.LabelFrame(self.tab_encode, text=" Multi-part Splitting (Max Output File Size) ",
                                font=("Segoe UI", 9, "bold"), fg=self.fg_accent, bg=self.bg_card, padx=10, pady=5)
        f_split.pack(fill=tk.X, pady=(0, 6))

        f_split_row = tk.Frame(f_split, bg=self.bg_card)
        f_split_row.pack(fill=tk.X)

        tk.Label(f_split_row, text="Size limit:", font=("Segoe UI", 9),
                 fg=self.fg_primary, bg=self.bg_card, width=14, anchor="w").pack(side=tk.LEFT)

        self.split_preset_var = tk.StringVar(value="None (Single video file)")
        self.split_cb = ttk.Combobox(f_split_row, textvariable=self.split_preset_var, state="readonly", width=28,
                                     values=[
                                         "None (Single video file)",
                                         "500 MB",
                                         "1 GB (1024 MB)",
                                         "2 GB (2048 MB)",
                                         "4 GB (FAT32 limit)",
                                         "Custom size (MB)..."
                                     ])
        self.split_cb.pack(side=tk.LEFT, padx=(0, 8))
        self.split_cb.bind("<<ComboboxSelected>>", self._on_split_preset_selected)

        self.custom_split_var = tk.StringVar(value="1024")
        self.custom_split_var.trace_add("write", lambda *args: self._on_enc_settings_changed())

        self.f_custom_split = tk.Frame(f_split_row, bg=self.bg_card)
        self.f_custom_split.pack(side=tk.LEFT)

        self.ent_custom_split = tk.Entry(self.f_custom_split, textvariable=self.custom_split_var, width=8,
                                         font=("Segoe UI", 9), bg=self.bg_input, fg=self.fg_primary, relief="flat")
        self.ent_custom_split.pack(side=tk.LEFT, ipady=1, padx=(0, 4))
        self.lbl_mb = tk.Label(self.f_custom_split, text="MB", font=("Segoe UI", 9), fg=self.fg_secondary, bg=self.bg_card)
        self.lbl_mb.pack(side=tk.LEFT)
        self.f_custom_split.pack_forget()

        # Section 4: Live Estimation Info Card
        self.enc_info_lbl = tk.Label(self.tab_encode, text="Select a file to inspect estimated video parameters and part splitting...",
                                     font=("Segoe UI", 9), fg=self.fg_secondary, bg=self.bg_card, justify="left")
        self.enc_info_lbl.pack(anchor="w", pady=(0, 6))

        # Section 5: Destination Video Path and Preset
        tk.Label(self.tab_encode, text="Target video file (.mp4) / part prefix:",
                 font=("Segoe UI", 10, "bold"), fg=self.fg_primary, bg=self.bg_card).pack(anchor="w")

        f_output = tk.Frame(self.tab_encode, bg=self.bg_card)
        f_output.pack(fill=tk.X, pady=(2, 6))

        self.enc_output_var = tk.StringVar(value="video.mp4")
        ent_output = tk.Entry(f_output, textvariable=self.enc_output_var, font=("Segoe UI", 10),
                              bg=self.bg_input, fg=self.fg_primary, insertbackground=self.fg_primary, relief="flat")
        ent_output.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 8))

        btn_browse_out = tk.Button(f_output, text="Save As...", font=("Segoe UI", 9),
                                   bg=self.bg_input, fg=self.fg_primary, relief="flat", cursor="hand2",
                                   command=self._browse_enc_output)
        btn_browse_out.pack(side=tk.RIGHT)

        # Encoder options (x264 Preset)
        f_options = tk.Frame(self.tab_encode, bg=self.bg_card)
        f_options.pack(fill=tk.X, pady=(0, 10))

        tk.Label(f_options, text="x264 Preset:", font=("Segoe UI", 9),
                 fg=self.fg_secondary, bg=self.bg_card).pack(side=tk.LEFT, padx=(0, 8))
        self.enc_preset_var = tk.StringVar(value=atv.DEFAULT_PRESET)
        preset_cb = ttk.Combobox(f_options, textvariable=self.enc_preset_var, state="readonly", width=12,
                                 values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium"])
        preset_cb.pack(side=tk.LEFT)

        tk.Label(f_options, text="(ultrafast = fastest encoding speed)", font=("Segoe UI", 8),
                 fg=self.fg_secondary, bg=self.bg_card).pack(side=tk.LEFT, padx=(8, 0))

        # Action Buttons
        btn_box = tk.Frame(self.tab_encode, bg=self.bg_card)
        btn_box.pack(fill=tk.X)

        self.btn_start_encode = tk.Button(btn_box, text="⚡ Start Encoding",
                                          font=("Segoe UI", 11, "bold"),
                                          bg=self.accent_btn, fg="#181926", activebackground="#91d7e3",
                                          relief="flat", cursor="hand2", padx=18, pady=6,
                                          command=self._start_encoding)
        self.btn_start_encode.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_cancel_encode = tk.Button(btn_box, text="✖ Cancel",
                                           font=("Segoe UI", 10),
                                           bg=self.bg_input, fg=self.error_color,
                                           relief="flat", cursor="hand2", padx=14, pady=6,
                                           state=tk.DISABLED, command=self._cancel_task)
        self.btn_cancel_encode.pack(side=tk.LEFT)

    def _build_decode_tab(self):
        # Input video file selection
        tk.Label(self.tab_decode, text="Select MP4 video file (or any part of an archive):",
                 font=("Segoe UI", 10, "bold"), fg=self.fg_primary, bg=self.bg_card).pack(anchor="w")

        f_video = tk.Frame(self.tab_decode, bg=self.bg_card)
        f_video.pack(fill=tk.X, pady=(2, 8))

        self.dec_video_var = tk.StringVar()
        self.dec_video_var.trace_add("write", self._on_dec_video_changed)
        ent_video = tk.Entry(f_video, textvariable=self.dec_video_var, font=("Segoe UI", 10),
                             bg=self.bg_input, fg=self.fg_primary, insertbackground=self.fg_primary, relief="flat")
        ent_video.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 8))

        btn_browse_vid = tk.Button(f_video, text="Browse...", font=("Segoe UI", 9),
                                   bg=self.bg_input, fg=self.fg_primary, relief="flat", cursor="hand2",
                                   command=self._browse_dec_video)
        btn_browse_vid.pack(side=tk.RIGHT)

        # Metadata & Video Format Card
        self.dec_info_card = tk.LabelFrame(self.tab_decode, text=" Detected Metadata & Video Specs ",
                                           font=("Segoe UI", 9, "bold"), fg=self.fg_accent, bg=self.bg_card, padx=12, pady=8)
        self.dec_info_card.pack(fill=tk.X, pady=(0, 10))

        self.dec_meta_lbl = tk.Label(self.dec_info_card,
                                     text="Select a video file to inspect metadata, video specs, and archive status...",
                                     font=("Segoe UI", 9), fg=self.fg_secondary, bg=self.bg_card, justify="left")
        self.dec_meta_lbl.pack(anchor="w")

        # Destination Directory
        tk.Label(self.tab_decode, text="Destination extraction folder:",
                 font=("Segoe UI", 10, "bold"), fg=self.fg_primary, bg=self.bg_card).pack(anchor="w")

        f_outdir = tk.Frame(self.tab_decode, bg=self.bg_card)
        f_outdir.pack(fill=tk.X, pady=(2, 12))

        self.dec_outdir_var = tk.StringVar(value=os.path.abspath("."))
        ent_outdir = tk.Entry(f_outdir, textvariable=self.dec_outdir_var, font=("Segoe UI", 10),
                              bg=self.bg_input, fg=self.fg_primary, insertbackground=self.fg_primary, relief="flat")
        ent_outdir.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3, padx=(0, 8))

        btn_browse_dir = tk.Button(f_outdir, text="Browse Folder...", font=("Segoe UI", 9),
                                   bg=self.bg_input, fg=self.fg_primary, relief="flat", cursor="hand2",
                                   command=self._browse_dec_dir)
        btn_browse_dir.pack(side=tk.RIGHT)

        # Action Buttons
        btn_box = tk.Frame(self.tab_decode, bg=self.bg_card)
        btn_box.pack(fill=tk.X)

        self.btn_start_decode = tk.Button(btn_box, text="🔓 Start Decoding & Merging",
                                          font=("Segoe UI", 11, "bold"),
                                          bg=self.success_color, fg="#181926", activebackground="#b8f2a7",
                                          relief="flat", cursor="hand2", padx=18, pady=6,
                                          command=self._start_decoding)
        self.btn_start_decode.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_cancel_decode = tk.Button(btn_box, text="✖ Cancel",
                                           font=("Segoe UI", 10),
                                           bg=self.bg_input, fg=self.error_color,
                                           relief="flat", cursor="hand2", padx=14, pady=6,
                                           state=tk.DISABLED, command=self._cancel_task)
        self.btn_cancel_decode.pack(side=tk.LEFT)

    # --- FFmpeg Configuration ---
    def _update_ffmpeg_badge(self):
        if self.ffmpeg_path and os.path.isfile(self.ffmpeg_path):
            self.ffmpeg_lbl.config(text=f"✓ FFmpeg located: {self.ffmpeg_path}", fg=self.success_color)
        else:
            self.ffmpeg_lbl.config(text="⚠ FFmpeg not found! Please locate ffmpeg.exe", fg=self.error_color)

    def _choose_ffmpeg(self):
        path = filedialog.askopenfilename(
            title="Locate ffmpeg executable",
            filetypes=[("Executable Files", "ffmpeg.exe;*.exe"), ("All Files", "*.*")]
        )
        if path:
            self.ffmpeg_path = path
            self._update_ffmpeg_badge()
            self._log(f"[*] Updated FFmpeg path: {path}")

    # --- Video & Split Preset Selection Handlers ---
    def _on_res_preset_selected(self, event=None):
        sel = self.res_preset_var.get()
        if "Custom" in sel:
            self.f_custom_res.pack(side=tk.LEFT)
        else:
            self.f_custom_res.pack_forget()
            if "1920x1080" in sel: self.custom_w_var.set("1920"); self.custom_h_var.set("1080")
            elif "1280x720" in sel: self.custom_w_var.set("1280"); self.custom_h_var.set("720")
            elif "2560x1440" in sel: self.custom_w_var.set("2560"); self.custom_h_var.set("1440")
            elif "3840x2160" in sel: self.custom_w_var.set("3840"); self.custom_h_var.set("2160")
            elif "854x480" in sel: self.custom_w_var.set("854"); self.custom_h_var.set("480")
            elif "640x360" in sel: self.custom_w_var.set("640"); self.custom_h_var.set("360")
        self._on_enc_settings_changed()

    def _on_fps_preset_selected(self, event=None):
        sel = self.fps_preset_var.get()
        if "Custom" in sel:
            self.f_custom_fps.pack(side=tk.LEFT)
        else:
            self.f_custom_fps.pack_forget()
            if "60 fps" in sel: self.custom_fps_var.set("60")
            elif "30 fps" in sel: self.custom_fps_var.set("30")
            elif "24 fps" in sel: self.custom_fps_var.set("24")
            elif "15 fps" in sel: self.custom_fps_var.set("15")
        self._on_enc_settings_changed()

    def _on_split_preset_selected(self, event=None):
        sel = self.split_preset_var.get()
        if "Custom" in sel:
            self.f_custom_split.pack(side=tk.LEFT)
        else:
            self.f_custom_split.pack_forget()
            if "500 MB" in sel: self.custom_split_var.set("500")
            elif "1 GB" in sel: self.custom_split_var.set("1024")
            elif "2 GB" in sel: self.custom_split_var.set("2048")
            elif "4 GB" in sel: self.custom_split_var.set("4096")
        self._on_enc_settings_changed()

    def _get_current_enc_params(self):
        # Resolution with defaults
        try:
            w_str = self.custom_w_var.get().strip()
            h_str = self.custom_h_var.get().strip()
            w = int(w_str) if w_str else atv.DEFAULT_WIDTH
            h = int(h_str) if h_str else atv.DEFAULT_HEIGHT
        except ValueError:
            w, h = atv.DEFAULT_WIDTH, atv.DEFAULT_HEIGHT

        # FPS with defaults
        try:
            fps_str = self.custom_fps_var.get().strip()
            fps = int(fps_str) if fps_str and int(fps_str) > 0 else atv.DEFAULT_FPS
        except ValueError:
            fps = atv.DEFAULT_FPS

        # Color mode with defaults
        c_sel = self.color_mode_var.get()
        if "8 Colors" in c_sel:
            color_mode = atv.COLOR_8COL
        elif "Black & White" in c_sel:
            color_mode = atv.COLOR_BW
        else:
            color_mode = atv.COLOR_RGB24

        # Multipart size limit
        split_sel = self.split_preset_var.get()
        split_bytes = None
        if "None" not in split_sel:
            try:
                mb = float(self.custom_split_var.get().strip())
                if mb > 0: split_bytes = int(mb * 1024 * 1024)
            except ValueError:
                pass

        return w, h, fps, color_mode, split_bytes

    def _on_enc_settings_changed(self):
        path = self.enc_input_var.get().strip()
        w, h, fps, color_mode, split_bytes = self._get_current_enc_params()
        specs = atv.get_frame_specs(w, h, color_mode)
        payload_frame = specs["payload_bytes"]

        mode_desc = {
            atv.COLOR_RGB24: "24-bit RGB (Full Color)",
            atv.COLOR_8COL: "8 Colors (3 bits/pixel)",
            atv.COLOR_BW: "Black & White (1 bit/pixel)"
        }

        if os.path.isfile(path):
            size = os.path.getsize(path)
            total_payload = 110 + len(os.path.basename(path).encode("utf-8")) + size
            total_frames = (total_payload + payload_frame - 1) // payload_frame
            sec = total_frames / float(fps)

            if split_bytes and size > split_bytes:
                num_parts = (size + split_bytes - 1) // split_bytes
                info_text = (
                    f"📁 File size: {atv.format_size(size)} | Specs: {w}x{h} @ {fps} fps | {mode_desc[color_mode]}\n"
                    f"⚡ Capacity/frame: {atv.format_size(payload_frame)} | Est. duration: ~{sec:.1f} s (~{total_frames:,} frames)\n"
                    f"📦 Multi-part: {num_parts} parts (max {atv.format_size(split_bytes)} each: ...part1.mp4 ... part{num_parts}.mp4)"
                )
            else:
                info_text = (
                    f"📁 File size: {atv.format_size(size)} | Specs: {w}x{h} @ {fps} fps | {mode_desc[color_mode]}\n"
                    f"⚡ Capacity/frame: {atv.format_size(payload_frame)} | Est. duration: ~{sec:.1f} s (~{total_frames:,} frames)\n"
                    f"📦 Output: 1 single video file (no splitting)."
                )
            self.enc_info_lbl.config(text=info_text, fg=self.fg_accent)
        else:
            self.enc_info_lbl.config(
                text=f"Selected specs: {w}x{h} @ {fps} fps | {mode_desc[color_mode]} ({atv.format_size(payload_frame)}/frame)",
                fg=self.fg_secondary
            )

    # --- File Browsing Handlers ---
    def _browse_enc_input(self):
        path = filedialog.askopenfilename(title="Select file to encode")
        if path:
            self.enc_input_var.set(path)
            base_name = os.path.splitext(os.path.basename(path))[0]
            def_out = os.path.join(os.path.dirname(path), f"{base_name}_video.mp4")
            self.enc_output_var.set(def_out)

    def _browse_enc_output(self):
        path = filedialog.asksaveasfilename(
            title="Save video file as",
            defaultextension=".mp4",
            filetypes=[("MP4 Video Files", "*.mp4")]
        )
        if path:
            self.enc_output_var.set(path)

    def _browse_dec_video(self):
        path = filedialog.askopenfilename(
            title="Select video file (or archive part)",
            filetypes=[("MP4 Video Files", "*.mp4"), ("All Files", "*.*")]
        )
        if path:
            self.dec_video_var.set(path)

    def _browse_dec_dir(self):
        path = filedialog.askdirectory(title="Select destination extraction folder")
        if path:
            self.dec_outdir_var.set(path)

    def _on_dec_video_changed(self, *args):
        path = self.dec_video_var.get().strip()
        if os.path.isfile(path):
            threading.Thread(target=self._async_peek_and_check_parts, args=(path,), daemon=True).start()
        else:
            self.current_dec_parts_info = None
            self.dec_meta_lbl.config(
                text="Select a video file to inspect metadata, video specs, and archive status...",
                fg=self.fg_secondary
            )

    def _async_peek_and_check_parts(self, video_path):
        try:
            parts_info = atv.find_related_parts(video_path, self.ffmpeg_path)
            self.current_dec_parts_info = parts_info
            meta = parts_info["meta"]
            total_parts = parts_info["total_parts"]
            total_size_str = atv.format_size(meta["total_file_size"])

            mode_names = {
                atv.COLOR_RGB24: "24-bit RGB (Full Color)",
                atv.COLOR_8COL: "8 Colors (3 bits/pixel)",
                atv.COLOR_BW: "Black & White (1 bit/pixel)"
            }
            c_mode_str = mode_names.get(meta.get("color_mode", "rgb24"), meta.get("color_mode"))

            if total_parts > 1:
                if parts_info["is_complete"]:
                    status_part = (f"✔ Multi-part archive: All {total_parts}/{total_parts} parts detected in folder!\n"
                                   f"   Ready for automatic sequential merging.")
                    color = self.success_color
                else:
                    missing_str = ", ".join(str(p) for p in parts_info["missing"])
                    status_part = (f"⚠ Multi-part archive ({len(parts_info['parts'])}/{total_parts} parts found).\n"
                                   f"   MISSING PARTS: {missing_str} in this directory!")
                    color = self.warn_color

                info_text = (
                    f"✔ Original file: {meta['filename']}\n"
                    f"✔ Total size:    {total_size_str} ({meta['total_file_size']:,} bytes)\n"
                    f"✔ Video specs:   {meta['width']}x{meta['height']} @ {meta['fps']} fps | {c_mode_str}\n"
                    f"✔ SHA-256 hash:  {meta['sha256']}\n"
                    f"{status_part}"
                )
            else:
                info_text = (
                    f"✔ Original file: {meta['filename']}\n"
                    f"✔ Total size:    {total_size_str} ({meta['total_file_size']:,} bytes)\n"
                    f"✔ Video specs:   {meta['width']}x{meta['height']} @ {meta['fps']} fps | {c_mode_str}\n"
                    f"✔ SHA-256 hash:  {meta['sha256']}\n"
                    f"✔ Single video file (no merging required)."
                )
                color = self.success_color

            self.root.after(0, lambda: self.dec_meta_lbl.config(text=info_text, fg=color))
            self.root.after(0, lambda: self._log(f"[*] Detected '{meta['filename']}' ({total_size_str}) | {meta['width']}x{meta['height']}@{meta['fps']}fps [{meta['color_mode']}]"))
        except Exception as e:
            self.current_dec_parts_info = None
            err = f"Failed to read AnythingToVideo header: {e}"
            self.root.after(0, lambda: self.dec_meta_lbl.config(text=f"⚠ {err}", fg=self.warn_color))

    # --- Logging & UI Updates ---
    def _log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _set_busy(self, busy, is_encoding=True):
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        cancel_state = tk.NORMAL if busy else tk.DISABLED

        self.btn_start_encode.config(state=state)
        self.btn_start_decode.config(state=state)
        self.btn_cancel_encode.config(state=cancel_state if is_encoding else tk.DISABLED)
        self.btn_cancel_decode.config(state=cancel_state if not is_encoding else tk.DISABLED)

    def _update_progress(self, current, total, text):
        def _cb():
            if total > 0:
                pct = (current / total) * 100
                self.progressbar["value"] = pct
            self.status_lbl.config(text=text)
        self.root.after(0, _cb)

    def _cancel_task(self):
        if self.is_busy:
            self.cancel_event.set()
            self._log("[!] Cancellation request sent...")
            self.status_lbl.config(text="Cancelling operation...", fg=self.warn_color)

    # --- Background Tasks ---
    def _start_encoding(self):
        input_path = self.enc_input_var.get().strip()
        output_path = self.enc_output_var.get().strip()
        preset = self.enc_preset_var.get()
        w, h, fps, color_mode, split_bytes = self._get_current_enc_params()

        if not input_path or not os.path.isfile(input_path):
            messagebox.showerror("Error", "Please select a valid input file to encode.")
            return

        if not output_path:
            messagebox.showerror("Error", "Please specify an output video file path.")
            return

        self._set_busy(True, is_encoding=True)
        self.cancel_event.clear()
        self.progressbar["value"] = 0
        self.status_lbl.config(text="Starting encoding process...", fg=self.fg_primary)

        def run():
            success, msg = atv.encode_file(
                input_path=input_path,
                output_mp4=output_path,
                max_part_size=split_bytes,
                width=w,
                height=h,
                fps=fps,
                color_mode=color_mode,
                preset=preset,
                progress_callback=self._update_progress,
                log_callback=lambda m: self.root.after(0, lambda: self._log(m)),
                cancel_event=self.cancel_event,
                ffmpeg_path=self.ffmpeg_path
            )
            def done():
                self._set_busy(False)
                if success:
                    self.status_lbl.config(text="Encoding completed successfully!", fg=self.success_color)
                    messagebox.showinfo("Success", msg)
                else:
                    self.status_lbl.config(text=f"Error / Cancelled: {msg}", fg=self.error_color)
                    if not self.cancel_event.is_set():
                        messagebox.showerror("Error", msg)
            self.root.after(0, done)

        self.worker_thread = threading.Thread(target=run, daemon=True)
        self.worker_thread.start()

    def _start_decoding(self):
        video_path = self.dec_video_var.get().strip()
        out_dir = self.dec_outdir_var.get().strip()

        if not video_path or not os.path.isfile(video_path):
            messagebox.showerror("Error", "Please select a valid video file to decode.")
            return

        if self.current_dec_parts_info and not self.current_dec_parts_info["is_complete"]:
            missing = ", ".join(str(p) for p in self.current_dec_parts_info["missing"])
            if not messagebox.askyesno(
                "Missing Parts",
                f"Missing archive parts in folder: {missing}.\n\nDo you want to proceed anyway?"
            ):
                return

        if not out_dir:
            out_dir = "."

        self._set_busy(True, is_encoding=False)
        self.cancel_event.clear()
        self.progressbar["value"] = 0
        self.status_lbl.config(text="Starting decoding & merging...", fg=self.fg_primary)

        def run():
            success, msg = atv.decode_file(
                video_path=video_path,
                output_dir=out_dir,
                progress_callback=self._update_progress,
                log_callback=lambda m: self.root.after(0, lambda: self._log(m)),
                cancel_event=self.cancel_event,
                ffmpeg_path=self.ffmpeg_path
            )
            def done():
                self._set_busy(False)
                if success:
                    self.status_lbl.config(text="File decoded, merged, and verified with SHA-256!", fg=self.success_color)
                    messagebox.showinfo("Success", msg)
                else:
                    self.status_lbl.config(text=f"Error / Cancelled: {msg}", fg=self.error_color)
                    if not self.cancel_event.is_set():
                        messagebox.showerror("Decoding Error", msg)
            self.root.after(0, done)

        self.worker_thread = threading.Thread(target=run, daemon=True)
        self.worker_thread.start()


def main():
    root = tk.Tk()
    app = AnythingToVideoGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
