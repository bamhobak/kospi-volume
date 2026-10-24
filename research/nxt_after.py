# -*- coding: utf-8 -*-
"""⑪ NXT 장후 → 다음 날 (2026-10-25 사용자 아이디어 실측).
토스 일봉은 NXT 장전·장후가 섞인 통합 봉(종가 = 20:00 까지 마지막 체결) — KRX 종가(1분봉 마지막 봉 15:30)와의 차이가 장후 움직임.
  AH    = 토스 종가 / KRX 종가 - 1 (%)      rel = AH - 그날 대형주 평균 AH
  다음 날: 갭 = KRX 시가 / KRX 종가 - 1 · 시가→종가 · NXT 장후 종가 → 다음 날 시가(o1 / 토스 종가 - 1)
대형주 = 최근 60일 1분봉 거래대금 상위 120(ETF 빼고). 자료 2025-03~(NXT 출범). 학습 2025-03~12 / 검증 2026~. 비용 왕복 0.23%.
    python research/nxt_after.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
import collect_m1 as M
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
CK = 0.23
TR, VA = ("20250301", "20251231"), ("20260101", "20991231")
NC = [0]


def fetch(sym):
    rows, before = [], None
    for _ in range(3):
        q = dict(symbol=sym, interval="1d", count=200)
        if before: q["before"] = before
        c = (M.get("/api/v1/candles", **q) or {}).get("candles") or []
        if not c: break
        rows += [(sym, x["timestamp"][:10].replace("-", ""), float(x["openPrice"]), float(x["closePrice"])) for x in c]
        before = min(x["timestamp"] for x in c)
        if min(r[1] for r in rows) < "20250201": break
    return rows


def cell(x, cost):
    x = pd.Series(x).dropna() - cost
    if len(x) < 15: return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))
    return "%+.3f (%d%% · %d · t%.1f)" % (x.mean(), (x > 0).mean() * 100, len(x), t)


def row(lab, df, col, cost=CK, ctrl=None):
    NC[0] += 1
    a = df[(df.d >= TR[0]) & (df.d <= TR[1])]; b = df[df.d >= VA[0]]
    s = "| %s | %s | %s |" % (lab, cell(a[col], cost), cell(b[col], cost))
    if ctrl: s += " %+.3f | %+.3f |" % ((a[col] - a[ctrl]).mean(), (b[col] - b[ctrl]).mean())
    P(s)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    D = pd.read_parquet(ROOT / "cache" / "m1_daysum.parquet")
    stocks = set(pd.read_pickle(BASE / "data/kr_scan.pkl").ticker.unique())
    D = D[D.t.isin(stocks)]
    top = D[D.d >= sorted(D.d.unique())[-60]].groupby("t").val.mean().nlargest(120).index.tolist()
    cp = ROOT / "cache" / "toss_kr_1d.parquet"
    if cp.exists():
        T = pd.read_parquet(cp)
    else:
        rows = []
        for i, s in enumerate(top):
            rows += fetch(s)
            if i % 20 == 0: print("토스 일봉 %d/%d" % (i, len(top)), flush=True)
        T = pd.DataFrame(rows, columns=["t", "d", "to", "tc"]).drop_duplicates(["t", "d"])
        T.to_parquet(cp)
    X = D[D.t.isin(top)][["t", "d", "o", "c"]].merge(T, on=["t", "d"], how="inner").sort_values(["t", "d"])
    X = X[X.d >= "20250301"].copy()
    X["AH"] = (X.tc / X.c - 1) * 100
    g = X.groupby("t")
    X["o1"], X["c1"], X["d1"] = g.o.shift(-1), g.c.shift(-1), g.d.shift(-1)
    X = X.dropna(subset=["o1"])
    X["gap1"] = (X.o1 / X.c - 1) * 100
    X["oc1"] = (X.c1 / X.o1 - 1) * 100
    X["nx1"] = (X.o1 / X.tc - 1) * 100            # NXT 장후 종가 매수 → 다음 날 KRX 시가
    X["cc1"] = (X.c1 / X.c - 1) * 100
    X["mAH"] = X.groupby("d").AH.transform("mean"); X["rel"] = X.AH - X.mAH
    for c in ("oc1", "nx1", "cc1"): X["m_" + c] = X.groupby("d")[c].transform("mean")
    same = (X.AH.abs() < 1e-9).mean()
    P("# ⑪ NXT 장후 → 다음 날 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 대형주 %d종목 · %s~%s · %d행 · 장후 움직임 없는 행(토스 종가 = KRX 종가) %.0f%%" % (X.t.nunique(), X.d.min(), X.d.max(), len(X), same * 100))
    P("- AH 분포: 절대값 평균 %.2f%% · 하루 대형주 평균 AH 와 다음 날 평균 갭 상관 %.2f · 종목 AH 와 그 종목 다음 날 갭 상관 %.2f" % (
        X.AH.abs().mean(), X.groupby("d")[["mAH", "gap1"]].mean().corr().iloc[0, 1], X[["AH", "gap1"]].corr().iloc[0, 1]))
    b = X.assign(q=pd.qcut(X.AH, 5, labels=False, duplicates="drop")).groupby("q").agg(AH=("AH", "mean"), gap1=("gap1", "mean"), oc1=("oc1", "mean"), n=("AH", "size"))
    P("- AH 5분위(비용 전): " + " · ".join("AH %+.2f → 갭 %+.2f·시가→종가 %+.2f(%d)" % (r.AH, r.gap1, r.oc1, r.n) for r in b.itertuples())); P("")
    P("| 조건 | 학습 2025-03~12 | 검증 2026~ | 대조 차 학습 | 대조 차 검증 |"); P("|---|---|---|---|---|")
    row("대조 · 아무 대형주 다음 날 시가→종가", X, "oc1")
    for th in (1.0, 2.0):
        row("장후 시장보다 %.0f%%p↓ 덜 오름(rel ≤ -%.0f) · 다음 날 시가→종가" % (th, th), X[X.rel <= -th], "oc1", ctrl="m_oc1")
        row("　└ 같은 조건 · NXT 장후 종가 매수 → 다음 날 시가", X[X.rel <= -th], "nx1", ctrl="m_nx1")
        row("　└ 같은 조건 · KRX 종가 → 다음 날 종가(참고, 미리 못 삼)", X[X.rel <= -th], "cc1", ctrl="m_cc1")
        row("장후 시장보다 %.0f%%p↑ 더 오름 · 다음 날 시가→종가" % th, X[X.rel >= th], "oc1", ctrl="m_oc1")
        row("장후 %+.0f%%↑ 오름 · 다음 날 시가→종가" % th, X[X.AH >= th], "oc1", ctrl="m_oc1")
        row("장후 -%.0f%%↓ 빠짐 · 다음 날 시가→종가" % th, X[X.AH <= -th], "oc1", ctrl="m_oc1")
        row("장후 -%.0f%%↓ 빠짐 · NXT 장후 종가 매수 → 다음 날 시가" % th, X[X.AH <= -th], "nx1", ctrl="m_nx1")
    P(""); P("(칸 %d · %.1f분)" % (NC[0], (time.time() - t0) / 60))
    log_trials("nxt_after_%s" % time.strftime("%Y%m%d"), NC[0])
    (ROOT / "reports" / ("nxt_after_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
