# -*- coding: utf-8 -*-
"""1분봉 '이벤트 날' 도구 (2026-10-07) — 일봉으로 고른 (종목, 날짜) 의 그날 1분봉을 쓴다. 없으면 토스에서 받아 bf 에 보탠다.
과거 채우기(backfill)는 지금 거래대금 상위 종목만이라 상한가·급등 같은 소형주 이벤트 날이 빠진다 → 이벤트 날만 받아 표본 편향을 줄인다
(H0295: 상위 1,000만 쓰면 T1 후보 33% 만 잡혔다). 토스에 없는 폐지 종목은 못 받는다 — 받은/못 받은 수를 꼭 적을 것.
  ensure(mk, pairs)  → 없는 날 받아 저장, (받음, 못 받음) 반환
  bars(mk, ticker, dates) → {date: DataFrame(hm,o,h,l,c,v)} (그날 정규장 1분봉)
"""
import sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE))
import collect_m1 as M
TZ = {"KR": "Asia/Seoul", "US": "America/New_York"}


def _dates_in(f, mk):
    if not f.exists(): return set()
    D = pd.read_parquet(f, columns=["ts"])
    return set(pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(TZ[mk]).dt.strftime("%Y%m%d"))


def ensure(mk, pairs, log=print):
    """pairs = [(ticker, 'YYYYMMDD'), ...] — 없는 날만 토스에서 받는다. 돌리는 동안 1분봉 과거 채우기는 쉰다(토스 속도 한도 공유)."""
    bf = BASE / "data" / "m1" / mk / "bf"; bf.mkdir(parents=True, exist_ok=True)
    by = {}
    for t, d in pairs: by.setdefault(t, set()).add(d)
    need = []
    for t, ds in by.items():
        have = _dates_in(bf / (t + ".parquet"), mk)
        need += [(t, d) for d in sorted(ds - have)]
    if not need: return 0, 0
    log("1분봉 받을 종목-일 %d (종목 %d)" % (len(need), len({t for t, _ in need})))
    M.BUSY.write_text("event")
    got, miss = {}, 0
    try:
        with ThreadPoolExecutor(M.WORKERS) as ex:
            for (t, d), rows in zip(need, ex.map(lambda x: M.fetch_day(mk, x[0], x[1]), need)):
                if len(rows) >= (200 if mk == "KR" else 150): got.setdefault(t, []).extend(rows)
                else: miss += 1
    finally:
        try: M.BUSY.unlink()
        except Exception: pass
    for t, rows in got.items():
        f = bf / (t + ".parquet"); D = M.frame(rows)
        if f.exists(): D = pd.concat([pd.read_parquet(f), D]).drop_duplicates(["t", "ts"]).sort_values("ts")
        D.to_parquet(f, index=False, compression="zstd")
    return len(need) - miss, miss


def bars(mk, ticker, dates):
    f = BASE / "data" / "m1" / mk / "bf" / (ticker + ".parquet")
    if not f.exists(): return {}
    D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(TZ[mk])
    D["date"] = t.dt.strftime("%Y%m%d").values; D["hm"] = t.dt.strftime("%H%M").values
    D = D[D.date.isin(set(dates))].sort_values("ts")
    out = {}
    for d, g in D.groupby("date"):
        g = g[["hm", "o", "h", "l", "c", "v"]].reset_index(drop=True)
        for k in ("o", "h", "l", "c"): g[k] = g[k].astype("float64")
        out[d] = g
    return out
