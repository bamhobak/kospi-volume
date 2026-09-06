# -*- coding: utf-8 -*-
"""[폭락반등]·[낙폭과대] 조이기 전/후 — 연도별 수익률과 실제 수익금.

규칙 평균 수익률은 '한 거래당' 이야기라 자리 경쟁과 자금 규모를 안 보여준다. 아홉 규칙이 함께
도는 계좌(원금 1억) 안에서 두 규칙이 해마다 실제로 얼마를 벌었는지 청산 시점 기준으로 적는다.
시드 12개의 중앙값을 쓴다(진입 순서가 무작위라 한 번만 돌리면 우연이 섞인다).
사용: IX_FROM=2004-06-01 DART_FROM=20040101 PANEL_KP=panel_kp.pkl PANEL_KQ=panel_kq.pkl python cmp_money.py
"""
import io, os, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent; SEEDS = 12; CAPITAL = 1_0000_0000   # 1억
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
adates = sorted(set(KP.date) | set(KQ.date)); ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE/"rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())

def sim(S, ds, seed):
    """원래 sim 과 같되, 청산될 때마다 (연도, 규칙, 손익) 을 남긴다."""
    eq = 1.0; op = []; log = []
    lo_i, hi_i = ADI[ds[0]], ADI[ds[-1]]
    byd = {i: g for i, g in S[(S.di >= lo_i) & (S.di <= hi_i)].groupby("di")}
    rng = np.random.default_rng(seed)
    for d in ds:
        i = ADI[d]; st = []
        for p in op:
            if p["ex"] <= i:
                hit = (p["stop"] == p["stop"]) and (p["low"]/p["buy"]-1)*100 <= -p["stop"]*100
                r = (-p["stop"]*100-p["cost"]) if hit else ((p["exit"]/p["buy"]-1)*100-p["cost"])
                g = p["amt"]*r/100; eq += g
                log.append((d[:4], p["rid"], g, r))
            else: st.append(p)
        op = st; td = byd.get(i)
        if td is not None:
            td = td.sample(frac=1, random_state=int(rng.integers(1 << 31)))
            inv = sum(p["amt"] for p in op)
            for t in td.itertuples():
                nr = sum(1 for p in op if p["rid"] == t.rid); w = eq*t.pct/100
                if nr >= t.mx or inv+w > eq or any(p["tk"] == t.ticker for p in op): continue
                op.append(dict(rid=t.rid, tk=t.ticker, buy=t.buy, exit=t.exit, low=t.low,
                               cost=t.cost, stop=t.stop, amt=w, ex=i+t.hold)); inv += w
    return pd.DataFrame(log, columns=["y", "rid", "gain", "ret"])

def variant(**patch):
    R = dict(RULES)
    for rid, cond in patch.items():
        P, h, stop, pct, mx, _ = R[rid]; R[rid] = (P, h, stop, pct, mx, cond)
    return build(R)

# ⚠ portfolio.py 는 이미 조인 값(-25/-30)이라 RULES 를 그대로 쓰면 '전' 과 '후' 가 같아진다.
#   두 규칙의 조건을 문턱만 바꿔 다시 짓는다(나머지 항은 portfolio.py 정의 그대로).
base, dn60 = ns["base"], ns["dn60"]
def p3(th): return (base(KP,3)&dn60(KP)&(KP.ret20<=th)&(KP.su1>=1.5)&(KP.fw60>=1)
                    &(KP.u<=-10)&(KP.srd==True)&(KP.cr_chg20<=-15))
def d1(th): return (base(KQ,2)&dn60(KQ)&(KQ.ret20<=th)&(KQ.su1>=1.5)&(KQ.fw60>=1)
                    &(KQ.u<=-20)&(KQ.srd==True)&(KQ.ow20>=0)
                    &(KQ['부채비율'].isna()|(KQ['부채비율']<=200)))
assert int((p3(-25)!=RULES["P3"][5]).sum())==0 and int((d1(-30)!=RULES["D1"][5]).sum())==0, "조건 재구성 불일치"

ds = [d for d in adates if d >= "20050101"]
OLD = variant(P3=p3(-20), D1=d1(-20))
NEW = variant(P3=p3(-25), D1=d1(-30))
LO = [sim(OLD, ds, k) for k in range(SEEDS)]
LN = [sim(NEW, ds, k) for k in range(SEEDS)]
YRS = [str(y) for y in range(2005, 2027)]

def agg(logs, rid):
    """시드별로 연도 집계 후 중앙값 — 건수·평균수익률·수익금(원)"""
    n, r, g = {}, {}, {}
    for y in YRS:
        v = [(L[(L.y == y) & (L.rid == rid)]) for L in logs]
        n[y] = np.median([len(x) for x in v])
        r[y] = np.nanmedian([x.ret.mean() if len(x) else np.nan for x in v])
        g[y] = np.median([x.gain.sum() for x in v])*CAPITAL
    return n, r, g

for rid, nm in (("P3", "폭락반등 (코스피)"), ("D1", "낙폭과대 (코스닥)")):
    o = agg(LO, rid); w = agg(LN, rid)
    tot_o = sum(o[2][y] for y in YRS); tot_w = sum(w[2][y] for y in YRS)
    print(f"\n[{nm}]  원금 1억 · 9규칙 계좌 안 · 청산 연도 기준 · 시드 12개 중앙값")
    print(f"  {'해':<6}{'건수(전)':>9}{'수익률(전)':>11}{'수익금(전)':>13}"
          f"{'건수(후)':>9}{'수익률(후)':>11}{'수익금(후)':>13}{'수익금 차이':>13}")
    print("  " + "-"*96)
    for y in YRS:
        if o[0][y] == 0 and w[0][y] == 0: continue
        f = lambda v: "—" if v != v else f"{v:+.1f}%"
        m = lambda v: f"{v/10000:>+,.0f}만"
        print(f"  {y:<6}{o[0][y]:>9.0f}{f(o[1][y]):>11}{m(o[2][y]):>13}"
              f"{w[0][y]:>9.0f}{f(w[1][y]):>11}{m(w[2][y]):>13}{m(w[2][y]-o[2][y]):>13}")
    print("  " + "-"*96)
    no = sum(o[0][y] for y in YRS); nw = sum(w[0][y] for y in YRS)
    print(f"  {'합계':<6}{no:>9.0f}{'':>11}{tot_o/10000:>+12,.0f}만"
          f"{nw:>9.0f}{'':>11}{tot_w/10000:>+12,.0f}만{(tot_w-tot_o)/10000:>+12,.0f}만")

# 계좌 전체도 같이
print("\n[계좌 전체 9규칙]  최종 자산 (원금 1억)")
for nm, S in (("전(현행)", OLD), ("후(조인 안)", NEW)):
    L = LO if nm.startswith("전") else LN
    tot = np.median([l.gain.sum() for l in L])*CAPITAL
    print(f"  {nm:<12} 실현 손익 합계 {tot/1_0000_0000:+.2f}억")
