# -*- coding: utf-8 -*-
"""스윙 규칙에 '잔잔하다 아래로 깨진 종목 빼기' 거르개 — 2026-11-16 사용자 "응 해봐"(quiet_break_1112 의 회피 재료를 스윙 낙폭 규칙에).
거래 = C:/temp/kp/port_sig.pkl(portfolio.py 9규칙 신호표, 비용 뒤 · mix_swing_1114) · 표시 = quiet_break_1112.build() 재료로 신호 날까지 5거래일 안에
  잔잔(직전 L일 |등락|≤1% 비율 ≥ q)하다 아래로 깨짐(오늘 처음 > m% 하락 또는 3일 중 2일 깨지고 3일 합 < -m%) 이 한 번이라도 있었나.
판 4개: 넓게(60일·80%·1%) · 보통(60일·80%·2%) · 좁게(120일·90%·2%) · 3일 중 2일만(120일·90%·2%).
보는 것: 규칙별 걸린 비율 · 걸린 거래 vs 나머지 건당(학습 2016~22 · 검증 2023~) · 계좌(portfolio.py 자리·비중·우선순위, 1억, 체결 손해 0.143+1.321√p) 연수익 — 빼면 학습·검증 둘 다 늘어야 후보.
    python research/memguard.py research/qb_filter_1112.py
"""
import math, pickle, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import quiet_break_1112 as Q

OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
VARS = {"넓게 60일·80%·1%": (60, 0.8, "any", 1.0), "보통 60일·80%·2%": (60, 0.8, "any", 2.0),
        "좁게 120일·90%·2%": (120, 0.9, "any", 2.0), "3일 중 2일 120일·90%·2%": (120, 0.9, "B3", 2.0)}
# 11-16 첫 판: 신호 날까지 5거래일 안이면 9규칙 7,538건 중 10건만 걸림 — 낙폭 규칙은 몇 주 빠진 뒤 신호라 처음 깨진 날이 더 앞 → 20·60거래일 안으로 넓힌 판
WINS = (5, 20, 60)


def flags():
    D = Q.build(Q.load())
    out = D[["ticker", "date"]].copy()
    for nm, (L, q, B, m) in VARS.items():
        b1 = (D["q%d_1" % L] >= q) & (D.calm5_1 >= 1) & (D.change < -m)
        b3 = (D["q%d_3" % L] >= q) & (D.calm5_3 >= 1) & (D.out3 >= 2) & (D.r3 < -m)
        f = (b3 if B == "B3" else (b1 | b3)).astype("int8")
        for w in WINS:
            out["%s · %d일 안" % (nm, w)] = f.groupby(D.ticker).transform(lambda s: s.rolling(w, min_periods=1).max()).astype("int8")   # 신호 날까지 w거래일 안
    return out


def main():
    Z = pickle.load(open(r"C:\temp\kp\port_sig.pkl", "rb")); S = Z["S"].copy(); dates = Z["dates"]; DI = {d: i for i, d in enumerate(dates)}
    S["date"] = S.date.astype(str); S["ticker"] = S.ticker.astype(str)
    S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    S = S[S.date >= "20160101"].reset_index(drop=True)
    F = flags()
    X = S.merge(F, on=["ticker", "date"], how="left")
    NAMES = ["%s · %d일 안" % (nm, w) for nm in VARS for w in WINS]
    for nm in NAMES: X[nm] = X[nm].fillna(0).astype("int8")
    X = X.sort_values("di").reset_index(drop=True)
    imp = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))

    def acct(drop, C=1e8, d0="20160101", d1="20221231"):
        i0 = DI[min(d for d in dates if d >= d0)]; i1 = DI[max(d for d in dates if d <= d1)]
        Y = X[(X.di >= i0) & (X.di <= i1) & ~drop]
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
                pos.append((t.rid, w, i + t.hold, t.ret - imp(pi), t.ticker)); inv += w
        for p in pos: eq += p[1] * p[3] / 100
        return ((eq / C) ** (250 / (i1 - i0 + 1)) - 1) * 100

    none = pd.Series(False, index=X.index)
    base_l, base_v = acct(none), acct(none, d0="20230101", d1="20261031")
    P("국장 스윙 9규칙 2016~ %d건 · 지금 계좌(1억) 연수익 학습 %+.1f%% · 검증 %+.1f%%\n" % (len(X), base_l, base_v))
    L_, V_ = X.date < "20230101", X.date >= "20230101"
    for nm in NAMES:
        f = X[nm] == 1
        if f.sum() < 20: P("## %s — 걸린 거래 %d건뿐(생략)" % (nm, f.sum())); continue
        P("## %s — 걸린 거래 %d건(%.1f%%)\n" % (nm, f.sum(), f.mean() * 100))
        P("| 규칙 | 걸림 | 걸린 건당 학습 / 검증 | 나머지 건당 학습 / 검증 |"); P("|---|---|---|---|")
        for rid, g in X.groupby("rid"):
            gf = g[nm] == 1
            m = lambda sel: ("%+.2f%%(%d)" % (g[sel].ret.mean(), sel.sum())) if sel.sum() else "-"
            P("| %s | %d (%.0f%%) | %s / %s | %s / %s |" % (rid, gf.sum(), gf.mean() * 100, m(gf & (g.date < "20230101")), m(gf & (g.date >= "20230101")),
                                                     m(~gf & (g.date < "20230101")), m(~gf & (g.date >= "20230101"))))
        al, av = acct(f), acct(f, d0="20230101", d1="20261031")
        P("\n전 규칙에서 빼면 계좌 연수익: 학습 %+.1f%% → %+.1f%% (%+.1f) · 검증 %+.1f%% → %+.1f%% (%+.1f)" % (base_l, al, al - base_l, base_v, av, av - base_v))
        for rid in ("P3", "P6", "D1", "D2", "P4", "P5"):
            fr = f & (X.rid == rid)
            if fr.sum() < 5: continue
            rl, rv = acct(fr), acct(fr, d0="20230101", d1="20261031")
            P("  %s 에서만 빼면: 학습 %+.1f (%+.2f) · 검증 %+.1f (%+.2f)" % (rid, rl, rl - base_l, rv, rv - base_v))
        P("")
    (ROOT / "qb_filter_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
