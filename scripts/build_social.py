"""Threads-ready 4:5 pages (1080 x 1350 CSS px) for JRF 2026: one overall page and one per race.

Usage: python -I build_social.py <data_dir> <out_dir>
Render each page with: python -I render.py <page.html> <page.png> --exact 1080x1350
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

RACES = [
    dict(key="fm", short="FM", title="Hydroplus Marathon", stem="hydroplus_marathon", km=42.195,
         cot=5 * 3600, cot_label="COT 5 jam",
         cops=[("COP 1", 18.0, "2:10"), ("COP 2", 28.0, "3:20"), ("COP 3", 31.8, "3:45"), ("COP 4", 36.8, "4:20")],
         bin=15, tick_step=60),
    dict(key="hm", short="HM", title="myBCA Jakarta Half Marathon", stem="mybca_jakarta_half_marathon", km=21.0975,
         cot=3 * 3600 + 45 * 60, cot_label="COT 3 jam 45 menit",
         cops=[("COP 1", 10.5, "2:00"), ("COP 2", 15.5, "2:45")],
         bin=30, tick_step=120),
    dict(key="10k", short="10K", title="Le Minerale 10K", stem="le_minerale_10k", km=10.0,
         cot=2 * 3600, cot_label="COT 2 jam", cops=[], bin=30, tick_step=120),
    dict(key="5k", short="5K", title="Samsung Galaxy 5K", stem="samsung_galaxy_5k", km=5.0,
         cot=1 * 3600, cot_label="COT 1 jam", cops=[], bin=30, tick_step=120),
]

C = dict(
    fin="#2a78d6", wall="#184f95", dnf="#eb6834", dns="#b9b8b0",
    ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", base="#c3c2b7",
    surface="#fcfcfb", tone="#f1f0ec",
)
W = 952   # content width: 1080 minus 64px margins

# ---------- formatting ----------
def num(x):
    return f"{int(x):,}".replace(",", ".")

def pct(x, d=1):
    return f"{100 * x:.{d}f}".replace(".", ",") + "%"

def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"

def jam_menit(s):
    h, m = divmod(int(round(s / 60)), 60)
    return " ".join(p for p in (f"{h} jam" if h else "", f"{m} menit" if m else "") if p)

def km_label(km):
    return f"{km:g}".replace(".", ",")

def mix(hex_color, t):
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(C["surface"][i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(bb + (aa - bb) * t):02x}" for aa, bb in zip(a, b))

def ink_on(hex_color):
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return "#ffffff" if 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2] < 0.32 else C["ink"]

# ---------- data (same rules as build_chart.py) ----------
def load(race):
    df = pd.read_csv(SRC / f"{race['stem']}_JRF2026_results.csv", encoding="utf-8-sig", dtype=str)
    t = df["Time"]
    ok = t.str.match(r"^\d{1,2}:\d{2}:\d{2}$", na=False)
    secs = pd.to_timedelta(t.where(ok)).dt.total_seconds()
    fin = ok & (secs <= race["cot"])            # a finisher has an official time inside the COT
    dns = t.eq("DNS")
    dnf = ~fin & ~dns
    r = dict(race)
    r.update(all=len(df), fin=int(fin.sum()), dnf=int(dnf.sum()), dns=int(dns.sum()))
    r["start"] = r["fin"] + r["dnf"]
    r.update(fin_rate=r["fin"] / r["start"], dnf_rate=r["dnf"] / r["start"], dns_rate=r["dns"] / r["all"])
    r["pace_s"] = secs[fin] / race["km"]
    r["pace"] = float(r["pace_s"].mean())
    r["time"] = float(secs[fin].mean())
    r["cot_pace"] = race["cot"] / race["km"]
    if race["cops"]:
        # A DNF belongs to the first COP beyond their last recorded split (no split at all -> COP 1).
        cps = [c for c in df.columns if c.startswith("KM ")] + [c for c in ["FINISH"] if c in df.columns]
        cp_km = [race["km"] if c == "FINISH" else float(c[3:]) for c in cps]
        has = df.loc[dnf, cps].notna().to_numpy()
        last = np.where(has.any(axis=1), has.shape[1] - 1 - np.argmax(has[:, ::-1], axis=1), -1)
        last_km = np.array([cp_km[i] if i >= 0 else 0.0 for i in last])
        counts, lower = [], -1.0
        for _, km, _ in race["cops"]:
            counts.append(int(((last_km > lower) & (last_km < km)).sum()))
            lower = km
        r["cop_counts"] = counts
        r["after_cops"] = int((last_km > race["cops"][-1][1]).sum())
        assert sum(counts) + r["after_cops"] == r["dnf"]
    return r

R = {race["key"]: load(race) for race in RACES}

# ---------- shared pieces ----------
def stacked(r, width, height=26, label=True):
    """One bar: its parts finish / DNF / DNS with 2px seams and rounded ends."""
    parts = [(r["fin"], C["fin"]), (r["dnf"], C["dnf"]), (r["dns"], C["dns"])]
    gap, avail = 2, width - 2 * (len(parts) - 1)
    x, out = 0.0, []
    for i, (v, c) in enumerate(parts):
        w = max(avail * v / r["all"], 2)
        rl, rr = (5 if i == 0 else 0), (5 if i == len(parts) - 1 else 0)
        out.append(f'<path fill="{c}" d="M{x + rl:.1f},0 H{x + w - rr:.1f} Q{x + w:.1f},0 {x + w:.1f},{rr} '
                   f'V{height - rr} Q{x + w:.1f},{height} {x + w - rr:.1f},{height} H{x + rl:.1f} '
                   f'Q{x:.1f},{height} {x:.1f},{height - rl} V{rl} Q{x:.1f},0 {x + rl:.1f},0 Z"/>')
        x += w + gap
    total_w = width + (110 if label else 0)
    text = (f'<text x="{width + 14:.1f}" y="{height - 6}" class="barlabel">{num(r["all"])}</text>' if label else "")
    return f'<svg width="{total_w:.0f}" height="{height}" viewBox="0 0 {total_w:.0f} {height}">{"".join(out)}{text}</svg>'

def bar_path(x, y, w, h, r=5):
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    return (f'<path d="M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} '
            f'H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z"/>')

def pace_chart(r, PH):
    """Finishers per pace: the axis ends at the COT; tallest bin in the deeper blue; average as a cut."""
    BIN, km = r["bin"], r["km"]
    pace = r["pace_s"]
    cot_pace = r["cot_pace"]
    cot_i = math.ceil((cot_pace - pace.min()) / BIN)
    edges = cot_pace + BIN * np.arange(-cot_i, 1)
    hist, _ = np.histogram(pace, edges)
    assert hist.sum() == r["fin"]
    for step in (100, 200, 250, 500, 1000, 2000):
        if math.ceil(hist.max() * 1.12 / step) <= 4:
            break
    y_max = step * math.ceil(hist.max() * 1.12 / step)
    ML, MT, MB, COT_W = 62, 48, 74, 8
    plot_w = W - ML - COT_W - 6

    def x_of(p):
        return ML + (p - edges[0]) / (edges[-1] - edges[0]) * plot_w

    def y_of(v):
        return MT + PH - v / y_max * PH

    top, base = y_of(y_max), y_of(0)
    xc = x_of(cot_pace)
    g = []
    for v in range(0, y_max + 1, step):
        y = y_of(v)
        g.append(f'<line x1="{ML}" x2="{xc:.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{C["base"] if v == 0 else C["grid"]}" stroke-width="1.5"/>')
        g.append(f'<text x="{ML - 12}" y="{y + 6:.1f}" class="tick" text-anchor="end">{num(v)}</text>')
    g.append(f'<rect x="{xc + 2:.1f}" y="{top:.1f}" width="{COT_W}" height="{base - top:.1f}" rx="2" fill="{C["dnf"]}"/>')
    xr = xc + 2 + COT_W
    g.append(f'<text x="{xr:.1f}" y="{top - 16:.1f}" class="cotlabel" text-anchor="end">{r["cot_label"]}</text>')
    slot = plot_w / len(hist)
    peak_i, wall_i = int(np.argmax(hist)), cot_i - 1
    for i, v in enumerate(hist):
        g.append(f'<g fill="{C["wall"] if i == peak_i else C["fin"]}">{bar_path(x_of(edges[i]) + 1.5, y_of(v), slot - 3, PH * v / y_max)}</g>')
    avg = r["pace"]
    xa = x_of(avg)
    avg_i = int(np.searchsorted(edges, avg, side="right") - 1)
    bar_top = y_of(hist[avg_i])
    label_y = y_of(max(hist[max(avg_i - 1, 0): avg_i + 2]) + 0.15 * y_max)
    room = 32
    g.append(f'<line x1="{xa:.1f}" x2="{xa:.1f}" y1="{bar_top + room:.1f}" y2="{base:.1f}" stroke="{C["surface"]}" stroke-width="4"/>')
    g.append(f'<line x1="{xa:.1f}" x2="{xa:.1f}" y1="{label_y + 9:.1f}" y2="{bar_top - 5:.1f}" stroke="{C["ink"]}" stroke-width="1.5"/>')
    g.append(f'<circle cx="{xa:.1f}" cy="{base:.1f}" r="7" fill="{C["ink"]}" stroke="{C["surface"]}" stroke-width="3"/>')
    g.append(f'<text x="{xa:.1f}" y="{label_y:.1f}" text-anchor="middle"><tspan class="avgs">Rata-rata </tspan>'
             f'<tspan class="avgh">{mmss(avg)}/km</tspan></text>')
    for i in sorted({peak_i, wall_i, avg_i}):
        x, y = x_of(edges[i]) + slot / 2, y_of(hist[i])
        if base - y > room + 8:
            g.append(f'<text x="{x:.1f}" y="{y + 25:.1f}" class="inval" text-anchor="middle">{num(hist[i])}</text>')
        else:
            g.append(f'<text x="{x:.1f}" y="{y - 10:.1f}" class="val" text-anchor="middle">{num(hist[i])}</text>')
    g.append(f'<text x="{xr:.1f}" y="{base + 30}" class="tickb" text-anchor="end">{mmss(cot_pace)}</text>')
    g.append(f'<text x="{xr:.1f}" y="{base + 60}" class="tickb2" text-anchor="end">{jam_menit(r["cot"])}</text>')
    step_x = r["tick_step"]
    for p in range(math.ceil(edges[0] / step_x) * step_x, int(edges[-1]) + 1, step_x):
        x = x_of(p)
        if xr - x < 175 or x - ML < 70:
            continue
        g.append(f'<text x="{x:.1f}" y="{base + 30}" class="tick" text-anchor="middle">{mmss(p)}</text>')
        g.append(f'<text x="{x:.1f}" y="{base + 60}" class="tick2" text-anchor="middle">{jam_menit(p * km)}</text>')
    g.append(f'<text x="{ML - 12}" y="{base + 30}" class="tick" text-anchor="end">/km</text>')
    g.append(f'<text x="{ML - 12}" y="{base + 60}" class="tick2" text-anchor="end">finish</text>')
    h = MT + PH + MB
    return f'<svg width="{W}" height="{h}" viewBox="0 0 {W} {h}">{"".join(g)}</svg>'

CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1080px; height: 1350px; overflow: hidden; }}
body {{ background: {C["surface"]}; color: {C["ink"]}; padding: 60px 64px 44px;
  font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; display: flex; flex-direction: column; }}
.meta {{ font-size: 24px; color: {C["ink2"]}; }}
h1 {{ font-size: 60px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.05; margin-top: 14px; }}
.lede {{ font-size: 28px; line-height: 1.38; margin-top: 18px; color: {C["ink2"]}; }}
.lede b {{ color: {C["ink"]}; font-weight: 700; }}
.dot {{ width: 14px; height: 14px; border-radius: 50%; display: inline-block; flex: none; }}
.kpis {{ display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 24px; margin-top: 36px; }}
.klabel {{ font-size: 22px; color: {C["ink2"]}; display: flex; align-items: center; gap: 10px; }}
.kval {{ font-size: 50px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; margin-top: 4px; }}
.ksub {{ font-size: 20px; color: {C["ink2"]}; margin-top: 2px; }}
.strip {{ margin-top: 22px; position: relative; height: 66px; }}
.strip svg {{ display: block; }}
.strip .mark {{ position: absolute; top: 36px; font-size: 20px; color: {C["ink2"]}; }}
.strip .tickline {{ position: absolute; top: -4px; width: 2px; height: 38px; background: {C["ink"]}; }}
h2 {{ font-size: 30px; font-weight: 700; letter-spacing: -0.01em; }}
.section {{ margin-top: 30px; }}
.section svg {{ display: block; margin-top: 4px; }}
svg text {{ font-family: inherit; }}
.tick {{ font-size: 19px; fill: {C["ink2"]}; font-variant-numeric: tabular-nums; }}
.tick2 {{ font-size: 19px; fill: {C["muted"]}; }}
.tickb {{ font-size: 19px; font-weight: 700; fill: {C["ink"]}; font-variant-numeric: tabular-nums; }}
.tickb2 {{ font-size: 19px; font-weight: 700; fill: {C["ink2"]}; }}
.val {{ font-size: 19px; font-weight: 700; fill: {C["ink"]}; }}
.inval {{ font-size: 19px; font-weight: 700; fill: #ffffff; }}
.avgs {{ font-size: 20px; fill: {C["ink2"]}; }}
.avgh {{ font-size: 28px; font-weight: 700; fill: {C["ink"]}; }}
.cotlabel {{ font-size: 24px; font-weight: 700; fill: {C["ink"]}; }}
.barlabel {{ font-size: 22px; font-weight: 700; fill: {C["ink"]}; font-variant-numeric: tabular-nums; }}
.cophead {{ display: flex; justify-content: space-between; align-items: baseline; }}
.cophead span {{ font-size: 20px; color: {C["ink2"]}; }}
.cops {{ display: grid; gap: 12px; margin-top: 14px; }}
.cop {{ background: {C["tone"]}; border-radius: 10px; padding: 14px 18px; }}
.copname {{ font-size: 20px; color: {C["ink2"]}; display: flex; align-items: center; gap: 8px; }}
.copname .dot {{ width: 11px; height: 11px; }}
.copn {{ font-size: 44px; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; margin-top: 2px; }}
.copsub {{ font-size: 18px; color: {C["ink2"]}; }}
.foot {{ margin-top: auto; padding-top: 18px; font-size: 20px; color: {C["muted"]}; display: flex; justify-content: space-between; }}
.legend {{ display: flex; gap: 26px; margin-top: 30px; font-size: 22px; color: {C["ink2"]}; }}
.legend span {{ display: flex; align-items: center; gap: 10px; }}
.race {{ margin-top: 50px; }}
.racehead {{ display: flex; align-items: baseline; gap: 14px; }}
.racehead b {{ font-size: 40px; font-weight: 700; letter-spacing: -0.02em; }}
.racehead span {{ font-size: 21px; color: {C["ink2"]}; }}
.race .barwrap {{ margin-top: 10px; }}
.race .barwrap svg {{ display: block; }}
.cells {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px; }}
.cell {{ border-radius: 10px; padding: 10px 16px 12px; }}
.cell small {{ display: block; font-size: 18px; opacity: 0.85; }}
.cell strong {{ display: block; font-size: 34px; font-weight: 700; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; line-height: 1.15; }}
"""

