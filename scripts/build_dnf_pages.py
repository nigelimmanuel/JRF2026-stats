"""Two Threads-ready 4:5 pages (1080 x 1350 CSS px) for JRF 2026 HM & FM:
  6_start_dnf  start time vs DNF, and where DNF runners stopped
  7_peta_cop   HM & FM routes on one map with the COPs and their DNF counts

Usage: python -I build_dnf_pages.py <map_dir> <out_dir>
  map_dir holds stats.json (from dnf_stats.py) and route_hm.csv / route_fm.csv; OpenStreetMap tiles
  are cached in map_dir/tiles.
Render each page with: python -I render.py <page.html> <page.png> --exact 1080x1350
"""
import io
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd
from PIL import Image, ImageEnhance, ImageOps

MAP, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
S = json.loads((MAP / "stats.json").read_text(encoding="utf-8"))
HM, FM = S["hm"], S["fm"]
OFFICIAL_KM = {"hm": 21.0975, "fm": 42.195}

C = dict(
    ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", base="#c3c2b7",
    surface="#fcfcfb", tone="#f1f0ec", fm="#2a78d6", hm="#1baf7a",
)
# Where a DNF stopped, along the course: one orange ramp, light (early) to dark (COT). Validated --ordinal.
RAMP5 = ["#f2a07e", "#eb6834", "#c24d1c", "#9a3a14", "#6f270b"]
STOP_COLOR = {"fm": dict(zip(FM["stops"], RAMP5)),
              "hm": dict(zip(HM["stops"], [RAMP5[0], RAMP5[1], RAMP5[4]]))}
W = 952


def num(x):
    return f"{int(x):,}".replace(",", ".")


def pct(x, d=1):
    return f"{100 * x:.{d}f}".replace(".", ",") + "%"


def km_label(km):
    return f"{km:g}".replace(".", ",")


CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1080px; height: 1350px; overflow: hidden; }}
body {{ background: {C["surface"]}; color: {C["ink"]}; padding: 60px 64px 44px;
  font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; display: flex; flex-direction: column; }}
