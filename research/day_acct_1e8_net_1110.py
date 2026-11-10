# -*- coding: utf-8 -*-
"""데이 3규칙 1억 계좌 — [갭 하락 조용주](T1)를 장전 예상 오차까지 넣어 다시(2026-11-10 후속, 연구만).
day_acct_1e8_1110 은 T1 그물·체결을 실제 시장 대비(rel)로 깨끗하게 갈랐다. 실전은 08:52 예상값으로 그물을 걸고, 지정가는
'어제 종가 × (1 + 예상 시장 갭 + LIMIT_THR)' 라 예상 시장 갭이 틀린 만큼 문턱이 움직인다(11-10 부터 LIMIT_THR -2.0).
  날마다 e_d = 예상 시장 갭 − 실제 시장 갭: 실전 10-13~11-04 17일 값(snap mgap − y1_hist mgap)을 실전 통계(평균 +0.41 · 표준편차 0.59,
       10-13~11-09)에 맞게 늘려 붙인 것에서 뽑는다(부트스트랩) · 종목마다 예상 갭 오차 ~ N(0, 0.7%p)
  그물(08:53 돈 묶임) = 예상 시장 대비(실제 rel + e_d + 종목 오차) ≤ NET · 갭 순위는 실제로(노이즈 무시)
  사지는 것 = 그물 안 & 실제 rel ≤ LIMIT_THR + e_d (= 실제 시가 ≤ 지정가) · 놓침 0.89 는 안 곱함(오차로 직접 넣음)
  T5 100만 · T6 3천만·500만 고정(지금 설정) · 씨앗 30개 평균 · 나머지 모형·잣대는 day_acct_1e8_1110 그대로.
    python research/day_acct_1e8_net_1110.py
"""
import io, contextlib, sys, json, glob, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_acct_1e8_1110 as A

LIMIT_THR, IDIO, SEEDS = -2.0, 0.7, 30
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def live_e():
    U = pd.read_pickle(BASE / "data" / "y1_hist.pkl"); am = U.groupby("date").mgap.first()
    e = []
    for f in sorted(glob.glob(str(BASE / "data" / "day" / "snap_*.json"))):
        d = f[-13:-5]
        if d < "20261013" or d not in am.index: continue
        mg = json.load(open(f, encoding="utf-8")).get("mgap")
        if mg is not None: e.append(mg - am[d])
    e = np.array(e)
    return 0.41 + (e - e.mean()) / e.std() * 0.59, len(e)


def t1_wide():
    U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
    U = U[(U.date >= A.D0) & (U.date <= A.D1) & (U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= 3.0)].dropna(subset=["oc", "amt20"]).copy()
    U["lm"] = (U.amt20 / U.groupby("date").amt20.transform("median")).clip(0.3, 3)
    return U


def run(T6g, T5g, T1, days, NET, b1, E, rng, imp, fill):
    ed = dict(zip(days, rng.choice(E, len(days))))
    X = T1.assign(e=T1.date.map(ed).fillna(0.41))
    X["xrel"] = X.rgap + X.e + rng.normal(0, IDIO, len(X))
    X = X[X.xrel <= NET].sort_values(["date", "xrel"])
    G = {d: g for d, g in X.groupby("date")}
    tot_true = (T1.rgap <= -1.5).sum(); got_true = 0
    rows = []
    for d in days:
        used6 = pnl6 = used5 = pnl5 = 0.0
        g = T6g.get(d)
        if g is not None:
            amt = np.minimum(500e4, 0.10 * g.v41.to_numpy())[:40]; amt = np.where(amt >= 30e4, amt, 0)
            cum = np.cumsum(amt); amt = np.clip(3000e4 - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
            r = g.g_vw.to_numpy()[:40] - A.nimp(amt, g.a10.to_numpy()[:40]) - A.nimp(amt, g.v0f.to_numpy()[:40])
            used6 = amt.sum(); pnl6 = float(np.sum(amt * r / 100))
        g = T5g.get(d)
        if g is not None:
            amt = np.minimum(100e4 * g.k.to_numpy(), 0.10 * g.val5.to_numpy())
            cum = np.cumsum(amt); amt = np.clip(A.EQ - used6 - (cum - amt), 0, amt)
            r = g.r_vw.to_numpy() - A.nimp(amt, g.val5.to_numpy()); used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100))
        res1 = pnl1 = 0.0
        g = G.get(d)
        if g is not None:
            want = b1 * (-g.xrel.to_numpy()).clip(1, 3) * g.lm.to_numpy()          # 깊이 배율도 예상값으로
            room = A.EQ - used6 - used5; cum = np.cumsum(want); amt = np.clip(room - (cum - want), 0, want)
            res1 = amt.sum()
            f = (g.rgap.to_numpy() <= LIMIT_THR + g.e.to_numpy()) & (amt > 0)
            got_true += int((f & (g.rgap.to_numpy() <= -1.5)).sum())
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100
            pnl1 = float(np.sum(a * fill(p) * (oc - A.COST - imp(p)) / 100))
        rows.append((d, pnl6, pnl5, pnl1, used6, used5, res1, 0, (used6 + used5 + res1) >= A.EQ * 0.999))
    R = pd.DataFrame(rows, columns=["d", "p6", "p5", "p1", "u6", "u5", "r1", "cut", "full"])
    s = A.summ(R); s["cap"] = got_true / tot_true * 100
    return s


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    E, ne = live_e()
    T6, T5, _ = A.load(); T1 = t1_wide()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
    T6g = {d: g for d, g in T6.groupby("d1")}; T5g = {d: g for d, g in T5.groupby("d")}
    P("# T1 장전 예상 오차 넣은 1억 계좌 · e_d 실전 %d일(평균 %+.2f · 표준편차 %.2f · %+.2f~%+.2f) · 종목 오차 N(0,%.1f) · 지정가 문턱 %.1f · 씨앗 %d" % (
        ne, E.mean(), E.std(), E.min(), E.max(), IDIO, LIMIT_THR, SEEDS))
    P("\n| 그물(예상 시장 대비) | T1 기본 | 달 중앙 | 달 평균 | 최악의 달 | 최대 낙폭 | 2025 / 2026 중앙 | 꽉 찬 날 | 08:53 묶이는 돈 90% | T1 몫(달) | 진짜 후보 잡은 비율 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    res = []
    for NET, b1 in itertools.product((-0.5, -1.0, -1.5), (30e4, 40e4, 50e4)):
        S = [run(T6g, T5g, T1, days, NET, b1, E, np.random.default_rng(s), imp, fill) for s in range(SEEDS)]
        m = {k: float(np.mean([x[k] for x in S])) for k in S[0]}
        sd = float(np.std([x["mean"] for x in S]))
        res.append((NET, b1, m))
        P("| ≤ %.1f | %d만 | %+.0f | %+.0f(±%.0f) | %+.0f | %.0f | %+.0f / %+.0f | %.0f%% | %.0f만 | %+.0f | %.0f%% |" % (
            NET, b1 / 1e4, m["med"], m["mean"], sd, m["worst"], m["dd"], m["h25"], m["h26"], m["full"], m["peak"], m["k1"], m["cap"]))
    P("\n비교(앞 판, 예상 오차 없음 · 놓침 0.89): T1 30만·깊이3 / T5 100만 / T6 3천만·500만 — 달 중앙 +179 · 평균 +257 · 최악 -30 · 낙폭 -581 · 2025/2026 +172/+291 · 꽉 찬 날 2% · T1 몫 +34")
    (ROOT / "day_acct_1e8_net_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
