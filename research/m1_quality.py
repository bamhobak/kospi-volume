# -*- coding: utf-8 -*-
"""C — 1분봉 품질 점검 (2026-10-03). 1분봉을 하루로 합쳐 일봉(data/kr_scan.pkl)과 맞춘다.
시가 = 09:01 봉 시가(시가 단일가) · 종가 = 15:31 봉 종가(종가 단일가) · 고가·저가 = 그날 최대·최소 · 거래량 = 정규장 합(시간외 빠짐 → 일봉보다 조금 작아야 정상)
    python research/m1_quality.py
"""
import sys, glob, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
KST = ZoneInfo("Asia/Seoul")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def daily_from_m1(f):
    D = pd.read_parquet(f)
    t = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(KST)
    D["date"] = t.dt.strftime("%Y%m%d"); D["hm"] = t.dt.strftime("%H%M")
    g = D.sort_values("ts").groupby("date")
    return pd.DataFrame({"o1": g.o.first(), "h1": g.h.max(), "l1": g.l.min(), "c1": g.c.last(), "v1": g.v.sum(), "n": g.size(),
                         "first": g.hm.first(), "last": g.hm.last()}).reset_index().assign(ticker=Path(f).stem)


def main():
    fs = sorted(glob.glob(str(BASE / "data/m1/KR/bf/*.parquet")))
    M = pd.concat([daily_from_m1(f) for f in fs])
    K = pd.read_pickle(BASE / "data/kr_scan.pkl")[["ticker", "date", "open", "high", "low", "close", "volume"]]
    J = M.merge(K, on=["ticker", "date"], how="inner")
    P("# C — 1분봉 품질 점검(국장) · %s" % pd.Timestamp.now().strftime("%Y-%m-%d")); P("")
    P("- 종목 %d · 종목-일 %s · 기간 %s~%s (일봉 패널은 %s 까지)" % (M.ticker.nunique(), f"{len(J):,}", J.date.min(), J.date.max(), K.date.max()))
    P("- 하루 봉 수 중앙 %d (정규장 391 = 09:01~15:31) · 391 미만인 날 %.1f%%" % (M.n.median(), (M.n < 391).mean() * 100)); P("")
    rows = []
    for nm, a, b in (("시가", "o1", "open"), ("고가", "h1", "high"), ("저가", "l1", "low"), ("종가", "c1", "close")):
        r = (J[a] / J[b] - 1).abs()
        rows.append((nm, (r < 1e-9).mean() * 100, (r < 0.005).mean() * 100, (r >= 0.05).mean() * 100))
    vr = J.v1 / J.volume.replace(0, np.nan)
    P("| 항목 | 정확히 같음 | 0.5% 안 | 5% 넘게 다름 |"); P("|---|---|---|---|")
    for nm, x, y, z in rows: P("| %s | %.1f%% | %.1f%% | %.2f%% |" % (nm, x, y, z))
    P("| 거래량(1분 합 ÷ 일봉) | 중앙 %.3f | 0.9~1.0 %.1f%% | 0.5 미만 %.2f%% |" % (vr.median(), vr.between(0.9, 1.0001).mean() * 100, (vr < 0.5).mean() * 100)); P("")
    # 해별
    J["y"] = J.date.str[:4]; J["ok"] = ((J.c1 / J.close - 1).abs() < 0.005) & ((J.o1 / J.open - 1).abs() < 0.005)
    P("| 해 | 종목-일 | 시가·종가 0.5% 안 | 거래량 비 중앙 |"); P("|---|---|---|---|")
    for y, g in J.groupby("y"):
        P("| %s | %s | %.1f%% | %.3f |" % (y, f"{len(g):,}", g.ok.mean() * 100, (g.v1 / g.volume.replace(0, np.nan)).median()))
    bad = J[~J.ok].copy(); bad["dc"] = (bad.c1 / bad.close - 1) * 100
    P(""); P("어긋난 예(종가 차이 큰 순 8개):"); P("")
    P("| 종목 | 날짜 | 1분 시가·종가 | 일봉 시가·종가 | 봉 수 |"); P("|---|---|---|---|---|")
    for _, x in bad.reindex(bad.dc.abs().sort_values(ascending=False).index).head(8).iterrows():
        P("| %s | %s | %s · %s | %s · %s | %d |" % (x.ticker, x.date, f"{x.o1:,.0f}", f"{x.c1:,.0f}", f"{x.open:,.0f}", f"{x.close:,.0f}", x.n))
    (ROOT / "reports" / "m1_quality_%s.md" % pd.Timestamp.now().strftime("%Y%m%d")).write_text("\n".join(OUT) + "\n", encoding="utf-8") if False else \
        (ROOT / "reports" / ("m1_quality_%s.md" % pd.Timestamp.now().strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
