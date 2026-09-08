# -*- coding: utf-8 -*-
"""장기 축을 **절대 수익** 기준으로 다시 본다 (2026-09-09 사용자 지적).

어제 장기 132셀을 전부 기각했는데 잣대가 '유니버스 평균 대비 초과' 였다.
250일이면 유니버스가 +8.7~11.2% 오르므로, 초과 -3% 라도 절대로는 +8% 인 경우가 있다.
사용자는 지수를 따라가려는 게 아니라 **절대 수익**을 원한다. 그러니 다시 본다.

  기준 ① 절대 수익(비용 차감) 중앙값 > 0  — 보통 한 건이 돈을 버는가
       ② 상위 5% 제거 평균 > 0            — 복권형이 아닌가
       ③ 학습·검증 둘 다 중앙 > 0
       ④ 초과는 참고로만 표기(선별력이 있는지 보는 용도)
"""
import io, sys, re, warnings
warnings.filterwarnings("ignore")
# ⚠ TextIOWrapper 를 겹쳐 씌우면 먼저 것이 GC 될 때 공유 버퍼를 닫아버린다.
#   새 래퍼를 만들지 말고 reconfigure 로 인코딩만 바꾸고, exec 할 소스의
#   stdout 조작 줄도 정규식으로 걷어낸다.
sys.stdout.reconfigure(encoding="utf-8")
_src = open("long_scan.py", encoding="utf-8").read().split("NT = 0")[0]
_src = re.sub(r"^\s*sys\.stdout\s*=.*$", "", _src, flags=re.M)
exec(_src)
import verdict, pandas as pd, numpy as np

def stat2(K, mk, m, h, name):
    col = f"n{h}"
    X = K[m.fillna(False)].dropna(subset=[col]).copy()
    X = X[X.date >= TR0]
    if len(X) < 200: return None
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    X = X.loc[keep]
    if len(X) < 60: return None
    a = X[col]                                   # 절대 수익(비용 차감)
    e = a - X.date.map(UNI[(mk, h)])             # 참고용 초과
    tr, va = X[X.date <= TR1][col], X[X.date >= VA0][col]
    if len(tr) < 30 or len(va) < 15: return None
    yr = X.assign(y=X.date.str[:4]).groupby("y")[col].median()
    return dict(name=name, h=h, n=len(X), abs=a.mean(), med=a.median(),
                trim=a[a <= a.quantile(0.95)].mean(), win=(a > 0).mean()*100,
                trm=tr.median(), vam=va.median(), ex=e.mean(),
                ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm")[col].mean(), 0.10),
                pos=int((yr > 0).sum()), ny=len(yr))

NT, ROWS = 0, []
for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ")):
    A = axes(K)
    print("=" * 128)
    print(f"[{mk}] 장기 축 — **절대 수익** 기준 (비용 차감, 2016~). 초과는 참고")
    print("=" * 128)
    print(f"  {'축':<30}{'보유':>5}{'건수':>7}{'절대':>9}{'중앙':>9}{'절삭':>9}{'승률':>6}"
          f"{'학습중앙':>9}{'검증중앙':>9}{'월CI':>9}{'양수해':>7}{'(초과)':>9}")
    for nm, m in A.items():
        for h in HS:
            NT += 1
            r = stat2(K, mk, m, h, nm)
            if r is None: continue
            r["mk"] = mk; ROWS.append(r)
            print(f"  {nm:<30}{h:>5}{r['n']:>7,}{r['abs']:>+9.2f}{r['med']:>+9.2f}"
                  f"{r['trim']:>+9.2f}{r['win']:>5.0f}%{r['trm']:>+9.2f}{r['vam']:>+9.2f}"
                  f"{r['ci']:>+9.2f}{r['pos']:>4}/{r['ny']}{r['ex']:>+9.2f}")
R = pd.DataFrame(ROWS)
print("\n" + "=" * 128)
print("생존 후보 — **절대** 중앙>0 · 절삭>0 · 학습중앙>0 · 검증중앙>0 · 양수해 70%↑")
print("=" * 128)
G = R[(R.med > 0) & (R.trim > 0) & (R.trm > 0) & (R.vam > 0) & (R.pos/R.ny >= 0.7)]
if len(G):
    for _, r in G.sort_values("med", ascending=False).iterrows():
        print(f"  [{r.mk}] {r['name']:<30} {r.h}일 · {r.n:>5,}건 · 절대 평균 {r['abs']:+.2f}% "
              f"중앙 {r.med:+.2f}% 절삭 {r.trim:+.2f}% 승률 {r.win:.0f}% "
              f"양수해 {r.pos}/{r.ny} (초과 {r.ex:+.2f})")
else:
    print("  없음")
R.to_pickle("data/long_abs.pkl")
verdict.log_trials("장기 절대기준 재판정", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
