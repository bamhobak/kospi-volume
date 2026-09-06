# -*- coding: utf-8 -*-
"""감사 5단계 — 남은 구멍 넷: 무상증자 · 2026 코스닥 점프 · 2018 이음새 · 거래세."""
import io, sys, warnings, os
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import numpy as np, pandas as pd
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

def events(K):
    """주식수가 뛰고 종가가 역비율로 움직인 날 = 분할·무상증자·병합 (±32% 안쪽 포함)"""
    g = K.groupby("ticker", sort=False)
    jj = K.close/g.close.shift(1); ss = K.shares/g.shares.shift(1)
    ev = (ss.sub(1).abs() > 0.08) & ((jj*ss).sub(1).abs() < 0.12) & (jj.sub(1).abs() > 0.08)
    return ev.fillna(False), jj, ss

print("① 무상증자·분할·병합 이벤트(주식수 변화로 확인) — 크기별 · 2005~2017")
for nm, K in (("코스피", KP), ("코스닥", KQ)):
    ev, jj, ss = events(K)
    E = K[ev & (K.date < "20180101")].assign(_jj=jj[ev & (K.date < "20180101")])
    small = E[(E._jj >= 0.68) & (E._jj <= 1.32)]   # ±32% 안쪽 = 기존 필터가 못 본 것
    print(f"  {nm}: 이벤트 {len(E):,}건 · 그중 ±32% 안쪽(못 봤던 것) {len(small):,}건 "
          f"· 배율 분포: ÷1.1~1.5 {((E._jj>=0.68)&(E._jj<0.91)).sum()} · ÷2 {((E._jj>=0.45)&(E._jj<0.68)).sum()} · ÷5이상 {(E._jj<0.25).sum()} · 병합(×) {(E._jj>1.32).sum()}")

print("\n② 그 이벤트가 신호 '앞 20일' 또는 '보유 중' 에 끼는 거래 — 규칙별(2005~2017)")
print(f"  {'규칙':<12}{'신호':>7}{'앞20일에 이벤트':>14}{'보유중 이벤트':>12}{'오염 평균':>10}{'정상 평균':>10}")
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    if "shares" not in K.columns: print(f"  {NAME[rid]:<12} (합본 패널 · 주식수 없음 · 건너뜀)"); continue
    ev, jj, ss = events(K); K = K.assign(_e=ev.astype(int).values); g = K.groupby("ticker", sort=False)
    back = sum(g._e.shift(i).fillna(0) for i in range(0, 21)) > 0
    fwd = sum(g._e.shift(-i).fillna(0) for i in range(1, hold+1)) > 0
    col = f"n{hold}"; m = cond.fillna(False) & (K.date < "20180101") & K[col].notna()
    if not m.sum(): continue
    dirty = m & (back | fwd)
    print(f"  {NAME[rid]:<12}{int(m.sum()):>7}{int((m&back).sum()):>14}{int((m&fwd).sum()):>12}"
          f"{K.loc[dirty,col].mean() if dirty.sum() else float('nan'):>+9.1f}%{K.loc[m&~dirty,col].mean():>+9.1f}%")

print("\n③ 2026년 코스닥 점프 217건의 정체")
g = KQ.groupby("ticker", sort=False); jj = KQ.close/g.close.shift(1)
J = KQ[((jj>1.32)|(jj<0.68)) & (KQ.date>="20260101")].assign(_jj=jj)
print("  날짜 상위:", " · ".join(f"{d}:{n}" for d,n in J.groupby("date").size().sort_values(ascending=False).head(5).items()))
print(f"  폐지그룹 비율 {(J.grp!='생존').mean()*100:.0f}% · 상승점프 {(J._jj>1.32).sum()} · 하락점프 {(J._jj<0.68).sum()} · 종가 중앙 {J.close.median():,.0f}원")
print("  예시:", J[["date","ticker","name","close","_jj","grp"]].head(6).to_string(index=False).replace("\n","\n       "))
print("  참고 — 코스피 2026:", end=" ")
g2 = KP.groupby("ticker", sort=False); j2 = KP.close/g2.close.shift(1)
J2 = KP[((j2>1.32)|(j2<0.68)) & (KP.date>="20260101")]
print(f"{len(J2)}건 · 폐지그룹 {(J2.grp!='생존').mean()*100:.0f}%")

print("\n④ 2018 이음새(원주가→수정주가) 근처 신호 — 2018-01~03 에 이음새 점프 종목이 낸 신호")
seam = set(KP[(KP.date=="20180102") & ((j2>1.32)|(j2<0.68))].ticker)
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    if K is not KP: continue
    col = f"n{hold}"; m = cond.fillna(False) & (K.date>="20180101") & (K.date<="20180331")
    ms = m & K.ticker.isin(seam)
    if m.sum(): print(f"  {NAME[rid]:<12} 1~3월 신호 {int(m.sum()):>4} · 이음새 종목 {int(ms.sum()):>3} · 이음새 평균 {K.loc[ms,col].mean() if ms.sum() else float('nan'):+.1f}% vs 나머지 {K.loc[m&~ms,col].mean():+.1f}%")

print("\n⑤ 거래세를 연도별 실제값으로 바꾸면 평균이 얼마나 내려가나 (패널은 0.18% 고정)")
TAX = lambda y: 0.30 if y<=2018 else 0.25 if y<=2020 else 0.23 if y<=2022 else 0.20 if y==2023 else 0.18 if y==2024 else 0.15
tot = 0; n = 0
for rid,(K,hold,stop,pct,mx,cond) in RULES.items():
    col = f"n{hold}"; m = cond.fillna(False) & K[col].notna()
    d = (K.loc[m,"date"].str[:4].astype(int).map(TAX) - 0.18)
    print(f"  {NAME[rid]:<12} 신호 {int(m.sum()):>6} · 평균 보정 {-d.mean():+.3f}%p (2005~18 은 -0.12%p, 2025~ 는 +0.03%p)")