FOOT = '<p class="foot"><span>Sumber: results.scorenow.co.id</span><span>JRF 2026</span></p>'

def page(body):
    return f'<!doctype html><html lang="id"><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body}</body></html>'

def kpis(r):
    def k(label, color, value, sub):
        return (f'<div><div class="klabel"><span class="dot" style="background:{color}"></span>{label}</div>'
                f'<div class="kval">{value}</div><div class="ksub">{sub}</div></div>')
    start_x = W * r["start"] / r["all"]
    return (f'<div class="kpis">{k("Finish", C["fin"], num(r["fin"]), pct(r["fin_rate"]) + " dari yang start")}'
            f'{k("DNF", C["dnf"], num(r["dnf"]), pct(r["dnf_rate"]) + " dari yang start")}'
            f'{k("DNS", C["dns"], num(r["dns"]), pct(r["dns_rate"]) + " dari terdaftar")}</div>'
            f'<div class="strip">{stacked(r, W, 30, label=False)}'
            f'<div class="tickline" style="left:{start_x - 1:.1f}px"></div>'
            f'<div class="mark" style="right:0">{num(r["start"])} start · {num(r["all"])} terdaftar</div></div>')

def cop_section(r):
    tiles = "".join(
        f'<div class="cop"><div class="copname"><span class="dot" style="background:{C["dnf"]}"></span>{name}</div>'
        f'<div class="copn">{num(v)}</div><div class="copsub">KM {km_label(km)} · tutup {close}</div></div>'
        for (name, km, close), v in zip(r["cops"], r["cop_counts"]))
    return (f'<div class="section"><div class="cophead"><h2>DNF per COP</h2>'
            f'<span>+{num(r["after_cops"])} setelah {r["cops"][-1][0]} atau lewat COT</span></div>'
            f'<div class="cops" style="grid-template-columns:repeat({len(r["cops"])}, 1fr)">{tiles}</div></div>')

