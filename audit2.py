# -*- coding: utf-8 -*-
"""감사 2단계 — 분할 재검사(거래정지 감안) · 2018 점프 정체 · bad 신호 유입 · 가짜 OHLC · 폐지 청산."""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent
KP = pd.read_pickle(BASE/"data"/"panel_kp.pkl").sort_values(["ticker","date"]).reset_index(drop=True)
g = KP.groupby("ticker", sort=False)
KP["_y"] = KP.date.str[:4]

print("① 액면분할 — 분할일과 그 직전 거래 행")
for t, nm, d1, r in [("005930","삼성전자","20180504","50:1"), ("035420","NAVER","20181012","5:1"),
                     ("090430","아모레퍼시픽","20150508","10:1"), ("035720","카카오","20210415","5:1")]:
    s = KP[KP.ticker==t]; b = s[s.date>=d1].head(1); a = s[s.date<d1].tail(1)
    if len(a) and len(b):
        ca, cb = a.close.iloc[0], b.close.iloc[0]
        print(f"  {nm:<8}{r:>5}  {a.date.iloc[0]} {ca:>10,.0f} → {b.date.iloc[0]} {cb:>10,.0f}  비율 {ca/cb:>5.1f}"
              f"  → {'⚠ 원주가(미수정)' if ca/cb>2 else '수정주가'}")

print("\n② 2018년 점프 260행의 정체 — 날짜별")
jj = KP.close/g.close.shift(1)
J = KP[((jj>1.32)|(jj<0.68)) & (KP._y=="2018")]
print("  날짜 상위:", " · ".join(f"{d}:{n}" for d,n in J.groupby("date").size().sort_values(ascending=False).head(6).items()))
print("  예시:", J[["date","ticker","name","close"]].head(5).to_string(index=False).replace("\n","\n       "))

print("\n③ 규칙 신호에 bad(분할·병합 의심) 행이 끼는가")
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
import os; os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP="panel_kp.pkl", PANEL_KQ="panel_kq.pkl")
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
RULES = ns["RULES"]
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    if "bad" not in K.columns: print(f"  {NAME[rid]:<10} bad 열 없음"); continue
    m = cond.fillna(False); n = int(m.sum()); nb = int((m & K.bad.fillna(False)).sum())
    col = f"n{hold}"
    rb = K.loc[m & K.bad.fillna(False), col].mean() if nb else float("nan")
    ro = K.loc[m & ~K.bad.fillna(False), col].mean()
    print(f"  {NAME[rid]:<10} 신호 {n:>6} · bad 포함 {nb:>4} ({nb/max(n,1)*100:.1f}%) · bad 평균 {rb:>+6.1f}% vs 정상 {ro:>+6.1f}%")

print("\n④ 시=고=저=종 행 — 거래량이 있는데 평평하면 가짜 OHLC")
flat = (KP.open==KP.high)&(KP.high==KP.low)&(KP.low==KP.close)
F = KP[flat]
print(f"  평평한 행 {len(F):,} · 그중 거래량>0 {(F.volume>0).mean()*100:.0f}% · 거래량 중앙 {F.volume.median():,.0f}주"
      f" · 일반 행 거래량 중앙 {KP.volume.median():,.0f}주")
bigflat = F[F.volume > KP.volume.median()]
print(f"  거래량이 전체 중앙값보다 큰데 평평한 행: {len(bigflat):,} ({len(bigflat)/len(KP)*100:.2f}%)"
      + ("  → 연도: " + " · ".join(f"{y}:{n}" for y,n in bigflat.groupby("_y").size().items()) if len(bigflat) else ""))

print("\n⑤ 폐지 종목 — 신호가 폐지 20일 안에 났을 때 청산가가 붙는가")
if "grp" in KP.columns:
    last = g.date.transform("max"); D = KP[(KP.grp!="생존")]
    from bisect import bisect_left
    dates = sorted(KP.date.unique()); DI = {d:i for i,d in enumerate(dates)}
    D = D.assign(_dl = D.groupby("ticker").date.transform("max").map(DI) - D.date.map(DI))
    near = D[(D._dl>=1)&(D._dl<=20)]
    print(f"  폐지 1~20일 전 행 {len(near):,} · n20 결측 {near.n20.isna().mean()*100:.1f}% · n20 평균 {near.n20.mean():+.1f}% · 중앙 {near.n20.median():+.1f}%")
    print(f"  (결측이 0% 근처이고 평균이 크게 음수여야 폐지 손실이 반영된 것)")
