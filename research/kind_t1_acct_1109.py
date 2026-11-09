# -*- coding: utf-8 -*-
"""H0395 후속 — [갭 하락 조용주] 갭 구간 공시를 계좌에서 어떻게 쓰나 (2026-11-09).
t1_live_sim_1103.py 의 실전 과정(08:52 예상 갭 오차·지정가·체결률·충격비용·하루 한도)을 그대로 쓰고,
공시 있음(08:50 까지 알 수 있는 것만) 거래를 ① 그대로 ② 빼기 ③ 0.5배 ④ 한도 찰 때 맨 뒤로(순서만) 로 바꿔 연 손익을 잰다.
하루 한도 5천만(지금 설정)과 1천만(돈 모자란 계좌 흉내) 두 가지.
    python research/kind_t1_acct_1109.py
"""
import os, sys, io, re, contextlib, sqlite3
os.chdir(r"C:\vscode\kospi-volume"); sys.path[:0] = ["research", "research/factory", "."]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT
import t1_size_liq_1021 as SL
from verdict import log_trials
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
E = pd.read_pickle("C:/temp/kp/gap_err.pkl")
M = E.groupby("d").agg(em=("eg", "median"), am=("ag", "median"))
b1, b0 = np.polyfit(M.am, M.em - M.am, 1)
res = (M.em - M.am) - (b0 + b1 * M.am)
BK = [-99, -7, -4, -2, -1, 0, 1, 99]
E["ab"] = np.digitize(E.ag, BK[1:-1])
POOL = {k: g.ei.values for k, g in E.groupby("ab")}

H = lab.hist()[["ticker", "date", "oc", "gap", "rgap", "q_vm", "liq", "amt20"]].dropna(subset=["oc", "gap", "rgap", "liq", "amt20"])
H = H[H.date >= "20160101"].reset_index(drop=True)
H["oc"] -= FT.COST; H["a20"] = H.amt20 * 1e8; H["am"] = H.gap - H.rgap
base = (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9)
H["ab"] = np.digitize(H.gap, BK[1:-1])
days = H.date.values; ud, di = np.unique(days, return_inverse=True)
amd = H.groupby("date").am.first().reindex(ud).values

# 공시: 전 거래일 15:30 뒤 ~ 당일 08:50 전(실전 08:52 판단 때 알 수 있는 것)
cal = np.array(sorted(ud))
c = sqlite3.connect("data/dart/kind_time.db")
K = pd.read_sql("select day, hm, kcode from kind where market in ('유가증권','코스닥')", c)
hm = K.hm.astype(int); calset = set(cal); trd = K.day.isin(calset)
nxt = cal[np.minimum(np.searchsorted(cal, K.day.values, side="right"), len(cal) - 1)]
K["gd"] = np.where(trd & (hm < 850), K.day, np.where(trd & (hm <= 1530), "", nxt))
S = set(zip(K.kcode, K.gd))
H["disc"] = [(t[:5], d) in S for t, d in zip(H.ticker.values, H.date.values)]
print("공시 있음 비율(기본 거르개 통과 중) %.1f%%" % (H.disc[base].mean() * 100))


def gen(seed):
    rng = np.random.default_rng(seed)
    me = b0 + b1 * amd + rng.choice(res.values, len(ud))
    ei = np.empty(len(H))
    for k, idx in H.groupby("ab").indices.items():
        ei[idx] = rng.choice(POOL[k], len(idx))
    eg = H.gap.values + me[di] + ei
    egs = pd.Series(eg)
    em = egs.groupby(di).transform("median").values
    eq = egs.groupby(di).rank(pct=True).values
    return eg, em, eq


def run(eg, em, eq, mode, cap, Q=0.40, R=-0.5, thr=-1.5, mmax=3.0):
    erel = eg - em
    lim = em + thr
    m = base.values & (eq <= Q) & (erel <= R) & (eg > -27.5) & (H.gap.values <= lim)
    if mode == "drop": m &= ~H.disc.values
    W = H.loc[m, ["date", "oc", "rgap", "a20", "disc"]].copy()
    W["dep"] = np.clip(-erel[m], 1, mmax)
    W["amt"] = 50e4 * W.dep * (W.a20 / W.groupby("date").a20.transform("median")).clip(0.3, 3)
    if mode == "half": W.loc[W.disc, "amt"] *= 0.5
    W["k"] = W.disc.astype(int) if mode == "last" else 0
    W = W.sort_values(["date", "k", "rgap"]); W["cum"] = W.groupby("date").amt.cumsum(); W = W[W.cum <= cap]
    p = W.amt / W.a20 * 100
    W["pnl"] = W.amt * fill(p) * (W.oc - imp(p) + 0.05) / 100
    return W


def summ(W):
    tr, te = W.date < "20230101", W.date >= "20230101"
    yrs = lambda z: max(z.date.str[:4].nunique(), 1)
    ys = W.groupby(W.date.str[:4]).pnl.sum() / 1e4
    dd = W.groupby("date").pnl.sum().cumsum() / 1e4
    return dict(n=len(W) / yrs(W), per=W.oc.mean(), tr=W[tr].pnl.sum() / 1e4 / yrs(W[tr]), te=W[te].pnl.sum() / 1e4 / yrs(W[te]),
                worst=ys.loc["2016":"2025"].min(), mdd=(dd - dd.cummax()).min(), dshare=W.disc.mean() * 100)


MODES = (("base", "그대로(지금)"), ("drop", "공시 있음 빼기"), ("half", "공시 있음 0.5배"), ("last", "한도 찰 때 공시 있음 맨 뒤로"))
CAPS = (5e7, 1e7)
acc = {(m, cp): [] for m, _ in MODES for cp in CAPS}
for sd in (1, 2, 3, 4, 5):
    eg, em, eq = gen(sd)
    for m, _ in MODES:
        for cp in CAPS: acc[(m, cp)].append(summ(run(eg, em, eq, m, cp)))
    print("시드", sd, flush=True)
L = ["# [갭 하락 조용주] 갭 구간 공시 — 계좌 실측(실전 과정 흉내, 시드 5개 평균) · 2026-11-09", "",
     "| 하루 한도 | 방법 | 연 건수 | 건당 % | 공시 있음 비중 | **학습 연 손익(만)** | **검증 연 손익(만)** | 최악의 해 | 최대 낙폭(만) |", "|---|---|---|---|---|---|---|---|---|"]
for cp in CAPS:
    for m, nm in MODES:
        d = pd.DataFrame(acc[(m, cp)]).mean()
        L.append("| %d천만 | %s | %.0f | %+.2f | %.1f%% | **%+.0f** | **%+.0f** | %+.0f | %+.0f |" % (cp / 1e7, nm, d.n, d.per, d.dshare, d.tr, d.te, d.worst, d.mdd))
L.append(""); L.append("(칸 %d)" % (len(MODES) * len(CAPS)))
print("\n".join(L))
log_trials("kind_t1_acct_1109", len(MODES) * len(CAPS))
open("research/reports/kind_t1_acct_1109.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
