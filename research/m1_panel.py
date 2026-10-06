# -*- coding: utf-8 -*-
"""국장 1분봉 → 종목-일 '장중 단면' 표 (2026-10-06, 사용자 "다른 규칙 찾아봐").
전 기간을 다 받은 종목(collect_m1 backfill 완료 · 지금 거래대금 상위 1,000)만 쓴다 — 후보일만 받은 759종목은 하루치뿐이라 뺀다.
가격은 **1분봉끼리만**(일봉 수정주가와 섞지 않는다 — H0295 함정). 전날 종가도 같은 파일의 전날 마지막 봉.
칸:
  o 시가(09:01 봉 시가 = 장전 단일가) · c 종가(마지막 봉 = 종가 단일가) · pc 전날 종가 · no 다음날 시가
  p{hm} 그 시각 가격(그때까지 마지막 봉 종가) — 0905 0910 0915 0930 1000 1030 1100 1200 1300 1400 1430 1500 1519
  hi/lo{hm} 그 시각까지 고·저 · v{hm} 그 시각까지 거래량 · vw{hm} 그 시각까지 VWAP · amt 하루 거래대금 · vol 하루 거래량
  orb15/orb30: 09:15/09:30 까지 고가를 11:00 전에 처음 넘은 봉의 시각·체결가(max(선, 그 봉 시가))
  vwr: 10:00 에 VWAP 아래였다가 10:01~13:00 에 처음 VWAP 위로 마감한 봉의 시각·가격
  lo_t 저가 시각 · hi_t 고가 시각 · lo14 14:00 뒤 저가 · lo_am 14:00 전 저가
    python research/m1_panel.py      → research/cache/m1_panel_KR.pkl
"""
import json, sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
SNAP = ["0905", "0910", "0915", "0930", "1000", "1030", "1100", "1200", "1300", "1400", "1430", "1500", "1519"]


def one(f):
    D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c", "v"])
    if len(D) < 5000: return None
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul")
    D["date"] = t.dt.strftime("%Y%m%d").values; D["hm"] = t.dt.strftime("%H%M").values
    D = D.sort_values("ts").reset_index(drop=True)
    for k in ("o", "h", "l", "c"): D[k] = D[k].astype("float64")
    D["v"] = D.v.astype("float64"); D["pv"] = D.c * D.v
    g = D.groupby("date", sort=True)
    R = pd.DataFrame({"o": g.o.first(), "c": g.c.last(), "n": g.size(), "first": g.hm.first(), "last": g.hm.last(),
                      "vol": g.v.sum(), "amt": g.pv.sum(), "hi": g.h.max(), "lo": g.l.min()})
    R["hi_t"] = D.loc[g.h.idxmax(), ["date", "hm"]].set_index("date").hm
    R["lo_t"] = D.loc[g.l.idxmin(), ["date", "hm"]].set_index("date").hm
    for hm in SNAP:
        S = D[D.hm <= hm]; gs = S.groupby("date")
        R["p" + hm] = gs.c.last(); R["hi" + hm] = gs.h.max(); R["lo" + hm] = gs.l.min(); R["v" + hm] = gs.v.sum()
        R["vw" + hm] = gs.pv.sum() / gs.v.sum().replace(0, np.nan)
    am = D[D.hm < "1400"].groupby("date").l.min(); pm = D[D.hm >= "1400"].groupby("date").l.min()
    R["lo_am"] = am; R["lo14"] = pm
    # 시가 범위 돌파(ORB) — 11:00 전 처음 넘은 봉
    for k, cut in (("orb15", "0915"), ("orb30", "0930")):
        rh = D[D.hm <= cut].groupby("date").h.max()
        A = D[(D.hm > cut) & (D.hm <= "1100")].copy(); A["rh"] = A.date.map(rh)
        A = A[A.h > A.rh]
        fst = A.groupby("date").head(1).set_index("date")
        R[k + "_t"] = fst.hm; R[k + "_px"] = np.maximum(fst.rh, fst.o)
    # VWAP 되찾기 — 10:00 에 VWAP 아래 → 10:01~13:00 에 처음 VWAP 위 마감
    D["cv"] = g.v.cumsum(); D["cpv"] = g.pv.cumsum(); D["vwap"] = D.cpv / D.cv.replace(0, np.nan)
    below10 = (R.p1000 < R.vw1000)
    A = D[(D.hm > "1000") & (D.hm <= "1300") & (D.c > D.vwap) & D.date.map(below10).fillna(False).astype(bool)]
    fst = A.groupby("date").head(1).set_index("date")
    R["vwr_t"] = fst.hm; R["vwr_px"] = fst.c
    R["pc"] = R.c.shift(1); R["pdate"] = pd.Series(R.index, index=R.index).shift(1)
    R["no"] = R.o.shift(-1)
    # 첫 5분 거래량 기준선(지난 20거래일 평균) · 거래대금 20일(전날까지)
    R["v5_20"] = R.v0905.shift(1).rolling(20, min_periods=10).mean()
    R["amt20"] = R.amt.shift(1).rolling(20, min_periods=10).mean()
    R["ticker"] = Path(f).stem
    return R.reset_index()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    syms = sorted(k.split(":")[1] for k in done if k.startswith("KR:"))
    fs = [BASE / "data" / "m1" / "KR" / "bf" / (s + ".parquet") for s in syms]
    fs = [f for f in fs if f.exists()]
    out = []
    with ProcessPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(one, fs, chunksize=4)):
            if r is not None: out.append(r)
            if (i + 1) % 100 == 0: print("  %d/%d · %.1f분" % (i + 1, len(fs), (time.time() - t0) / 60), flush=True)
    P = pd.concat(out, ignore_index=True)
    P = P[(P.n >= 300) & (P["first"] <= "0905") & (P["last"] >= "1530")]
    P.to_pickle(ROOT / "cache" / "m1_panel_KR.pkl")
    print("끝 — %d행 · 종목 %d · %s~%s · %.1f분" % (len(P), P.ticker.nunique(), P.date.min(), P.date.max(), (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
