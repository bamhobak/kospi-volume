# -*- coding: utf-8 -*-
"""데이 3규칙 — 계좌 2억·3억이면 금액을 어떻게 잡나(2026-11-10 후속, 연구만). 1억은 기준 줄.
모형은 day_acct_1e8_net_1110 그대로: [갭 하락 조용주](T1) 그물 = 예상 시장 대비 ≤ -1.0 · 지정가 문턱 -2.0 · 날 오차 e_d 부트스트랩 ·
종목 오차 N(0,0.7) · 씨앗 30. 08:53 에 [NXT 장후](T6) + [NXT 장전](T5) + T1 그물 주문 합 ≤ 계좌.
격자(계좌마다, 과적합 줄이려고 한 규칙씩 → 위 몇 개만 함께):
  1단계 지금 근처(T1 30만 · T5 100만 · T6 3천만·500만·k0.10)에서 하나씩: T1 기본 {30,40,50,70만} · T5 {100,150,200만} ·
        T6 (계좌 상한, 종목 상한) {(3천만,500만),(5천만,700만),(8천만,1천만),(1억,1.5천만)}(계좌 크기까지) × 거래대금 비율 k {0.10, 0.15}
  2단계 1단계 각 규칙 1등끼리 + T6 2등 조합.
    python research/day_acct_2e8_3e8_1110.py
"""
import io, contextlib, sys, itertools
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_acct_1e8_1110 as A
import day_acct_1e8_net_1110 as N

NET, LIM, IDIO, SEEDS = -1.0, -2.0, 0.7, 30
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def run(T6g, T5g, T1, days, EQ, b1, p5, a6, c6, k6, E, rng, imp, fill):
    ed = dict(zip(days, rng.choice(E, len(days))))
    X = T1.assign(e=T1.date.map(ed).fillna(0.41))
    X["xrel"] = X.rgap + X.e + rng.normal(0, IDIO, len(X))
    X = X[X.xrel <= NET].sort_values(["date", "xrel"])
    G = {d: g for d, g in X.groupby("date")}
    rows = []
    for d in days:
        used6 = pnl6 = used5 = pnl5 = 0.0
        g = T6g.get(d)
        if g is not None:
            amt = np.minimum(c6, k6 * g.v41.to_numpy())[:40]; amt = np.where(amt >= 30e4, amt, 0)
            cum = np.cumsum(amt); amt = np.clip(min(a6, EQ) - (cum - amt), 0, amt); amt = np.where(amt >= 30e4, amt, 0)
            r = g.g_vw.to_numpy()[:40] - A.nimp(amt, g.a10.to_numpy()[:40]) - A.nimp(amt, g.v0f.to_numpy()[:40])
            used6 = amt.sum(); pnl6 = float(np.sum(amt * r / 100))
        g = T5g.get(d)
        if g is not None:
            amt = np.minimum(p5 * g.k.to_numpy(), 0.10 * g.val5.to_numpy())
            cum = np.cumsum(amt); amt = np.clip(EQ - used6 - (cum - amt), 0, amt)
            r = g.r_vw.to_numpy() - A.nimp(amt, g.val5.to_numpy()); used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100))
        res1 = pnl1 = 0.0
        g = G.get(d)
        if g is not None:
            want = b1 * (-g.xrel.to_numpy()).clip(1, 3) * g.lm.to_numpy()
            cum = np.cumsum(want); amt = np.clip(EQ - used6 - used5 - (cum - want), 0, want); res1 = amt.sum()
            f = (g.rgap.to_numpy() <= LIM + g.e.to_numpy()) & (amt > 0)
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100
            pnl1 = float(np.sum(a * fill(p) * (oc - A.COST - imp(p)) / 100))
        rows.append((d, pnl6, pnl5, pnl1, used6, used5, res1, 0, (used6 + used5 + res1) >= EQ * 0.999))
    R = pd.DataFrame(rows, columns=["d", "p6", "p5", "p1", "u6", "u5", "r1", "cut", "full"])
    s = A.summ(R)
    lk = R.u6 + R.u5 + R.r1
    s.update(avg=lk.mean() / 1e4, peak=lk.quantile(0.9) / 1e4)
    return s


