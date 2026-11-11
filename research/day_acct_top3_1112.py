# -*- coding: utf-8 -*-
"""[갭 하락 조용주] '하루 위 3개'(H0362 · day_top3.py 그림자) 를 계좌에 넣으면 — 쓰는 돈·1년 손익(2026-11-12 후속, 연구만).
모형은 day_acct_2e8_3e8_1110 그대로(그물 = 예상 시장 대비 ≤ -1.0 · 지정가 -2.0 + e_d · 날 오차 부트스트랩 · 종목 오차 0.7 · 씨앗 30).
1억 · [NXT 장전] 100만 · [NXT 장후] 3천만·500만 고정. T1 만 바꾼다:
  (a) 지금: 그물 전부에 30만 × 깊이(1~3) × 거래대금 배율 지정가
  (b) 위 3개: 그물 중 예상 시장 대비 깊은 3개에만 주문 · 금액 (a) 와 같음
  (c) 위 3개 · 하루 T1 예산 B 를 셋에 똑같이(B/3) · B ∈ {300,600,1000,1500만}
  (d) 위 5개 · 같은 예산 B/5
  사지는 것 = 주문 낸 종목 중 실제 시가 ≤ 지정가 · 큰 금액은 t1_size_liq 체결 손해·체결률 모형이 깎는다.
    python research/day_acct_top3_1112.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import day_acct_1e8_1110 as A, day_acct_1e8_net_1110 as N

NET, LIM, IDIO, SEEDS, EQ = -1.0, -2.0, 0.7, 30, 1e8
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def run(ctx, var, rng):
    T6g, T5g, T1, days, E, imp, fill = ctx
    kind, top, B = var
    ed = dict(zip(days, rng.choice(E, len(days))))
    X = T1.assign(e=T1.date.map(ed).fillna(0.41))
    X["xrel"] = X.rgap + X.e + rng.normal(0, IDIO, len(X))
    X = X[X.xrel <= NET].sort_values(["date", "xrel"])
    if top: X = X.groupby("date").head(top)
    G = {d: g for d, g in X.groupby("date")}
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
            cum = np.cumsum(amt); amt = np.clip(EQ - used6 - (cum - amt), 0, amt)
            r = g.r_vw.to_numpy() - A.nimp(amt, g.val5.to_numpy()); used5 = amt.sum(); pnl5 = float(np.nansum(amt * r / 100))
        res1 = pnl1 = fil1 = 0.0; n1 = 0
        g = G.get(d)
        if g is not None:
            if kind == "size":
                want = 30e4 * (-g.xrel.to_numpy()).clip(1, 3) * g.lm.to_numpy()
            else:
                want = np.full(len(g), B / top)
            cum = np.cumsum(want); amt = np.clip(EQ - used6 - used5 - (cum - want), 0, want); res1 = amt.sum()
            f = (g.rgap.to_numpy() <= LIM + g.e.to_numpy()) & (amt > 0)
            a, oc, a20 = amt[f], g.oc.to_numpy()[f], g.amt20.to_numpy()[f] * 1e8
            p = a / a20 * 100; fa = a * fill(p)
            pnl1 = float(np.sum(fa * (oc - A.COST - imp(p)) / 100)); fil1 = float(fa.sum()); n1 = int(f.sum())
        rows.append((d, pnl6, pnl5, pnl1, used6, used5, res1, fil1, n1, (used6 + used5 + res1) >= EQ * 0.999))
    R = pd.DataFrame(rows, columns=["d", "p6", "p5", "p1", "u6", "u5", "r1", "f1", "n1", "full"])
    s = A.summ(R.assign(cut=0))
    s.update(r1a=R.r1.mean() / 1e4, r1p=R.r1.quantile(0.9) / 1e4, f1a=R.f1.mean() / 1e4, f1p=R.f1.quantile(0.9) / 1e4,
             n1=R.n1.mean(), pt=R.p1.sum() / max(R.f1.sum(), 1) * 100, y1=s["k1"] * 12)
    return s


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    E, _ = N.live_e()
    T6, T5, _ = A.load(); T1 = N.t1_wide()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
    ctx = ({d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}, T1, days, E, imp, fill)
    P("# [갭 하락 조용주] 위 3개·위 5개 vs 지금 · 1억 · NXT 장전 100만 · NXT 장후 3천만·500만 · 그물 %.1f · 지정가 %.1f · 같은 씨앗 %d" % (NET, LIM, SEEDS))
    P("\n| T1 방식 | 08:53 주문 평균 / 90% | 체결 평균 / 90% | 하루 체결 건 | 건당(체결금 대비) | T1 1년 | 계좌 달 평균(씨앗 ±) / 중앙 | 최악의 달 | 최대 낙폭 | 2025 / 2026 중앙 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    V = [("(a) 지금 · 전부 · 30만×깊이×배율", ("size", 0, 0)), ("(b) 위 3개 · 30만×깊이×배율", ("size", 3, 0))]
    V += [("(c) 위 3개 · 예산 %d만 ÷3" % (B / 1e4), ("bud", 3, B)) for B in (300e4, 600e4, 1000e4, 1500e4)]
    V += [("(d) 위 5개 · 예산 %d만 ÷5" % (B / 1e4), ("bud", 5, B)) for B in (300e4, 600e4, 1000e4, 1500e4)]
    for lab, var in V:
        S = [run(ctx, var, np.random.default_rng(s)) for s in range(SEEDS)]
        m = {k: float(np.mean([x[k] for x in S])) for k in S[0]}; sd = float(np.std([x["mean"] for x in S]))
        P("| %s | %.0f / %.0f만 | %.0f / %.0f만 | %.2f | %+.2f%% | %+.0f만 | %+.0f(±%.0f) / %+.0f | %+.0f | %.0f | %+.0f / %+.0f |" % (
            lab, m["r1a"], m["r1p"], m["f1a"], m["f1p"], m["n1"], m["pt"], m["y1"], m["mean"], sd, m["med"], m["worst"], m["dd"], m["h25"], m["h26"]))
    (ROOT / "day_acct_top3_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
