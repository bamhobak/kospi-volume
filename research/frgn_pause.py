# -*- coding: utf-8 -*-
"""외국인 연속 매수 뒤 주춤 (2026-10-12 사용자: "반대로 외국인 매수가 쭉 있다가 주춤한 거 사서 매도하는 건 어때? 데이랑 스윙 둘 다").

신호(장 전에 아는 것만 — 수급은 어제까지)
  쭉 사다 = 그제까지 외국인 순매수(금액) k 거래일 연속 (k = 3·5·7)
  주춤   = ⓐ 어제 순매도로 돌아섬  ⓑ 어제도 샀지만 비중(fw = 순매수 ÷ 5일 거래대금)이 연속 구간 평균의 30% 미만
데이  = 오늘 시가 → 종가 (비용 0.23)
스윙  = 오늘 시가 → 5·10·20 거래일 보유(공장 패널 sw, 비용 포함) · 초과 = 같은 날 유니버스 아무 종목 같은 보유 평균을 뺀 값
유니버스 = 거래대금 20일 상위 40%(공장 패널). 학습 2018~22 · 검증 2023~.
    python research/frgn_pause.py
"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

BASE = C.BASE
U = lab.hist()
U = U[U.oc.notna() & (U.date >= "20180115")][["ticker", "date", "oc", "liq", "gap", "r1", "sw5", "sw10", "sw20"]].copy()
A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
A = A[A.date >= "20171101"][["ticker", "date", "close", "volume"]].sort_values(["ticker", "date"])
con = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "investor.db"), uri=True)
A = A.merge(pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20171101'", con), on=["ticker", "date"], how="left")
g = A.groupby("ticker", sort=False)
A["amt5"] = (A.close * A.volume).groupby(A.ticker).transform(lambda s: s.rolling(5, min_periods=5).sum())
A["fw"] = A.frgn / A.amt5 * 100
pos = (A.frgn > 0).astype(int)
grp = (pos != pos.groupby(A.ticker).shift()).cumsum()
A["run"] = pos.groupby([A.ticker, grp]).cumsum() * pos                          # 그날까지 연속 순매수 일수
# 연속 구간 평균 비중(그날까지)
A["fwpos"] = A.fw.where(pos == 1)
A["runmean"] = A.fwpos.groupby([A.ticker, grp]).transform(lambda s: s.expanding().mean())
for k, c in (("run_yy", "run"), ("runmean_yy", "runmean"), ("fw_y", "fw"), ("frgn_y", "frgn")):
    A[k] = g[c].shift(2 if k.endswith("_yy") else 1)
U = U.merge(A[["ticker", "date", "run_yy", "runmean_yy", "fw_y", "frgn_y"]], on=["ticker", "date"], how="left")
U["ret"] = U.oc.clip(-60, 60) - FT.COST
for h in (5, 10, 20):
    c = "sw%d" % h
    U[c] = U[c].clip(-90, 300)
    U["x%d" % h] = U[c] - U.date.map(U.groupby("date")[c].mean())               # 같은 날 아무 종목 대비 초과
has = U.run_yy.notna() & U.fw_y.notna()
sell_y = U.frgn_y <= 0
shrink_y = (U.frgn_y > 0) & (U.fw_y < 0.3 * U.runmean_yy)
TR, VA = ("20180115", "20221231"), lab.VA


def f(s):
    return ("%6d %+6.2f %4.1f%% t%5.1f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "     0      -"


def st(m, col, a, b):
    return lab.stats(U.loc[m & (U.date >= a) & (U.date <= b) & U[col].notna(), ["date", col]].rename(columns={col: "ret"}))


def row(nm, m):
    print("%-40s | 데이 학습 %s | 검증 %s" % (nm[:40], f(st(m, "ret", *TR)), f(st(m, "ret", *VA))))
    for h in (5, 10, 20):
        a, b = st(m, "x%d" % h, *TR), st(m, "x%d" % h, *VA)
        ra, rb = st(m, "sw%d" % h, *TR), st(m, "sw%d" % h, *VA)
        print("%-40s |   %2d일 보유 학습 %+6.2f%%(초과 %+5.2f, 승률 %4.1f%%) | 검증 %+6.2f%%(초과 %+5.2f, 승률 %4.1f%%)" % (
            "", h, ra["mean"] if ra else np.nan, a["mean"] if a else np.nan, ra["win"] if ra else np.nan,
            rb["mean"] if rb else np.nan, b["mean"] if b else np.nan, rb["win"] if rb else np.nan))
    print(flush=True)


print("유니버스 줄 %d · 수급 있는 줄 %d\n" % (len(U), has.sum()))
row("[대조] 유니버스 아무 종목", has)
for k in (3, 5, 7):
    row("그제까지 %d일↑ 연속 매수 · 어제 순매도(주춤)" % k, has & (U.run_yy >= k) & sell_y)
    row("그제까지 %d일↑ 연속 매수 · 어제 확 줄어듦" % k, has & (U.run_yy >= k) & shrink_y)
row("[비교] 5일↑ 연속 매수 · 어제도 계속 삼(주춤 없음)", has & (U.run_yy >= 5) & (U.frgn_y > 0) & ~shrink_y)
k5 = has & (U.run_yy >= 5) & sell_y
row("5일↑·어제 순매도 & 어제 주가 하락", k5 & (U.r1 < 0))
row("5일↑·어제 순매도 & 오늘 갭 하락", k5 & (U.gap < 0))
row("5일↑·어제 순매도 & 유니버스 아래 절반", k5 & (U.liq <= 0.5))
row("5일↑·어제 순매도 & 유니버스 위 절반", k5 & (U.liq > 0.5))
