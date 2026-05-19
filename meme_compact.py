#!/usr/bin/env python3
"""
╔══════════════════════════════════════════╗
║  MEOWND MEME VIDEO MAKER  v2  — compact ║
║  • Plain tkinter (no customtkinter)      ║
║  • Yellow zone is a constant (no opencv) ║
╚══════════════════════════════════════════╝
"""

# ── 0. Bootstrap ──────────────────────────────────────────────────
import sys, subprocess, os

DEPS = {
    "PIL":      "pillow",
    "moviepy":  "moviepy",
    "yt_dlp":   "yt-dlp",
    "numpy":    "numpy",
    "requests": "requests",
}

def _bootstrap():
    missing = [pkg for mod, pkg in DEPS.items()
               if not __import__("importlib.util").util.find_spec(mod)]
    if missing:
        print(f"[setup] Installing: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)
        print("[setup] Done — restarting…\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

# ── 1. Imports ────────────────────────────────────────────────────
import threading, queue, re, time, traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
import numpy as np
from PIL import Image, ImageTk

# ── 2. Constants ──────────────────────────────────────────────────
APP_TITLE     = "🐱  Meownd Meme Video Maker  v2"
TEMPLATE_NAME = "1778721896370_final_meownd_meme_TEMPLATE.jpg"
OUTPUT_DIR    = Path("meownd_outputs")
TEMPLATE_SIZE = (1080, 1080)
YELLOW_ZONE   = (466, 101, 1036, 731)   # constant — no detection needed

PREVIEW_SIZE  = 380   # px

# Dark theme colours (used for plain tk styling)
BG_DARK  = "#1a1a1a"
BG_MID   = "#242424"
BG_CARD  = "#2e2e2e"
ACCENT   = "#f5c842"
ACCENT2  = "#e0a800"
TEXT_W   = "#f0f0f0"
TEXT_DIM = "#888888"
GREEN    = "#4caf50"
RED      = "#f44336"
BLUE     = "#4fc3f7"


# ── 3. Stream URL resolver ────────────────────────────────────────

def resolve_stream_url(url: str, log_cb) -> str:
    if re.search(r"\.(mp4|webm|mov|avi|mkv|flv|m4v)(\?.*)?$", url, re.I):
        log_cb("🔗  Direct video URL — streaming in place.")
        return url
    if Path(url).exists():
        log_cb("📂  Local file detected.")
        return url
    log_cb("🔍  Resolving via yt-dlp (no download)…")
    import yt_dlp
    opts = {"format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "quiet": True, "no_warnings": True, "skip_download": True,
            "merge_output_format": "mp4"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    formats = info.get("formats", [])
    best = next((f.get("url") for f in reversed(formats)
                 if f.get("vcodec") != "none" and f.get("acodec") != "none"
                 and f.get("ext") == "mp4"), None)
    if not best:
        best = formats[-1].get("url") if formats else info.get("url")
    log_cb(f"✅  Resolved: {info.get('title','?')[:50]}")
    return best


# ── 4. Compositor ─────────────────────────────────────────────────

def composite_video(params: dict, log_cb, progress_cb):
    try:
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip
    except ModuleNotFoundError:
        from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip

    stream_url = params["stream_url"]
    tmpl_path  = params["tmpl_path"]
    out_path   = params["out_path"]
    zone       = params["zone"]         # always YELLOW_ZONE (constant)
    out_size   = params["out_size"]
    start_t    = params["start_t"]
    end_t      = params["end_t"]
    keep_audio = params["keep_audio"]
    fps_out    = params["fps"]
    loop_video = params["loop"]
    border_px  = params["border_px"]
    border_col = params["border_col"]

    ow, oh = out_size
    x1, y1, x2, y2 = zone
    tw, th = TEMPLATE_SIZE
    sx, sy = ow / tw, oh / th
    zx1, zy1 = int(x1 * sx), int(y1 * sy)
    zx2, zy2 = int(x2 * sx), int(y2 * sy)
    zw, zh   = zx2 - zx1, zy2 - zy1

    log_cb(f"📐  Zone in output: ({zx1},{zy1})→({zx2},{zy2})  [{zw}×{zh}]")
    progress_cb(5)

    from moviepy import VideoFileClip as _VFC
    _has = lambda name: hasattr(_VFC, name)

    def _subclip(c, s, e):
        if _has("subclipped"):   return c.subclipped(s, e)
        if _has("with_subclip"): return c.with_subclip(s, e)
        return c.subclip(s, e)

    def _resize(c, sz):
        return c.resized(sz) if _has("resized") else c.resize(sz)

    def _crop(c, **kw):
        return c.cropped(**kw) if _has("cropped") else c.crop(**kw)

    def _set_pos(c, pos):
        return c.with_position(pos) if _has("with_position") else c.set_position(pos)

    def _set_dur(c, d):
        return c.with_duration(d) if _has("with_duration") else c.set_duration(d)

    def _set_fps(c, f):
        return c.with_fps(f) if _has("with_fps") else c.set_fps(f)

    def _set_audio(c, a):
        return c.with_audio(a) if _has("with_audio") else c.set_audio(a)

    import moviepy as _mp
    log_cb(f"Opening stream (MoviePy {getattr(_mp,'__version__','?')})…")
    src = VideoFileClip(stream_url, audio=keep_audio)
    dur = src.duration
    end = min(end_t, dur) if end_t else dur
    src = _subclip(src, start_t, end)
    log_cb(f"Clip: {src.duration:.1f}s  {src.w}×{src.h}")
    progress_cb(15)

    if loop_video:
        try:
            from moviepy.editor import concatenate_videoclips
        except ModuleNotFoundError:
            from moviepy import concatenate_videoclips
        loops = max(1, int(60 / src.duration) + 1)
        src = _subclip(concatenate_videoclips([src] * loops), 0,
                       min(src.duration * loops, 60))

    scale  = max(zw / src.w, zh / src.h)
    nw, nh = int(src.w * scale), int(src.h * scale)
    vid    = _resize(src, (nw, nh))
    cx, cy = (nw - zw) // 2, (nh - zh) // 2
    vid    = _crop(vid, x1=cx, y1=cy, x2=cx + zw, y2=cy + zh)
    vid    = _set_pos(vid, (zx1, zy1))
    progress_cb(30)

    tmpl_img = Image.open(tmpl_path).convert("RGBA").resize((ow, oh), Image.LANCZOS)
    tmpl_np  = np.array(tmpl_img)
    tmpl_np[zy1:zy2, zx1:zx2, 3] = 0   # punch transparent hole

    if border_px > 0:
        r, g, b = tuple(int(border_col.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        bp = border_px
        for sl in [
            (slice(max(0,zy1-bp),zy1),         slice(max(0,zx1-bp),zx2+bp)),
            (slice(zy2, zy2+bp),               slice(max(0,zx1-bp),zx2+bp)),
            (slice(max(0,zy1-bp),zy2+bp),      slice(max(0,zx1-bp),zx1)),
            (slice(max(0,zy1-bp),zy2+bp),      slice(zx2, zx2+bp)),
        ]:
            tmpl_np[sl[0], sl[1], :3] = [r, g, b]
            tmpl_np[sl[0], sl[1],  3] = 255

    tmpl_clip = _set_fps(_set_dur(ImageClip(tmpl_np, is_mask=False), src.duration), fps_out)
    progress_cb(50)

    log_cb("Compositing layers…")
    white_bg = _set_dur(ColorClip(size=(ow, oh), color=[255, 255, 255]), src.duration)
    final    = CompositeVideoClip([white_bg, vid, tmpl_clip], size=(ow, oh), use_bgclip=True)
    if keep_audio and src.audio:
        final = _set_audio(final, src.audio)
    progress_cb(60)

    log_cb(f"💾  Writing → {out_path} …")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    wv_kwargs = dict(fps=fps_out, codec="libx264", preset="fast",
                     ffmpeg_params=["-crf", "23"], logger=None)
    if keep_audio and src.audio:
        wv_kwargs["audio_codec"] = "aac"
    else:
        wv_kwargs["audio"] = False

    t = threading.Thread(target=final.write_videofile,
                         args=(str(out_path),), kwargs=wv_kwargs, daemon=True)
    t.start()
    pct = 60
    while t.is_alive():
        time.sleep(0.4)
        pct = min(pct + 1, 95)
        progress_cb(pct)
    t.join()

    progress_cb(100)
    log_cb(f"✅  Done → {out_path}")
    return str(out_path)


# ── 5. Zone Preview Canvas ────────────────────────────────────────

class ZonePreview(tk.Canvas):
    """Plain-tkinter canvas — shows template with a fixed YELLOW_ZONE indicator."""
    HANDLE_R = 6

    def __init__(self, parent, size=PREVIEW_SIZE, on_change=None, **kw):
        kw.pop("bg", None)   # ignore any bg passed by caller; canvas uses its own
        super().__init__(parent, width=size, height=size,
                         bg="#111111", highlightthickness=1,
                         highlightbackground=ACCENT2, **kw)
        self._size      = size
        self._on_change = on_change
        self._tmpl_img  = None
        self._tk_img    = None
        self._scale     = size / TEMPLATE_SIZE[0]
        self._zone_t    = list(YELLOW_ZONE)
        self._zone_c    = [v * self._scale for v in self._zone_t]

        # drag state
        self._drag_mode  = None
        self._drag_start = (0, 0)
        self._zone_start = (0, 0, 0, 0)

        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)
        self._draw_placeholder()

    def load_template(self, path: str):
        try:
            img = Image.open(path).convert("RGB").resize(
                (self._size, self._size), Image.LANCZOS)
            self._tmpl_img = img
            self._redraw()
        except Exception as e:
            self._draw_placeholder(str(e))

    def set_zone_template(self, zone: tuple):
        self._zone_t = list(zone)
        self._zone_c = [v * self._scale for v in self._zone_t]
        self._redraw()
        if self._on_change:
            self._on_change(*[int(v) for v in self._zone_t])

    def get_zone_template(self) -> tuple:
        return tuple(int(v) for v in self._zone_t)

    # ── internal ──────────────────────────────────────────────────
    def _update_template_zone(self):
        s = self._scale
        self._zone_t = [v / s for v in self._zone_c]
        self._zone_t[0] = max(0, min(self._zone_t[0], TEMPLATE_SIZE[0]))
        self._zone_t[1] = max(0, min(self._zone_t[1], TEMPLATE_SIZE[1]))
        self._zone_t[2] = max(self._zone_t[0]+10, min(self._zone_t[2], TEMPLATE_SIZE[0]))
        self._zone_t[3] = max(self._zone_t[1]+10, min(self._zone_t[3], TEMPLATE_SIZE[1]))
        if self._on_change:
            self._on_change(*[int(v) for v in self._zone_t])

    def _redraw(self):
        self.delete("all")
        s = self._size
        if self._tmpl_img:
            self._tk_img = ImageTk.PhotoImage(self._tmpl_img)
            self.create_image(0, 0, anchor="nw", image=self._tk_img)
        else:
            self.create_rectangle(0, 0, s, s, fill="#1a1a1a", outline="")
            self.create_text(s//2, s//2, text="No template loaded",
                             fill=TEXT_DIM, font=("Calibri", 11))

        x1, y1, x2, y2 = [int(v) for v in self._zone_c]
        for rect in [(0,0,s,y1),(0,y2,s,s),(0,y1,x1,y2),(x2,y1,s,y2)]:
            self.create_rectangle(*rect, fill="#000000", outline="", stipple="gray50")

        self.create_rectangle(x1, y1, x2, y2, outline=ACCENT, width=2, dash=(6,3))
        self.create_text(x1+4, y1+4, anchor="nw",
                         text=f"{int(self._zone_t[2]-self._zone_t[0])}×"
                              f"{int(self._zone_t[3]-self._zone_t[1])}",
                         fill=ACCENT, font=("Calibri", 9, "bold"))
        r = self.HANDLE_R
        for hx, hy in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
            self.create_oval(hx-r, hy-r, hx+r, hy+r,
                             fill=ACCENT, outline=BG_DARK, width=1)

    def _draw_placeholder(self, msg="Drop a template image"):
        self.delete("all")
        s = self._size
        self.create_rectangle(0, 0, s, s, fill="#1a1a1a", outline="")
        self.create_text(s//2, s//2, text=msg, fill=TEXT_DIM,
                         font=("Calibri", 11), width=s-20)

    def _hit_handle(self, mx, my):
        r = self.HANDLE_R + 3
        x1, y1, x2, y2 = self._zone_c
        for hx, hy, name in [(x1,y1,"NW"),(x2,y1,"NE"),(x1,y2,"SW"),(x2,y2,"SE")]:
            if abs(mx-hx) <= r and abs(my-hy) <= r:
                return name
        return None

    def _hit_zone(self, mx, my):
        x1, y1, x2, y2 = self._zone_c
        return x1 <= mx <= x2 and y1 <= my <= y2

    def _on_press(self, ev):
        handle = self._hit_handle(ev.x, ev.y)
        if handle:
            self._drag_mode = f"resize-{handle}"
        elif self._hit_zone(ev.x, ev.y):
            self._drag_mode = "move"
        else:
            self._drag_mode = None
            return
        self._drag_start = (ev.x, ev.y)
        self._zone_start = tuple(self._zone_c)

    def _on_drag(self, ev):
        if not self._drag_mode:
            return
        dx = ev.x - self._drag_start[0]
        dy = ev.y - self._drag_start[1]
        x1, y1, x2, y2 = self._zone_start
        s = self._size
        if self._drag_mode == "move":
            w, h = x2-x1, y2-y1
            nx1 = max(0, min(x1+dx, s-w))
            ny1 = max(0, min(y1+dy, s-h))
            self._zone_c = [nx1, ny1, nx1+w, ny1+h]
        elif self._drag_mode == "resize-NW":
            self._zone_c = [max(0,min(x1+dx,x2-10)), max(0,min(y1+dy,y2-10)), x2, y2]
        elif self._drag_mode == "resize-NE":
            self._zone_c = [x1, max(0,min(y1+dy,y2-10)), min(s,max(x2+dx,x1+10)), y2]
        elif self._drag_mode == "resize-SW":
            self._zone_c = [max(0,min(x1+dx,x2-10)), y1, x2, min(s,max(y2+dy,y1+10))]
        elif self._drag_mode == "resize-SE":
            self._zone_c = [x1, y1, min(s,max(x2+dx,x1+10)), min(s,max(y2+dy,y1+10))]
        self._update_template_zone()
        self._redraw()

    def _on_release(self, _ev):
        self._drag_mode = None

    def _on_hover(self, ev):
        handle = self._hit_handle(ev.x, ev.y)
        if handle in ("NW", "SE"):
            self.configure(cursor="size_nw_se")
        elif handle in ("NE", "SW"):
            self.configure(cursor="size_ne_sw")
        elif self._hit_zone(ev.x, ev.y):
            self.configure(cursor="fleur")
        else:
            self.configure(cursor="")


# ── 6. Helper: styled tk widgets ─────────────────────────────────

def _label(parent, text, color=TEXT_W, size=11, bold=False, **kw):
    font = ("Calibri", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, bg=parent["bg"] if hasattr(parent,"__getitem__") else BG_DARK,
                    fg=color, font=font, **kw)

def _entry(parent, textvariable, width=28):
    e = tk.Entry(parent, textvariable=textvariable, width=width,
                 bg=BG_DARK, fg=TEXT_W, insertbackground=TEXT_W,
                 relief="flat", highlightthickness=1,
                 highlightbackground=ACCENT2, highlightcolor=ACCENT)
    return e

def _btn(parent, text, cmd, bg=BG_CARD, fg=TEXT_W, bold=False, width=None):
    bkw = dict(bg=bg, fg=fg, relief="flat", cursor="hand2",
               font=("Calibri", 11, "bold" if bold else "normal"),
               activebackground=ACCENT2, activeforeground=BG_DARK,
               padx=8, pady=4)
    if width is not None:
        bkw["width"] = width
    return tk.Button(parent, text=text, command=cmd, **bkw)

def _section(parent, title, row):
    """Dark card frame with a title label."""
    f = tk.Frame(parent, bg=BG_CARD, padx=10, pady=8)
    f.grid(row=row, column=0, sticky="ew", padx=14, pady=(0,8))
    f.grid_columnconfigure(0, weight=1)
    tk.Label(f, text=title, bg=BG_CARD, fg=ACCENT,
             font=("Calibri", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
    inner = tk.Frame(f, bg=BG_CARD)
    inner.grid(row=1, column=0, sticky="ew")
    inner.grid_columnconfigure(0, weight=1)
    return inner, row + 1


# ── 7. Main App ───────────────────────────────────────────────────

class MeowndApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x860")
        self.minsize(900, 760)
        self.configure(bg=BG_DARK)

        self._log_q      = queue.Queue()
        self._prog_q     = queue.Queue()
        self._busy       = False
        self._stream_url = ""
        self._zone       = YELLOW_ZONE           # ← always constant
        self._tmpl_path  = self._find_template()

        self._build_ui()
        if self._tmpl_path:
            self.after(200, lambda: self._load_template_preview())
        self._poll_queues()

    def _find_template(self) -> str:
        p = Path(TEMPLATE_NAME)
        return str(p) if p.exists() else ""

    # ── UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── LEFT: Preview ─────────────────────────────────────────
        left = tk.Frame(self, bg=BG_MID, width=PREVIEW_SIZE + 24)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        tk.Label(left, text="ZONE PREVIEW", bg=BG_MID, fg=ACCENT,
                 font=("Calibri", 11, "bold")).grid(row=0, column=0, pady=(10,4))

        self._preview = ZonePreview(left, size=PREVIEW_SIZE,
                                    on_change=self._zone_changed, bg=BG_MID)
        self._preview.grid(row=1, column=0, padx=12, pady=(0,8))

        tk.Label(left, text="Drag to move  •  Corners to resize",
                 bg=BG_MID, fg=TEXT_DIM,
                 font=("Calibri", 10)).grid(row=2, column=0, pady=(0,4))

        _btn(left, "Reset Zone", self._reset_zone).grid(
            row=3, column=0, sticky="ew", padx=12, pady=2)

        # Zone coord display (read-only, updated live)
        zf = tk.Frame(left, bg=BG_CARD, padx=6, pady=6)
        zf.grid(row=4, column=0, padx=12, pady=(8,0), sticky="ew")
        for i in range(4):
            zf.grid_columnconfigure(i, weight=1)
        self._zone_vars = []
        for i, lbl in enumerate(["x1", "y1", "x2", "y2"]):
            tk.Label(zf, text=lbl, bg=BG_CARD, fg=TEXT_DIM,
                     font=("Calibri", 10)).grid(row=0, column=i, padx=3)
            v = tk.StringVar(value=str(self._zone[i]))
            e = tk.Entry(zf, textvariable=v, width=6,
                         bg=BG_DARK, fg=TEXT_W, insertbackground=TEXT_W,
                         relief="flat", highlightthickness=1,
                         highlightbackground=ACCENT2)
            e.grid(row=1, column=i, padx=3, pady=(0,2))
            v.trace_add("write", lambda *a, i=i, v=v: self._zone_entry_changed(i, v))
            self._zone_vars.append(v)

        # ── RIGHT: Scrollable controls ────────────────────────────
        right_outer = tk.Frame(self, bg=BG_DARK)
        right_outer.grid(row=0, column=1, sticky="nsew")
        right_outer.grid_rowconfigure(0, weight=1)
        right_outer.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(right_outer, bg=BG_DARK, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(right_outer, orient="vertical", command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        right = tk.Frame(canvas, bg=BG_DARK)
        right.grid_columnconfigure(0, weight=1)
        _win = canvas.create_window((0,0), window=right, anchor="nw")

        def _on_configure(ev):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(_win, width=ev.width)

        right.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", _on_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        # Header
        tk.Label(right, text="🐱  MEOWND  MEME  VIDEO  MAKER  v2",
                 bg=BG_MID, fg=ACCENT, font=("Calibri", 16, "bold"),
                 pady=12).grid(row=0, column=0, sticky="ew")

        r = 1

        # ── Template ──────────────────────────────────────────────
        tc, r = _section(right, "📄  Template Image", r)
        self._tmpl_var = tk.StringVar(value=self._tmpl_path)
        _entry(tc, self._tmpl_var).grid(row=0, column=0, sticky="ew", pady=(0,4))
        bf = tk.Frame(tc, bg=BG_CARD); bf.grid(row=1, column=0, sticky="ew")
        bf.grid_columnconfigure((0,1), weight=1)
        _btn(bf, "Browse", self._browse_template).grid(row=0, column=0, sticky="ew", padx=(0,2))
        _btn(bf, "Load Preview", self._load_template_preview,
             bg=ACCENT, fg=BG_DARK, bold=True).grid(row=0, column=1, sticky="ew", padx=(2,0))

        # ── Video / Link ──────────────────────────────────────────
        vc, r = _section(right, "🎬  Video — Paste any link (YT / TikTok / IG / FB…)", r)
        self._url_var = tk.StringVar()
        _entry(vc, self._url_var).grid(row=0, column=0, sticky="ew", pady=(0,4))
        bf2 = tk.Frame(vc, bg=BG_CARD); bf2.grid(row=1, column=0, sticky="ew")
        bf2.grid_columnconfigure((0,1), weight=1)
        _btn(bf2, "Browse File", self._browse_video).grid(
            row=0, column=0, sticky="ew", padx=(0,2))
        _btn(bf2, "✅  Use this link / file", self._use_link,
             bg=ACCENT, fg=BG_DARK, bold=True).grid(row=0, column=1, sticky="ew", padx=(2,0))
        self._vid_status = tk.Label(vc, text="No video set", bg=BG_CARD,
                                    fg=TEXT_DIM, font=("Calibri", 10))
        self._vid_status.grid(row=2, column=0, sticky="w", pady=(4,0))
        tk.Label(vc, text="💡 No download needed — video is streamed during render",
                 bg=BG_CARD, fg=BLUE, font=("Calibri", 10),
                 wraplength=480, justify="left").grid(row=3, column=0, sticky="w")

        # ── Trim ──────────────────────────────────────────────────
        tr, r = _section(right, "✂️  Trim", r)
        tf = tk.Frame(tr, bg=BG_CARD); tf.grid(row=0, column=0, sticky="ew")
        tf.grid_columnconfigure((0,1), weight=1)
        self._start_var = tk.StringVar(value="0")
        self._end_var   = tk.StringVar(value="")
        for i, (lbl, var, ph) in enumerate([
            ("Start (s)", self._start_var, "0"),
            ("End (s)",   self._end_var,   "blank = full clip"),
        ]):
            tk.Label(tf, text=lbl, bg=BG_CARD, fg=TEXT_DIM,
                     font=("Calibri", 10)).grid(row=0, column=i, padx=6, sticky="w")
            e = _entry(tf, var, width=14)
            e.grid(row=1, column=i, padx=6, sticky="ew")

        # ── Output Settings ───────────────────────────────────────
        oc, r = _section(right, "⚙️  Output Settings", r)
        of = tk.Frame(oc, bg=BG_CARD); of.grid(row=0, column=0, sticky="ew")
        of.grid_columnconfigure((0,1,2), weight=1)

        tk.Label(of, text="Size", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Calibri",10)).grid(row=0, column=0, padx=4, sticky="w")
        self._size_var = tk.StringVar(value="1080×1080")
        ttk.Combobox(of, textvariable=self._size_var, state="readonly", width=14,
                     values=["1080×1080","1920×1080","1080×1920","Custom"]
                     ).grid(row=1, column=0, padx=4, sticky="ew")
        self._size_var.trace_add("write", lambda *a: self._toggle_custom_size())

        tk.Label(of, text="FPS", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Calibri",10)).grid(row=0, column=1, padx=4, sticky="w")
        self._fps_var = tk.StringVar(value="30")
        ttk.Combobox(of, textvariable=self._fps_var, state="readonly", width=6,
                     values=["24","25","30","50","60"]
                     ).grid(row=1, column=1, padx=4, sticky="ew")

        tk.Label(of, text="Border px", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Calibri",10)).grid(row=0, column=2, padx=4, sticky="w")
        self._border_var = tk.StringVar(value="4")
        _entry(of, self._border_var, width=6).grid(row=1, column=2, padx=4, sticky="ew")

        # Custom size (hidden unless selected)
        self._custom_f = tk.Frame(oc, bg=BG_CARD)
        self._custom_f.grid(row=1, column=0, sticky="ew", pady=(6,0))
        self._custom_f.grid_columnconfigure((0,1), weight=1)
        self._cw_var = tk.StringVar(value="1080")
        self._ch_var = tk.StringVar(value="1080")
        for i, (lbl, var) in enumerate([("Custom W", self._cw_var),("Custom H", self._ch_var)]):
            tk.Label(self._custom_f, text=lbl, bg=BG_CARD, fg=TEXT_DIM,
                     font=("Calibri",10)).grid(row=0, column=i, padx=6, sticky="w")
            _entry(self._custom_f, var, width=8).grid(row=1, column=i, padx=6, sticky="ew")
        self._custom_f.grid_remove()

        # Toggles
        tgf = tk.Frame(oc, bg=BG_CARD); tgf.grid(row=2, column=0, sticky="ew", pady=(8,0))
        tgf.grid_columnconfigure((0,1,2,3), weight=1)
        self._audio_var = tk.BooleanVar(value=True)
        self._loop_var  = tk.BooleanVar(value=False)
        tk.Checkbutton(tgf, text="Keep Audio", variable=self._audio_var,
                       bg=BG_CARD, fg=TEXT_W, selectcolor=BG_DARK,
                       activebackground=BG_CARD, font=("Calibri",11)
                       ).grid(row=0, column=0, padx=4, sticky="w")
        tk.Checkbutton(tgf, text="Loop Video", variable=self._loop_var,
                       bg=BG_CARD, fg=TEXT_W, selectcolor=BG_DARK,
                       activebackground=BG_CARD, font=("Calibri",11)
                       ).grid(row=0, column=1, padx=4, sticky="w")
        tk.Label(tgf, text="Border colour:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Calibri",10)).grid(row=0, column=2, padx=(12,2), sticky="e")
        self._bcolor_var = tk.StringVar(value="#f5c842")
        _entry(tgf, self._bcolor_var, width=10).grid(row=0, column=3, padx=2, sticky="w")

        # ── Output path ───────────────────────────────────────────
        opf, r = _section(right, "💾  Output Path", r)
        opf2 = tk.Frame(opf, bg=BG_CARD); opf2.grid(row=0, column=0, sticky="ew")
        opf2.grid_columnconfigure(0, weight=1)
        self._out_var = tk.StringVar(value=str(OUTPUT_DIR / "meownd_output.mp4"))
        _entry(opf2, self._out_var).grid(row=0, column=0, sticky="ew")
        _btn(opf2, "…", self._browse_output, width=3).grid(row=0, column=1, padx=(4,0))

        # ── Log ───────────────────────────────────────────────────
        log_f, r = _section(right, "📋  Log", r)
        self._log_box = scrolledtext.ScrolledText(
            log_f, height=8, bg=BG_DARK, fg="#c8f5a0",
            font=("Calibri", 10), wrap="word", state="disabled",
            relief="flat", highlightthickness=1, highlightbackground=ACCENT2)
        self._log_box.grid(row=0, column=0, sticky="ew")

        # ── Progress + Render ─────────────────────────────────────
        bot = tk.Frame(right, bg=BG_DARK)
        bot.grid(row=r, column=0, sticky="ew", padx=14, pady=(4,14))
        bot.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Gold.Horizontal.TProgressbar",
                        troughcolor=BG_CARD, background=ACCENT, thickness=12)
        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(bot, variable=self._progress_var, maximum=1.0,
                        style="Gold.Horizontal.TProgressbar"
                        ).grid(row=0, column=0, sticky="ew", padx=(0,10))

        self._render_btn = _btn(bot, "🎬  RENDER VIDEO", self._run_render,
                                bg=ACCENT, fg=BG_DARK, bold=True)
        self._render_btn.configure(padx=16, pady=8)
        self._render_btn.grid(row=0, column=1)

    # ── Zone sync ─────────────────────────────────────────────────
    def _zone_changed(self, x1, y1, x2, y2):
        self._zone = (x1, y1, x2, y2)
        for var, val in zip(self._zone_vars, (x1, y1, x2, y2)):
            var.set(str(val))

    def _zone_entry_changed(self, i, v):
        try:
            vals = [int(var.get()) for var in self._zone_vars]
            self._zone = tuple(vals)
            self._preview.set_zone_template(tuple(vals))
        except ValueError:
            pass

    def _reset_zone(self):
        self._zone = YELLOW_ZONE
        self._preview.set_zone_template(YELLOW_ZONE)
        for var, val in zip(self._zone_vars, YELLOW_ZONE):
            var.set(str(val))

    # ── Logging ───────────────────────────────────────────────────
    def _log(self, msg: str):
        self._log_q.put(msg)

    def _append_log(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_progress(self, val: int):
        self._prog_q.put(val / 100)

    def _poll_queues(self):
        try:
            while True: self._append_log(self._log_q.get_nowait())
        except queue.Empty: pass
        try:
            while True: self._progress_var.set(self._prog_q.get_nowait())
        except queue.Empty: pass
        self.after(80, self._poll_queues)

    # ── Actions ───────────────────────────────────────────────────
    def _browse_template(self):
        f = filedialog.askopenfilename(filetypes=[("Images","*.jpg *.jpeg *.png")])
        if f:
            self._tmpl_var.set(f)

    def _load_template_preview(self):
        path = self._tmpl_var.get().strip()
        if not Path(path).exists():
            self._log("⚠  Template file not found.")
            return
        self._tmpl_path = path
        self._preview.load_template(path)
        self._preview.set_zone_template(self._zone)
        self._log(f"🖼  Template loaded: {Path(path).name}")

    def _browse_video(self):
        f = filedialog.askopenfilename(
            filetypes=[("Video","*.mp4 *.mov *.avi *.mkv *.webm *.flv")])
        if f:
            self._url_var.set(f)
            self._stream_url = f
            self._vid_status.configure(text=f"📂  {Path(f).name}", fg=GREEN)

    def _browse_output(self):
        f = filedialog.asksaveasfilename(defaultextension=".mp4",
                                          filetypes=[("MP4","*.mp4")])
        if f:
            self._out_var.set(f)

    def _toggle_custom_size(self):
        if self._size_var.get() == "Custom":
            self._custom_f.grid()
        else:
            self._custom_f.grid_remove()

    def _use_link(self):
        if self._busy:
            return
        url = self._url_var.get().strip()
        if not url:
            self._log("⚠  Paste a URL or browse a file first.")
            return
        self._set_busy(True)
        def _resolve():
            try:
                su = resolve_stream_url(url, self._log)
                self._stream_url = su
                name = Path(url).name if Path(url).exists() else url[:60]
                self.after(0, lambda: self._vid_status.configure(
                    text=f"✅  Ready: {name}", fg=GREEN))
                self._log("🔗  Stream URL ready.")
            except Exception as e:
                self._log(f"❌  Could not resolve URL: {e}")
                self.after(0, lambda: self._vid_status.configure(
                    text="❌  Failed to resolve", fg=RED))
            finally:
                self._set_busy(False)
        threading.Thread(target=_resolve, daemon=True).start()

    def _get_size(self):
        presets = {"1080×1080":(1080,1080),"1920×1080":(1920,1080),"1080×1920":(1080,1920)}
        sel = self._size_var.get()
        if sel in presets:
            return presets[sel]
        try:
            return (int(self._cw_var.get()), int(self._ch_var.get()))
        except ValueError:
            return (1080, 1080)

    def _run_render(self):
        if self._busy:
            return
        tmpl = self._tmpl_var.get().strip()
        if not Path(tmpl).exists():
            self._log("⚠  Template image not found — load it first.")
            return
        if not self._stream_url:
            self._log("⚠  No video set — paste a link and click 'Use this link / file'.")
            return

        end_raw = self._end_var.get().strip()
        params = {
            "stream_url": self._stream_url,
            "tmpl_path":  tmpl,
            "out_path":   self._out_var.get(),
            "zone":       self._zone,          # constant YELLOW_ZONE (or dragged)
            "out_size":   self._get_size(),
            "start_t":    float(self._start_var.get() or 0),
            "end_t":      float(end_raw) if end_raw else None,
            "keep_audio": self._audio_var.get(),
            "fps":        int(self._fps_var.get()),
            "loop":       self._loop_var.get(),
            "border_px":  int(self._border_var.get() or 0),
            "border_col": self._bcolor_var.get(),
        }
        self._set_busy(True)
        self._progress_var.set(0)
        self._log("─" * 44)
        self._log(f"🚀  Render started …  size={params['out_size']}  fps={params['fps']}")

        def _render():
            try:
                out = composite_video(params, self._log, self._set_progress)
                self._log(f"🎉  Saved: {out}")
            except Exception as e:
                self._log(f"❌  Render error: {e}")
                self._log(traceback.format_exc())
            finally:
                self._set_busy(False)

        threading.Thread(target=_render, daemon=True).start()

    def _set_busy(self, state: bool):
        self._busy = state
        txt = "⏳  Working…" if state else "🎬  RENDER VIDEO"
        st  = "disabled"   if state else "normal"
        self.after(0, lambda: self._render_btn.configure(text=txt, state=st))


# ── 8. Entry point ────────────────────────────────────────────────
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    app = MeowndApp()
    app.mainloop()