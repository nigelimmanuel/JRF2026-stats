"""Build all eight Threads charts from data/ into out/.

Usage: python scripts/build_all.py
Steps: fetch the HM/FM routes (once), compute the DNF stats, write the HTML pages, render each to PNG.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS, DATA, OUT = ROOT / "scripts", ROOT / "data", ROOT / "out"
MAP = OUT / "map"


def run(script, *args):
    subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)], check=True)


MAP.mkdir(parents=True, exist_ok=True)
if not (MAP / "route_hm.csv").exists() or not (MAP / "route_fm.csv").exists():
    run("fetch_routes.py", MAP)
run("dnf_stats.py", DATA, MAP / "stats.json")
run("build_social.py", DATA, OUT)          # 1-5: overall, FM, HM, 10K, 5K
run("build_dnf_pages.py", MAP, OUT)        # 6-7: start time vs DNF, route map with COPs
run("build_double.py", DATA, OUT)          # 8: runners on both days
for page in sorted(OUT.glob("jrf2026_threads_*.html")):
    run("render.py", page, page.with_suffix(".png"), "--exact", "1080x1350")