def evalc(ctx, EQ, cfg):
    T6g, T5g, T1, days, E, imp, fill = ctx
    S = [run(T6g, T5g, T1, days, EQ, *cfg, E, np.random.default_rng(s), imp, fill) for s in range(SEEDS)]
    m = {k: float(np.mean([x[k] for x in S])) for k in S[0]}
    m["sd"] = float(np.std([x["mean"] for x in S]))
    return m


def name(cfg):
    b1, p5, a6, c6, k6 = cfg
    return "T1 %d만 · T5 %d만 · T6 %s·%s·k%.2f" % (b1 / 1e4, p5 / 1e4, "%g천만" % (a6 / 1e7) if a6 < 1e8 else "%g억" % (a6 / 1e8), "%g만" % (c6 / 1e4), k6)


def line(EQ, cfg, m):
    return "| %s | %+.0f | %+.0f(±%.0f) | %+.0f | %.0f | %+.0f / %+.0f | %.0f%% | %+.0f/%+.0f/%+.0f | %.1f%% | %.0f / %.0f만 |" % (
        name(cfg), m["med"], m["mean"], m["sd"], m["worst"], m["dd"], m["h25"], m["h26"], m["full"], m["k6"], m["k5"], m["k1"],
        m["mean"] * 12 / (EQ / 1e4) * 100, m["avg"], m["peak"])


HDR = "| 조합 | 달 중앙 | 달 평균 | 최악의 달 | 최대 낙폭 | 2025 / 2026 중앙 | 꽉 찬 날 | 몫 T6/T5/T1(달) | 1년 % | 묶이는 돈 평균 / 90% |"


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    E, ne = N.live_e()
    T6, T5, _ = A.load(); T1 = N.t1_wide()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
    ctx = ({d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}, T1, days, E, imp, fill)
    P("# 데이 3규칙 계좌 크기별 · %s~%s · T1 그물 ≤ %.1f · 지정가 %.1f · 씨앗 %d (값: 만원, 고정 계좌)" % (A.D0, A.D1, NET, LIM, SEEDS))
    T6S = [(3000e4, 500e4), (5000e4, 700e4), (8000e4, 1000e4), (1e8, 1500e4)]
    cur = (30e4, 100e4, 3000e4, 500e4, 0.10)
    for EQ in (1e8, 2e8, 3e8):
        P("\n## 계좌 %d억\n" % (EQ / 1e8)); P(HDR); P("|---" * 10 + "|")
        seen = {}

        def go(cfg, show=True):
            if cfg not in seen:
                seen[cfg] = evalc(ctx, EQ, cfg)
                if show: P(line(EQ, cfg, seen[cfg]))
            return seen[cfg]
        go(cur)
        if EQ == 1e8:
            continue
        for b1 in (40e4, 50e4, 70e4): go((b1,) + cur[1:])
        for p5 in (150e4, 200e4): go((cur[0], p5) + cur[2:])
        for (a6, c6), k6 in itertools.product(T6S, (0.10, 0.15)):
            if a6 <= EQ: go(cur[:2] + (a6, c6, k6))
        b1b = max((c for c in seen if c[1:] == cur[1:]), key=lambda c: seen[c]["med"])[0]
        p5b = max((c for c in seen if c[0] == cur[0] and c[2:] == cur[2:]), key=lambda c: seen[c]["med"])[1]
        t6 = sorted((c for c in seen if c[:2] == cur[:2]), key=lambda c: -seen[c]["med"])[:2]
        P("| **함께(1단계 1등끼리)** | | | | | | | | | |")
        for c in t6: go((b1b, p5b) + c[2:])
        best = max(seen, key=lambda c: seen[c]["med"])
        P("\n→ 계좌 %d억 1등(달 중앙): %s" % (EQ / 1e8, name(best)))
    (ROOT / "day_acct_2e8_3e8_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