# Copy: one headline from the data, then the numbers that back it.
fm, hm, k10, k5 = R["fm"], R["hm"], R["10k"], R["5k"]
top_cop = int(np.argmax(fm["cop_counts"]))
COPY = {
    "fm": ("1 dari 3 pelari marathon tidak finish",
           f'Hanya <b>{num(fm["fin"])}</b> dari {num(fm["start"])} pelari yang start finish dalam COT 5 jam '
           f'(<b>{pct(fm["fin_rate"])}</b>). Paling banyak berhenti sebelum {fm["cops"][top_cop][0]} '
           f'(KM {km_label(fm["cops"][top_cop][1])}): <b>{num(fm["cop_counts"][top_cop])} pelari</b>.'),
    "hm": (f"{pct(hm['fin_rate'])} pelari HM berhasil finish",
           f'<b>{num(hm["fin"])}</b> dari {num(hm["start"])} pelari yang start finish dalam COT 3 jam 45 menit. '
           f'<b>{num(hm["cop_counts"][0])}</b> berhenti sebelum COP 1 (KM 10,5).'),
    "10k": (f"{pct(k10['fin_rate'])} pelari 10K finish",
            f'Finish rate tertinggi dari 4 kategori: <b>{num(k10["fin"])}</b> dari {num(k10["start"])} yang start. '
            f'Rata-rata pace <b>{mmss(k10["pace"])}/km</b>, sekitar <b>{jam_menit(k10["time"])}</b>.'),
    "5k": (f"{num(k5['dns'])} pendaftar 5K tidak datang",
           f'DNS <b>{pct(k5["dns_rate"])}</b>, tertinggi dari 4 kategori. Yang datang hampir semua finish: '
           f'<b>{num(k5["fin"])}</b> dari {num(k5["start"])} (<b>{pct(k5["fin_rate"])}</b>).'),
}
assert max(R.values(), key=lambda r: r["fin_rate"])["key"] == "10k"
assert max(R.values(), key=lambda r: r["dns_rate"])["key"] == "5k"

