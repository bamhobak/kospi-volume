# -*- coding: utf-8 -*-
"""미장 1분봉 → 종목·날짜 요약표(2026-10-25, 미장 장중 아이디어 실측용). data/m1/US/bf/*.parquet + day/*.parquet.
봉 시각 = 봉 끝(뉴욕 09:31~16:01 · 서머타임은 America/New_York 로). 정규장만 쓴다.
열: o 첫 봉 시가 · p1000 · p1500 · p1530 · p1550 = 그 시각 봉 종가(없으면 직전) · c 마지막 봉 종가 · val Σc·v · pc 전날 종가 · nb 봉 수
출력 research/cache/m1_daysum_us.parquet
    python research/m1_daysum_us.py
"""
import glob, os, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
CUTS = {"p1000": 1000, "p1500": 1500, "p1530": 1530, "p1550": 1550}


def summarize(x):
    x = x.sort_values("ts")
    k = pd.to_datetime(x.ts, unit="s", utc=True).dt.tz_convert("America/New_York")
    x = x.assign(d=k.dt.strftime("%Y%m%d"), hm=k.dt.hour * 100 + k.dt.minute)
    x = x[(x.hm >= 931) & (x.hm <= 1601)]
    if x.empty: return None
    g = x.groupby("d", sort=True)
    R = pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "val": (x.c * x.v).groupby(x.d).sum()})
    for col, hm in CUTS.items():
        R[col] = x[x.hm <= hm].groupby("d").c.last()
    R["nb"] = g.size()
    R = R.reset_index().rename(columns={"index": "d"})
    R["pc"] = R.c.shift(1)
    return R


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    M1 = BASE / "data" / "m1" / "US"
    day = sorted(glob.glob(str(M1 / "day" / "*.parquet")))
    D = pd.concat([pd.read_parquet(f) for f in day], ignore_index=True) if day else None
    out = []
    files = sorted(glob.glob(str(M1 / "bf" / "*.parquet")))
    for i, f in enumerate(files):
        t = os.path.basename(f)[:-8]
        x = pd.read_parquet(f)
        if D is not None:
            x = pd.concat([x, D[D.t == t]], ignore_index=True).drop_duplicates("ts")
        R = summarize(x)
        if R is not None:
            R.insert(0, "t", t); out.append(R)
        if i % 100 == 0: print(f"{i}/{len(files)} {time.time() - t0:.0f}s", flush=True)
    A = pd.concat(out, ignore_index=True)
    A.to_parquet(ROOT / "cache" / "m1_daysum_us.parquet")
    print(f"완료 {len(A):,}행 · {A.t.nunique()}종목 · {A.d.min()}~{A.d.max()} · {(time.time() - t0) / 60:.1f}분")


if __name__ == "__main__":
    main()
