# -*- coding: utf-8 -*-
"""2026-11-14 새 규칙 찾기 2번 '장부 모형' 덧대기 — ledger_1114 재료(외인·기관·개인·공매도 '물린 정도'·'물린 물량')를
지금 규칙 거래에 삼등분으로 덧대 '그 칸을 빼면' 나아지나(anatomy_1114 와 같은 판정 · 학습 99.5% · 검증 90%) → 계좌 확인.
재료는 그날 장 끝나고 아는 값: [갭하락]·[장전 되돌림](아침 매수)은 전날 값, [장후 낙폭](19:50 매수)·스윙(신호 날 종가 → 다음 날 시가)은 그날 값.
구간: [갭하락]·스윙 학습 2018~22(수급 자료 2018~) / 검증 2023~ · [장전 되돌림]·[장후 낙폭] 학습 2025 / 검증 2026.
계좌: [갭하락] = 실전 과정 시뮬(t1_live_sim 틀, 지금 설정·30만·5천만·시드 5) · 스윙 = 1억 자리·비중 계좌(청산 확정·체결 손해) · T5·T6 = 100만씩 손익 합.
    python research/memguard.py research/ledger_test_1114.py   → research/reports/ledger_test_1114.md"""

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

import math

import pickle, time as _t
from pathlib import Path
BASE_AMT = 30e4
from pathlib import Path
OUTL = []; PR = lambda s="": (OUTL.append(str(s)), print(s, flush=True))
L = pd.read_pickle(r"C:\temp\kp\ledger_1114.pkl"); L["ticker"] = L.ticker.astype(str); L["date"] = L.date.astype(str)
LF = [c for c in L.columns if c not in ("ticker", "date")]
CAL = sorted(L.date.unique()); PREV = dict(zip(CAL[1:], CAL[:-1]))
LP = L.copy(); LP["date"] = LP.date.map({v: k for k, v in PREV.items()})      # 전날 값 → 다음 날 행으로
LP = LP.dropna(subset=["date"])
rng2 = np.random.default_rng(17); NR = 300


def null_gain(r, k):
    m = r.mean(); N = len(r)
    idx = np.argsort(rng2.random((NR, N)), axis=1)[:, :k]
    return (r.sum() - r[idx].sum(1)) / (N - k) - m


def cells(T, TR, VA, nm):
    A = T[(T.date >= TR[0]) & (T.date <= TR[1])]; B = T[T.date >= VA[0]]
    out = []
    for f in LF:
        a = A.dropna(subset=[f]); b = B.dropna(subset=[f])
        if len(a) < 60 or len(b) < 20: continue
        q1, q2 = a[f].quantile([1 / 3, 2 / 3])
        if q1 == q2: continue
        for cut, lo, hi in (("하위 1/3", -np.inf, q1), ("가운데", q1, q2), ("상위 1/3", q2, np.inf)):
            ma = (a[f] > lo) & (a[f] <= hi); mb = (b[f] > lo) & (b[f] <= hi)
            k, kb = int(ma.sum()), int(mb.sum())
            if k < 15 or k > len(a) - 15 or kb < 5: continue
            g = a.ret[~ma].mean() - a.ret.mean()
            if g <= 0: continue
            pt = float((null_gain(a.ret.to_numpy(), k) < g).mean())
            if pt < 0.995: continue
            gv = b.ret[~mb].mean() - b.ret.mean()
            pv = float((null_gain(b.ret.to_numpy(), kb) < gv).mean()) if gv > 0 else 0.0
            out.append(dict(rule=nm, f=f, cut=cut, lo=lo, hi=hi, cell_tr=a.ret[ma].mean(), g_tr=g, p_tr=pt, cell_va=b.ret[mb].mean(), g_va=gv, p_va=pv,
                            sum_tr=-a.ret[ma].sum(), sum_va=-b.ret[mb].sum()))
    return out


