# -*- coding: utf-8 -*-
"""2026-11-14 새 규칙 찾기 3번 '규칙 손익 해부' — 채택 데이 규칙의 거래를 재료(공장 재료 사전 FT.FEATS) 삼등분으로 갈라 '어디서 지는가'.
규칙: [갭하락](T1 연구판: rgap ≤ -1.5 · 갭 하위 40% · 거래량 하위 30% · 크기 ≤ 2/3, 2016~) · [장전 되돌림](T5, 2025-03~) · [장후 낙폭](T6, 2025-04~)
재료는 그 규칙이 살 때 미리 아는 것만(T1 = 장전·시가 · T5 = 장전 · T6 = 그날 종가까지 다 앎 — 19:50 매수).
판정: 한 재료의 한 칸(삼등분 중 하나, 경계는 학습 구간 거래로)을 빼면 나머지 건당이 얼마나 오르나 →
  같은 개수를 무작위로 뺀 판 300번 중 몇 등(학습) — 99.5% 이상만 후보(재료 ~100 × 3칸 다중검정) → 검증에서도 같은 방향(빼면 오름·90% 이상)인가
  → 계좌 확인: 거래당 100만 고정 손익 합(빼면 건수가 줄어 합이 줄 수 있음) · T1 은 하루 20% 균등 일복리 계좌 연수익도.
구간: T1 학습 2016~22 / 검증 2023~ · T5·T6 학습 ~2025-12 / 검증 2026~.
    python research/anatomy_1114.py   → research/reports/anatomy_1114.md"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT / "factory"), str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
NR, P_TR, P_VA, SEED = 300, 0.995, 0.90, 11
t0 = time.time()
U = lab.hist()
FEAT = [f for f in FT.FEATS if f in U.columns and f not in FT.FLOW and U[f].dtype.kind in "fi"]
print("재료 %d · hist %.1f분" % (len(FEAT), (time.time() - t0) / 60), flush=True)

# ── 규칙별 거래(date·ticker·ret) ──
T1 = U[(U.rgap <= -1.5) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.liq <= 2 / 3) & U.oc.notna()][["date", "ticker", "oc"]].copy()
T1["ret"] = T1.oc.clip(-60, 60) - FT.COST
Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
T6 = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].dropna(subset=["g_vw"])
T6 = T6.rename(columns={"t": "ticker", "d": "date"})[["date", "ticker"]].assign(ret=T6.g_vw.values)
S5 = pd.read_pickle(r"C:\temp\kp\pmrev5_panel_1103.pkl")
S5 = S5[(S5.tm == 840) & S5.r_vw.notna() & (S5.rpre <= -3) & (S5.cum <= 1_019_060_000)]
S5 = S5.assign(rk=S5.groupby("d").rpre.rank(method="first"), ns=S5.groupby("d").rpre.transform("size"))
S5 = S5[(S5.rk <= 4) & (S5.ns < 10)]                                  # 순위 4 안 · 신호 10개↑ 날 쉼(지금 규칙, 장후 1.5 거르개는 패널에 없어 뺌)
T5 = S5.rename(columns={"t": "ticker", "d": "date"})[["date", "ticker"]].assign(ret=S5.r_vw.values)
for T in (T6, T5):
    T["date"] = T.date.astype(str); T["ticker"] = T.ticker.astype(str)
RULES = [("[갭하락]", T1, {"pre", "open"}, ("20160101", "20221231"), ("20230101", "20991231")),
         ("[장전 되돌림]", T5, {"pre"}, ("20250101", "20251231"), ("20260101", "20991231")),
         ("[장후 낙폭]", T6, {"pre", "open", "close"}, ("20250101", "20251231"), ("20260101", "20991231"))]
rng = np.random.default_rng(SEED)


def null_gain(r, k, n=NR):
    """r 에서 k 개를 무작위로 뺀 나머지 평균 − 전체 평균, n 번."""
    m = r.mean(); N = len(r)
    idx = np.argsort(rng.random((n, N)), axis=1)[:, :k]
    rem = (r.sum() - r[idx].sum(1)) / (N - k)
    return rem - m


def acct_t1(T):
    """하루 20% 를 그날 종목 균등 · 일복리 → 연 %."""
    d = T.groupby("date").ret.mean() / 100 * 0.20
    if not len(d): return np.nan
    return (float((1 + d).prod()) ** (1 / len(set(T.date.str[:4]))) - 1) * 100


for nm, T, ok_at, TR, VA in RULES:
    X = T.merge(U[["date", "ticker"] + [f for f in FEAT if FT.FEATS[f][1] in ok_at]], on=["date", "ticker"], how="left")
    fs = [f for f in FEAT if FT.FEATS[f][1] in ok_at and X[f].notna().mean() > 0.7]
    A = X[(X.date >= TR[0]) & (X.date <= TR[1])]; B = X[X.date >= VA[0]]
    P("\n## %s — 학습 %d건 %+.2f%% · 검증 %d건 %+.2f%% · 재료 %d개\n" % (nm, len(A), A.ret.mean(), len(B), B.ret.mean(), len(fs)))
    rows = []
    for f in fs:
        a = A.dropna(subset=[f]); b = B.dropna(subset=[f])
        if len(a) < 90 or len(b) < 30: continue
        q1, q2 = a[f].quantile([1 / 3, 2 / 3])
        if q1 == q2: continue
        for lab_, lo, hi in (("하위 1/3", -np.inf, q1), ("가운데", q1, q2), ("상위 1/3", q2, np.inf)):
            ma = (a[f] > lo) & (a[f] <= hi) if lo > -np.inf else a[f] <= hi
            mb = (b[f] > lo) & (b[f] <= hi) if lo > -np.inf else b[f] <= hi
            k = int(ma.sum()); kb = int(mb.sum())
            if k < 20 or k > len(a) - 20 or kb < 10: continue
            gain = a.ret[~ma].mean() - a.ret.mean()
            if gain <= 0: continue
            pt = float((null_gain(a.ret.to_numpy(), k) < gain).mean())
            rows.append(dict(f=f, cut=lab_, lo=lo, hi=hi, k=k, cell_tr=a.ret[ma].mean(), gain_tr=gain, p_tr=pt, kb=kb,
                             cell_va=b.ret[mb].mean(), gain_va=b.ret[~mb].mean() - b.ret.mean(), dtr=a.index[ma.to_numpy()].to_numpy(), dva=b.index[mb.to_numpy()].to_numpy()))
    R = pd.DataFrame(rows)
    if not len(R):
        P("- 후보 없음"); continue
    cand = R[R.p_tr >= P_TR].copy()
    P("- 칸 %d개 중 학습 무작위 %.1f%% 넘은 칸 %d개 (무작위면 기대 %.1f개)" % (len(R), P_TR * 100, len(cand), len(R) * (1 - P_TR)))
    out = []
    for r in cand.itertuples():
        b = B.dropna(subset=[r.f])
        pv = float((null_gain(b.ret.to_numpy(), r.kb) < r.gain_va).mean()) if r.gain_va > 0 else 0.0
        keep_a = A.drop(index=r.dtr); keep_b = B.drop(index=r.dva)
        out.append(dict(r._asdict(), p_va=pv, sum_tr=(keep_a.ret.sum() - A.ret.sum()) / 100 * 100, sum_va=(keep_b.ret.sum() - B.ret.sum()) / 100 * 100,
                        acc_tr=(acct_t1(keep_a) - acct_t1(A)) if nm == "[갭하락]" else np.nan, acc_va=(acct_t1(keep_b) - acct_t1(B)) if nm == "[갭하락]" else np.nan))
    O = pd.DataFrame(out).sort_values(["p_va", "gain_va"], ascending=False)
    P("| 재료 | 뺄 칸 | 학습: 그 칸 건당 · 빼면 +%p · 무작위 등수 | 검증: 그 칸 건당 · 빼면 +%p · 무작위 등수 | 100만씩 손익 변화 학습/검증(만원) | 하루 20% 계좌 연%p 학습/검증 | 판정 |")
    P("|---|---|---|---|---|---|---|")
    for r in O.head(15).itertuples():
        okv = r.gain_va > 0 and r.p_va >= P_VA
        acc_ok = (r.sum_va > 0) if nm != "[갭하락]" else (r.acc_va > 0)
        P("| %s(%s) | %s (%s) | %+.2f · %+.2f · %.1f%% | %+.2f · %+.2f · %.0f%% | %+.0f / %+.0f | %s | %s |" % (
            FT.FEATS[r.f][0][:22], r.f, r.cut, "≤%.3g" % r.hi if r.cut == "하위 1/3" else (">%.3g" % r.lo if r.cut == "상위 1/3" else "%.3g~%.3g" % (r.lo, r.hi)),
            r.cell_tr, r.gain_tr, r.p_tr * 100, r.cell_va, r.gain_va, r.p_va * 100, r.sum_tr, r.sum_va,
            ("%+.1f / %+.1f" % (r.acc_tr, r.acc_va)) if nm == "[갭하락]" else "-",
            "**후보**" if okv and acc_ok else ("검증 ✅ · 계좌 ❌" if okv else "검증 ❌")))
    print("  %s %.1f분" % (nm, (time.time() - t0) / 60), flush=True)
(ROOT / "reports" / "anatomy_1114.md").write_text("# 규칙 손익 해부 (11-14)\n" + "\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
