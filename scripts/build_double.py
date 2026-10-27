"""Threads-ready 4:5 page (1080 x 1350 CSS px): runners who raced on both days of JRF 2026.

Usage: python -I build_double.py <data_dir> <out_dir>
Render with: python -I render.py <page.html> <page.png> --exact 1080x1350

Day 1 = HM & 5K, Day 2 = FM & 10K. A runner is matched on an identical name (trimmed, upper case).
Names that more than one runner uses within a race, or that appear in both races of the same day, are
ambiguous and left out. Finish = official gun time inside the COT; "gagal" = started but did not finish
(DNF, QRY, CUT/COT, DQ, or over the COT); a runner who did not start on either day is left out of the
outcome counts. Pace: chip data for HM/FM; for 5K/10K the chip time is estimated from the
segment splits (the sum of segments plus the last stretch at the previous segment's pace).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)


def to_s(v):
    if not isinstance(v, str) or ":" not in v:
        return np.nan
    p = [int(x) for x in v.strip().split(":")]
    return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]


def load_chip(stem, km, cot):
    df = pd.read_csv(SRC / f"{stem}_JRF2026_results_chiptime.csv", encoding="utf-8-sig", dtype=str)
    gun = df["gun_time"].map(to_s)
    out = pd.DataFrame({"name": df["name"].fillna("").str.strip().str.upper()})
    out["state"] = np.where(df["status"] == "DNS", "DNS", np.where((df["status"] == "Finisher") & (gun <= cot), "F", "N"))
    out["pace"] = np.where(out["state"] == "F", df["chip_time"].map(to_s) / km, np.nan)
    out["start"] = np.where(out["state"] == "F", pd.to_numeric(df["start_offset_sec"], errors="coerce"), np.nan)
    return out


def load_old(stem, km, cot):
    df = pd.read_csv(SRC / f"{stem}_JRF2026_results.csv", encoding="utf-8-sig", dtype=str)
    t = df["Time"]
    ok = t.str.match(r"^\d{1,2}:\d{2}:\d{2}$", na=False)
    name = df["Name"].fillna("").str.strip()
    # The scraper glued the status code onto the names of runners without a time.
    name = name.where(t.notna(), name.str.replace(r"^(CUT|QRY|DQ)", "", regex=True))
    gun = t.map(to_s)
    kms = [c for c in df.columns if c.startswith("KM ")]
    dist = [float(c[3:]) for c in kms]
    seg = df[kms].apply(lambda c: c.map(to_s))
    chip = seg.sum(axis=1, min_count=len(kms)) + seg.iloc[:, -1] / np.diff([0.0] + dist)[-1] * (km - dist[-1])
    out = pd.DataFrame({"name": name.str.strip().str.upper()})
    out["state"] = np.where(t.eq("DNS"), "DNS", np.where(ok & (gun <= cot), "F", "N"))
    out["pace"] = np.where(out["state"] == "F", chip / km, np.nan)
    out["start"] = np.where(out["state"] == "F", gun - chip, np.nan)
    return out


R = {"HM": load_chip("mybca_jakarta_half_marathon", 21.0975, 13500),
     "FM": load_chip("hydroplus_marathon", 42.195, 18000),
     "5K": load_old("samsung_galaxy_5k", 5.0, 3600),
     "10K": load_old("le_minerale_10k", 10.0, 7200)}
for r in R.values():
    r.drop(r[r["name"].isin(["", "NAN"])].index, inplace=True)

ambiguous = set()
for r in R.values():
    ambiguous |= set(r.loc[r["name"].duplicated(keep=False), "name"])
ambiguous |= set(R["HM"]["name"]) & set(R["5K"]["name"])
ambiguous |= set(R["FM"]["name"]) & set(R["10K"]["name"])

FM_ALL = R["FM"][R["FM"]["state"] != "DNS"]
FM_RATE = (FM_ALL["state"] == "F").mean()

COMBOS = []
for d1, d2 in [("HM", "FM"), ("5K", "FM"), ("HM", "10K"), ("5K", "10K")]:
    a = R[d1][~R[d1]["name"].isin(ambiguous)].set_index("name")
    b = R[d2][~R[d2]["name"].isin(ambiguous)].set_index("name")
    m = a.join(b, lsuffix="1", rsuffix="2", how="inner")
    st = m[(m["state1"] != "DNS") & (m["state2"] != "DNS")]
    ff = st[(st["state1"] == "F") & (st["state2"] == "F")]
    COMBOS.append(dict(
        d1=d1, d2=d2, registered=len(m), started=len(st),
        both=len(ff), fail_d2=int(((st["state1"] == "F") & (st["state2"] == "N")).sum()),
        fail_d1=int(((st["state1"] == "N") & (st["state2"] == "F")).sum()),
        neither=int(((st["state1"] == "N") & (st["state2"] == "N")).sum()),
        rate1=(st["state1"] == "F").mean(), rate2=(st["state2"] == "F").mean(),
        pace1=ff["pace1"].median(), pace2=ff["pace2"].median(), dpace=(ff["pace2"] - ff["pace1"]).median(),
    ))
for c in COMBOS:
    assert c["both"] + c["fail_d1"] + c["fail_d2"] + c["neither"] == c["started"]
T_REG = sum(c["registered"] for c in COMBOS)
T_START = sum(c["started"] for c in COMBOS)
fm_combos = [c for c in COMBOS if c["d2"] == "FM"]
DOUBLE_FM_RATE = sum(c["both"] + c["fail_d1"] for c in fm_combos) / sum(c["started"] for c in fm_combos)

C = dict(ink="#0b0b0b", ink2="#52514e", muted="#898781", surface="#fcfcfb", tone="#f1f0ec",
         both="#2a78d6", one="#eb6834", neither="#6f270b")


def num(x):
    return f"{int(x):,}".replace(",", ".")


def pct(x, d=1):
    return f"{100 * x:.{d}f}".replace(".", ",") + "%"


def mmss(s):
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


def signed(s):
    return ("+" if s >= 0 else "−") + mmss(abs(s))


def card(c):
    one = c["fail_d1"] + c["fail_d2"]
    parts = [(c["both"], C["both"]), (one, C["one"]), (c["neither"], C["neither"])]
    W, H, x, segs = 400, 22, 0.0, ""
    avail = W - 2 * (sum(1 for v, _ in parts if v) - 1)
    shown = [(v, col) for v, col in parts if v]
    for i, (v, col) in enumerate(shown):
        w = max(avail * v / c["started"], 3)
        rl, rr = (5 if i == 0 else 0), (5 if i == len(shown) - 1 else 0)
        segs += (f'<path fill="{col}" d="M{x + rl:.1f},0 H{x + w - rr:.1f} Q{x + w:.1f},0 {x + w:.1f},{rr} V{H - rr} '
                 f'Q{x + w:.1f},{H} {x + w - rr:.1f},{H} H{x + rl:.1f} Q{x:.1f},{H} {x:.1f},{H - rl} V{rl} Q{x:.1f},0 {x + rl:.1f},0 Z"/>')
        x += w + 2
    fm_note = f'<i> (FM overall {pct(FM_RATE)})</i>' if (c["d1"], c["d2"]) == ("HM", "FM") else ""
    where = " · ".join(p for p in (f'{c["fail_d2"]} gagal di {c["d2"]}' if c["fail_d2"] else "",
                                   f'{c["fail_d1"]} gagal di {c["d1"]}' if c["fail_d1"] else "") if p) or "—"
    return f"""
