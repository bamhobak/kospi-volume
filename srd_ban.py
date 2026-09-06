# -*- coding: utf-8 -*-
"""공매도 전면 금지기에 srd 조건을 예외 처리할까 — 실측으로 판단한다.

배경(2026-09-07 era_scan): 다섯 규칙([폭락반등]·[업종붕괴 이탈]·[조정매집]·[낙폭과대]·[저PBR 낙폭])이
"공매도 비중 5일평균 < 20일평균"(srd)을 요구한다. 공매도가 0이면 이 조건은 성립할 수 없다.
2008.10~2009.5 · 2011.8~11 전면 금지기에 srd 통과율이 25%→4~8% 로 떨어져 규칙이 사실상 정지했고,
2009년 V자 반등(+45%)을 통째로 놓쳤다. 2020·2023 금지는 시장조성자 예외가 있어 srd 30~55% 로 정상.

물음: 전면 금지 창에서만 srd 를 '통과' 로 보면 나아지나? 공짜가 아니다 — srd 는 매물 소화를 보는
     실질 조건이라, 없애면 아직 안 꺼진 종목이 섞인다. 금지 창 안에서만 켜고 성적을 잰다.
방식: 금지 창(전면) = 2008-10-01~2009-05-31, 2011-08-10~2011-11-09.
     A) 현행  B) 금지창에서 srd 면제  를 규칙별로 · 계좌로 비교.
     ⚠ 2005~15 는 '스트레스 참고' 구간이라 채택 근거로 쓰지 않는다(2026-09-07 기준).
       그래서 기준 구간(2016~) 성적이 '변하지 않는지' 를 함께 확인한다 — 변하면 안 된다.
사용: python srd_ban.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).parent; SEEDS = 12
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["base"], ns["dn60"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
exec(rel[rel.index("def sim(S, ds, seed):"):rel.index("ds = [d for d in adates")].replace(
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid)",
     "return dict(nav=Cv.iloc[-1], mdd=dd.min(), byrid=byrid, curve=Cv)"), globals())
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙좍"}
NAME["P5"] = "자사주 낙폭"
BANW = [("20081001","20090531"), ("20110810","20111109")]
def inban(K):
    s = pd.Series(False, index=K.index)
    for lo, hi in BANW: s |= (K.date >= lo) & (K.date <= hi)
    return s
# srd 항을 '금지창에서는 통과' 로 바꾼 조건 재구성 (portfolio.py 정의 그대로, srd 만 완화)
def srd_ok(K): return (K.srd == True) | inban(K)
NEW = {
 "P3": base(KP,3)&dn60(KP)&(KP.ret20<=-25)&(KP.su1>=1.5)&(KP.fw60>=1)&(KP.u<=-10)&srd_ok(KP)&(KP.cr_chg20<=-15),
 "P4": base(KP,10)&dn60(KP)&(KP.u<=-20)&(KP.dma20<=-10)&(KP.mdd60<=-40)&srd_ok(KP),
 "P2": base(KP,3)&ns["dn20"](KP)&(KP.r16<30)&(KP.rw1>=200)&(KP.fw5>=2)&(KP.ret3<=-5)&(KP.ret10<=0)&srd_ok(KP),
 "D1": base(KQ,2)&dn60(KQ)&(KQ.ret20<=-30)&(KQ.su1>=1.5)&(KQ.fw60>=1)&(KQ.u<=-20)&srd_ok(KQ)&(KQ.ow20>=0)
       &(KQ['부채비율'].isna()|(KQ['부채비율']<=200)),
 "D2": base(KQ,5)&dn60(KQ)&(KQ.PBR>0)&(KQ.PBR<=0.5)&(KQ.ret20<=-10)&(KQ.su1>=2)&(KQ.u<=-10)&(KQ.ow20>=0)&srd_ok(KQ),
}
for rid, c in NEW.items():   # 무결성: 금지창 밖에서는 현행과 완전히 같아야 한다
    same = (c.fillna(False) == RULES[rid][5].fillna(False)) | inban(RULES[rid][0])
    assert same.all(), f"{rid}: 금지창 밖 조건이 달라졌다"
print("무결성 확인 ✅ 금지창 밖에서는 현행과 동일\n")

def take(K, cond, hold, stop):
    g = K.groupby("ticker", sort=False)
    if stop:
        low = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((low <= K.buy*(1-stop)).fillna(False), -stop*100-K.cost, K[f"n{hold}"])
    else: r = K[f"n{hold}"].values
    m = cond.fillna(False); X = K[m].copy(); X["_r"] = r[m.values]; X = X.dropna(subset=["_r"])
    di = {x: i for i, x in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i+hold; keep.append(ix)
    return X.loc[keep]
print("① 규칙 단위 — 금지창 두 개 안에서만 (현행 → srd 면제)")
print(f"  {'규칙':<12}{'현행 건수':>9}{'평균':>8}{'승률':>6}   {'면제 건수':>9}{'평균':>8}{'승률':>6}{'중앙':>8}")
for rid, cond in NEW.items():
    K, hold, stop, pct, mx, cur = RULES[rid]
    b = inban(K)
    A = take(K, cur & b, hold, stop); B = take(K, cond & b, hold, stop)
    fa = f"{len(A):>9}{A._r.mean():>+7.1f}%{(A._r>0).mean()*100:>5.0f}%" if len(A) else f"{'0':>9}{'—':>8}{'—':>6}"
    fb = f"{len(B):>9}{B._r.mean():>+7.1f}%{(B._r>0).mean()*100:>5.0f}%{B._r.median():>+7.1f}%" if len(B) else f"{'0':>9}{'—':>8}{'—':>6}{'—':>8}"
    print(f"  {NAME[rid]:<12}{fa}   {fb}")
print("\n② 계좌 — 구간별 (같은 시드 12개 짝 비교)")
def variant(use_new):
    R = dict(RULES)
    if use_new:
        for rid, c in NEW.items():
            K, h, st, pct, mx, _ = R[rid]; R[rid] = (K, h, st, pct, mx, c)
    return build(R)
PER = [("2008~09 위기","20080101","20091231"), ("2010~12","20100101","20121231"),
       ("스트레스2005~15","20050101","20151231"), ("기준2016~","20160101","20991231"),
       ("전체2005~","20050101","20991231")]
A, B = variant(False), variant(True)
print(f"  {'구간':<16}{'현행':>18}{'srd 면제':>18}{'시드승':>8}")
for pn, lo, hi in PER:
    ds = [d for d in adates if lo <= d <= hi]
    ra = [sim(A, ds, k) for k in range(SEEDS)]; rb = [sim(B, ds, k) for k in range(SEEDS)]
    na = [r["nav"] for r in ra]; nb = [r["nav"] for r in rb]
    ma = np.median([r["mdd"] for r in ra]); mb = np.median([r["mdd"] for r in rb])
    w = sum(x > y for x, y in zip(nb, na))
    print(f"  {pn:<16}{np.median(na):>10.2f}배{ma:>7.0f}%{np.median(nb):>10.2f}배{mb:>7.0f}%{w:>6}/{SEEDS}")
