[file-tag: code-generated-file-0-1779183969509737430]

Here is the clean, professional, and well-structured code for your **README.md** file. It is optimized to look visually stunning on GitHub, complete with status badges, clean code blocks, and detailed sections explaining the architecture of your dual-script project.

```markdown
# 🐱 Meownd Meme Video Maker v2

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![User Interface](https://img.shields.io/badge/UI-CustomTkinter%20%2F%20Tkinter-orange.svg)]()
[![Engine](https://img.shields.io/badge/Engine-MoviePy%20v1%20%2F%20v2-red.svg)]()

A high-performance, asynchronous desktop utility designed to overlay streamable or local video sources into meme layout templates with alpha-channel masks. Built entirely in Python, it offers a zero-download streaming rendering pipeline using `yt-dlp` and `MoviePy` backends, complete with custom dragging-resizing layout configurations.

---

## 🚀 Key Architectural Features

* **Stream-Direct Rendering Pipeline:** No physical preprocessing or massive video downloads are required. The pipeline leverages `yt-dlp` info-extractors to feed direct, variable-bitrate source network streams straight into `MoviePy` decoding engines.
* **Live Interactive Canvas:** Includes a customizable Tkinter-native canvas equipped with continuous mouse state listeners (`<ButtonPress-1>`, `<B1-Motion>`, `<Motion>`) enabling seamless real-time transformation matrix adjustments (Draggable and Resizable zone configurations).
* **Automated CV2 Matrix Thresholding:** Leverages an automated computer vision preprocessing sequence using `OpenCV` to convert templates to HSV space, filter color ranges (`inRange` matrices), and extract absolute spatial bounding boxes for the layout fields.
* **Dual GUI Compatibility Modes:**
  1. **`Meownd_Meme.py`:** Modern GUI experience relying on a customized compilation of `CustomTkinter` wrapper widgets for dark theme environments.
  2. **`meme_compact.py`:** Pure, lightweight fallback implementation leveraging standard boilerplate `tkinter` and `ttk` style components—designed for quick initializations and dependency-lean runtime configurations.
* **Robust Multi-Threaded Queue Control:** Decouples core video rendering tasks from the main interface execution loop. Thread safety is monitored using asynchronous queue pools (`queue.Queue`) refreshing every 80ms to avoid application freezing.

---

## 🛠️ System Requirements & Architecture

The application includes an automated bootstrap module. Upon script execution, missing operational environments are systematically fetched and deployed into your target path using silent subprocess triggers (`pip install --quiet`).

### Primary Libraries Used
* **UI Construction:** `customtkinter` (V2 Variant) or `tkinter` (Compact Variant)
* **Image Array Manipulation:** `pillow` (PIL), `numpy`
* **Computer Vision Analysis:** `opencv-python` (CV2 matrix engine used in full version)
* **Video Compositing:** `moviepy` (Supports fully backwards-compatible syntax across versions 1.x, 2.0, and 2.1+)
* **Stream Core Extraction:** `yt-dlp`

---

## 📦 Installation & Execution

1. Clone the repository into your local production workspace:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/meownd-meme-maker.git](https://github.com/YOUR_USERNAME/meownd-meme-maker.git)
   cd meownd-meme-maker
