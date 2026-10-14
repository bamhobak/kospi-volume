# -*- coding: utf-8 -*-
"""frgn_own.py 후속 — 후보 셋 연도별 + 주식 수 증가(증자·CB 전환으로 비율만 떨어짐) 갈라보기 (H0334).
    python research/frgn_own2.py   (frgn_own.py 먼저)
"""
import sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import common as C

BASE = C.BASE
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
U = pd.read_pickle(BASE / "research" / "cache" / "frgn_own.pkl")
fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
S = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "shares", "foreign_ratio"], dtype={"ticker": str, "date": str}) for f in fs if Path(f).stem >= "2009-01"], ignore_index=True)
S = S.sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"])
g = S.groupby("ticker", sort=False)
S["fsh"] = S.foreign_ratio * S.shares / 100
S["sh10"] = (S.shares / g.shares.shift(10) - 1) * 100          # 10일 주식 수 변화
S["fsh10"] = (S.fsh / g.fsh.shift(10) - 1) * 100               # 10일 외국인 보유 주식 수 변화
for c in ("sh10", "fsh10"): S[c] = g[c].shift(1)
U = U.merge(S[["ticker", "date", "sh10", "fsh10"]], on=["ticker", "date"], how="left")
U["yr"] = U.date.str[:4]
U["prev_up"] = U.groupby("ticker").upstk.shift(1)


def yrs(m, h):
    x = U.loc[m, ["yr", "x_" + h]].dropna()
    t = x.groupby("yr")["x_" + h].agg(["mean", "size"])
    pos = (t["mean"] > 0).sum()
    return t, pos, len(t)


CAND = [
    ("A 비중 10일↑ 연속 감소", U.dnstk >= 10),
    ("A1  └ 주식 수 그대로(10일 +0.5% 미만)", (U.dnstk >= 10) & (U.sh10 < 0.5)),
    ("A2  └ 주식 수 늘어남(증자·CB, +0.5%↑)", (U.dnstk >= 10) & (U.sh10 >= 0.5)),
    ("B 60일 비중 상위10% & 최근 5일 감소(눌림)", (U.q_d60 >= 0.9) & (U.d5 < 0)),
    ("C 20일 비중 급감 하위5%", U.q_d20 <= 0.05),
    ("C1  └ 주식 수 그대로", (U.q_d20 <= 0.05) & (U.sh10 < 0.5)),
    ("D 비중 수준 하위20%(회피 후보)", U.q_fr <= 0.2),
    ("E 비중 수준 상위20%", U.q_fr >= 0.8),
]
P("## 후보별 — 같은 날 유니버스 대비 초과(%) · 연도 중 플러스 해 수")
P("| 후보 | 20일 옛날/학습/검증 | 20일 +해 | 60일 옛날/학습/검증 | 60일 +해 |"); P("|---|---|---|---|---|")
PER = [("20100101", "20151231"), ("20160101", "20221231"), ("20230101", "20991231")]
for nm, m in CAND:
    row = [nm]
    for h in ("sw20", "sw60"):
        cs = []
        for a, b in PER:
            x = U.loc[m & (U.date >= a) & (U.date <= b), "x_" + h].dropna()
            cs.append("%+.2f(%d)" % (x.mean(), len(x)) if len(x) >= 30 else "-")
        _, pos, n = yrs(m, h)
        row += ["/".join(cs), "%d/%d" % (pos, n)]
    P("| %s |" % " | ".join(row))

P("\n## 연도별 20일 초과(%) — A1 · B · C1 · D")
keys = [("A1", CAND[1][1]), ("B", CAND[3][1]), ("C1", CAND[5][1]), ("D", CAND[6][1])]
tabs = {k: yrs(m, "sw20")[0] for k, m in keys}
P("| 해 | " + " | ".join(k for k, _ in keys) + " |"); P("|---" * (len(keys) + 1) + "|")
for y in sorted(U.yr.unique()):
    P("| %s | %s |" % (y, " | ".join("%+.2f(%d)" % (tabs[k].loc[y, "mean"], tabs[k].loc[y, "size"]) if y in tabs[k].index else "-" for k, _ in keys)))

# 중복신호 함정: 같은 종목 연속 날 신호 → 첫날만(20거래일 안 재신호 제외)
P("\n## 중복 걷어냄(같은 종목 20거래일 안 재신호 빼고 첫날만) — 20/60일 초과")
P("| 후보 | 20일 옛날/학습/검증 | 60일 옛날/학습/검증 | 연평균 건수 |"); P("|---|---|---|---|")
U["ix"] = U.groupby("ticker").cumcount()
for nm, m in CAND[:6]:
    sub = U.loc[m, ["ticker", "ix"]]
    keep = []
    last = {}
    for i, (tk, ix) in zip(sub.index, sub.values):
        if tk in last and ix - last[tk] < 20: continue
        last[tk] = ix; keep.append(i)
    mm = U.index.isin(keep)
    cs = []
    for h in ("sw20", "sw60"):
        c2 = []
        for a, b in PER:
            x = U.loc[mm & (U.date >= a) & (U.date <= b), "x_" + h].dropna()
            c2.append("%+.2f(%d)" % (x.mean(), len(x)) if len(x) >= 30 else "-")
        cs.append("/".join(c2))
    P("| %s | %s | %s | %.0f |" % (nm, cs[0], cs[1], mm.sum() / U.yr.nunique()))
(BASE / "research" / "cache" / "frgn_own2.out").write_text("\n".join(OUT), encoding="utf-8")
