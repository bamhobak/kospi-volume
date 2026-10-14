# -*- coding: utf-8 -*-
"""외국인 보유 비중(지분율) 늘고 줄고 중심 규칙 찾기 (2026-10-14 사용자 "외국인 비중 늘어나고 줄어들고를 중점으로 규칙 찾아봐") — H0334.

예전 기각(H 없음·09-01 flow-5week · 09-05 지분율 반토막·차익거래×지분율)은 순매수 조합 위주 → 여기선 **보유 비중 흐름 자체**를 넓게 훑는다.
자료: 월별 CSV(data/YYYY-MM.csv) foreign_ratio 일별(2005~) · 공장 패널 lab.hist(유니버스 = 거래대금 상위 40%, oc·sw5/10/20/40/60 비용 포함)
신호는 **전날 마감 기준**(재료를 하루 미룸) → 그날 시가 매수(oc = 그날 종가 매도 · swH = H거래일 보유).
초과 = 같은 날 유니버스 아무 종목 같은 보유 평균을 뺀 값. 옛날 10~15 · 학습 16~22 · 검증 23~.
    python research/frgn_own.py
"""
import sys, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

BASE = C.BASE
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))

fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
F = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "foreign_ratio", "close"], dtype={"ticker": str, "date": str}) for f in fs if Path(f).stem >= "2009-01"], ignore_index=True)
F = F[F.foreign_ratio.notna()].sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"])
F.loc[(F.foreign_ratio < 0) | (F.foreign_ratio > 100), "foreign_ratio"] = np.nan
g = F.groupby("ticker", sort=False).foreign_ratio
fr = F.foreign_ratio
for k in (5, 20, 60, 120):
    F["d%d" % k] = fr - g.shift(k)
F["hi250"] = g.transform(lambda s: s.rolling(250, min_periods=120).max())
F["lo250"] = g.transform(lambda s: s.rolling(250, min_periods=120).min())
F["pos250"] = (fr - F.lo250) / (F.hi250 - F.lo250).replace(0, np.nan)
up = (fr > g.shift(1)).astype(int)
grp = (up != up.groupby(F.ticker).shift()).cumsum()
F["upstk"] = up.groupby([F.ticker, grp]).cumsum() * up
dn = (fr < g.shift(1)).astype(int)
grp2 = (dn != dn.groupby(F.ticker).shift()).cumsum()
F["dnstk"] = dn.groupby([F.ticker, grp2]).cumsum() * dn
F["pr20"] = (F.close / F.groupby("ticker").close.shift(20) - 1) * 100
F["fr"] = fr
FE = ["fr", "d5", "d20", "d60", "d120", "pos250", "upstk", "dnstk", "pr20"]
# 하루 미룸(전날 마감까지 아는 값)
for c in FE: F[c] = F.groupby("ticker", sort=False)[c].shift(1)
F.loc[F.d5.abs() > 20, ["d5", "d20", "d60", "d120"]] = np.nan          # 자료 오류(지분율 급변) 제거

U = lab.hist()
U = U[U.date >= "20100101"][["ticker", "date", "oc", "sw5", "sw20", "sw60", "liq", "q_vm", "gap"]].copy()
U = U.merge(F[["ticker", "date"] + FE], on=["ticker", "date"], how="left")
U = U[U.fr.notna()].reset_index(drop=True)
U["oc"] = U.oc.clip(-60, 60) - FT.COST
H = ["oc", "sw5", "sw20", "sw60"]
for h in H:
    U[h] = U[h].clip(-90, 300)
    U["x_" + h] = U[h] - U.groupby("date")[h].transform("mean")
for c in ["d5", "d20", "d60", "d120", "fr", "pos250"]:
    U["q_" + c] = U[c].groupby(U.date).rank(pct=True)
