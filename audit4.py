# -*- coding: utf-8 -*-
"""감사 4단계 — 미수정 주가의 실제 피해 규모와 고칠 재료.

발견: 2005~2017 은 원주가, 2018~ 은 수정주가. 신호 당일의 점프는 거의 안 끼지만(0~1%),
**보유 중에 분할이 나면** 매수 100,000 → 분할 후 10,000 으로 '-90% 손실' 이 찍힌다.
bad 플래그는 점프 '뒤' 42일만 표시해서 이건 못 잡는다.
  A) 규칙별·구간별 '보유 중 점프' 거래 수와 그 수익률
  B) -97% 짜리 거래의 정체 (진짜 폐지인가, 분할인가)
  C) 상장주식수(shares)로 분할 비율을 복원할 수 있나 — 연도별 보유율, 아모레 2015 검증
  D) 점프 행 중 'shares 가 역비율로 같이 뛴 것'(=분할) 비율 — 연도별
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd, os
from pathlib import Path
BASE = Path(__file__).parent
os.environ.update(IX_FROM="2004-06-01", DART_FROM="20040101", PANEL_KP="panel_kp.pkl", PANEL_KQ="panel_kq.pkl")
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
PER = [("05~17","20050101","20171231"), ("18~26","20180101","20991231")]

def jump_in_hold(K, hold):
    """신호 다음날부터 hold 일 안에 하루 ±32% 점프가 있는가"""
    g = K.groupby("ticker", sort=False)
    jj = K.close/g.close.shift(1); j = ((jj>1.32)|(jj<0.68)).astype(int)
    fwd = pd.concat([g[j.name if hasattr(j,'name') and j.name else "close"].shift(0)*0 for _ in range(0)], axis=1) if False else None
    K = K.assign(_j=j.values); g = K.groupby("ticker", sort=False)
    cnt = sum(g._j.shift(-i).fillna(0) for i in range(1, hold+1))
    return cnt > 0

print("A) 보유 중 점프(분할·병합 의심)가 낀 거래 — 규칙별")
print(f"  {'규칙':<12}{'구간':>6}{'신호':>7}{'점프낀것':>9}{'비율':>7}{'점프 평균':>10}{'정상 평균':>10}{'전체 평균':>10}{'정상만 평균':>11}")
print("  " + "-"*84)
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    col = f"n{hold}"; m = cond.fillna(False)
    J = jump_in_hold(K, hold)
    for pn, lo, hi in PER:
        mm = m & (K.date>=lo) & (K.date<=hi) & K[col].notna()
        if not mm.sum(): continue
        a = K.loc[mm & J, col]; b = K.loc[mm & ~J, col]; c = K.loc[mm, col]
        print(f"  {NAME[rid]:<12}{pn:>6}{int(mm.sum()):>7}{len(a):>9}{len(a)/mm.sum()*100:>6.1f}%"
              f"{a.mean() if len(a) else float('nan'):>+9.1f}%{b.mean():>+9.1f}%{c.mean():>+9.1f}%{b.mean():>+10.1f}%")

print("\nB) -90% 아래 거래의 정체")
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    col = f"n{hold}"; m = cond.fillna(False) & (K[col] < -90)
    for r in K[m].head(3).itertuples():
        s = K[K.ticker==r.ticker]; i = s.index.get_loc(r.Index)
        seg = s.iloc[i:i+hold+2][["date","close","shares"]]
        jrow = seg[seg.close/seg.close.shift(1) < 0.68]
        info = ""
        if len(jrow):
            k = seg.index.get_loc(jrow.index[0]); p, q = seg.iloc[k-1], seg.iloc[k]
            sr = (q.shares/p.shares) if (p.shares and q.shares) else float("nan")
            info = f"점프 {p.date}→{q.date} 종가 {p.close:,.0f}→{q.close:,.0f} (÷{p.close/q.close:.1f}) · 주식수 ×{sr:.1f}"
        print(f"  {NAME[rid]:<10} {r.ticker} {r.name} {r.date} {getattr(r, col):+.1f}%  {info or '점프 없음(진짜 손실)'}")

print("\nC) 상장주식수(shares) 보유율 — 분할 복원 재료")
for nm, K in (("코스피", KP), ("코스닥", KQ)):
    r = K.assign(_y=K.date.str[:4]).groupby("_y").shares.apply(lambda s: s.notna().mean()*100)
    print(f"  {nm}: " + " · ".join(f"{y}:{v:.0f}%" for y, v in r.items()))
s = KP[KP.ticker=="090430"]; a = s[s.date<"20150508"].tail(1); b = s[s.date>="20150508"].head(1)
if len(a) and len(b):
    print(f"  아모레 2015: 주식수 {a.shares.iloc[0]:,.0f} → {b.shares.iloc[0]:,.0f} (×{b.shares.iloc[0]/a.shares.iloc[0]:.1f}) · 종가 ÷{a.close.iloc[0]/b.close.iloc[0]:.1f}  → 주식수로 복원 {'가능' if abs(b.shares.iloc[0]/a.shares.iloc[0]*b.close.iloc[0]/a.close.iloc[0]-1)<0.1 else '불가'}")

print("\nD) 점프 행 중 분할(주식수 역비율)로 설명되는 비율 — 연도별")
for nm, K in (("코스피", KP), ("코스닥", KQ)):
    g = K.groupby("ticker", sort=False)
    jj = K.close/g.close.shift(1); ss = K.shares/g.shares.shift(1)
    J = K[((jj>1.32)|(jj<0.68))].assign(_jj=jj, _ss=ss)
    J["_split"] = (J._jj*J._ss).sub(1).abs() < 0.15
    r = J.assign(_y=J.date.str[:4]).groupby("_y").agg(n=("_split","size"), sp=("_split","sum"), na=("_ss", lambda x: x.isna().sum()))
    print(f"  {nm}: " + " · ".join(f"{y}:{int(v.sp)}/{int(v.n)}(주식수없음{int(v.na)})" for y, v in r.iterrows()))