for key, n in [("fm", 2), ("hm", 3), ("10k", 4), ("5k", 5)]:
    r = R[key]
    head, lede = COPY[key]
    ph = {"fm": 340, "hm": 340, "10k": 570, "5k": 600}[key]
    body = (f'<div class="meta">JRF 2026 · {r["title"]} · {km_label(round(r["km"], 1))} km</div>'
            f'<h1>{head}</h1><p class="lede">{lede}</p>{kpis(r)}'
            f'<div class="section"><h2>Finisher per pace</h2>{pace_chart(r, ph)}</div>'
            f'{cop_section(r) if r["cops"] else ""}{FOOT}')
    (OUT / f"jrf2026_threads_{n}_{key}.html").write_text(page(body), encoding="utf-8")

# ---------- overall ----------
ORDER = ["fm", "hm", "10k", "5k"]
T_START = sum(r["start"] for r in R.values())
T_FIN = sum(r["fin"] for r in R.values())
max_all = max(r["all"] for r in R.values())

def heat(key, color):
    hi = max(r[key] for r in R.values())
    out = {}
    for k, r in R.items():
        fill = mix(color, 0.12 + 0.88 * r[key] / hi)
        out[k] = (fill, ink_on(fill))
    return out

HEAT = {k: heat(k, C[c]) for k, c in [("fin_rate", "fin"), ("dnf_rate", "dnf"), ("dns_rate", "dns")]}