.meta {{ font-size: 24px; color: {C["ink2"]}; }}
h1 {{ font-size: 56px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.06; margin-top: 14px; }}
.lede {{ font-size: 27px; line-height: 1.38; margin-top: 16px; color: {C["ink2"]}; }}
.lede b {{ color: {C["ink"]}; font-weight: 700; }}
h2 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.01em; }}
h2 span {{ font-weight: 400; color: {C["ink2"]}; font-size: 22px; }}
.panel {{ margin-top: 30px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 10px; font-size: 19px; color: {C["ink2"]}; }}
.chips span {{ display: flex; align-items: center; gap: 8px; }}
.sw {{ width: 16px; height: 16px; border-radius: 4px; display: inline-block; }}
.row {{ display: grid; grid-template-columns: 178px 1fr; align-items: center; margin-top: 10px; }}
.rl b {{ display: block; font-size: 21px; font-weight: 600; }}
.rl small {{ display: block; font-size: 16px; color: {C["ink2"]}; }}
.row svg {{ display: block; }}
.val {{ font-size: 24px; font-weight: 700; fill: {C["ink"]}; font-variant-numeric: tabular-nums; }}
.note {{ font-size: 18px; color: {C["muted"]}; line-height: 1.45; margin-top: 18px; }}
.foot {{ margin-top: auto; padding-top: 14px; font-size: 20px; color: {C["muted"]}; display: flex; justify-content: space-between; }}
.legend {{ display: flex; gap: 26px; margin-top: 24px; font-size: 21px; color: {C["ink2"]}; align-items: center; }}
.legend span {{ display: flex; align-items: center; gap: 10px; }}
.line {{ width: 34px; border-radius: 4px; display: inline-block; }}
.mapbox {{ position: relative; margin-top: 16px; border-radius: 14px; overflow: hidden; }}
.mapbox img, .mapbox svg {{ position: absolute; left: 0; top: 0; display: block; }}
.lab {{ font-size: 17px; fill: {C["ink2"]}; }}
.labn {{ font-size: 30px; font-weight: 700; fill: {C["ink"]}; letter-spacing: -0.01em; }}
.labh {{ font-size: 19px; font-weight: 700; fill: {C["ink"]}; }}
.attr {{ font-size: 13px; fill: {C["ink2"]}; }}
.labi {{ font-size: 18px; font-style: italic; fill: {C["ink2"]}; }}
.labn2 {{ font-size: 24px; font-weight: 700; fill: {C["ink"]}; }}
.lab2 {{ font-size: 16px; fill: {C["ink2"]}; }}
.labh2 {{ font-size: 16px; font-weight: 700; fill: {C["ink"]}; }}
.inval {{ font-size: 17px; font-weight: 700; fill: #ffffff; }}
"""

FOOT = '<p class="foot"><span>Sumber: results.scorenow.co.id</span><span>JRF 2026</span></p>'


def page(body):
    return f'<!doctype html><html lang="id"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'


# ---------- page 6: start time vs DNF ----------
SCALE_MAX = 0.5      # one shared scale for both races, so HM and FM bars compare honestly
BAR_W = W - 178 - 96


def group_rows(race, key):
    rows = ""
    for g in race["groups"]:
        x, segs = 0.0, ""
        for stop in race["stops"]:
            w = BAR_W * g["by_stop"][stop] / g["n"] / SCALE_MAX
            if w > 0:
                segs += f'<rect x="{x:.1f}" y="4" width="{max(w - 2, 1):.1f}" height="34" fill="{STOP_COLOR[key][stop]}"/>'
            x += w
        rate = g["dnf"] / g["n"]
        rows += (f'<div class="row"><div class="rl"><b>{g["label"]}</b><small>{num(g["n"])} pelari</small></div>'
                 f'<svg width="{BAR_W + 96}" height="42" viewBox="0 0 {BAR_W + 96} 42">'
                 f'<rect x="0" y="4" width="{BAR_W}" height="34" rx="6" fill="{C["tone"]}"/>{segs}'
                 f'<text x="{x + 12:.1f}" y="31" class="val">{pct(rate)}</text></svg></div>')
    return rows


def chips(key, race):
    names = {s: ("COT / setelah " + race["cops"][-1]["name"] if s == "COT" else
                 f'{s} · KM {km_label(next(c["km"] for c in race["cops"] if c["name"] == s))}') for s in race["stops"]}
    return '<div class="chips">' + "".join(
        f'<span><span class="sw" style="background:{STOP_COLOR[key][s]}"></span>{names[s]}</span>' for s in race["stops"]) + "</div>"


late, early = HM["groups"][-1], HM["groups"][:5]
early_rate = sum(g["dnf"] for g in early) / sum(g["n"] for g in early)
late_cop1 = late["by_stop"]["COP 1"]
fm_first, fm_mid = FM["groups"][0], FM["groups"][2]
page6 = page(f"""
<div class="meta">JRF 2026 · HM & FM · waktu start vs DNF</div>
<h1>Start 20+ menit setelah gun, hampir 1&nbsp;dari&nbsp;5 pelari HM tidak finish</h1>
<p class="lede">Di 10 menit pertama, DNF HM hanya <b>{pct(early_rate)}</b>. Di kelompok paling belakang <b>{pct(late["dnf"] / late["n"])}</b>,
dan <b>{num(late_cop1)}</b> di antaranya berhenti sebelum COP 1.</p>
<div class="panel"><h2>Half marathon <span>· DNF menurut waktu start</span></h2>{chips("hm", HM)}{group_rows(HM, "hm")}</div>
<div class="panel"><h2>Marathon <span>· start hampir serentak, 99% dalam 3 menit</span></h2>{chips("fm", FM)}{group_rows(FM, "fm")}</div>
<p class="note">Waktu start = berapa lama setelah gun time pelari melewati garis start. Untuk pelari DNF diestimasi dari
pelari dengan nomor bib berdekatan. DNF termasuk QRY, CUT/COT, DQ, dan finish lewat COT.</p>
{FOOT}""")
(OUT / "jrf2026_threads_6_start_dnf.html").write_text(page6, encoding="utf-8")

# ---------- page 7: map ----------
MW, MH = W, 890              # map box, CSS px; rendered at 2x
Z = 15                       # world pixel zoom used for all geometry


def world(lat, lng):
    n = 256 * 2 ** Z
    x = (lng + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


routes = {k: pd.read_csv(MAP / f"route_{k}.csv") for k in ("fm", "hm")}
for k, r in routes.items():
    r["wx"], r["wy"] = zip(*(world(a, b) for a, b in zip(r["lat"], r["lng"])))
allx = pd.concat([r["wx"] for r in routes.values()])
ally = pd.concat([r["wy"] for r in routes.values()])
PAD = 50
scale = min((MW - 2 * PAD) / (allx.max() - allx.min()), (MH - 2 * PAD) / (ally.max() - ally.min()))  # CSS px per world px
cx = (allx.max() + allx.min()) / 2 - 60 / scale   # routes a little right of centre; the inset takes the top left
cy = (ally.max() + ally.min()) / 2


def to_css(wx, wy):
    return MW / 2 + (wx - cx) * scale, MH / 2 + (wy - cy) * scale


TILES = MAP / "tiles"
TILES.mkdir(exist_ok=True)


def basemap(wx0, wy0, wx1, wy1, out_w, out_h, z):
    """OpenStreetMap tiles (cached) for a world-px box at zoom Z, fetched at zoom z, greyed and lightened."""
    f = 2 ** (z - Z)
    x0, y0, x1, y1 = wx0 * f, wy0 * f, wx1 * f, wy1 * f
    tx0, tx1, ty0, ty1 = int(x0 // 256), int(x1 // 256), int(y0 // 256), int(y1 // 256)
    mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            p = TILES / f"{z}_{tx}_{ty}.png"
            if not p.exists():
                req = urllib.request.Request(f"https://tile.openstreetmap.org/{z}/{tx}/{ty}.png",
                                             headers={"User-Agent": "jrf2026-route-chart/1.0 (one-off static map)"})
                p.write_bytes(urllib.request.urlopen(req, timeout=30).read())
                time.sleep(0.2)
            mosaic.paste(Image.open(p).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
    img = mosaic.crop((round(x0 - tx0 * 256), round(y0 - ty0 * 256), round(x1 - tx0 * 256), round(y1 - ty0 * 256)))
    img = img.resize((out_w * 2, out_h * 2), Image.LANCZOS)
    grey = ImageEnhance.Brightness(ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(0.55)).enhance(1.12)
    return Image.blend(ImageOps.colorize(grey, (120, 120, 116), (252, 252, 251)),
                       Image.new("RGB", grey.size, (252, 252, 251)), 0.25)


basemap(cx - MW / 2 / scale, cy - MH / 2 / scale, cx + MW / 2 / scale, cy + MH / 2 / scale, MW, MH, 15) \
    .save(OUT / "jrf2026_basemap.png")


def at_km(key, km):
    """World px on the route at an official race distance (route length scaled to the official one)."""
    r = routes[key]
    d = km * r["dist"].iloc[-1] / OFFICIAL_KM[key]
    i = min(max(int((r["dist"] < d).sum()), 1), len(r) - 1)
    t = (d - r["dist"].iloc[i - 1]) / max(r["dist"].iloc[i] - r["dist"].iloc[i - 1], 1e-9)
    return (r["wx"].iloc[i - 1] + t * (r["wx"].iloc[i] - r["wx"].iloc[i - 1]),
            r["wy"].iloc[i - 1] + t * (r["wy"].iloc[i] - r["wy"].iloc[i - 1]))


cops = []
for key, race in (("fm", FM), ("hm", HM)):
    for c in race["cops"]:
        wx, wy = at_km(key, c["km"])
        cops.append(dict(key=key, wx=wx, wy=wy, **c))
start_w = (routes["fm"]["wx"].iloc[0], routes["fm"]["wy"].iloc[0])


def routes_svg(tf, w_fm, w_hm):
    out = []
    for key, color, width in (("fm", C["fm"], w_fm), ("hm", C["hm"], w_hm)):
        pts = [tf(a, b) for a, b in zip(routes[key]["wx"], routes[key]["wy"])]
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if key == "fm":
            out.append(f'<path d="{d}" fill="none" stroke="{C["surface"]}" stroke-width="{width + 5}" '
                       f'stroke-linejoin="round" stroke-linecap="round"/>')
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>')
    return out


def marker(x, y, c, k=1.0):
    r = (7 + 0.75 * math.sqrt(c["dnf"])) * k
    return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{RAMP5[1]}" fill-opacity="0.9" '
            f'stroke="{C[c["key"]]}" stroke-width="{3 * k:.1f}"/>'), r


def halo_text(x, y, body, anchor="start", cls="lab"):
    """Text with a surface-coloured halo, so it stays readable over routes and the basemap."""
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{cls}" paint-order="stroke" '
            f'stroke="{C["surface"]}" stroke-width="6" stroke-linejoin="round">{body}</text>')


svg = routes_svg(to_css, 8, 3.5)

# Senayan: the start/finish and the COPs around it are too close at this scale, so they get a zoom inset.
near = [c for c in cops if math.dist(to_css(c["wx"], c["wy"]), to_css(*start_w)) < 120]
far = [c for c in cops if c not in near]
pts = [to_css(c["wx"], c["wy"]) for c in near] + [to_css(*start_w)]
bx0, by0 = min(p[0] for p in pts) - 20, min(p[1] for p in pts) - 20
bx1, by1 = max(p[0] for p in pts) + 20, max(p[1] for p in pts) + 20
side = max(bx1 - bx0, by1 - by0)                       # square region, centred on the cluster
mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
bx0, by0, bx1, by1 = mx - side / 2, my - side / 2, mx + side / 2, my + side / 2
IX, IY, IS = 18, 18, 400                                # inset box on the map, CSS px
k = IS / side


def to_inset(wx, wy):
    x, y = to_css(wx, wy)
    return IX + (x - bx0) * k, IY + (y - by0) * k


# main map: small markers everywhere, the Senayan box, and the connector to the inset
for c in cops:
    x, y = to_css(c["wx"], c["wy"])
    svg.append(marker(x, y, c, 0.55)[0])
sx, sy = to_css(*start_w)
svg.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="{C["ink"]}" stroke="{C["surface"]}" stroke-width="2.5"/>')
svg.append(f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{side:.1f}" height="{side:.1f}" rx="8" fill="none" '
           f'stroke="{C["ink"]}" stroke-width="2"/>')
svg.append(f'<line x1="{IX + IS:.1f}" y1="{IY + IS:.1f}" x2="{bx0:.1f}" y2="{by0 + side:.1f}" stroke="{C["ink"]}" stroke-width="1.5"/>')
svg.append(f'<line x1="{IX + IS:.1f}" y1="{IY:.1f}" x2="{bx1:.1f}" y2="{by0:.1f}" stroke="{C["ink"]}" stroke-width="1.5"/>')

# FM COP 1 and COP 2 are the same stretch of road, passed twice: one callout right beside them, no leader.
far.sort(key=lambda c: c["km"])
fx = sum(to_css(c["wx"], c["wy"])[0] for c in far) / len(far)
fy = sum(to_css(c["wx"], c["wy"])[1] for c in far) / len(far)
lx = MW - 24
ty = fy - 70
for j, c in enumerate(far):
    y = ty + j * 74
    svg.append(halo_text(lx, y + 30, f'<tspan class="labn">{num(c["dnf"])}</tspan><tspan class="lab"> DNF</tspan>', "end"))
    svg.append(halo_text(lx, y + 54, f'<tspan class="labh">FM {c["name"]}</tspan> · KM {km_label(c["km"])} · {c["close"]}', "end"))
svg.append(halo_text(lx, ty + 2 * 74 + 26, "titik yang sama, dilewati 2 kali", "end", "labi"))

# inset: its own sharper basemap, the routes, sized markers and direct labels
inset = [f'<clipPath id="ic"><rect x="{IX}" y="{IY}" width="{IS}" height="{IS}" rx="12"/></clipPath>',
         f'<g clip-path="url(#ic)"><image href="jrf2026_basemap_inset.png" x="{IX}" y="{IY}" width="{IS}" height="{IS}"/>']
inset += routes_svg(to_inset, 13, 5.5)
placed = []
for c in sorted(near, key=lambda c: -c["dnf"]):
    x, y = to_inset(c["wx"], c["wy"])
    m, r = marker(x, y, c, 1.2)
    inset.append(m)
    inset.append(f'<text x="{x:.1f}" y="{y + 6:.1f}" text-anchor="middle" class="inval">{num(c["dnf"])}</text>')
    placed.append((c, x, y, r))
ix, iy = to_inset(*start_w)
inset.append(f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="9" fill="{C["ink"]}" stroke="{C["surface"]}" stroke-width="3"/>')
inset.append("</g>")
inset.append(f'<rect x="{IX}" y="{IY}" width="{IS}" height="{IS}" rx="12" fill="none" stroke="{C["ink"]}" stroke-width="2"/>')
inset.append(halo_text(IX + 14, IY + 30, "Area Senayan", "start", "labh"))
inset.append(halo_text(ix, iy - 18, "Start / finish", "middle", "labh2"))
# Label side per COP in the inset (x, y direction), chosen by eye for this course so each name sits
# beside its own circle and inside the inset.
SIDE = {("hm", "COP 1"): (-1, -1), ("fm", "COP 3"): (1, 0), ("fm", "COP 4"): (-1, 1), ("hm", "COP 2"): (1, 1)}
for c, x, y, r in placed:
    race = "FM" if c["key"] == "fm" else "HM"
    sx_, sy_ = SIDE.get((c["key"], c["name"]), (1, 0))
    lx_ = x + sx_ * (r * 0.75 + 8)
    ly_ = y + sy_ * (r + 14) + (6 if sy_ == 0 else 0)
    anchor = "start" if sx_ > 0 else "end"
    top = ly_ - (18 if sy_ < 0 else 0)
    inset.append(halo_text(lx_, top, f'<tspan class="labh2">{race} {c["name"]}</tspan>', anchor, "lab2"))
    inset.append(halo_text(lx_, top + 19, f'KM {km_label(c["km"])}', anchor, "lab2"))
svg += inset
svg.append(f'<text x="{MW - 12}" y="{MH - 12}" text-anchor="end" class="attr">Peta © OpenStreetMap contributors · Rute: ruanglari.com</text>')

wx0, wy0 = cx + (bx0 - MW / 2) / scale, cy + (by0 - MH / 2) / scale
wx1, wy1 = cx + (bx1 - MW / 2) / scale, cy + (by1 - MH / 2) / scale
basemap(wx0, wy0, wx1, wy1, IS, IS, 17).save(OUT / "jrf2026_basemap_inset.png")
map_svg = f'<svg width="{MW}" height="{MH}" viewBox="0 0 {MW} {MH}">{"".join(svg)}</svg>'

total_cop = sum(c["dnf"] for c in cops)
worst_fm = max(FM["cops"], key=lambda c: c["dnf"])
worst_hm = max(HM["cops"], key=lambda c: c["dnf"])
page7 = page(f"""
<div class="meta">JRF 2026 · rute HM & FM · DNF per COP</div>
<h1>{num(total_cop)} pelari HM & FM berhenti sebelum COP</h1>
<p class="lede">Titik terberat: <b>COP 1 HM</b> di KM {km_label(worst_hm["km"])} (<b>{num(worst_hm["dnf"])}</b> pelari) dan
<b>{worst_fm["name"]} FM</b> di KM {km_label(worst_fm["km"])} (<b>{num(worst_fm["dnf"])}</b>). Ditambah
<b>{num(FM["after_last_cop"] + HM["after_last_cop"])}</b> yang berhenti setelah COP terakhir atau lewat COT.</p>
<div class="legend"><span><span class="line" style="height:8px;background:{C["fm"]}"></span>FM 42,2 km</span>
  <span><span class="line" style="height:4px;background:{C["hm"]}"></span>HM 21,1 km</span>
  <span style="margin-left:auto"><span class="sw" style="background:{RAMP5[1]};border-radius:50%;width:18px;height:18px"></span>besar lingkaran = jumlah DNF</span></div>
<div class="mapbox" style="width:{MW}px;height:{MH}px"><img src="jrf2026_basemap.png" width="{MW}" height="{MH}" alt="">{map_svg}</div>
{FOOT}""")
(OUT / "jrf2026_threads_7_peta_cop.html").write_text(page7, encoding="utf-8")
print("near start:", [(c["key"], c["name"]) for c in near], "| far:", [(c["key"], c["name"]) for c in far],
      "| inset zoom x", round(k, 1), "| total", total_cop)
