# -*- coding: utf-8 -*-
"""외국인 매수 비중 상승 + 거래량 하위 50% (2026-10-12 사용자):
"거래량 하위 50% 종목 중 일주일 거래량 대비 어제 외국인 매수 비중이 올라간 것 — 시가 매수 → 종가 매도,
 혹은 장 시작 후 3분봉 기준 연속 3번 오르면 매수 → 점심시간이나 종가에 매도".

정의
  거래량 하위 50% = 유니버스(거래대금 20일 상위 40%) 안의 아래 절반(liq ≤ 0.5)
  비중 fw = 어제 외국인 순매수 금액 ÷ 최근 5거래일(어제까지) 거래대금 합 × 100   (flow11 2018~)
  올라감 = fw(어제) > fw(그제)
  A 시가 매수 → 종가 (비용 0.23)
  B 09:00 부터 3분봉: 봉1 종가 > 시가, 봉2 > 봉1, 봉3 > 봉2 (11:30 전) → 봉3 종가에 매수(+0.05 미끄러짐) → 12:00 또는 종가 매도
     1분봉 2022-12~ · 비교 = 같은 날 거래량 하위 50% 아무 종목의 같은 3분봉 신호(외국인 조건 없이, 표본)
학습 2018~22(A) / 2022-12~24(B) · 검증 2023~(A) / 2025~(B)
    python research/frgn_ratio.py
"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import lab, feats as FT, common as C
import m1_event as ME

BASE = C.BASE
U = lab.hist()
U = U[U.oc.notna() & (U.date >= "20180110")][["ticker", "date", "oc", "liq", "q_vm", "gap", "mk_r1"]].copy()
A = pd.read_pickle(BASE / "data" / "kr_scan.pkl")
A = A[A.date >= "20171201"][["ticker", "date", "close", "volume"]].sort_values(["ticker", "date"])
con = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "investor.db"), uri=True)
Fl = pd.read_sql("SELECT ticker, date, frgn FROM flow11 WHERE date >= '20171201'", con)
A = A.merge(Fl, on=["ticker", "date"], how="left")
g = A.groupby("ticker", sort=False)
A["amt"] = A.close * A.volume
A["amt5"] = g.amt.transform(lambda s: s.rolling(5, min_periods=5).sum())
A["fw"] = A.frgn / A.amt5 * 100
A["fw_y"] = g.fw.shift(1); A["fw_yy"] = g.fw.shift(2)
U = U.merge(A[["ticker", "date", "fw_y", "fw_yy"]], on=["ticker", "date"], how="left")
U["ret"] = U.oc.clip(-60, 60) - FT.COST
low = (U.liq <= 0.5) & U.fw_y.notna() & U.fw_yy.notna()
U["up"] = U.fw_y > U.fw_yy
U["q_fw"] = U.fw_y.where(low).groupby(U.date).rank(pct=True)
print("거래량 하위 50%%(유니버스 아래 절반) 줄 %d · fw 분포(어제): 10%% %.2f · 중앙 %.2f · 90%% %.2f (%%)" % ((low).sum(), *U.loc[low, "fw_y"].quantile([.1, .5, .9])))

TR, VA = ("20180110", "20221231"), lab.VA


def f(s):
    return ("%6d %+6.2f %4.1f%% t%5.1f PF %.2f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["pf"] or 0, s["ypos"], s["ny"])) if s else "     0      -"


def row(nm, m, df=U, per=(TR, VA), col="ret"):
    a = lab.stats(df.loc[m & (df.date >= per[0][0]) & (df.date <= per[0][1]), ["date", col]].rename(columns={col: "ret"}))
    b = lab.stats(df.loc[m & (df.date >= per[1][0]) & (df.date <= per[1][1]), ["date", col]].rename(columns={col: "ret"}))
    print("%-46s | 학습 %s | 검증 %s" % (nm[:46], f(a), f(b)), flush=True)


print("\n== A 시가 매수 → 종가 매도 (비용 0.23) · 학습 2018~22 / 검증 2023~")
row("[대조] 거래량 하위 50% 아무 종목", low)
row("외국인 비중 올라감(어제 > 그제)", low & U.up)
row("올라감 & 어제 순매수(fw > 0)", low & U.up & (U.fw_y > 0))
for q in (0.7, 0.9, 0.97):
    row("올라감 & 비중 상위 %d%%" % round((1 - q) * 100), low & U.up & (U.q_fw >= q))
row("비중 상위 10% (올라감 상관없이)", low & (U.q_fw >= 0.9))
row("올라감 & 상위 10% & 갭 ≤ 0", low & U.up & (U.q_fw >= 0.9) & (U.gap <= 0))
row("올라감 & 상위 10% & 갭 > 0", low & U.up & (U.q_fw >= 0.9) & (U.gap > 0))

# ── B 3분봉 연속 3번 상승 ──
SIG = low & U.up & (U.q_fw >= 0.9) & (U.date >= "20221201")
ctrl = U[low & (U.date >= "20221201")].sample(n=min(12000, int((low & (U.date >= "20221201")).sum())), random_state=3)
need = pd.concat([U[SIG][["ticker", "date"]], ctrl[["ticker", "date"]]]).drop_duplicates()
print("\n== B 3분봉 신호 — 1분봉 받기: 신호 %d 종목-일 + 대조 표본 %d" % (SIG.sum(), len(ctrl)), flush=True)
got, miss = ME.ensure("KR", list(zip(need.ticker, need.date)), log=lambda *a: print(*a, flush=True))
print("받음 %d · 못 받음 %d" % (got, miss), flush=True)
SL = 0.05


def bar3(b):
    b = b[(b.hm >= "0901") & (b.hm <= "1530")].reset_index(drop=True)
    if len(b) < 100: return None
    mins = b.hm.str[:2].astype(int) * 60 + b.hm.str[2:].astype(int) - (9 * 60 + 1)
    k = mins // 3
    c3 = b.groupby(k).c.last(); t3 = b.groupby(k).hm.last()
    o = b.o.iloc[0]
    prev = o
    run = 0
    for i, (kk, cc) in enumerate(c3.items()):
        if t3[kk] > "1130": return None
        run = run + 1 if cc > prev else 0
        prev = cc
        if run >= 3:
            ent = cc * (1 + SL / 100)
            p12 = b[b.hm <= "1200"].c.iloc[-1]; pc = b.c.iloc[-1]
            return dict(hm=t3[kk], r12=(p12 / ent - 1) * 100 - FT.COST, rc=(pc / ent - 1) * 100 - FT.COST,
                        r_oc=(pc / o - 1) * 100 - FT.COST)
    return None


def run_b(df):
    out = []
    for t, gg in df.groupby("ticker"):
        B = ME.bars("KR", t, list(gg.date))
        for r in gg.itertuples():
            b = B.get(r.date)
            if b is None: continue
            x = bar3(b)
            out.append(dict(ticker=t, date=r.date, sig=x is not None, **(x or {})))
    return pd.DataFrame(out)


Rs = run_b(U[SIG][["ticker", "date"]]); Rs["grp"] = "외국인"
Rc = run_b(ctrl[["ticker", "date"]]); Rc["grp"] = "대조"
R = pd.concat([Rs, Rc]); R.to_pickle(C.CACHE / "frgn_ratio_b.pkl")
for nm, X in (("외국인 비중 올라감·상위10%", Rs), ("[대조] 거래량 하위 50% 아무 종목", Rc)):
    print("\n-- %s: 1분봉 있는 날 %d · 3분봉 3연속 상승 나온 날 %.0f%%" % (nm, len(X), X.sig.mean() * 100 if len(X) else 0))
    S = X[X.sig]
    per = (("20221201", "20241231"), ("20250101", "20991231"))
    for col, lab_ in (("r12", "신호 매수 → 12:00 매도"), ("rc", "신호 매수 → 종가 매도"), ("r_oc", "(참고) 그날 시가 매수 → 종가")):
        row(lab_, pd.Series(True, index=S.index), df=S.assign(t1=False), per=per, col=col)
    if len(S): print("   신호 시각 중앙 %s · 09:30 전 %.0f%%" % (S.hm.median() if False else sorted(S.hm)[len(S) // 2], (S.hm <= "0930").mean() * 100))
