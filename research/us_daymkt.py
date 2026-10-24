# -*- coding: utf-8 -*-
"""A3 토스 주간거래 → 미장 시가 (2026-10-25, 미장 후보 실측 3차) — H0367.

미장 정규장 날 d 마다 한국 시각 d 16:30 직전(국장 15:30 마감 뒤 · 뉴욕 새벽 02:30/03:30 · 프리장 전) 주간거래 마지막 체결가 dm 을
토스 1분봉 한 번 호출로 받는다(저장 research/cache/us_daymkt.parquet — 있으면 이어 받기).
그날 아시아가 새로 알려 준 몫(잔차 = 아시아 하루 등락 − 베타 × 전날 밤 미장 반도체)이 dm → 정규장 시가 에 남아 있나.
  매수 = 주간거래 dm(지정가로 그 값에 산다고 봄 — 주간거래는 얇다, 봉 수·거래량 같이 적음) · 매도 = 정규장 시가 또는 종가 · 비용 0.20
    python research/us_daymkt.py
"""
import sys, time, datetime as dt, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import collect_m1 as M
from verdict import log_trials

SYMS = ["NVDA", "MU", "AMD", "TSM", "AVGO", "AMAT", "QQQ", "SPY"]
SINCE = "20240301"
CACHE = ROOT / "cache" / "us_daymkt.parquet"
COST = 0.20
OUT = []; CELLS = [0]
def P(s=""): OUT.append(s); print(s, flush=True)
pct = lambda a, b: (a / b - 1) * 100


def fetch(A):
    have = pd.read_parquet(CACHE) if CACHE.exists() else pd.DataFrame(columns=["t", "d", "dm", "nbar", "vol", "first"])
    done = set(zip(have.t, have.d))
    rec, n = [], 0
    for tk in SYMS:
        days = sorted(A[(A.t == tk) & (A.d >= SINCE)].d.unique())
        for d in days:
            if (tk, d) in done: continue
            r = M.get("/api/v1/candles", symbol=tk, interval="1m", count=200, before="%s-%s-%sT16:30:00.000+09:00" % (d[:4], d[4:6], d[6:]))
            c = [x for x in (r or {}).get("candles") or [] if x["timestamp"][:10].replace("-", "") == d and x["timestamp"][11:13] >= "09"]
            if c:
                c = sorted(c, key=lambda x: x["timestamp"])
                rec.append(dict(t=tk, d=d, dm=float(c[-1]["closePrice"]), nbar=len(c), vol=sum(float(x["volume"]) for x in c), first=c[0]["timestamp"][11:16]))
            else:
                rec.append(dict(t=tk, d=d, dm=np.nan, nbar=0, vol=0.0, first=""))
            n += 1
            if n % 200 == 0:
                print("  %d호출 %s %s" % (n, tk, d), flush=True)
                pd.concat([have, pd.DataFrame(rec)]).to_parquet(CACHE)
    D = pd.concat([have, pd.DataFrame(rec)]) if rec else have
    D.to_parquet(CACHE)
    return D


def st(x):
    x = pd.Series(x).dropna()
    if len(x) < 15: return None
    t = x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
    return dict(n=len(x), mean=x.mean(), med=x.median(), win=(x > 0).mean() * 100, t=t)


def cell(s, n=0):
    return "- (%d)" % n if not s else "%+.2f · 중앙 %+.2f · %.0f%% · t%.1f (%d)" % (s["mean"], s["med"], s["win"], s["t"], s["n"])


def row(name, D, col, net=True, cut="20250101"):
    CELLS[0] += 1
    v = D[col] - (COST if net else 0)
    L, V = v[D.d < cut], v[D.d >= cut]
    P("| %s | %s | %s |" % (name, cell(st(L), L.notna().sum()), cell(st(V), V.notna().sum())))


t0 = time.time()
A = pd.read_parquet(ROOT / "cache" / "m1_daysum_us.parquet")
A = A[(A.nb >= 300) & (A.pc > 0)]
DM = fetch(A)
P("# A3 토스 주간거래 → 미장 · %s" % time.strftime("%Y-%m-%d"))
P("\n받은 날 %d · 주간거래 값 있는 날 %d · 봉 수 중앙 %d · 첫 봉 시각(한국) 많이: %s" % (
    len(DM), DM.dm.notna().sum(), DM[DM.nbar > 0].nbar.median(), DM[DM.nbar > 0]["first"].value_counts().head(3).to_dict()))
