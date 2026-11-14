# -*- coding: utf-8 -*-
"""2026-11-14 새 규칙 찾기 2번 '장부 모형' — [반대매매] 신용 장부처럼 쌓고 깎는 장부를 다른 주체에 씌워 '물린 정도' 재료를 만든다.
주체: 외인·기관·개인(data/investor.db flow11, 원 단위 순매수, 2018~ · 그날 장 끝나고 앎) · 공매도(data/krx_daily.db short_balance 잔고 주수, 2016-06~ · T+2 공개 → 2거래일 늦춰 씀).
장부(외인·기관·개인): 하루 순매수 금액 ÷ 그날 종가 = 주수. 매수면 평균 단가 = 가중 평균, 매도면 단가 그대로 물량만 줄임, 물량이 0 아래로 가면 0(새로 시작).
  매일 물량의 λ 만큼 덜어 냄(오래된 물량 잊기) — λ 1/20 · 1/60 · 1/120 세 판.
장부(공매도): 잔고가 늘면 그날 종가에 판 것으로 가중 평균, 줄면 단가 그대로.
재료(그날 종가 기준, 그날 장 끝나고 앎): uw_* = 종가 ÷ 평균 단가 − 1 (%) · ld_* = 남은 물량 × 종가 ÷ 20일 평균 거래대금(일 수).
  이름: f/i/p = 외인/기관/개인, 숫자 = 1/λ · s = 공매도.  결과 C:/temp/kp/ledger_1114.pkl (ticker·date·재료)
    python research/memguard.py research/ledger_1114.py"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
t0 = time.time()
PX = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl")[["ticker", "date", "close"]]
PX = PX[PX.date >= "20160101"].copy(); PX["ticker"] = PX.ticker.astype(str); PX["date"] = PX.date.astype(str)
c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
F = pd.read_sql("SELECT ticker, date, indiv AS p, frgn AS f, (COALESCE(fin,0)+COALESCE(ins,0)+COALESCE(tru,0)+COALESCE(pef,0)+COALESCE(bank,0)+COALESCE(ofin,0)+COALESCE(pens,0)) AS i FROM flow11", c)
k = sqlite3.connect("file:" + str(BASE / "data" / "krx_daily.db") + "?mode=ro", uri=True)
SB = pd.read_sql("SELECT ticker, date, bal_qty FROM short_balance", k)
U = pd.read_pickle(BASE / "research" / "cache" / "factory_kr.pkl")[["ticker", "date", "amt20"]]
print("자료 %.1f분 · 가격 %d · 수급 %d · 공매도 %d" % ((time.time() - t0) / 60, len(PX), len(F), len(SB)), flush=True)
X = PX.merge(F, on=["ticker", "date"], how="left").merge(SB, on=["ticker", "date"], how="left").merge(U, on=["ticker", "date"], how="left")
del F, SB, U
X = X.sort_values(["ticker", "date"]).reset_index(drop=True)
X["bal_qty"] = X.groupby("ticker").bal_qty.shift(2)                 # T+2 공개
LAMS = (20, 60, 120)
out = {("uw_%s%d" % (a, L)): np.full(len(X), np.nan, np.float32) for a in "fip" for L in LAMS}
out.update({("ld_%s%d" % (a, L)): np.full(len(X), np.nan, np.float32) for a in "fip" for L in LAMS})
out["uw_s"] = np.full(len(X), np.nan, np.float32); out["ld_s"] = np.full(len(X), np.nan, np.float32)
cl = X.close.to_numpy(float); a20 = X.amt20.to_numpy(float) * 1e8
FL = {a: X[a].to_numpy(float) for a in "fip"}; bq = X.bal_qty.to_numpy(float)
for n_, (tk, ix) in enumerate(X.groupby("ticker").indices.items()):
    ix = np.sort(ix)
    for a in "fip":
        v = FL[a][ix]
        if np.isnan(v).all(): continue
        for L in LAMS:
            lam = 1.0 / L; pos = 0.0; cost = np.nan
            uw = out["uw_%s%d" % (a, L)]; ld = out["ld_%s%d" % (a, L)]
            for j, g in enumerate(ix):
                p = cl[g]
                if not (p > 0): continue
                pos *= (1 - lam)
                q = v[j] / p if v[j] == v[j] else 0.0
                if q > 0:
                    cost = (pos * cost + q * p) / (pos + q) if pos > 0 and cost == cost else p; pos += q
                elif q < 0:
                    pos += q
                    if pos <= 0: pos = 0.0; cost = np.nan
                if pos > 0 and cost == cost:
                    uw[g] = (p / cost - 1) * 100
                    if a20[g] > 0: ld[g] = pos * p / a20[g]
    b = bq[ix]
    if not np.isnan(b).all():
        prev = np.nan; cost = np.nan
        for j, g in enumerate(ix):
            p = cl[g]; q = b[j]
            if not (p > 0) or q != q: continue
            if prev != prev or cost != cost: cost = p
            elif q > prev: cost = (prev * cost + (q - prev) * p) / q
            prev = q
            if q > 0:
                out["uw_s"][g] = (p / cost - 1) * 100
                if a20[g] > 0: out["ld_s"][g] = q * p / a20[g]
    if n_ % 500 == 0: print("  종목 %d · %.1f분" % (n_, (time.time() - t0) / 60), flush=True)
R = X[["ticker", "date"]].copy()
for kk, vv in out.items(): R[kk] = vv
R = R[R.date >= "20180101"].reset_index(drop=True)
R.to_pickle(r"C:\temp\kp\ledger_1114.pkl")
print("끝 %.1f분 · %d행 · 채움률 %s" % ((time.time() - t0) / 60, len(R), {k: round(float(R[k].notna().mean()), 2) for k in ("uw_f60", "uw_i60", "uw_p60", "uw_s")}))
