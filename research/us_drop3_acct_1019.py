"""미장 계좌 — [잔잔한 급등주](N5)·[S&P 편출](N9)·[저PBR 낙폭](N3) 빼면? (2026-10-19 사용자 "세개 빼봤을때 비교해봐")
점검(10-19)에서 지수 대비 약하다고 나온 셋. 빼기 전에 계좌로 확인한다([[contrib-not-removal]]).
틀은 us_drop2_acct.py 그대로: 거래 목록 = us_rules_recheck.py(폐지 포함·지금 정의) · 건당 그때 계좌의 2% · 자리 수 없음 ·
현금 모자라면 그날 남은 신호 못 삼 · 같은 날 순서 무작위 100시드 중앙 · 낙폭은 청산 기준.
지금 사이트 구성 = N1·N3·N5·N6·N8·N9 (N2·N4 는 10-07 뺐다).
    python research/us_drop3_acct_1019.py
"""
import sys, time
from itertools import combinations
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
HOLD = {"N1": 40, "N3": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
NAME = {"N3": "저PBR 낙폭", "N5": "잔잔한 급등주", "N9": "S&P 편출"}
ALL = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
ud = np.array(sorted(pd.read_pickle(BASE / "data/us_full_2007.pkl")["date"].unique()))
DI = {d: i for i, d in enumerate(ud)}
T = []
for rid in HOLD:
    z = ALL[rid].dropna(subset=["ret"]).copy(); z["rid"] = rid
    z["i_in"] = z.date.map(DI) + 1; z["i_out"] = z.date.map(DI) + HOLD[rid]
    T.append(z)
T = pd.concat(T, ignore_index=True)
YRS = sorted(T.date.str[:4].unique())


def sim(Z, lo, hi, seed):
    Z = Z[(Z.date >= lo) & (Z.date <= hi)]
    rng = np.random.default_rng(seed)
    Z = Z.assign(k=rng.random(len(Z))).sort_values(["i_in", "k"])
    eq, cash, pk, mdd, open_ = 1.0, 1.0, 1.0, 0.0, []
    used, n = [], 0
    byday = {d: g for d, g in Z.groupby("i_in")}
    days = sorted(set(Z.i_in) | set(Z.i_out))
    ye = {}   # 해마다 마지막 평가액(청산 기준)
    for d in days:
        keep = []
        for (o, amt, r) in open_:
            if o <= d:
                cash += amt * (1 + r / 100); eq += amt * r / 100
            else: keep.append((o, amt, r))
        open_ = keep
        pk = max(pk, eq); mdd = min(mdd, eq / pk - 1)
        if d in byday:
            for r in byday[d].itertuples():
                amt = 0.02 * eq
                if cash < amt: continue
                cash -= amt; open_.append((r.i_out, amt, r.ret)); n += 1
        used.append(1 - cash / eq if eq > 0 else 0)
        if d < len(ud): ye[ud[d][:4]] = eq
    for (o, amt, r) in open_: eq += amt * r / 100
    yrs = max((len(set(Z.i_in)) and (Z.i_out.max() - Z.i_in.min()) / 252), 1e-9)
    return eq, eq ** (1 / yrs) - 1, mdd, np.mean(used), n, ye


CASES = [("다 씀(지금)", set())] + [("[%s] 뺌" % NAME[k], {k}) for k in ("N5", "N9", "N3")] \
    + [("[%s]·[%s] 뺌" % (NAME[a], NAME[b]), {a, b}) for a, b in combinations(("N5", "N9", "N3"), 2)] + [("셋 다 뺌", {"N3", "N5", "N9"})]

P("# 미장 계좌 — [잔잔한 급등주]·[S&P 편출]·[저PBR 낙폭] 빼기 · %s" % time.strftime("%Y-%m-%d")); P("")
P("- 건당 그때 계좌의 2% · 자리 수 없음 · 현금 모자라면 못 삼 · 같은 날 순서 무작위 100시드 중앙 · 청산 기준 낙폭"); P("")
YR = {}
for lab, lo, hi in (("2016~", "20160101", "20991231"), ("2023~", "20230101", "20991231"), ("2009~15", "20090101", "20151231")):
    P("## %s" % lab)
    P("| 구성 | 산 건수 | 최종 배수 | 연수익 | 최대 낙폭 | 평균 투자 비중 | 지금 대비 | 지금보다 나은 시드 |"); P("|---|---|---|---|---|---|---|---|")
    base = None
    for nm, drop in CASES:
        Z = T[~T.rid.isin(drop)]
        R = [sim(Z, lo, hi, s) for s in range(100)]
        A = np.array([r[:5] for r in R])
        if base is None: base = A[:, 0]
        if lab == "2016~":
            YR[nm] = {y: np.median([r[5].get(y, np.nan) for r in R]) for y in YRS if y >= "2016"}
        better = (A[:, 0] > base).mean() * 100
        P("| %s | %d | %.2f배 | %+.1f%% | %.1f%% | %.0f%% | %s | %s |" % (nm, int(np.median(A[:, 4])), np.median(A[:, 0]), np.median(A[:, 1]) * 100,
          np.median(A[:, 2]) * 100, np.median(A[:, 3]) * 100, "—" if not drop else "%+.2f배" % (np.median(A[:, 0]) - np.median(base)), "—" if not drop else "%.0f%%" % better))
    P("")
P("## 해마다 수익(2016~ 계좌, 시드 중앙)")
ys = [y for y in YRS if y >= "2016"]
P("| 구성 | " + " | ".join(ys) + " | 손실 난 해 |"); P("|---" * (len(ys) + 2) + "|")
for nm, _ in CASES:
    v = YR[nm]; prev = 1.0; cells = []; neg = 0
    for y in ys:
        e = v.get(y, np.nan)
        if np.isnan(e): cells.append("-"); continue
        r = (e / prev - 1) * 100; prev = e; neg += r < 0; cells.append("%+.1f" % r)
    P("| %s | %s | %d |" % (nm, " | ".join(cells), neg))
(ROOT / "reports" / ("us_drop3_acct_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
