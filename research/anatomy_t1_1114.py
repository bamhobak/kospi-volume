# -*- coding: utf-8 -*-
"""2026-11-14 규칙 손익 해부(anatomy_1114) [갭하락] 후보 칸 — 실전 과정 시뮬로 계좌 확인.
지금 설정(Q .40 · 예상 시장 대비 ≤ -1.0 · 지정가 -2.0 · 크기 ≤ 2/3 · 기본 30만 × 깊이 × 거래대금 배율 · 하루 5천만) + 실측 예상 갭 오차 · 체결 손해·체결률, 시드 5.
각 칸을 '빼면' 연 손익(학습 2016~22 / 검증 2023~)이 둘 다 느는가. 칸 경계는 anatomy_1114 학습 삼등분 값.
    python research/anatomy_t1_1114.py"""
# (t1_live_sim_1103 에서 가져옴) 2026-11-03 사용자 "1 2 3 다 돌려봐" — [갭 하락 조용주] 실전 과정(08:52 예상 갭 → 후보 → 지정가 → 시가 체결)을
# 실측 오차(10-06~11-02 19일, gap_err.pkl)로 2016~ 과거에 입혀 설정별 성적을 잰다.
# ① 후보 넓이(CAND_Q·CAND_REL) ② 지정가 문턱(LIMIT_THR)과 시장 예상 갭 보정
import os, sys, io, contextlib, itertools
os.chdir(r"C:\vscode\kospi-volume"); sys.path.insert(0, "research"); sys.path.insert(0, "research/factory"); sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT
import t1_size_liq_1021 as SL
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
E = pd.read_pickle("C:/temp/kp/gap_err.pkl")
M = E.groupby("d").agg(em=("eg", "median"), am=("ag", "median"))
b1, b0 = np.polyfit(M.am, M.em - M.am, 1)                     # 시장 오차 = b0 + b1·실제 시장 갭
res = (M.em - M.am) - (b0 + b1 * M.am)
print("시장 오차 = %.2f %+.2f×실제 시장 갭 (잔차 sd %.2f)" % (b0, b1, res.std()))
c1, c0 = np.polyfit(M.em, M.am, 1)                            # 보정: 예상 시장 갭으로 실제 시장 갭 추정
print("보정식 실제 시장 ≈ %.2f + %.2f×예상 시장" % (c0, c1))
BK = [-99, -7, -4, -2, -1, 0, 1, 99]
E["ab"] = np.digitize(E.ag, BK[1:-1])
POOL = {k: g.ei.values for k, g in E.groupby("ab")}

H = lab.hist()[["ticker", "date", "oc", "gap", "rgap", "q_vm", "liq", "amt20"] + ['mk_r5', 'st_up', 'd60', 'kdev', 'd50', 'rsi14', 'mcap', 'r60', 'r5', 'd120', 'bbp', 'd20', 'd224']].dropna(subset=["oc", "gap", "rgap", "liq", "amt20"])
H = H[H.date >= "20160101"].reset_index(drop=True)
H["oc"] -= FT.COST; H["a20"] = H.amt20 * 1e8; H["am"] = H.gap - H.rgap
base = (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 2 / 3)          # 지금 T1_LIQ 2/3
H["ab"] = np.digitize(H.gap, BK[1:-1])
print("패널", len(H), "날", H.date.nunique(), "| 기본 거르개 통과", int(base.sum()))
days = H.date.values; ud, di = np.unique(days, return_inverse=True)
amd = H.groupby("date").am.first().reindex(ud).values

def gen(seed):
    rng = np.random.default_rng(seed)
    me = b0 + b1 * amd + rng.choice(res.values, len(ud))       # 날마다 시장 오차
    ei = np.empty(len(H))
    for k, idx in H.groupby("ab").indices.items():
        ei[idx] = rng.choice(POOL[k], len(idx))
    eg = H.gap.values + me[di] + ei
    egs = pd.Series(eg)
    em = egs.groupby(di).transform("median").values               # 예상 시장 갭(유니버스 중앙)
    eq = egs.groupby(di).rank(pct=True).values
    return eg, em, eq

