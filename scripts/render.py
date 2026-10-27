"""Render a fixed-size HTML page to a 2x PNG with headless Chrome, Edge or Chromium.

Usage: python -I render.py <page.html> <out.png> [--exact 1080x1350]
  The browser is taken from the CHROME environment variable, else found in the usual install places.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

CANDIDATES = [
    os.environ.get("CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "", shutil.which("chromium-browser") or "",
]
browser = next((c for c in CANDIDATES if c and Path(c).exists()), None)
if browser is None:
    sys.exit("No Chrome, Edge or Chromium found; set CHROME to the browser's path.")

html, png = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
size = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == "--exact" else "1080x1350"
raw = png.with_name("_raw.png")
subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                f"--window-size={size.replace('x', ',')}", f"--screenshot={raw}", html.as_uri()],
               check=True, capture_output=True)
im = Image.open(raw).convert("RGB")
raw.unlink()
w, h = (2 * int(v) for v in size.split("x"))
assert im.size == (w, h), f"rendered {im.size}, expected {(w, h)}"
im.save(png, optimize=True)
print(png.name, *im.size)