PER = [("옛날", "20100101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]
P("유니버스 줄 %d · 외인 비중 있는 줄 · %s~%s" % (len(U), U.date.min(), U.date.max()))


def cell(m, h):
    out = []
    for nm, a, b in PER:
        x = U.loc[m & (U.date >= a) & (U.date <= b), "x_" + h].dropna()
        out.append("%+.2f(%d)" % (x.mean(), len(x)) if len(x) >= 30 else "-")
    return out


P("\n## 1. 한 축씩 — 10분위(같은 날 유니버스 안 순위) · 같은 날 대비 초과(%) 옛날/학습/검증")
for c in ["d5", "d20", "d60", "d120", "fr", "pos250"]:
    P("\n### %s" % {"d5": "5일 비중 변화(%p)", "d20": "20일 변화", "d60": "60일 변화", "d120": "120일 변화", "fr": "비중 수준", "pos250": "1년 범위 안 위치"}[c])
    P("| 분위 | 시가→종가 | 5일 | 20일 | 60일 |"); P("|---|---|---|---|---|")
    for lo in np.arange(0, 1, 0.1):
        m = (U["q_" + c] > lo) & (U["q_" + c] <= lo + 0.1)
        P("| %d~%d%% | %s |" % (lo * 100, lo * 100 + 10, " | ".join("/".join(cell(m, h)) for h in H)))

P("\n## 2. 흐름 모양 후보 — 초과(%) 옛날/학습/검증(건수)")
P("| 후보 | 시가→종가 | 5일 | 20일 | 60일 |"); P("|---|---|---|---|---|")
CAND = [
    ("비중 1년 신고점 & 주가 20일 하락(매집 괴리)", (U.pos250 >= 0.98) & (U.pr20 < 0)),
    ("비중 1년 신고점 & 주가 20일 상승", (U.pos250 >= 0.98) & (U.pr20 > 0)),
    ("60일 크게 증가(상위10%) & 최근 5일 감소(눌림)", (U.q_d60 >= 0.9) & (U.d5 < 0)),
    ("60일 크게 증가(상위10%) & 최근 5일도 증가", (U.q_d60 >= 0.9) & (U.d5 > 0)),
    ("20일 급감(하위5%) — 매도 소진?", U.q_d20 <= 0.05),
    ("20일 급감(하위5%) & 최근 5일 증가 전환", (U.q_d20 <= 0.05) & (U.d5 > 0)),
    ("120일 감소(하위20%) & 5일 증가(상위20%) — 장기 이탈 뒤 복귀", (U.q_d120 <= 0.2) & (U.q_d5 >= 0.8)),
    ("비중 1% 미만 & 20일 +0.5%p↑ — 외인 첫 진입", (U.fr < 1) & (U.d20 >= 0.5)),
    ("20일 비중 +1%p↑ & 주가 20일 ≤ 0(아직 안 오름)", (U.d20 >= 1) & (U.pr20 <= 0)),
    ("20일 비중 +1%p↑ & 주가 20일 > +10%(이미 오름)", (U.d20 >= 1) & (U.pr20 > 10)),
    ("비중 10일↑ 연속 증가", U.upstk >= 10),
    ("비중 10일↑ 연속 감소", U.dnstk >= 10),
    ("비중 연속 증가 10일↑ 끝난 첫날(오늘 감소)", (U.upstk == 0) & (U.groupby("ticker").upstk.shift(1) >= 10)),
    ("작은 쪽(유동성 아래 1/3) & 20일 비중 상위10%", (U.liq <= 1 / 3) & (U.q_d20 >= 0.9)),
    ("큰 쪽(유동성 위 1/3) & 20일 비중 상위10%", (U.liq >= 2 / 3) & (U.q_d20 >= 0.9)),
]
for nm, m in CAND:
    P("| %s | %s |" % (nm, " | ".join("/".join(cell(m, h)) for h in H)))

P("\n## 3. [갭 하락 조용주](T1) 덧조건 — 외인 비중 흐름별 T1 시가→종가(비용 뒤, 절대값)")
T1 = lab.hist()[["ticker", "date", "t1"]]
U = U.merge(T1, on=["ticker", "date"], how="left")
t1 = U.t1.fillna(False).astype(bool)
P("| T1 & | 옛날 | 학습 | 검증 |"); P("|---|---|---|---|")
for nm, m in (("전체", t1), ("20일 비중 증가(>0)", t1 & (U.d20 > 0)), ("20일 비중 감소(<0)", t1 & (U.d20 < 0)),
              ("60일 비중 상위30%", t1 & (U.q_d60 >= 0.7)), ("60일 비중 하위30%", t1 & (U.q_d60 <= 0.3)),
              ("5일 비중 감소(외인이 판 갭하락)", t1 & (U.d5 < 0)), ("5일 비중 증가", t1 & (U.d5 > 0))):
    out = []
    for _, a, b in PER:
        x = U.loc[m & (U.date >= a) & (U.date <= b), "oc"].dropna()
        out.append("%d건 %+.2f%% · %.0f%%" % (len(x), x.mean(), (x > 0).mean() * 100) if len(x) else "-")
    P("| %s | %s |" % (nm, " | ".join(out)))
(BASE / "research" / "cache" / "frgn_own.out").write_text("\n".join(OUT), encoding="utf-8")
U.to_pickle(BASE / "research" / "cache" / "frgn_own.pkl")