J = A.merge(DM[DM.nbar >= 5], on=["t", "d"])
J["dm_gap"] = pct(J.dm, J.pc); J["dm_open"] = pct(J.o, J.dm); J["dm_close"] = pct(J.c, J.dm); J["gap"] = pct(J.o, J.pc)
SEMI = ["NVDA", "MU", "AMD", "TSM", "AVGO", "AMAT"]
prev = A[A.t.isin(SEMI)].assign(day=lambda x: pct(x.c, x.pc)).groupby("d").day.mean().shift(1).rename("prev")
asia = {}
K = pd.read_parquet(ROOT / "cache" / "toss_kr_1d.parquet")
K = K[K.t.isin(["005930", "000660"])].pivot(index="d", columns="t", values="tc").sort_index()
asia["삼성·하이닉스"] = (K.pct_change() * 100).mean(axis=1)
try:
    import yfinance as yf
    for nm, sym in (("TSMC 대만", "2330.TW"), ("도쿄일렉", "8035.T"), ("닛케이", "^N225")):
        h = yf.Ticker(sym).history(start="2024-01-01", auto_adjust=True)
        s = h.Close.pct_change() * 100; s.index = s.index.strftime("%Y%m%d"); asia[nm] = s
except Exception as ex:
    P("야후 실패 %r" % ex)
P("\n| 아시아 | 무리 | 잔차↔주간거래 갭(전날 종가→dm) | 잔차↔dm→시가 | 잔차↔dm→종가 | 잔차↔정규장 갭 | 날 |"); P("|---|---|---|---|---|---|---|")
for nm, s in asia.items():
    X = J.merge(s.rename("a"), left_on="d", right_index=True).merge(prev, left_on="d", right_index=True).dropna(subset=["a", "prev"])
    b = np.polyfit(X.prev, X.a, 1)[0]
    X["res"] = X.a - b * X.prev
    for grp, m in (("반도체 6", X.t.isin(SEMI)), ("QQQ·SPY", X.t.isin(["QQQ", "SPY"]))):
        q = X[m]
        P("| %s | %s | %+.2f | %+.2f | %+.2f | %+.2f | %d |" % (nm, grp, q.res.corr(q.dm_gap), q.res.corr(q.dm_open), q.res.corr(q.dm_close), q.res.corr(q.gap), q.d.nunique()))
    asia[nm] = X
P("\n| 칸 | 2024 (평균 · 중앙 · 승률 · t · 건) | 2025~ |"); P("|---|---|---|")
for nm in list(asia):
    X = asia[nm]
    if not isinstance(X, pd.DataFrame): continue
    S = X[X.t.isin(SEMI)]
    for th in (1.5, 3.0):
        row("%s 잔차 ≥ +%.1f%% · 반도체 dm → 시가" % (nm, th), S[S.res >= th], "dm_open")
        row("%s 잔차 ≥ +%.1f%% · 반도체 dm → 종가" % (nm, th), S[S.res >= th], "dm_close")
        row("  [비용 전] dm → 시가", S[S.res >= th], "dm_open", net=False)
        row("%s 잔차 ≤ -%.1f%% · dm → 시가 (비용 전 · 내리면 마이너스가 맞음)" % (nm, th), S[S.res <= -th], "dm_open", net=False)
    row("%s [대조] 아무 날 반도체 dm → 시가 (비용 전)" % nm, S, "dm_open", net=False)
row("[참고] 반도체 dm 이 전날 종가보다 +2%↑ · dm → 시가 (비용 전)", J[J.t.isin(SEMI) & (J.dm_gap >= 2)], "dm_open", net=False)
row("[참고] 반도체 dm 이 전날 종가보다 -2%↓ · dm → 시가 (비용 전)", J[J.t.isin(SEMI) & (J.dm_gap <= -2)], "dm_open", net=False)
P("\n주간거래 유동성: 봉 수 중앙 %d · 16:30 까지 거래량 중앙 %s주(반도체 6)" % (
    J[J.t.isin(SEMI)].nbar.median(), f"{J[J.t.isin(SEMI)].vol.median():,.0f}"))
P("\n칸 수 %d · %.1f분" % (CELLS[0], (time.time() - t0) / 60))
log_trials("us_daymkt_20261025", CELLS[0])
(ROOT / "reports" / "us_daymkt_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
