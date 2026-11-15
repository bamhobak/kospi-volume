# -*- coding: utf-8 -*-
"""미장 스윙 규칙에 '잔잔하다 아래로 깨진 종목 빼기' — qb_filter_1112 의 미장판(2026-11-16).
거래 = research/cache/us_rules_recheck.pkl(10-07 정의 · ret 비용 뒤 · idx 같은 보유기간 S&P) — 살아 있는 규칙 N1·N3·N5·N6·N8·N9.
표시 = quiet_break_1112.build() 를 거래에 나온 종목만(묶음) — 신호 날까지 5거래일 안에 잔잔하다 아래로 깨짐.
계좌 틀이 없어 걸린 거래 vs 나머지 지수 대비(학습 2016~22 · 검증 2023~)와 '빼면 남는 거래 건당'만 본다.
    python research/memguard.py research/qb_filter_us_1112.py
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import quiet_break_1112 as Q
import quiet_break_us_1112 as QU
import qb_filter_1112 as QF

OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
LIVE = ("N1", "N3", "N5", "N6", "N8", "N9")


def main():
    A = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
    T = pd.concat([v.assign(rid=k) for k, v in A.items() if k in LIVE], ignore_index=True)
    T["date"] = T.date.astype(str); T["ex"] = T.ret - T.idx
    T = T[T.date >= "20160101"]
    need = set(T.ticker)
    fl = []
    for D in QU.batches():
        D = D[D.ticker.isin(need)]
        if not len(D): continue
        D = Q.build(D.reset_index(drop=True))
        out = D[["ticker", "date"]].copy()
        for nm, (L, q, B, m) in QF.VARS.items():
            b1 = (D["q%d_1" % L] >= q) & (D.calm5_1 >= 1) & (D.change < -m)
            b3 = (D["q%d_3" % L] >= q) & (D.calm5_3 >= 1) & (D.out3 >= 2) & (D.r3 < -m)
            f = (b3 if B == "B3" else (b1 | b3)).astype("int8")
            out[nm] = f.groupby(D.ticker).transform(lambda s: s.rolling(5, min_periods=1).max()).astype("int8")
        fl.append(out[out.set_index(["ticker", "date"]).index.isin(list(zip(T.ticker, T.date)))])
    F = pd.concat(fl, ignore_index=True).drop_duplicates(["ticker", "date"])
    X = T.merge(F, on=["ticker", "date"], how="left")
    for nm in QF.VARS: X[nm] = X[nm].fillna(0).astype("int8")
    P("미장 스윙 %d규칙 2016~ %d건(표시 붙은 것 %d)\n" % (len(LIVE), len(X), len(F)))
    for nm in QF.VARS:
        P("## %s\n" % nm)
        P("| 규칙 | 걸림 | 걸린 지수 대비 학습 / 검증 | 나머지 지수 대비 학습 / 검증 | 빼면 남는 건당(전체) |"); P("|---|---|---|---|---|")
        for rid, g in X.groupby("rid"):
            f = g[nm] == 1
            m = lambda sel: ("%+.2f%%p(%d)" % (g[sel].ex.mean(), sel.sum())) if sel.sum() else "-"
            P("| %s | %d (%.0f%%) | %s / %s | %s / %s | %+.2f%% → %+.2f%% |" % (rid, f.sum(), f.mean() * 100, m(f & (g.date < "20230101")), m(f & (g.date >= "20230101")),
                                                                m(~f & (g.date < "20230101")), m(~f & (g.date >= "20230101")), g.ret.mean(), g[~f].ret.mean()))
        P("")
    (ROOT / "qb_filter_us_1112.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
