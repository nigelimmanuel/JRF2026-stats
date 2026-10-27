"""Download the HM and FM routes from ruanglari.com into <map_dir>/route_hm.csv and route_fm.csv.

Usage: python -I fetch_routes.py <map_dir>
The route pages embed their track as a JSON list (lat, lng, ele, dist in km); this keeps that list.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

import pandas as pd

PAGES = {
    "hm": "https://ruanglari.com/gpx/jakarta-running-festival-half-marathon",
    "fm": "https://ruanglari.com/gpx/jrf-marathon-2026-full-marathon",
}
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for key, url in PAGES.items():
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (jrf2026-stats)"})
    page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="replace")
    m = re.search(r"const rawRouteCoords = (\[.*?\]);", page, re.S)
    if not m:
        sys.exit(f"route data not found on {url}")
    pts = pd.DataFrame(json.loads(m.group(1)))[["lat", "lng", "ele", "dist"]]
    assert pts["lat"].between(-6.4, -6.0).all() and pts["lng"].between(106.6, 107.0).all(), "route is not in Jakarta"
    pts.to_csv(out / f"route_{key}.csv", index=False)
    print(key, len(pts), "points,", pts["dist"].iloc[-1], "km")
