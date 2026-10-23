# -*- coding: utf-8 -*-
"""데이 최종 예상 — 10-21 확정 설정 전부 넣고 5천 계좌 해마다 1년 손익 (2026-10-21 사용자 "최종 예상 수익률").
[갭 하락 조용주] 본체: 4/9 · 갭 하위 40% · 거래량 하위 30% · 실제 시장 대비 -1.5%p(지정가) · 금액 50만 × 깊이(1.5~5) × 거래대금 배율(0.3~3)
  덤: [+] 어제 14:00→종가 ≤ -1%(1분봉 — 2023~ 만) · [++] 짝 미장 예상 갭 ≤ -0.5 — 둘 다 1/3 안에서만, 같은 금액 한 번 더
  후보 문턱 -0.5 로 진짜 후보의 약 89% 를 잡는다(t1_time_1021) → 손익 × 0.89 (보수: 놓치는 건 무작위라고 봄)
  매도: 장중 걸어 팔기(최우선 매도 − 1칸) 이득을 금액 배수별 **보수 쪽** 값으로 더함(t1_passive_sell3: 1배 +0.05 · 2배 +0.16 · 3배 +0.24%p)
[미장 폭락 과잉 갭]: 나스닥 전날 -2.5%↓ · 갭 -2%↓ · 덜 반영 하위 10% · 1/2 · 50만 × 깊이 — 같은 날 돈은 [갭 하락 조용주] 다음 순서
계좌 5천(그리고 3천·1억) · 깊은 순으로 담다 돈 떨어지면 못 삼 · 체결 손해 모형 = t1_size_liq_1021.fit · 비용 0.23 뒤.
    python research/t1_final_1021.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import t1_size_liq_1021 as SL
import lab, feats as FT, common as C
import m1_event as ME

import os
CAPTURE = 0.89
IMP_SCALE = float(os.environ.get("IMP_SCALE", "1"))         # 체결 밀림 모형 배수(1 = 실측 모형 · 0.5 = 절반 · 0 = 밀림 없음)
PASS_GAIN = {1: 0.13, 2: 0.24, 3: 0.33} if os.environ.get("PASS_OPT") else {1: 0.05, 2: 0.16, 3: 0.24}
MA_N = int(os.environ.get("MA_N", "0")); MA_MULT = float(os.environ.get("MA_MULT", "1")); MA_IDX = os.environ.get("MA_IDX", "KS11")   # 10-24 이평 아래 날 더 싣기
MA_SIDE = os.environ.get("MA_SIDE", "below")                                                  # above 면 위인 날에 MA_MULT(덜 사기)
D_MAX = float(os.environ.get("D_MAX", "5")); D_POW = float(os.environ.get("D_POW", "1"))     # 10-24 깊이 배율 = clip(|rgap|,1,D_MAX)^D_POW
depth = lambda r: (-r).clip(1, D_MAX) ** D_POW


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: IMP_SCALE * np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + IMP_SCALE * cf * p)
    H = lab.hist()[["ticker", "date", "oc", "gap", "rgap", "q_gap", "q_vm", "liq", "amt20", "tr_pred", "q_tr_res"]].dropna(subset=["oc", "rgap", "q_gap", "liq", "amt20"])
    H = H[H.date >= "20160101"].copy(); H["oc"] -= FT.COST; H["a20"] = H.amt20 * 1e8
    # 본체
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9)].copy()
    Px = pd.read_pickle(C.CACHE / "factory_px.pkl")[["ticker", "date"]].sort_values(["ticker", "date"])
    Px["pdate"] = Px.groupby("ticker").date.shift(1)
    W = W.merge(Px, on=["ticker", "date"], how="left").reset_index(drop=True)
    need = W[(W.date >= "20230101") & W.pdate.notna() & (W.liq <= 1 / 3)]
    with contextlib.redirect_stdout(io.StringIO()):
        ME.ensure("KR", list(zip(need.ticker, need.pdate)), log=lambda *a: None)
    lh = pd.Series(np.nan, index=W.index)
    for t, g in need.groupby("ticker"):
        B = ME.bars("KR", t, list(g.pdate))
        for i, r in zip(g.index, g.itertuples()):
            b = B.get(r.pdate)
            if b is None or not len(b): continue
            b14 = b[b.hm <= "1400"]
            if len(b14): lh[i] = (b.c.iloc[-1] / b14.c.iloc[-1] - 1) * 100
    small = W.liq <= 1 / 3
    W["k"] = 1 + ((lh <= -1.0).values & small.values).astype(int) + ((W.tr_pred <= -0.5).fillna(False) & small).astype(int)
    W["unit"] = 50e4 * depth(W.rgap) * (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    W["amt"] = W.unit * W.k; W["rule"] = "T1"
    if MA_N:                                                    # 10-24: 지수가 어제 N일선 아래인 날 본체 금액 × MA_MULT
        Xi = fdr.DataReader(MA_IDX, "2015-01-01"); Xi = Xi[Xi.Close > 0]
        bl = dict(zip(Xi.index.strftime("%Y%m%d"), (Xi.Close < Xi.Close.rolling(MA_N).mean()).shift(1)))
        W.loc[W.date.map(bl) == (MA_SIDE == "below"), "amt"] *= MA_MULT
    # T4
    X = fdr.DataReader("IXIC", "2015-06-01"); X = X[X.Close > 0]
    us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d"); ud = us.index.values
    H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
    U = H[(H.us <= -2.5) & (H.gap <= -2.0) & (H.q_tr_res <= 0.10) & (H.liq <= 1 / 2)].copy()
    U = U[~U.set_index(["ticker", "date"]).index.isin(W.set_index(["ticker", "date"]).index)]          # 겹치면 한 번만
    U["k"] = 1; U["amt"] = 50e4 * depth(U.rgap); U["rule"] = "T4"
    A = pd.concat([W[["date", "ticker", "oc", "rgap", "a20", "k", "amt", "rule"]], U[["date", "ticker", "oc", "rgap", "a20", "k", "amt", "rule"]]], ignore_index=True)
    A["pri"] = np.where(A.rule == "T1", 0, 1)
    A = A.sort_values(["date", "pri", "rgap"])
    p = A.amt / A.a20 * 100
    A["pnl"] = A.amt * fill(p) * (A.oc - imp(p) + A.k.map(PASS_GAIN).fillna(0.24)) / 100 * CAPTURE
    A["cum"] = A.groupby("date").amt.cumsum()
    y = A.date.str[:4]
    print("| 해 | 3천 계좌 | **5천 계좌** | 1억 계좌 | 5천: 주문 건수 | 5천: [미장 폭락 과잉 갭] 몫 |"); print("|---|---|---|---|---|---|")
    R = {}
    for acct in (3000, 5000, 10000):
        K = A[A.cum <= acct * 1e4]; R[acct] = (K.groupby(K.date.str[:4]).pnl.sum() / 1e4, K)
    for yy in sorted(y.unique()):
        K5 = R[5000][1]; k5 = K5[K5.date.str[:4] == yy]
        print("| %s | %+.0f만 | **%+.0f만 (%+.1f%%)** | %+.0f만 | %d건 | %+.0f만 |" % (yy, R[3000][0].get(yy, 0), R[5000][0].get(yy, 0), R[5000][0].get(yy, 0) / 5000 * 100,
              R[10000][0].get(yy, 0), k5.k.sum(), k5[k5.rule == "T4"].pnl.sum() / 1e4))
    for acct in (3000, 5000, 10000):
        s = R[acct][0].loc["2016":"2025"]; s3 = R[acct][0].loc["2023":"2025"]
        print("\n%d만 계좌 2016~25: 평균 %+.0f만(연 %+.1f%%) · 중앙 %+.0f만(%+.1f%%) · 최악 %+.0f만 · 최고 %+.0f만 · 2023~25 평균 %+.0f만(%+.1f%%)" % (
            acct, s.mean(), s.mean() / acct * 100, s.median(), s.median() / acct * 100, s.min(), s.max(), s3.mean(), s3.mean() / acct * 100), end="")
    print("\n\n(2016~22 는 덤 [+] 자료가 없어 [++] 만 — 그 구간은 조금 낮게 나온다)")


if __name__ == "__main__":
    main()
