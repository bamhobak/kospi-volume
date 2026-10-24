# -*- coding: utf-8 -*-
"""1분봉 → 종목·날짜 요약표(2026-10-25, 장중 아이디어 실측용). data/m1/KR/bf/*.parquet + day/*.parquet.
봉 시각 = 봉 **끝** 시각(KST, 09:01~15:31 — m1-collect). 열:
  o    첫 봉 시가(≈ 시가 단일가)      p0905·p1000·p1100·p1430·p1500·p1520 = 그 시각 봉 종가(없으면 직전 봉)
  c    마지막 봉 종가(≈ 종가 단일가)   uv1·dv1·tv1 = 09:01~10:00 오른 봉·내린 봉·전체 거래량
  val  그날 거래대금(Σ c·v)           pc   전날 마지막 봉 종가
출력 research/cache/m1_daysum.parquet
    python research/m1_daysum.py
"""
import glob, os, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
CUTS = {"p0905": 905, "p1000": 1000, "p1100": 1100, "p1430": 1430, "p1500": 1500, "p1520": 1520}


def summarize(x):
    x = x.sort_values("ts")
    k = pd.to_datetime(x.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul")
    x = x.assign(d=k.dt.strftime("%Y%m%d"), hm=k.dt.hour * 100 + k.dt.minute)
    x = x[(x.hm >= 901) & (x.hm <= 1531)]
    if x.empty:
        return None
    g = x.groupby("d", sort=True)
    R = pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "val": (x.c * x.v).groupby(x.d).sum()})
    for col, hm in CUTS.items():
        R[col] = x[x.hm <= hm].groupby("d").c.last()
    f = x[x.hm <= 1000]
    R["uv1"] = f[f.c > f.o].groupby("d").v.sum()
    R["dv1"] = f[f.c < f.o].groupby("d").v.sum()
    R["tv1"] = f.groupby("d").v.sum()
    R["nb"] = g.size()
    R = R.reset_index().rename(columns={"index": "d"})
    R["pc"] = R.c.shift(1)
    return R


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    M1 = BASE / "data" / "m1" / "KR"
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
            R.insert(0, "t", t)
            out.append(R)
        if i % 200 == 0:
            print(f"{i}/{len(files)} {time.time() - t0:.0f}s", flush=True)
    A = pd.concat(out, ignore_index=True)
    (ROOT / "cache").mkdir(exist_ok=True)
    A.to_parquet(ROOT / "cache" / "m1_daysum.parquet")
    print(f"완료 {len(A):,}행 · {A.t.nunique()}종목 · {A.d.min()}~{A.d.max()} · {(time.time() - t0) / 60:.1f}분")


if __name__ == "__main__":
    main()