def fmt_cut(r):
    return "%s (%s)" % (r["cut"], "≤%.3g" % r["hi"] if r["cut"] == "하위 1/3" else (">%.3g" % r["lo"] if r["cut"] == "상위 1/3" else "%.3g~%.3g" % (r["lo"], r["hi"])))


ROWS = []
# ── [갭하락] 연구판 거래 ──
U1 = lab.hist()
T1 = U1[(U1.rgap <= -1.5) & (U1.q_gap <= 0.40) & (U1.q_vm.fillna(1) <= 0.30) & (U1.liq <= 2 / 3) & U1.oc.notna()][["date", "ticker", "oc"]].copy()
T1["ret"] = T1.oc.clip(-60, 60) - FT.COST; T1["date"] = T1.date.astype(str); T1["ticker"] = T1.ticker.astype(str)
del U1
T1 = T1.merge(LP, on=["date", "ticker"], how="left")
ROWS += cells(T1, ("20180101", "20221231"), ("20230101", "20991231"), "[갭하락]")
# ── [장전 되돌림]·[장후 낙폭] ──
Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
T6 = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].dropna(subset=["g_vw"])
T6 = pd.DataFrame({"date": T6.d.astype(str).values, "ticker": T6.t.astype(str).values, "ret": T6.g_vw.values}).merge(L, on=["date", "ticker"], how="left")
S5 = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
S5 = S5[(S5.rpre <= -3) & (S5.cum <= 1_019_060_000) & S5.r_vwhs.notna()].copy()
S5["rk"] = S5.groupby("d").rpre.rank(method="first"); S5["ns"] = S5.groupby("d").rpre.transform("size"); S5 = S5[(S5.rk <= 4) & (S5.ns < 10)]
T5 = pd.DataFrame({"date": S5.d.astype(str).values, "ticker": S5.t.astype(str).values, "ret": S5.r_vwhs.values}).merge(LP, on=["date", "ticker"], how="left")
ROWS += cells(T5, ("20250101", "20251231"), ("20260101", "20991231"), "[장전 되돌림]")
ROWS += cells(T6, ("20250101", "20251231"), ("20260101", "20991231"), "[장후 낙폭]")
# ── 스윙 9규칙 ──
Zs = pickle.load(open(r"C:\temp\kp\port_sig.pkl", "rb")); S = Zs["S"].copy(); dates = Zs["dates"]; DI = {d: i for i, d in enumerate(dates)}
S["date"] = S.date.astype(str); S["ticker"] = S.ticker.astype(str); S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
S = S[S.date >= "20180101"].merge(L, on=["date", "ticker"], how="left").sort_values("di").reset_index(drop=True)
X = S
imp1 = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))
def acct(drop_idx, C=1e8, d0="20160101", d1="20221231"):
    """portfolio.py 자리 규칙 그대로(규칙별 mx · 같은 종목 중복 X · 비중 pct · 계좌 넘으면 안 삼), 청산 때 확정 → 연 %."""
    i0 = DI[min(d for d in dates if d >= d0)]; i1 = DI[max(d for d in dates if d <= d1)]
    Y = X[(X.di >= i0) & (X.di <= i1) & ~X.index.isin(drop_idx)]
    G = {i: g for i, g in Y.groupby("di")}
    eq = C; pos = []
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p[2] <= i: eq += p[1] * p[3] / 100
            else: still.append(p)
        pos = still
        g = G.get(i)
        if g is None: continue
        inv = sum(p[1] for p in pos)
        for t in g.itertuples():
            w = eq * t.pct / 100
            if sum(1 for p in pos if p[0] == t.rid) >= t.mx or inv + w > eq or any(p[4] == t.ticker for p in pos): continue
            pi = w / (t.amt20 * 1e8) * 100 if t.amt20 and t.amt20 > 0 else 50
            pos.append((t.rid, w, i + t.hold, t.ret - imp1(pi), t.ticker)); inv += w
    for p in pos: eq += p[1] * p[3] / 100
    yrs = (i1 - i0 + 1) / 250
    return ((eq / C) ** (1 / yrs) - 1) * 100



