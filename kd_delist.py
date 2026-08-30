# -*- coding: utf-8 -*-
"""코스닥 폐지위험 1 — D1 신호 중 폐지 종목의 실제 피해 측정"""
import io,sys,sqlite3,numpy as np,pandas as pd
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding="utf-8")
T=pd.read_csv("data/rules_trades_kosdaq.csv",dtype={"date":str,"ticker":str})
T.columns=[c.lstrip("\ufeff") for c in T.columns]
c=sqlite3.connect("file:data/delisted_kd.db?mode=ro",uri=True,timeout=300)
last=pd.read_sql("SELECT ticker, max(date) AS lastday, count(*) n FROM daily GROUP BY ticker",c); c.close()
DEL=dict(zip(last.ticker,last.lastday))
print(f"폐지 종목 {len(DEL)}개 · 폐지연도 분포:")
yy=pd.Series([v[:4] for v in DEL.values()]).value_counts().sort_index()
print("  "+" · ".join(f"{k} {v}종목" for k,v in yy.items()))
T["lastday"]=T.ticker.map(DEL)
T["isdel"]=T.lastday.notna()
def mm(a,b):
    return (pd.to_datetime(b,format="%Y%m%d")-pd.to_datetime(a,format="%Y%m%d")).days/30.4
T["m_to_del"]=[mm(d,l) if isinstance(l,str) else np.nan for d,l in zip(T.date,T.lastday)]
print(f"\n## D1 신호 {len(T):,}건 중 폐지 종목이 만든 신호\n")
for lab,m in [("폐지 종목 전체",T.isdel),
              ("신호 후 6개월 내 폐지",T.m_to_del.between(0,6)),
              ("신호 후 12개월 내 폐지",T.m_to_del.between(0,12)),
              ("신호 후 24개월 내 폐지",T.m_to_del.between(0,24)),
              ("생존 종목",~T.isdel)]:
    s=T[m.fillna(False)]
    if not len(s): print(f"- {lab}: 0건"); continue
    print(f"- {lab}: **{len(s)}건** · 평균 **{s.r.mean():+.2f}%** · 중앙 {s.r.median():+.2f}% · 승률 {(s.r>0).mean()*100:.0f}% · 최악 {s.r.min():.1f}%")
sub=T[T.m_to_del.between(0,12).fillna(False)]
base=T.r.mean(); ex=T[~T.m_to_del.between(0,12).fillna(False)].r.mean()
print(f"\n전체 평균 {base:+.2f}%  →  12개월 내 폐지 종목 제외 시 **{ex:+.2f}%** (신호 {len(T)-len(sub)}건, {(1-len(sub)/len(T))*100:.1f}% 보존)")
print(f"검증기간: 전체 {T[T.y>=2023].r.mean():+.2f}% → 제외 시 {T[(T.y>=2023)&~T.m_to_del.between(0,12).fillna(False)].r.mean():+.2f}%")
print(f"\n## 폐지 예정 종목의 최악 거래 (신호 후 12개월 내 폐지)\n")
print("| 날짜 | 종목 | 수익 | 폐지까지 |\n|---|---|---|---|")
for r in sub.nsmallest(10,"r").itertuples():
    print(f"| {r.date} | {r.name} | **{r.r:+.1f}%** | {r.m_to_del:.1f}개월 |")
T.to_csv("data/kd_trades_del.csv",index=False,encoding="utf-8-sig")
