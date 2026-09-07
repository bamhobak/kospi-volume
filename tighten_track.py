# -*- coding: utf-8 -*-
"""낙폭 문턱 조이기(-25%/-30%) 추적 — 조인 뒤 실제 신호가 어떻게 달라졌나.

2026-09-06 배포: [폭락반등] 20일 낙폭 -20%→-25% · [낙폭과대] -20%→-30%.
배포 이후로는 아직 신호가 없을 수 있으니, '조이기가 없었다면 났을 신호' 를 되짚어 본다.
  ① 최근 1년 월별로 옛 조건·새 조건 각각 몇 건이 났고, 걸러진 신호의 성적은 어땠나
  ② 이번 국면(2026-07~09)에서 걸러진 종목을 이름과 함께 나열 — 실제로 안 사길 잘했나
  ③ 아직 결과가 안 나온(보유기간 미도래) 최근 신호 표시
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["base"], ns["dn60"]
# 옛 조건 = 문턱만 -20% 로 되돌린 것
OLD = {
 "P3": (KP, 20, base(KP,3)&dn60(KP)&(KP.ret20<=-20)&(KP.su1>=1.5)&(KP.fw60>=1)&(KP.u<=-10)
        &(KP.srd==True)&(KP.cr_chg20<=-15)),
 "D1": (KQ, 20, base(KQ,2)&dn60(KQ)&(KQ.ret20<=-20)&(KQ.su1>=1.5)&(KQ.fw60>=1)&(KQ.u<=-20)
        &(KQ.srd==True)&(KQ.ow20>=0)&(KQ['부채비율'].isna()|(KQ['부채비율']<=200))),
}
NAME = {"P3":"폭락반등","D1":"낙폭과대"}
def dedup(X, hold, K):
    di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
    X = X.assign(_di=X.date.map(di)).sort_values("_di"); keep, last = [], {}
    for t,i,ix in zip(X.ticker.values, X._di.values, X.index):
        if last.get(t,-10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
last_date = max(KP.date.max(), KQ.date.max())
print(f"패널 최종일 {last_date}\n")
for rid, (K, hold, oldc) in OLD.items():
    newc = RULES[rid][5]
    col = f"n{hold}"
    O = dedup(K[oldc.fillna(False)].copy(), hold, K)
    N = dedup(K[newc.fillna(False)].copy(), hold, K)
    cut = O[~O.index.isin(N.index)]                     # 조이기로 걸러진 신호
    print("="*104); print(f"[{NAME[rid]}]  옛(-20%) {len(O)}건 → 새 문턱 {len(N)}건 · 걸러냄 {len(cut)}건"); print("="*104)
    for nm, z in (("남긴 신호", N), ("걸러낸 신호", cut)):
        for pn, lo in (("기준2016~","20160101"), ("검증2023~","20230101"), ("2026년","20260101")):
            v = z[(z.date>=lo)].dropna(subset=[col])
            if len(v) >= 3:
                print(f"  {nm:<10}{pn:<10}{len(v):>4}건 평균 {v[col].mean():>+6.1f}% 중앙 {v[col].median():>+6.1f}%"
                      f" 승률 {(v[col]>0).mean()*100:>3.0f}% 최악 {v[col].min():>+6.1f}%")
        print()
    print("  최근 1년 월별 (옛→새 건수, 걸러진 것 평균)")
    for m in sorted(set(O[O.date>="20250901"].date.str[:6])):
        o = O[O.date.str[:6]==m]; n2 = N[N.date.str[:6]==m]; c = cut[cut.date.str[:6]==m]
        cr = c[col].dropna()
        print(f"    {m[:4]}-{m[4:]}  옛 {len(o):>3}건 → 새 {len(n2):>3}건 · 걸러냄 {len(c):>3}건"
              + (f" (평균 {cr.mean():+.1f}%, 최악 {cr.min():+.1f}%)" if len(cr) else " (결과 미도래)"))
    rec = cut[cut.date >= "20260701"]
    if len(rec):
        print(f"\n  이번 국면(2026-07~)에 걸러진 종목 {len(rec)}건")
        for r in rec.sort_values("date").head(15).itertuples():
            v = getattr(r, col)
            print(f"    {r.date}  {r.name[:12]:<12} {r.ticker}  20일낙폭 {r.ret20:>6.1f}%  "
                  + (f"결과 {v:>+6.1f}%" if v == v else "결과 미도래"))
    print()