for rid, R in S.groupby("rid"):
    ROWS += cells(R.reset_index(drop=True).assign(_ix=R.index.values), ("20180101", "20221231"), ("20230101", "20991231"), "스윙 " + rid)
PR("# 장부 모형 덧대기 (11-14)\n")
PR("- 재료 %d개: %s" % (len(LF), ", ".join(LF)))
PR("- 학습 무작위 99.5%% 넘은 칸 %d개 · 그중 검증 90%% 통과 %d개\n" % (len(ROWS), sum(1 for r in ROWS if r["g_va"] > 0 and r["p_va"] >= 0.90)))
# 계좌 확인
B0s = None; base_t1 = None
PR("| 규칙 | 재료 | 뺄 칸 | 학습: 칸 건당 · 빼면 +%p · 등수 | 검증: 칸 건당 · 빼면 +%p · 등수 | 계좌 확인(학습 / 검증) | 판정 |"); PR("|---|---|---|---|---|---|---|")
acc_t1 = None
for r in sorted(ROWS, key=lambda r: (r["rule"], -r["p_va"], -r["g_va"])):
    okv = r["g_va"] > 0 and r["p_va"] >= 0.90
    acc = "-"; ok = False
    if okv:
        if r["rule"] == "[갭하락]":
            if acc_t1 is None:
                Hm = H[["date", "ticker"]].astype(str).merge(LP, on=["date", "ticker"], how="left")
                SEEDS_ = [1, 2, 3, 4, 5]; EG = [gen(sd) for sd in SEEDS_]
                B1 = pd.DataFrame([summ(run(*e, 0.40, -1.0, -2.0, False)) for e in EG]).mean(); acc_t1 = True
            v = Hm[r["f"]]; dm = ((v > r["lo"]) & (v <= r["hi"])).fillna(False).values
            d = pd.DataFrame([summ(run(*e, 0.40, -1.0, -2.0, False, drop=dm)) for e in EG]).mean()
            acc = "연 %+.0f / %+.0f만" % (d.tr - B1.tr, d.te - B1.te); ok = d.tr > B1.tr and d.te > B1.te
        elif r["rule"].startswith("스윙"):
            if B0s is None: B0s = (acct([], d0="20180101", d1="20221231"), acct([], d0="20230101", d1="20261231"))
            rid = r["rule"].split()[1]; v = X[r["f"]]
            m = (X.rid == rid) & (v > r["lo"]) & (v <= r["hi"])
            da = acct(list(X.index[(m & (X.date <= "20221231")).to_numpy()]), d0="20180101", d1="20221231") - B0s[0]
            db = acct(list(X.index[(m & (X.date >= "20230101")).to_numpy()]), d0="20230101", d1="20261231") - B0s[1]
            acc = "연 %+.1f / %+.1f%%p" % (da, db); ok = da > 0 and db > 0
        else:
            acc = "100만씩 %+.0f / %+.0f만" % (r["sum_tr"], r["sum_va"]); ok = r["sum_tr"] > 0 and r["sum_va"] > 0
    PR("| %s | %s | %s | %+.2f · %+.2f · %.1f%% | %+.2f · %+.2f · %.0f%% | %s | %s |" % (r["rule"], r["f"], fmt_cut(r), r["cell_tr"], r["g_tr"], r["p_tr"] * 100,
       r["cell_va"], r["g_va"], r["p_va"] * 100, acc, "**후보**" if ok else ("검증 ✅ · 계좌 ❌" if okv else "검증 ❌")))
Path(r"C:\vscode\kospi-volume\research\reports\ledger_test_1114.md").write_text(chr(10).join(OUTL), encoding="utf-8")
