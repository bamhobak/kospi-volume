# -*- coding: utf-8 -*-
"""미장 계좌 — [낙폭과대]·[자사주 낙폭] 빼면? (2026-10-07 사용자 "빼는 게 맞는 것 같아", [[contrib-not-removal]] 확인)
거래 목록 = us_rules_recheck.py(폐지 포함·지금 정의). 계좌 = 지금 자동매매 방식: 처음 시드 1.0 · 건당 시드의 2%(자리 수 없음) ·
현금이 모자라면 그날 신호 중 남은 건 못 산다(같은 날 순서는 무작위 → 100시드 중앙) · 청산 때 손익 반영 · 낙폭은 청산 기준(실제보다 작다).
건당 금액은 '그때 계좌의 2%' (복리) — 고정 금액이면 빼는 효과가 계좌 크기에 묻혀 잘 안 보인다.
기간: 2016~ 와 2009~15 따로 · 비교: 다 씀 / 낙폭과대 뺌 / 자사주 낙폭 뺌 / 둘 다 뺌.
    python research/us_drop2_acct.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
HOLD = {"N1": 40, "N2": 20, "N3": 60, "N4": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
NAME = {"N2": "낙폭과대", "N4": "자사주 낙폭"}
ALL = pd.read_pickle(ROOT / "cache" / "us_rules_recheck.pkl")
ud = np.array(sorted(pd.read_pickle(BASE / "data/us_full_2007.pkl", )["date"].unique()))
DI = {d: i for i, d in enumerate(ud)}
T = []
for rid, z in ALL.items():
    z = z.dropna(subset=["ret"]).copy(); z["rid"] = rid
    z["i_in"] = z.date.map(DI) + 1; z["i_out"] = z.date.map(DI) + HOLD[rid]
    T.append(z)
T = pd.concat(T, ignore_index=True)


def sim(Z, lo, hi, seed):
    Z = Z[(Z.date >= lo) & (Z.date <= hi)]
    rng = np.random.default_rng(seed)
    Z = Z.assign(k=rng.random(len(Z))).sort_values(["i_in", "k"])
    eq, cash, pk, mdd, open_ = 1.0, 1.0, 1.0, 0.0, []
    used, n = [], 0
    byday = {d: g for d, g in Z.groupby("i_in")}
    days = sorted(set(Z.i_in) | set(Z.i_out))
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
    for (o, amt, r) in open_: eq += amt * r / 100
    yrs = max((len(set(Z.i_in)) and (Z.i_out.max() - Z.i_in.min()) / 252), 1e-9)
    return eq, eq ** (1 / yrs) - 1, mdd, np.mean(used), n


P("# 미장 계좌 — [낙폭과대]·[자사주 낙폭] 빼기 · %s" % time.strftime("%Y-%m-%d")); P("")
P("- 건당 그때 계좌의 2% · 자리 수 없음 · 현금 모자라면 못 삼 · 같은 날 순서 무작위 100시드 중앙 · 청산 기준 낙폭"); P("")
P("| 기간 | 구성 | 산 건수 | 최종 배수 | 연수익 | 최대 낙폭(청산 기준) | 평균 투자 비중 | 다 씀 대비 배수 | 다 씀보다 나은 시드 |"); P("|---|---|---|---|---|---|---|---|---|")
for lab, lo, hi in (("2016~", "20160101", "20991231"), ("2009~15", "20090101", "20151231")):
    base = None
    for nm, drop in (("다 씀", set()), ("[낙폭과대] 뺌", {"N2"}), ("[자사주 낙폭] 뺌", {"N4"}), ("둘 다 뺌", {"N2", "N4"})):
        Z = T[~T.rid.isin(drop)]
        R = np.array([sim(Z, lo, hi, s) for s in range(100)])
        if base is None: base = R[:, 0]
        better = (R[:, 0] > base).mean() * 100 if drop else np.nan
        P("| %s | %s | %d | %.2f배 | %+.1f%% | %.1f%% | %.0f%% | %s | %s |" % (lab, nm, int(np.median(R[:, 4])), np.median(R[:, 0]), np.median(R[:, 1]) * 100,
          np.median(R[:, 2]) * 100, np.median(R[:, 3]) * 100, "—" if not drop else "%+.2f배" % (np.median(R[:, 0]) - np.median(base)), "—" if not drop else "%.0f%%" % better))
P("")
(ROOT / "reports" / ("us_drop2_acct_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