<div class="card">
  <div class="ch"><b>{c["d1"]} <span>→</span> {c["d2"]}</b><small>{num(c["started"])} start di dua hari · {num(c["registered"])} terdaftar</small></div>
  <svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" class="bar">{segs}</svg>
  <div class="outs">
    <div><strong>{num(c["both"])}</strong><small>finish dua-duanya</small></div>
    <div><strong>{num(one)}</strong><small>gagal salah satu</small></div>
    <div><strong>{num(c["neither"])}</strong><small>gagal dua-duanya</small></div>
  </div>
  <p class="where">{where}</p>
  <div class="kv"><span>Finish rate</span><b>{pct(c["rate1"])} → {pct(c["rate2"])}{fm_note}</b></div>
  <div class="kv"><span>Pace median</span><b>{mmss(c["pace1"])} → {mmss(c["pace2"])}<i>/km ({signed(c["dpace"])})</i></b></div>
</div>"""


CSS = f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ width: 1080px; height: 1350px; overflow: hidden; }}
body {{ background: {C["surface"]}; color: {C["ink"]}; padding: 60px 64px 44px;
  font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif; display: flex; flex-direction: column; }}
.meta {{ font-size: 24px; color: {C["ink2"]}; }}
h1 {{ font-size: 56px; font-weight: 700; letter-spacing: -0.025em; line-height: 1.06; margin-top: 14px; }}
.lede {{ font-size: 27px; line-height: 1.38; margin-top: 16px; color: {C["ink2"]}; }}
.lede b {{ color: {C["ink"]}; font-weight: 700; }}
.legend {{ display: flex; gap: 24px; margin-top: 24px; font-size: 20px; color: {C["ink2"]}; }}
.legend span {{ display: flex; align-items: center; gap: 8px; }}
.sw {{ width: 16px; height: 16px; border-radius: 4px; display: inline-block; }}
.grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 26px; margin-top: 22px; }}
.card {{ background: {C["tone"]}; border-radius: 14px; padding: 38px 26px 36px; }}
.ch b {{ display: block; font-size: 34px; font-weight: 700; letter-spacing: -0.02em; }}
.ch b span {{ color: {C["ink2"]}; font-weight: 400; }}
.ch small {{ display: block; font-size: 17px; color: {C["ink2"]}; margin-top: 2px; }}
.bar {{ display: block; margin-top: 14px; }}
.outs {{ display: grid; grid-template-columns: repeat(3, auto); justify-content: space-between; margin-top: 16px; }}
.outs strong {{ display: block; font-size: 38px; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }}
.outs small {{ display: block; white-space: nowrap; font-size: 16px; color: {C["ink2"]}; line-height: 1.25; }}
.where {{ font-size: 17px; color: {C["ink2"]}; margin: 8px 0 12px; }}
.kv {{ display: flex; justify-content: space-between; align-items: baseline; padding-top: 20px; font-size: 18px; color: {C["ink2"]}; }}
.kv b {{ font-size: 23px; color: {C["ink"]}; font-weight: 700; font-variant-numeric: tabular-nums; }}
.kv i {{ font-style: normal; font-weight: 400; font-size: 15px; color: {C["ink2"]}; }}
.note {{ font-size: 17px; color: {C["muted"]}; line-height: 1.45; margin-top: 16px; }}
.foot {{ margin-top: auto; padding-top: 12px; font-size: 20px; color: {C["muted"]}; display: flex; justify-content: space-between; }}
"""