def run(eg, em, eq, Q, R, thr, corr, mmax=3.0, drop=None):
    erel = eg - em
    lim = (c0 + c1 * em if corr else em) + thr                  # 지정가 갭(어제 종가 대비)
    m = base.values & (eq <= Q) & (erel <= R) & (eg > -27.5) & (H.gap.values <= lim)
    if drop is not None: m &= ~drop
    W = H.loc[m, ["date", "oc", "rgap", "a20"]].copy()
    W["dep"] = np.clip(-erel[m], 1, mmax)
    W["amt"] = BASE_AMT * W.dep * (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    W = W.sort_values(["date", "rgap"]); W["cum"] = W.groupby("date").amt.cumsum(); W = W[W.cum <= 5e7]
    p = W.amt / W.a20 * 100
    W["pnl"] = W.amt * fill(p) * (W.oc - imp(p) + 0.05) / 100
    return W

def summ(W):
    y = W.date.str[:4]; ys = W.groupby(y).pnl.sum() / 1e4
    tr, te = W.date < "20230101", W.date >= "20230101"
    db = W.groupby("date").oc.mean()
    yrs = lambda z: z.date.str[:4].nunique()
    return dict(n=len(W) / yrs(W), per=W.oc.mean(), win=(W.oc > 0).mean() * 100, day=db.mean(),
                tr=W[tr].pnl.sum() / 1e4 / max(yrs(W[tr]), 1), te=W[te].pnl.sum() / 1e4 / max(yrs(W[te]), 1),
                worst=ys.loc["2016":"2025"].min(), rel_bad=(W.rgap > -0.5).mean() * 100)

BASE_AMT = 30e4
CUT = [("빼지 않음(지금)", None),
       ("시장 5일 등락 > 0", H.mk_r5 > 0), ("Supertrend 위(st_up 1)", (H.st_up > 0) & (H.st_up <= 1)), ("60일선 +5.89%↑", H.d60 > 5.89),
       ("코스피 60일선 +0.9%↑", H.kdev > 0.901), ("50일선 +4.85%↑", H.d50 > 4.85), ("RSI14 > 51", H.rsi14 > 51), ("크기 순위 > 0.455", H.liq > 0.455),
       ("시총 > 1,400억", H.mcap > 1400), ("20일 거래대금 > 50.4억", H.amt20 > 50.4), ("60일 등락 > +15%", H.r60 > 15), ("5일 등락 > -0.55%", H.r5 > -0.551),
       ("120일선 +9.26%↑", H.d120 > 9.26), ("볼린저 %b > 0.494", H.bbp > 0.494), ("20일선 -0.16%↑", H.d20 > -0.162), ("224일선 +12.9%↑", H.d224 > 12.9)]
acc = {k: [] for k, _ in CUT}
for sd in [1, 2, 3, 4, 5]:
    eg, em, eq = gen(sd)
    for k, dm in CUT:
        acc[k].append(summ(run(eg, em, eq, 0.40, -1.0, -2.0, False, drop=None if dm is None else dm.fillna(False).values)))
    print("시드", sd, flush=True)
OUT = ["# [갭하락] 해부 후보 — 실전 과정 시뮬 계좌 확인 (11-14)", "", "지금 설정 · 기본 30만 · 하루 5천만 · 시드 5 평균 · 연 손익 만원", "",
       "| 뺄 칸 | 연 건수 | 건당 | 승률 | 연 손익 학습 2016~22 | 연 손익 검증 2023~ | 최악의 해 | 판정 |", "|---|---|---|---|---|---|---|---|"]
B = pd.DataFrame(acc["빼지 않음(지금)"]).mean()
for k, _ in CUT:
    d = pd.DataFrame(acc[k]).mean()
    ok = k != "빼지 않음(지금)" and d.tr > B.tr and d.te > B.te
    OUT.append("| %s | %.0f | %+.2f%% | %.0f%% | %+.0f (%+.0f) | %+.0f (%+.0f) | %+.0f | %s |" % (k, d.n, d.per, d.win, d.tr, d.tr - B.tr, d.te, d.te - B.te, d.worst,
               "기준" if k == "빼지 않음(지금)" else ("**둘 다 늘어남**" if ok else "줄어듦")))
print(chr(10).join(OUT))
open("research/reports/anatomy_t1_1114.md", "w", encoding="utf-8").write(chr(10).join(OUT))
