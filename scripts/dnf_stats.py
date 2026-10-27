"""HM & FM start time vs DNF, and DNF per COP, from the chip-time scrapes.

Usage: python -I dnf_stats.py <data_dir> <out.json>

Definitions (same as the other charts):
  finish = official gun time inside the COT; DNF = started but no finish (DNF / QRY / COT / DQ status,
  or a gun time over the COT); DNS = did not start.
Start time = seconds after the gun a runner crossed the start mat (start_offset). scorenow only gives it
for finishers, so for everyone else it is estimated as the median start offset of finishers with
neighbouring bib numbers (same block of 10, widening to 25/50/100/500 when a block has no finisher).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])

RACES = {
    "hm": dict(stem="mybca_jakarta_half_marathon", km=21.0975, cot=3 * 3600 + 45 * 60,
               cops=[("COP 1", 10.5, "2:00"), ("COP 2", 15.5, "2:45")],
               groups=[(0, 60, "0–1 menit"), (60, 210, "1–3,5 menit"), (210, 360, "3,5–6 menit"),
                       (360, 510, "6–8,5 menit"), (510, 630, "8,5–10,5 menit"), (630, 1200, "10,5–20 menit"),
                       (1200, 99999, "20–32 menit")]),
    "fm": dict(stem="hydroplus_marathon", km=42.195, cot=5 * 3600,
               cops=[("COP 1", 18.0, "2:10"), ("COP 2", 28.0, "3:20"), ("COP 3", 31.8, "3:45"), ("COP 4", 36.8, "4:20")],
               groups=[(0, 30, "< 30 detik"), (30, 60, "30–60 detik"), (60, 120, "1–2 menit"), (120, 99999, "> 2 menit")]),
}


def analyse(race):
    df = pd.read_csv(SRC / f"{race['stem']}_JRF2026_results_chiptime.csv", encoding="utf-8-sig", dtype=str)
    n_all = len(df)
    df = df[df["status"] != "DNS"].copy()
    df["num"] = pd.to_numeric(df["bib"].str.extract(r"^[A-Z](\d+)$")[0], errors="coerce")
    gun = pd.to_timedelta(df["gun_time"]).dt.total_seconds()
    df["fin"] = (df["status"] == "Finisher") & (gun <= race["cot"])
    df["off"] = pd.to_numeric(df["start_offset_sec"], errors="coerce")

    # Start offset: measured for finishers; estimated from bib neighbours for everyone else.
    ref = df[df["status"] == "Finisher"]
    est = df["off"].copy()
    for size in (10, 25, 50, 100, 500):
        med = ref.groupby(ref["num"] // size)["off"].median()
        est = est.fillna((df["num"] // size).map(med))
    df["start"] = est

    # Where a DNF stopped: the first COP beyond their last recorded split (no split -> COP 1);
    # past the last COP (or a finish over the COT) counts as "COT".
    splits = [c for c in df.columns if c.startswith("KM")] + ["FINISH_chip"]
    split_km = [race["km"] if c == "FINISH_chip" else (21.0975 if c == "KM21" else float(c[2:])) for c in splits]
    has = df[splits].notna().to_numpy()
    last = np.where(has.any(axis=1), has.shape[1] - 1 - np.argmax(has[:, ::-1], axis=1), -1)
    last_km = np.array([split_km[i] if i >= 0 else 0.0 for i in last])
    where = np.full(len(df), "COT", dtype=object)
    lower = -1.0
    for name, km, _ in race["cops"]:
        where[(last_km > lower) & (last_km < km)] = name
        lower = km
    df["where"] = np.where(df["fin"], "finish", where)

    stops = [c[0] for c in race["cops"]] + ["COT"]
    groups = []
    for lo, hi, label in race["groups"]:
        g = df[(df["start"] >= lo) & (df["start"] < hi)]
        groups.append(dict(label=label, n=len(g), dnf=int((~g["fin"]).sum()),
                           by_stop={s: int((g["where"] == s).sum()) for s in stops}))
    dnf = df[~df["fin"]]
    out = dict(
        registered=n_all, started=len(df), finish=int(df["fin"].sum()), dnf=len(dnf),
        no_start_estimate=int(df["start"].isna().sum()),
        cops=[dict(name=n, km=k, close=c, dnf=int((dnf["where"] == n).sum())) for n, k, c in race["cops"]],
        after_last_cop=int((dnf["where"] == "COT").sum()),
        groups=groups, stops=stops,
        measured_start_p50=float(ref["off"].median()), measured_start_p99=float(ref["off"].quantile(0.99)),
    )
    assert sum(c["dnf"] for c in out["cops"]) + out["after_last_cop"] == out["dnf"]
    assert sum(g["n"] for g in groups) + out["no_start_estimate"] == out["started"]
    return out


stats = {k: analyse(r) for k, r in RACES.items()}
OUT.write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
for k, s in stats.items():
    print(k, {x: s[x] for x in ("registered", "started", "finish", "dnf", "after_last_cop", "no_start_estimate")},
          [(c["name"], c["dnf"]) for c in s["cops"]])
    for g in s["groups"]:
        print("   ", g["label"], g["n"], f"{100 * g['dnf'] / g['n']:.1f}%", g["by_stop"])
