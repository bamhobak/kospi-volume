# -*- coding: utf-8 -*-
"""연도별 구조 스캔 2 — 외국인 보유율 · 투자자별 순매수 · 국면 비율 · 2018 종목수 점프 · 공매도 금지기에 놓친 신호."""
import io, sys, sqlite3, warnings; warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd, os
from pathlib import Path
YRS = [str(y) for y in range(2005, 2027)]
c = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)

print("① 외국인 보유율(코스피 · 시총가중) · 투자자별 연간 순매수(조원, 종가×순매수량 근사)")
D = pd.read_sql("SELECT substr(date,1,4) y, ticker, close, foreign_ratio, marcap, indiv, organ, frgn FROM daily WHERE market='KOSPI' AND date>='20050101'", c)
D["w"] = D.marcap.fillna(0).astype(float)
fr = D[D.foreign_ratio.notna() & (D.w>0)].groupby("y").apply(lambda x: np.average(x.foreign_ratio, weights=x.w))
frs = D[D.foreign_ratio.notna()].groupby("y").foreign_ratio.mean()
for k in ("indiv","organ","frgn"): D[k+"_w"] = D[k].astype(float).fillna(0)*D.close/1e12
NB = D.groupby("y")[["indiv_w","organ_w","frgn_w"]].sum()
cov = D.groupby("y").frgn.apply(lambda s: s.notna().mean()*100)
print(f"  {'해':<5}{'외인%(시총가중)':>12}{'외인%(단순)':>10}{'개인순매수':>10}{'기관':>8}{'외국인':>8}{'수급자료%':>8}")
for y in YRS:
    print(f"  {y:<5}{fr.get(y, float('nan')):>12.1f}{frs.get(y, float('nan')):>10.1f}{NB.indiv_w.get(y,0):>+10.1f}{NB.organ_w.get(y,0):>+8.1f}{NB.frgn_w.get(y,0):>+8.1f}{cov.get(y,0):>7.0f}%")

print("\n② 2018년 종목 수 913→1,097 의 정체 — 2018에 새로 나타난 종목")
old = {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily WHERE market='KOSPI' AND date BETWEEN '20170101' AND '20171231'")}
new = {r[0] for r in c.execute("SELECT DISTINCT ticker FROM daily WHERE market='KOSPI' AND date BETWEEN '20180101' AND '20181231'")}
add = new - old
nm = dict(c.execute("SELECT ticker, name FROM daily WHERE date='20180102'").fetchall())
pref = [t for t in add if not t.endswith("0")]
names = [nm.get(t,"?") for t in add]
kw = lambda k: sum(1 for n in names if k in n)
print(f"  새 종목 {len(add)} · 우선주(코드 끝자리≠0) {len(pref)} · 이름에 'KODEX/TIGER/ETF/ETN/스팩' {kw('KODEX')+kw('TIGER')+kw('ETF')+kw('ETN')+kw('스팩')}")
print("  예시:", ", ".join(f"{t} {nm.get(t,'?')}" for t in sorted(add)[:10]))
c.close()

print("\n③ 연도별 국면 비율(코스피 60일선 이격 ±5%)")
import FinanceDataReader as fdr
IX = fdr.DataReader("KS11", "2004-06-01"); IX = IX[IX.Close>0]
gap = (IX.Close/IX.Close.rolling(60).mean()-1)*100; y = IX.index.year.astype(str)
R = pd.DataFrame({"y":y, "up":(gap>5), "dn":(gap<-5)}).groupby("y").mean()*100
print("  " + " · ".join(f"{k}: 상승{v.up:.0f}/횡보{100-v.up-v.dn:.0f}/하락{v.dn:.0f}" for k, v in R.iterrows() if k >= "2005"))

print("\n④ 공매도 금지기에 srd 조건 때문에 못 낸 신호 — srd 만 뺀 조건으로 다시 세면")
os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP="panel_kp.pkl", PANEL_KQ="panel_kq.pkl")
src = Path("portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(Path("portfolio.py").resolve())}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["base"], ns["dn60"]
NOSRD = {  # srd==True 항만 뺀 조건 (portfolio.py 정의에서)
 "폭락반등": (KP, 20, base(KP,3)&dn60(KP)&(KP.ret20<=-25)&(KP.su1>=1.5)&(KP.fw60>=1)&(KP.u<=-10)&(KP.cr_chg20<=-15)),
 "업종붕괴": (KP, 5,  base(KP,10)&dn60(KP)&(KP.u<=-20)&(KP.dma20<=-10)&(KP.mdd60<=-40)),
 "낙폭과대": (KQ, 20, base(KQ,2)&dn60(KQ)&(KQ.ret20<=-30)&(KQ.su1>=1.5)&(KQ.fw60>=1)&(KQ.u<=-20)&(KQ.ow20>=0)&(KQ['부채비율'].isna()|(KQ['부채비율']<=200))),
}
BAN = [("2008.10~2009.5", "20081001", "20090531"), ("2011.8~11", "20110810", "20111109")]
for nm, (K, hold, cond) in NOSRD.items():
    for bn, lo, hi in BAN:
        m = cond.fillna(False) & (K.date>=lo) & (K.date<=hi) & K[f"n{hold}"].notna()
        ms = m & (K.srd==True)
        z = K.loc[m, f"n{hold}"]; zs = K.loc[ms, f"n{hold}"]
        print(f"  {nm:<5} {bn:<14} srd 빼면 {int(m.sum()):>5}건 평균 {z.mean() if len(z) else float('nan'):>+6.1f}% 승률 {(z>0).mean()*100 if len(z) else 0:>3.0f}%"
              f"   ← 실제(srd 포함) {int(ms.sum()):>4}건 {zs.mean() if len(zs) else float('nan'):>+6.1f}%")
