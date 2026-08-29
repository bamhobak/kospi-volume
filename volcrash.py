# -*- coding: utf-8 -*-
"""거래량·거래대금 '급락' 신호 검증 (미래참조 제거 · 두 벤치마크 · 포트폴리오)"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,open FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con); con.close()
g = df.groupby("ticker", sort=False)
df["dret"] = g["close"].transform(lambda x: x.pct_change()) * 100
df["v5"]  = g["volume"].transform(lambda x: x.rolling(5).mean())
df["v60"] = g["volume"].transform(lambda x: x.rolling(60).mean())
df["a5"]  = (df.volume*df.close).groupby(df.ticker).transform(lambda x: x.rolling(5).mean())
df["a60"] = (df.volume*df.close).groupby(df.ticker).transform(lambda x: x.rolling(60).mean())
df["vsurge"] = df.v5 / df.v60
df["asurge"] = df.a5 / df.a60
df["amt"] = df.a60 / 1e8
U = df[df.ticker.str.endswith("0")].copy()
dates = sorted(U.date.unique())
COLS = sorted(U.ticker.unique())
P = lambda c: U.pivot_table(index="date", columns="ticker", values=c, aggfunc="first").reindex(index=dates, columns=COLS)
RET = P("dret"); VS = P("vsurge"); AS = P("asurge"); AMT = P("amt")
VSl, ASl, AMTl = VS.shift(1), AS.shift(1), AMT.shift(1)      # ★ 1일 지연
ELIG = (AMTl >= 10) & RET.notna()
BAN = [("20200316","20210502"),("20231106","20250330")]
COSTR = pd.DataFrame(0.18 + np.select([AMTl>=100, AMTl>=50, AMTl>=20, AMTl>=10],
                                      [0.20,0.30,0.50,0.70], default=1.00), index=dates, columns=RET.columns)
# ── ① 횡단면: 전방수익 (다음날 시가→h일 뒤 종가), 동일가중 평균 대비
OP = P("open").shift(-1); CL = P("close")
def fwd(h):
    raw = (CL.shift(-h) / OP - 1) * 100
    raw = raw.where(raw.abs() < 200)
    return raw.sub(raw.mean(axis=1), axis=0)
FW = {h: fwd(h) for h in (5, 10, 20, 60)}
def xsec(rank_df, lo, hi, lab):
    r = rank_df.where(ELIG).rank(axis=1, pct=True)
    m = (r > lo) & (r <= hi)
    out = {}
    for h, F in FW.items():
        v = F.where(m).stack()
        yy = v.groupby(v.index.get_level_values(0).str[:4]).mean()
        yy = yy[yy.index >= "2019"]
        out[h] = (v.mean(), (yy > 0).sum(), len(yy))
    return lab, out
print("## ① 횡단면 초과수익 (동일가중 평균 대비) · 1일 지연 적용\n")
print("| 구간 | " + " | ".join(f"{h}일" for h in (5,10,20,60)) + " |\n|---|" + "---|"*4)
rows = [xsec(VSl, 0.0, 0.10, "거래량 급락 최하위 10%"), xsec(VSl, 0.0, 0.20, "거래량 급락 하위 20%"),
        xsec(VSl, 0.0, 0.30, "거래량 급락 하위 30%"), xsec(VSl, 0.80, 1.0, "(참고) 거래량 급등 상위 20%"),
        xsec(ASl, 0.0, 0.10, "거래대금 급락 최하위 10%"), xsec(ASl, 0.0, 0.20, "거래대금 급락 하위 20%"),
        xsec(ASl, 0.80, 1.0, "(참고) 거래대금 급등 상위 20%")]
for lab, o in rows:
    print(f"| {lab} | " + " | ".join(f"{o[h][0]:+.2f}% ({o[h][1]}/{o[h][2]})" for h in (5,10,20,60)) + " |")
# ── ② 포트폴리오
banset = {d for d in dates for a,b in BAN if a<=d<=b}
def run(mask, reb, lab):
    keep = (ELIG & mask).astype(float)
    rebd = set(dates[::reb]); cur=None; W=[]; cost=[]
    for d in dates:
        if cur is None or d in rebd:
            t = keep.loc[d]; s = t.sum(); new = t/s if s>0 else t
            cost.append(0.0 if cur is None else float(((new-cur).abs()/2*COSTR.loc[d].fillna(1.0)).sum()))
            cur = new
        else:
            cur = cur*(1+RET.loc[d].fillna(0)/100); cur = cur/cur.sum(); cost.append(0.0)
        W.append(cur.copy())
    w = pd.DataFrame(W, index=dates)
    pr = ((w.shift(1).fillna(0)*RET.fillna(0)).sum(axis=1) - pd.Series(cost, index=dates)).iloc[1:]
    cum=(1+pr/100).cumprod(); dd=(cum/cum.cummax()-1)*100; yrs=len(pr)/246
    yr={}
    for y in range(2019,2027):
        c=cum[cum.index.str[:4]==str(y)]; yr[y]=(c.iloc[-1]/c.iloc[0]-1)*100 if len(c)>5 else None
    return dict(lab=lab, cagr=(cum.iloc[-1]**(1/yrs)-1)*100, mdd=dd.min(),
                sh=pr.mean()/pr.std()*np.sqrt(246), n=keep.sum(axis=1).mean(), yr=yr)
ki = fdr.DataReader("KS11","2018-01-01"); ki=ki[ki.Close>0]; ki.index=ki.index.strftime("%Y%m%d")
b = ki.Close.reindex(dates).ffill(); cb=b/b.iloc[0]; prb=b.pct_change().dropna()*100
print("\n## ② 포트폴리오 (비용 반영 · 60일 리밸런싱)\n")
print("| 전략 | CAGR | MDD | 샤프 | 종목 | " + " | ".join(str(y) for y in range(2019,2027)) + " |")
print("|---|---|---|---|---|" + "---|"*8)
print(f"| 코스피 지수 | {(cb.iloc[-1]**(246/len(dates))-1)*100:+.1f}% | {((cb/cb.cummax()-1)*100).min():.1f}% | {prb.mean()/prb.std()*np.sqrt(246):.2f} | - |" + " - |"*8)
VR = VSl.where(ELIG).rank(axis=1, pct=True); AR = ASl.where(ELIG).rank(axis=1, pct=True)
for lab, m in [("동일가중 전종목", ELIG), ("거래량 급락 하위20%", VR<=0.20), ("거래량 급락 하위30%", VR<=0.30),
               ("거래량 급락 하위50%", VR<=0.50), ("거래대금 급락 하위20%", AR<=0.20),
               ("(참고) 거래량 급등 상위20%", VR>0.80)]:
    r = run(m, 60, lab)
    print(f"| {lab} | **{r['cagr']:+.1f}%** | {r['mdd']:.1f}% | {r['sh']:.2f} | {r['n']:.0f} | "
          + " | ".join(f"{v:+.0f}%" if v is not None else "-" for v in r["yr"].values()) + " |")
