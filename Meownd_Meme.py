#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║     MEOWND MEME VIDEO MAKER  v2  —  CTk GUI Edition         ║
║  • Live draggable/resizable zone preview on template         ║
║  • Stream-direct render — just paste any link, no download   ║
╚══════════════════════════════════════════════════════════════╝
Run:   python meownd_meme_gui.py
"""

# ── 0. Bootstrap ──────────────────────────────────────────────────
import sys, subprocess, os

DEPS = {
    "customtkinter": "customtkinter",
    "PIL":           "pillow",
    "cv2":           "opencv-python",
    "numpy":         "numpy",
    "moviepy":       "moviepy",
    "yt_dlp":        "yt-dlp",
    "requests":      "requests",
}

def _can_import(mod):
    try: __import__(mod); return True
    except ImportError: return False

def _bootstrap():
    missing = [pkg for mod, pkg in DEPS.items() if not _can_import(mod)]
    if missing:
        print(f"[setup] Installing: {', '.join(missing)}")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + missing
        )
        print("[setup] Done — restarting…\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

_bootstrap()

# ── 1. Imports ────────────────────────────────────────────────────
import threading, queue, shutil, re, time, traceback
from pathlib import Path
from tkinter import filedialog, Canvas

import customtkinter as ctk
import numpy as np
import cv2
from PIL import Image, ImageTk, ImageDraw

# ── 2. Constants ──────────────────────────────────────────────────
APP_TITLE     = "🐱  Meownd Meme Video Maker  v2"
TEMPLATE_NAME = "1778721896370_final_meownd_meme_TEMPLATE.jpg"
OUTPUT_DIR    = Path("meownd_outputs")
TEMPLATE_SIZE = (1080, 1080)
YELLOW_ZONE   = (466, 101, 1036, 731)

ACCENT   = "#f5c842"
ACCENT2  = "#e0a800"
BG_DARK  = "#1a1a1a"
BG_MID   = "#242424"
BG_CARD  = "#2e2e2e"
TEXT_W   = "#f0f0f0"
TEXT_DIM = "#888888"
GREEN    = "#4caf50"
RED      = "#f44336"
BLUE     = "#4fc3f7"

PREVIEW_SIZE = 380   # px — square canvas for preview

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── 3. Stream URL resolver (no file download) ─────────────────────

def resolve_stream_url(url: str, log_cb) -> str:
    """
    Returns a direct streamable URL for any supported platform link.
    For plain video file URLs, returns the URL as-is.
    """
    # Already a direct video file link?
    if re.search(r"\.(mp4|webm|mov|avi|mkv|flv|m4v)(\?.*)?$", url, re.I):
        log_cb(f"🔗  Direct video URL detected — streaming in place.")
        return url

    # Local file?
    if Path(url).exists():
        log_cb(f"📂  Local file detected.")
        return url

    log_cb("🔍  Resolving stream URL via yt-dlp (no download)…")
    import yt_dlp
    opts = {
        "format":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet":   True,
        "no_warnings": True,
        "skip_download": True,       # ← key: extract info only
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Prefer a single merged mp4 URL
    formats = info.get("formats", [])
    # Try to find best combined (video+audio) mp4
    best = None
    for f in reversed(formats):
        if f.get("vcodec") != "none" and f.get("acodec") != "none":
            if f.get("ext") == "mp4":
                best = f.get("url")
                break
    if not best:
        # fallback — just take the last format
        best = formats[-1].get("url") if formats else info.get("url")

    log_cb(f"✅  Stream URL resolved ({info.get('title','?')[:50]})")
    return best


# ── 4. Yellow-zone detector ───────────────────────────────────────

def detect_yellow_zone(path: str) -> tuple:
    img = cv2.imread(path)
    if img is None:
        return YELLOW_ZONE
    hsv  = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([18,80,150]), np.array([35,255,255]))
    ys, xs = np.where(mask > 0)
    if len(xs) < 100:
        return YELLOW_ZONE
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


# ── 5. Compositor ─────────────────────────────────────────────────

def composite_video(params: dict, log_cb, progress_cb):
    # Support both moviepy v1 (.editor) and v2 (direct import)
    try:
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip
    except ModuleNotFoundError:
        from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, ColorClip

    stream_url  = params["stream_url"]
    tmpl_path   = params["tmpl_path"]
    out_path    = params["out_path"]
    zone        = params["zone"]
    out_size    = params["out_size"]
    start_t     = params["start_t"]
    end_t       = params["end_t"]
    keep_audio  = params["keep_audio"]
    fps_out     = params["fps"]
    loop_video  = params["loop"]
    border_px   = params["border_px"]
    border_col  = params["border_col"]

    ow, oh = out_size
    x1,y1,x2,y2 = zone
    tw, th = TEMPLATE_SIZE
    sx, sy = ow/tw, oh/th
    zx1,zy1 = int(x1*sx), int(y1*sy)
    zx2,zy2 = int(x2*sx), int(y2*sy)
    zw, zh  = zx2-zx1, zy2-zy1

    log_cb(f"📐  Zone in output: ({zx1},{zy1})→({zx2},{zy2})  [{zw}×{zh}]")
    progress_cb(5)

    # Compat shims — probe actual class methods, works across moviepy 1.x/2.0/2.1+
    from moviepy import VideoFileClip as _VFC
    _has = lambda name: hasattr(_VFC, name)

    # moviepy 2.1+: subclipped / resized / cropped / with_position / with_duration / with_fps / with_audio
    # moviepy 2.0:  with_subclip / resized / cropped / with_position / with_duration / with_fps / with_audio
    # moviepy 1.x:  subclip      / resize  / crop    / set_position  / set_duration  / set_fps  / set_audio

    def _subclip(c, s, e):
        if _has("subclipped"):   return c.subclipped(s, e)
        if _has("with_subclip"): return c.with_subclip(s, e)
        return c.subclip(s, e)

    def _resize(c, sz):
        if _has("resized"): return c.resized(sz)
        return c.resize(sz)

    def _crop(c, **kw):
        if _has("cropped"): return c.cropped(**kw)
        return c.crop(**kw)

    def _set_pos(c, pos):
        if _has("with_position"): return c.with_position(pos)
        return c.set_position(pos)

    def _set_dur(c, d):
        if _has("with_duration"): return c.with_duration(d)
        return c.set_duration(d)

    def _set_fps(c, f):
        if _has("with_fps"): return c.with_fps(f)
        return c.set_fps(f)

    def _set_audio(c, a):
        if _has("with_audio"): return c.with_audio(a)
        return c.set_audio(a)

    import moviepy as _mp
    log_cb("Opening stream (MoviePy {} reads directly from URL)...".format(getattr(_mp, "__version__", "?")))
    src = VideoFileClip(stream_url, audio=keep_audio)
    dur = src.duration
    end = min(end_t, dur) if end_t else dur
    src = _subclip(src, start_t, end)
    log_cb("Clip: {:.1f}s  {}x{}".format(src.duration, src.w, src.h))
    progress_cb(15)

    if loop_video:
        try:
            from moviepy.editor import concatenate_videoclips
        except ModuleNotFoundError:
            from moviepy import concatenate_videoclips
        loops = max(1, int(60 / src.duration) + 1)
        src = _subclip(concatenate_videoclips([src]*loops), 0, min(src.duration*loops, 60))

    # Resize & crop to zone
    scale  = max(zw/src.w, zh/src.h)
    nw, nh = int(src.w*scale), int(src.h*scale)
    vid    = _resize(src, (nw, nh))
    cx, cy = (nw-zw)//2, (nh-zh)//2
    vid    = _crop(vid, x1=cx, y1=cy, x2=cx+zw, y2=cy+zh)
    vid    = _set_pos(vid, (zx1, zy1))
    progress_cb(30)

    # Build template layer — keep RGBA so the hole is truly transparent
    tmpl_img = Image.open(tmpl_path).convert("RGBA").resize((ow, oh), Image.LANCZOS)
    tmpl_np  = np.array(tmpl_img)   # shape: H x W x 4  (R,G,B,A)

    # Cut a fully transparent hole where the video will show through
    tmpl_np[zy1:zy2, zx1:zx2, 3] = 0   # alpha = 0 → transparent

    if border_px > 0:
        r,g,b = tuple(int(border_col.lstrip("#")[i:i+2],16) for i in (0,2,4))
        bp = border_px
        for sl in [
            (slice(max(0,zy1-bp),zy1),    slice(max(0,zx1-bp),zx2+bp)),
            (slice(zy2, zy2+bp),           slice(max(0,zx1-bp),zx2+bp)),
            (slice(max(0,zy1-bp),zy2+bp), slice(max(0,zx1-bp),zx1)),
            (slice(max(0,zy1-bp),zy2+bp), slice(zx2, zx2+bp)),
        ]:
            tmpl_np[sl[0], sl[1], :3] = [r,g,b]
            tmpl_np[sl[0], sl[1],  3] = 255   # fully opaque border

    tmpl_clip = _set_fps(_set_dur(ImageClip(tmpl_np, is_mask=False), src.duration), fps_out)
    progress_cb(50)

    log_cb("Compositing layers...")
    # Stack: white bg → video (in the hole) → template (RGBA, transparent hole on top)
    white_bg = _set_dur(ColorClip(size=(ow,oh), color=[255,255,255]), src.duration)
    # use_bgclip=True tells MoviePy the first clip sets the output size & fps baseline
    final    = CompositeVideoClip([white_bg, vid, tmpl_clip], size=(ow,oh), use_bgclip=True)
    if keep_audio and src.audio:
        final = _set_audio(final, src.audio)
    progress_cb(60)

    log_cb(f"💾  Writing → {out_path} …")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    def _write():
        wv_kwargs = dict(
            fps=fps_out,
            codec="libx264",
            preset="fast",
            ffmpeg_params=["-crf","23"],
            logger=None,
        )
        if keep_audio and src.audio:
            wv_kwargs["audio_codec"] = "aac"
        else:
            wv_kwargs["audio"] = False
        final.write_videofile(str(out_path), **wv_kwargs)
    t = threading.Thread(target=_write, daemon=True)
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


# ── 6. Zone Preview Canvas ─────────────────────────────────────────

class ZonePreview(Canvas):
    """
    A tkinter Canvas showing the template image with a draggable,
    resizable zone rectangle.  Emits zone changes via on_change(x1,y1,x2,y2).
    All coordinates are in template-image space (1080×1080).
    """
    HANDLE_R = 6   # resize handle radius in canvas px

    def __init__(self, parent, size=PREVIEW_SIZE, on_change=None, **kw):
        super().__init__(parent, width=size, height=size,
                         bg="#111111", highlightthickness=1,
                         highlightbackground=ACCENT2, **kw)
        self._size     = size
        self._on_change= on_change
        self._tmpl_img = None   # PIL Image (preview sized)
        self._tk_img   = None   # kept alive
        self._zone_c   = list(YELLOW_ZONE)   # canvas coords
        self._zone_t   = list(YELLOW_ZONE)   # template coords
        self._scale    = 1.0

        self._drag_mode  = None   # "move" | "resize-NW/NE/SW/SE"
        self._drag_start = (0,0)
        self._zone_start = (0,0,0,0)

        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)

        self._draw_placeholder()

    # ── Template loading ────────────────────────────────────────
    def load_template(self, path: str):
        try:
            img = Image.open(path).convert("RGB")
            s   = self._size
            img = img.resize((s, s), Image.LANCZOS)
            self._tmpl_img = img
            self._scale    = s / TEMPLATE_SIZE[0]   # assumes square
            self._update_canvas_zone()
            self._redraw()
        except Exception as e:
            self._draw_placeholder(str(e))

    def set_zone_template(self, zone: tuple):
        """Set zone in template (1080×1080) space."""
        self._zone_t = list(zone)
        self._update_canvas_zone()
        self._redraw()
        if self._on_change:
            self._on_change(*self._zone_t)

    def get_zone_template(self) -> tuple:
        return tuple(int(v) for v in self._zone_t)

    # ── Internal helpers ────────────────────────────────────────
    def _update_canvas_zone(self):
        s = self._scale
        self._zone_c = [v * s for v in self._zone_t]

    def _update_template_zone(self):
        s = self._scale
        self._zone_t = [v / s for v in self._zone_c]
        # clamp
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
            self.create_rectangle(0,0,s,s,fill="#1a1a1a",outline="")
            self.create_text(s//2, s//2, text="No template loaded",
                             fill=TEXT_DIM, font=("Calibri",11))

        x1,y1,x2,y2 = [int(v) for v in self._zone_c]

        # Dim overlay outside zone (stipple = ~50% alpha, Tkinter-compatible)
        for rect in [(0,0,s,y1),(0,y2,s,s),(0,y1,x1,y2),(x2,y1,s,y2)]:
            self.create_rectangle(*rect, fill="#000000", outline="", stipple="gray50")

        # Zone rect
        self.create_rectangle(x1,y1,x2,y2,
                              outline=ACCENT, width=2, dash=(6,3), tags="zone")
        # Zone label
        self.create_text(x1+4, y1+4, anchor="nw",
                         text=f"{int(self._zone_t[2]-self._zone_t[0])}×{int(self._zone_t[3]-self._zone_t[1])}",
                         fill=ACCENT, font=("Calibri",9,"bold"))

        # Corner handles
        r = self.HANDLE_R
        for hx, hy, tag in [
            (x1,y1,"NW"), (x2,y1,"NE"), (x1,y2,"SW"), (x2,y2,"SE")
        ]:
            self.create_oval(hx-r,hy-r,hx+r,hy+r,
                             fill=ACCENT, outline=BG_DARK, width=1, tags=f"handle-{tag}")

    def _draw_placeholder(self, msg="Drop a template image"):
        self.delete("all")
        s = self._size
        self.create_rectangle(0,0,s,s,fill="#1a1a1a",outline="")
        self.create_text(s//2,s//2,text=msg,fill=TEXT_DIM,
                         font=("Calibri",11), width=s-20)

    # ── Hit testing ─────────────────────────────────────────────
    def _hit_handle(self, mx, my):
        r = self.HANDLE_R + 3
        x1,y1,x2,y2 = self._zone_c
        for hx, hy, name in [(x1,y1,"NW"),(x2,y1,"NE"),(x1,y2,"SW"),(x2,y2,"SE")]:
            if abs(mx-hx) <= r and abs(my-hy) <= r:
                return name
        return None

    def _hit_zone(self, mx, my):
        x1,y1,x2,y2 = self._zone_c
        return x1 <= mx <= x2 and y1 <= my <= y2

    # ── Mouse events ─────────────────────────────────────────────
    def _on_press(self, ev):
        handle = self._hit_handle(ev.x, ev.y)
        if handle:
            self._drag_mode  = f"resize-{handle}"
        elif self._hit_zone(ev.x, ev.y):
            self._drag_mode  = "move"
        else:
            self._drag_mode  = None
            return
        self._drag_start = (ev.x, ev.y)
        self._zone_start = tuple(self._zone_c)

    def _on_drag(self, ev):
        if not self._drag_mode:
            return
        dx = ev.x - self._drag_start[0]
        dy = ev.y - self._drag_start[1]
        x1,y1,x2,y2 = self._zone_start
        s = self._size

        if self._drag_mode == "move":
            w, h = x2-x1, y2-y1
            nx1 = max(0, min(x1+dx, s-w))
            ny1 = max(0, min(y1+dy, s-h))
            self._zone_c = [nx1, ny1, nx1+w, ny1+h]

        elif self._drag_mode == "resize-NW":
            self._zone_c = [max(0,min(x1+dx,x2-10)),
                            max(0,min(y1+dy,y2-10)), x2, y2]
        elif self._drag_mode == "resize-NE":
            self._zone_c = [x1, max(0,min(y1+dy,y2-10)),
                            min(s,max(x2+dx,x1+10)), y2]
        elif self._drag_mode == "resize-SW":
            self._zone_c = [max(0,min(x1+dx,x2-10)), y1,
                            x2, min(s,max(y2+dy,y1+10))]
        elif self._drag_mode == "resize-SE":
            self._zone_c = [x1, y1,
                            min(s,max(x2+dx,x1+10)),
                            min(s,max(y2+dy,y1+10))]

        self._update_template_zone()
        self._redraw()

    def _on_release(self, _ev):
        self._drag_mode = None

    def _on_hover(self, ev):
        handle = self._hit_handle(ev.x, ev.y)
        if handle in ("NW","SE"):
            self.configure(cursor="size_nw_se")
        elif handle in ("NE","SW"):
            self.configure(cursor="size_ne_sw")
        elif self._hit_zone(ev.x, ev.y):
            self.configure(cursor="fleur")
        else:
            self.configure(cursor="")


# ── 7. Main App ───────────────────────────────────────────────────

class MeowndApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x860")
        self.minsize(900, 760)
        self.configure(fg_color=BG_DARK)

        self._log_q      = queue.Queue()
        self._prog_q     = queue.Queue()
        self._busy       = False
        self._stream_url = ""   # resolved stream URL (or local path)
        self._zone       = YELLOW_ZONE
        self._tmpl_path  = self._find_template()

        self._build_ui()
        if self._tmpl_path:
            self.after(200, lambda: self._preview.load_template(self._tmpl_path))
        self._poll_queues()

    def _find_template(self) -> str:
        p = Path(TEMPLATE_NAME)
        return str(p) if p.exists() else ""

    # ── UI ────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)   # left sidebar
        self.grid_columnconfigure(1, weight=1)   # right content
        self.grid_rowconfigure(0, weight=1)

        # ── LEFT: Preview panel ───────────────────────────────────
        left = ctk.CTkFrame(self, fg_color=BG_MID, corner_radius=0, width=PREVIEW_SIZE+24)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="ZONE PREVIEW",
                     font=ctk.CTkFont("Calibri", 11, "bold"),
                     text_color=ACCENT).grid(row=0, column=0, pady=(10,4))

        self._preview = ZonePreview(left, size=PREVIEW_SIZE,
                                    on_change=self._zone_changed)
        self._preview.grid(row=1, column=0, padx=12, pady=(0,8))

        hint = ctk.CTkLabel(left,
            text="Drag to move  •  Corners to resize",
            font=ctk.CTkFont("Calibri", 10),
            text_color=TEXT_DIM)
        hint.grid(row=2, column=0, pady=(0,6))

        # Reset zone button
        self._btn_small(left, "Reset Zone", self._reset_zone, row=3)

        # Auto-detect button
        self._btn_small(left, "Auto-detect Yellow Zone",
                        self._run_detect_zone, row=4, accent=True)

        # Zone coords display (read-only labels, updated live)
        zf = ctk.CTkFrame(left, fg_color=BG_CARD, corner_radius=8)
        zf.grid(row=5, column=0, padx=12, pady=(8,0), sticky="ew")
        zf.grid_columnconfigure((0,1,2,3), weight=1)
        self._zone_vars = []
        for i, lbl in enumerate(["x1","y1","x2","y2"]):
            ctk.CTkLabel(zf, text=lbl, text_color=TEXT_DIM,
                         font=ctk.CTkFont(size=10)).grid(row=0,column=i,padx=3,pady=(6,0))
            v = ctk.StringVar(value=str(self._zone[i]))
            ctk.CTkEntry(zf, textvariable=v, width=66,
                         fg_color=BG_DARK, border_color=ACCENT2,
                         font=ctk.CTkFont(size=11),
                         ).grid(row=1,column=i,padx=3,pady=(0,6))
            v.trace_add("write", lambda *a, i=i, v=v: self._zone_entry_changed(i, v))
            self._zone_vars.append(v)

        # ── RIGHT: Controls ───────────────────────────────────────
        right = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                       scrollbar_button_color=ACCENT2)
        right.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        right.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(right, fg_color=BG_MID, corner_radius=0, height=60)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0,12))
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="🐱  MEOWND  MEME  VIDEO  MAKER  v2",
                     font=ctk.CTkFont("Calibri", 18, "bold"),
                     text_color=ACCENT).place(relx=0.5, rely=0.5, anchor="center")

        r = 1  # current row in right panel

        # ── Card: Template ────────────────────────────────────────
        tc, r = self._card(right, "📄  Template Image", r)
        self._tmpl_var = ctk.StringVar(value=self._tmpl_path)
        self._entry(tc, self._tmpl_var, row=0, placeholder="Path to meme template .jpg/.png")
        bf = ctk.CTkFrame(tc, fg_color="transparent"); bf.grid(row=1,column=0,sticky="ew",pady=(4,0)); bf.grid_columnconfigure((0,1),weight=1)
        self._btn(bf, "Browse", self._browse_template, col=0, accent=False)
        self._btn(bf, "Load Preview", self._load_template_preview, col=1, accent=True)

        # ── Card: Video / Link ────────────────────────────────────
        vc, r = self._card(right, "🎬  Video — Paste any link (YT / TikTok / IG / FB / Reddit…)", r)
        self._url_var = ctk.StringVar()
        self._entry(vc, self._url_var, row=0,
                    placeholder="https://…  OR  browse a local file")
        bf2 = ctk.CTkFrame(vc, fg_color="transparent"); bf2.grid(row=1,column=0,sticky="ew",pady=(4,0)); bf2.grid_columnconfigure((0,1),weight=1)
        self._btn(bf2, "Browse File", self._browse_video, col=0, accent=False)
        self._btn(bf2, "✅  Use this link / file", self._use_link, col=1, accent=True)
        self._vid_status = ctk.CTkLabel(vc, text="No video set",
                                        font=ctk.CTkFont(size=11), text_color=TEXT_DIM)
        self._vid_status.grid(row=2, column=0, sticky="w", pady=(4,0))
        ctk.CTkLabel(vc,
            text="💡 No download needed — the video is streamed directly during render",
            font=ctk.CTkFont("Calibri", 10), text_color=BLUE,
            wraplength=480).grid(row=3,column=0,sticky="w",pady=(2,0))

        # ── Card: Trim ────────────────────────────────────────────
        tr, r = self._card(right, "✂️  Trim", r)
        tf = ctk.CTkFrame(tr, fg_color="transparent"); tf.grid(row=0,column=0,sticky="ew"); tf.grid_columnconfigure((0,1),weight=1)
        self._start_var = ctk.StringVar(value="0")
        self._end_var   = ctk.StringVar(value="")
        for i,(lbl,var,ph) in enumerate([
            ("Start (s)", self._start_var, "0"),
            ("End (s)",   self._end_var,   "blank = full clip"),
        ]):
            ctk.CTkLabel(tf, text=lbl, text_color=TEXT_DIM,
                         font=ctk.CTkFont(size=11)).grid(row=0,column=i,padx=6,sticky="w")
            ctk.CTkEntry(tf, textvariable=var, placeholder_text=ph,
                         fg_color=BG_DARK, border_color=ACCENT2,
                         font=ctk.CTkFont(size=12)).grid(row=1,column=i,padx=6,sticky="ew")

        # ── Card: Output Settings ─────────────────────────────────
        oc, r = self._card(right, "⚙️  Output Settings", r)
        of = ctk.CTkFrame(oc, fg_color="transparent"); of.grid(row=0,column=0,sticky="ew"); of.grid_columnconfigure((0,1,2),weight=1)

        ctk.CTkLabel(of,text="Size",text_color=TEXT_DIM,font=ctk.CTkFont(size=11)).grid(row=0,column=0,padx=4,sticky="w")
        self._size_var = ctk.StringVar(value="1080×1080")
        ctk.CTkOptionMenu(of,variable=self._size_var,
                          values=["1080×1080","1920×1080","1080×1920","Custom"],
                          fg_color=BG_DARK,button_color=ACCENT2,
                          dropdown_fg_color=BG_CARD,font=ctk.CTkFont(size=12),
                          command=self._toggle_custom_size
                          ).grid(row=1,column=0,padx=4,sticky="ew")

        ctk.CTkLabel(of,text="FPS",text_color=TEXT_DIM,font=ctk.CTkFont(size=11)).grid(row=0,column=1,padx=4,sticky="w")
        self._fps_var = ctk.StringVar(value="30")
        ctk.CTkOptionMenu(of,variable=self._fps_var,values=["24","25","30","50","60"],
                          fg_color=BG_DARK,button_color=ACCENT2,
                          dropdown_fg_color=BG_CARD,font=ctk.CTkFont(size=12)
                          ).grid(row=1,column=1,padx=4,sticky="ew")

        ctk.CTkLabel(of,text="Border px",text_color=TEXT_DIM,font=ctk.CTkFont(size=11)).grid(row=0,column=2,padx=4,sticky="w")
        self._border_var = ctk.StringVar(value="4")
        ctk.CTkEntry(of,textvariable=self._border_var,width=60,
                     fg_color=BG_DARK,border_color=ACCENT2,
                     font=ctk.CTkFont(size=12)).grid(row=1,column=2,padx=4,sticky="ew")

        # Custom size
        self._custom_f = ctk.CTkFrame(oc,fg_color="transparent")
        self._custom_f.grid(row=1,column=0,sticky="ew",pady=(6,0))
        self._custom_f.grid_columnconfigure((0,1),weight=1)
        self._cw_var = ctk.StringVar(value="1080")
        self._ch_var = ctk.StringVar(value="1080")
        for i,(lbl,var) in enumerate([("Custom W",self._cw_var),("Custom H",self._ch_var)]):
            ctk.CTkLabel(self._custom_f,text=lbl,text_color=TEXT_DIM,font=ctk.CTkFont(size=11)).grid(row=0,column=i,padx=6,sticky="w")
            ctk.CTkEntry(self._custom_f,textvariable=var,fg_color=BG_DARK,border_color=ACCENT2,font=ctk.CTkFont(size=12)).grid(row=1,column=i,padx=6,sticky="ew")
        self._custom_f.grid_remove()

        # Toggles + border colour
        tgf = ctk.CTkFrame(oc,fg_color="transparent")
        tgf.grid(row=2,column=0,sticky="ew",pady=(8,0))
        tgf.grid_columnconfigure((0,1,2,3),weight=1)
        self._audio_var = ctk.BooleanVar(value=True)
        self._loop_var  = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(tgf,text="Keep Audio",variable=self._audio_var,
                        checkmark_color=BG_DARK,fg_color=ACCENT,hover_color=ACCENT2,
                        font=ctk.CTkFont(size=12)).grid(row=0,column=0,padx=4,sticky="w")
        ctk.CTkCheckBox(tgf,text="Loop Video",variable=self._loop_var,
                        checkmark_color=BG_DARK,fg_color=ACCENT,hover_color=ACCENT2,
                        font=ctk.CTkFont(size=12)).grid(row=0,column=1,padx=4,sticky="w")
        ctk.CTkLabel(tgf,text="Border colour:",text_color=TEXT_DIM,
                     font=ctk.CTkFont(size=11)).grid(row=0,column=2,padx=(12,2),sticky="e")
        self._bcolor_var = ctk.StringVar(value="#f5c842")
        ctk.CTkEntry(tgf,textvariable=self._bcolor_var,width=80,
                     fg_color=BG_DARK,border_color=ACCENT2,
                     font=ctk.CTkFont(size=12)).grid(row=0,column=3,padx=2,sticky="w")

        # ── Output path ───────────────────────────────────────────
        opf, r = self._card(right, "💾  Output Path", r)
        opf2 = ctk.CTkFrame(opf,fg_color="transparent"); opf2.grid(row=0,column=0,sticky="ew"); opf2.grid_columnconfigure(0,weight=1)
        self._out_var = ctk.StringVar(value=str(OUTPUT_DIR / "meownd_output.mp4"))
        ctk.CTkEntry(opf2,textvariable=self._out_var,fg_color=BG_DARK,
                     border_color=ACCENT,font=ctk.CTkFont(size=12)).grid(row=0,column=0,sticky="ew")
        self._btn_w(opf2,"…",self._browse_output,col=1,w=36)

        # ── Log ───────────────────────────────────────────────────
        log_f, r = self._card(right, "📋  Log", r)
        self._log_box = ctk.CTkTextbox(log_f,fg_color=BG_DARK,
                                       font=ctk.CTkFont("Calibri",10),
                                       text_color="#c8f5a0",wrap="word",
                                       state="disabled",height=130)
        self._log_box.grid(row=0,column=0,sticky="ew")

        # ── Progress + Render ─────────────────────────────────────
        bot = ctk.CTkFrame(right, fg_color="transparent")
        bot.grid(row=r, column=0, sticky="ew", padx=18, pady=(6,18))
        bot.grid_columnconfigure(0, weight=1)
        self._progress = ctk.CTkProgressBar(bot, height=12,
                                            progress_color=ACCENT, fg_color=BG_CARD)
        self._progress.grid(row=0, column=0, sticky="ew", padx=(0,12))
        self._progress.set(0)
        self._render_btn = ctk.CTkButton(bot, text="🎬  RENDER VIDEO",
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         fg_color=ACCENT, hover_color=ACCENT2,
                                         text_color=BG_DARK, width=180, height=40,
                                         corner_radius=8, command=self._run_render)
        self._render_btn.grid(row=0, column=1)

    # ── Widget helpers ────────────────────────────────────────────
    def _card(self, parent, title, row):
        f = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        f.grid(row=row, column=0, padx=18, pady=(0,10), sticky="ew")
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=ACCENT).grid(row=0,column=0,sticky="w",padx=12,pady=(10,4))
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew", padx=10, pady=(0,10))
        inner.grid_columnconfigure(0, weight=1)
        return inner, row + 1

    def _entry(self, parent, var, row, placeholder=""):
        e = ctk.CTkEntry(parent, textvariable=var, placeholder_text=placeholder,
                         fg_color=BG_DARK, border_color=ACCENT2,
                         font=ctk.CTkFont(size=12), height=34)
        e.grid(row=row, column=0, sticky="ew")
        return e

    def _btn(self, parent, text, cmd, col, accent=True):
        b = ctk.CTkButton(parent, text=text, command=cmd,
                          font=ctk.CTkFont(size=12),
                          fg_color=ACCENT if accent else BG_MID,
                          hover_color=ACCENT2 if accent else "#3a3a3a",
                          text_color=BG_DARK if accent else TEXT_W,
                          height=30, corner_radius=6)
        b.grid(row=0, column=col, padx=4, pady=2, sticky="ew")
        parent.grid_columnconfigure(col, weight=1)
        return b

    def _btn_w(self, parent, text, cmd, col, w=100):
        b = ctk.CTkButton(parent, text=text, command=cmd, width=w,
                          font=ctk.CTkFont(size=12), fg_color=BG_MID,
                          hover_color="#3a3a3a", text_color=TEXT_W,
                          height=34, corner_radius=6)
        b.grid(row=0, column=col, padx=(6,0))
        return b

    def _btn_small(self, parent, text, cmd, row, accent=False):
        b = ctk.CTkButton(parent, text=text, command=cmd,
                          font=ctk.CTkFont(size=11),
                          fg_color=ACCENT if accent else BG_CARD,
                          hover_color=ACCENT2 if accent else "#3a3a3a",
                          text_color=BG_DARK if accent else TEXT_W,
                          height=28, corner_radius=6)
        b.grid(row=row, column=0, padx=12, pady=2, sticky="ew")
        return b

    # ── Zone sync ─────────────────────────────────────────────────
    def _zone_changed(self, x1, y1, x2, y2):
        """Called by preview when zone is dragged/resized."""
        self._zone = (x1, y1, x2, y2)
        for var, val in zip(self._zone_vars, (x1,y1,x2,y2)):
            var.set(str(val))

    def _zone_entry_changed(self, i, v):
        """Called when user manually edits a zone coord entry."""
        try:
            vals = [int(var.get()) for var in self._zone_vars]
            self._zone = tuple(vals)
            self._preview.set_zone_template(tuple(vals))
        except ValueError:
            pass

    def _reset_zone(self):
        self._preview.set_zone_template(YELLOW_ZONE)

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
            while True: self._progress.set(self._prog_q.get_nowait())
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
            filetypes=[("Video","*.mp4 *.mov *.avi *.mkv *.webm *.flv")]
        )
        if f:
            self._url_var.set(f)
            self._stream_url = f
            self._vid_status.configure(text=f"📂  {Path(f).name}", text_color=GREEN)

    def _browse_output(self):
        f = filedialog.asksaveasfilename(defaultextension=".mp4",
                                         filetypes=[("MP4","*.mp4")])
        if f:
            self._out_var.set(f)

    def _toggle_custom_size(self, val):
        if val == "Custom": self._custom_f.grid()
        else: self._custom_f.grid_remove()

    def _use_link(self):
        """Resolve the URL to a stream URL in background (non-blocking)."""
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
                    text=f"✅  Ready: {name}", text_color=GREEN))
                self._log(f"🔗  Stream URL ready.")
            except Exception as e:
                self._log(f"❌  Could not resolve URL: {e}")
                self.after(0, lambda: self._vid_status.configure(
                    text="❌  Failed to resolve", text_color=RED))
            finally:
                self._set_busy(False)
        threading.Thread(target=_resolve, daemon=True).start()

    def _run_detect_zone(self):
        tmpl = self._tmpl_var.get().strip()
        if not Path(tmpl).exists():
            self._log("⚠  Load a template first.")
            return
        def _detect():
            self._log("🔍  Detecting yellow zone…")
            z = detect_yellow_zone(tmpl)
            self._zone = z
            self.after(0, lambda: self._preview.set_zone_template(z))
            self._log(f"✅  Zone detected: {z}")
        threading.Thread(target=_detect, daemon=True).start()

    def _get_size(self):
        presets = {"1080×1080":(1080,1080),"1920×1080":(1920,1080),"1080×1920":(1080,1920)}
        sel = self._size_var.get()
        if sel in presets: return presets[sel]
        try: return (int(self._cw_var.get()), int(self._ch_var.get()))
        except ValueError: return (1080,1080)

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
        params  = {
            "stream_url":  self._stream_url,
            "tmpl_path":   tmpl,
            "out_path":    self._out_var.get(),
            "zone":        self._zone,
            "out_size":    self._get_size(),
            "start_t":     float(self._start_var.get() or 0),
            "end_t":       float(end_raw) if end_raw else None,
            "keep_audio":  self._audio_var.get(),
            "fps":         int(self._fps_var.get()),
            "loop":        self._loop_var.get(),
            "border_px":   int(self._border_var.get() or 0),
            "border_col":  self._bcolor_var.get(),
        }

        self._set_busy(True)
        self._progress.set(0)
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
        self.after(0, lambda: self._render_btn.configure(
            state="disabled" if state else "normal",
            text="⏳  Working…" if state else "🎬  RENDER VIDEO",
        ))


# ── 8. Entry point ─────────────────────────────────────────────────
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(exist_ok=True)
    app = MeowndApp()
    app.mainloop()