legend = "".join(f'<span><span class="sw" style="background:{col}"></span>{lab}</span>'
                 for lab, col in [("Finish dua-duanya", C["both"]), ("Gagal salah satu", C["one"]), ("Gagal dua-duanya", C["neither"])])
html = f"""<!doctype html><html lang="id"><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="meta">JRF 2026 · Day 1 (HM, 5K) → Day 2 (FM, 10K)</div>
<h1>{num(T_REG)} pelari ikut JRF 2026 dua hari berturut-turut</h1>
<p class="lede"><b>{num(T_START)}</b> di antaranya start di dua hari, <b>{num(T_REG - T_START)}</b> DNS di salah satu
atau kedua hari.</p>
<div class="legend">{legend}</div>
<div class="grid">{"".join(card(c) for c in COMBOS)}</div>
<p class="note">Dicocokkan dari nama yang sama persis; nama ganda dibuang. Pace = median pelari yang finish dua-duanya,
dalam kurung perubahan per orang. 5K/10K pakai chip time estimasi.</p>
<p class="foot"><span>Sumber: results.scorenow.co.id</span><span>JRF 2026</span></p>
</body></html>"""
(OUT / "jrf2026_threads_8_dua_hari.html").write_text(html, encoding="utf-8")
print("ambiguous names", len(ambiguous), "| registered", T_REG, "started", T_START,
      "| double FM rate", round(DOUBLE_FM_RATE, 3), "vs FM", round(FM_RATE, 3))
for c in COMBOS:
    print(c["d1"], c["d2"], c["registered"], c["started"], c["both"], c["fail_d1"], c["fail_d2"], c["neither"],
          pct(c["rate1"]), pct(c["rate2"]), mmss(c["pace1"]), mmss(c["pace2"]), signed(c["dpace"]).replace("−", "-"))