def cell(label, value, fill, ink):
    return f'<div class="cell" style="background:{fill};color:{ink}"><small>{label}</small><strong>{value}</strong></div>'

races_html = ""
for k in ORDER:
    r = R[k]
    races_html += (
        f'<div class="race"><div class="racehead"><b>{r["short"]}</b><span>{r["title"]} · {num(r["all"])} pelari</span></div>'
        f'<div class="barwrap">{stacked(r, W * r["all"] / max_all, label=False)}</div>'
        f'<div class="cells">{cell("Finish", pct(r["fin_rate"]), *HEAT["fin_rate"][k])}'
        f'{cell("DNF", pct(r["dnf_rate"]), *HEAT["dnf_rate"][k])}'
        f'{cell("DNS", pct(r["dns_rate"]), *HEAT["dns_rate"][k])}'
        f'{cell("Rata-rata pace", mmss(r["pace"]) + "/km", C["tone"], C["ink"])}</div></div>')

legend = "".join(f'<span><span class="dot" style="background:{c}"></span>{label}</span>'
                 for label, c in [("Finish", C["fin"]), ("DNF", C["dnf"]), ("DNS", C["dns"])])
overall = (f'<div class="meta">JRF 2026 · 4 kategori · {num(sum(r["all"] for r in R.values()))} pelari terdaftar</div>'
           f'<h1>{num(T_FIN)} pelari finish di JRF 2026</h1>'
           f'<p class="lede">Dari {num(T_START)} yang start, <b>{pct(T_FIN / T_START)}</b> sampai garis finish. '
           f'Tapi di marathon, <b>1 dari 3</b> pelari tidak finish.</p>'
           f'<div class="legend">{legend}<span style="margin-left:auto">Finish & DNF dari start · DNS dari terdaftar</span></div>'
           f'{races_html}{FOOT}')
(OUT / "jrf2026_threads_1_overall.html").write_text(page(overall), encoding="utf-8")

for k in ORDER:
    r = R[k]
    print(k, r["all"], r["start"], r["fin"], r["dnf"], r["dns"], pct(r["fin_rate"]), pct(r["dnf_rate"]), pct(r["dns_rate"]),
          mmss(r["pace"]), r.get("cop_counts"))
print("total", T_FIN, T_START, pct(T_FIN / T_START))
