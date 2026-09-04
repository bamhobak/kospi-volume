# -*- coding: utf-8 -*-
"""상승장 규칙 세 번째 축 찾기 — 1단계 스크리닝.

왜: 9규칙 중 하락장 6개는 월 동조 0.96 으로 한 덩어리다. 진짜 분산 축은 하락 덩어리·
[외인 매집]·[조용한 신고가] 셋뿐이고, [조용한 신고가]는 공매도 금지기 전용이라 실질 둘이다.
그래서 기존 두 상승장 규칙과 '재료가 겹치지 않는' 상승장 축을 찾는다.
(예전 1만2천 셀 격자 탐색은 기각됐다 — 같은 격자를 다시 돌리지 않고 축을 달리 잡는다.)

축 9개: 눌림목 · 내부자 단독(외인 없이) · 자사주 상승장 · 저PBR 상승장 · 공매도 커버링 ·
        개인 투매 흡수 · 기관 · 장중 강세 · 코스닥.
게이트 2종: G0 = 코스피 60일선 위(배포 게이트) · G5 = 이격 +5% 이상(강한 상승).
판정 = techlib ✅ (학습CI>0 · 붐제외CI>0 · 중앙>0 · 붐제외중앙>0 · 상위5%제거>0).
사용: python bull_axes.py
"""
import sys, sqlite3, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from techlib import *

# ── 보조 데이터 붙이기: 내부자(ins60) · 자사주(bb) · 기술지표 일부 ───────────────
O = pd.read_pickle(BASE/"data/insider_feat.pkl")[["ticker","date","ins60"]]
n0 = len(A); T = A.merge(O, on=["ticker","date"], how="left"); assert len(T)==n0
A["ins60"] = T.ins60.fillna(0).values; del T, O
con = sqlite3.connect(f"file:{BASE}/data/dart/disclosures.db?mode=ro", uri=True)
D = pd.read_sql("SELECT stock_code t, rcept_dt d, report_nm FROM disclosure WHERE length(stock_code)=6 "
                "AND rcept_dt>='20180101' AND replace(report_nm,' ','') LIKE '%자기주식취득결정%'", con); con.close()
nm_ = D.report_nm.str.replace(" ", "", regex=False)
BB = set(zip(*D[~nm_.str.contains("신탁") & ~nm_.str.contains("정정")][["t","d"]].values.T))
A["bb"] = [(t,d) in BB for t,d in zip(A.ticker, A.date)]
I = pd.read_pickle(BASE/"data/tech_ind.pkl"); assert len(I)==len(A)
for c in ("rsi","mgold2","stk"): A[c] = I[c].values
del I
g = A.groupby("ticker", sort=False)
A["dma20_prev"] = g.dma20.shift(1)
A["ret1"] = g.close.pct_change()*100
print(f"보조 데이터: ins60>0 {int((A.ins60>0).sum()):,}행 · 자사주 공시일 {int(A.bb.sum()):,}행", flush=True)

up = A.dma60>0; up2 = (A.dma60>0)&(A.dma120>0)
C = {
 # 눌림목
 "눌림1 추세중 20선 눌림·거래량고갈":      up2&A.dma20.between(-6,0)&(A.v5<0.7*A.v20)&(A.fw20>=0)&(A.ret5<=0),
 "눌림2 +외인60일≥1":                  up2&A.dma20.between(-6,0)&(A.v5<0.7*A.v20)&(A.fw60>=1)&(A.ret5<=0),
 "눌림3 20선 재돌파(거래량 조용)":         up&(A.dma20_prev<=0)&(A.dma20>0)&(A.v5<0.8*A.v20)&(A.fw20>=0),
 # 내부자 단독 (외인 없이 — P7 과 구조적으로 안 겹침)
 "내부자1 ins≥2·추세·외인<1·저변동":      (A.ins60>=2)&up&(A.fromhi>=-15)&(A.fw20<1)&(A.vol20<=3),
 "내부자2 ins≥1·저점+50·120선위·침체":    (A.ins60>=1)&(A.fromlo>=50)&(A.dma120>0)&(A.r16<120),
 "내부자3 ins≥2·시총<1조·추세":          (A.ins60>=2)&(A.marcap<1e4)&up&(A.amt20>=30),
 "내부자4 ins≥3·추세":                 (A.ins60>=3)&up&(A.fromhi>=-20),
 # 자사주 상승장
 "자사주1 공시·추세·고점-15·저점+30":      A.bb&up&(A.fromhi>=-15)&(A.fromlo>=30),
 "자사주2 공시·20선위·외인≥0":           A.bb&(A.dma20>0)&(A.fw20>=0),
 # 저PBR 상승장 (밸류 축)
 "저PBR1 PBR≤1·저점+30·추세·외인20≥1":   (A.PBR<=1)&(A.fromlo>=30)&up&(A.fw20>=1),
 "저PBR2 PBR≤0.8·120선위·기관60≥0":     (A.PBR<=0.8)&(A.dma120>0)&(A.ow60>=0),
 "저PBR3 PBR≤1·내부자≥1·추세":          (A.PBR<=1)&(A.ins60>=1)&up,
 # 공매도 커버링
 "커버링1 srd·sr20≥1·외인5≥1·20선위":    (A.srd==True)&(A.sr20>=1)&(A.fw5>=1)&(A.dma20>0),
 "커버링2 sr20≥2·srd·고점-10":          (A.sr20>=2)&(A.srd==True)&(A.fromhi>=-10),
 # 개인 투매 흡수 (개인 데이터는 어느 규칙도 안 쓴다)
 "개인1 개인5<0·외인5≥1·가격버팀·추세":    (A.indiv5<0)&(A.fw5>=1)&A.ret5.between(-3,3)&up,
 "개인2 개인5<0·기관≥0·외인≥0·저변동":     (A.indiv5<0)&(A.ow5>=0)&(A.fw5>=0)&(A.dma20>0)&(A.vol20<=2.5),
 # 기관 축 (P7 은 기관이 '안 사는' 것을 요구)
 "기관1 기관20≥1·외인20≥0·추세·고점-10":   (A.ow20>=1)&(A.fw20>=0)&up&(A.fromhi>=-10),
 "기관2 기관60≥1·외인60≥1·침체":         (A.ow60>=1)&(A.fw60>=1)&(A.r16<120),
 # 장중 강세 / 가격 구조
 "강세1 clv≥0.7·거래량보통·20선위·고점-10":  (A.clv>=0.7)&(A.body>=0)&A.v5.between(0.8*A.v20,1.5*A.v20)&(A.dma20>0)&(A.fromhi>=-10),
 "강세2 3연속양봉·저변동·외인5≥1":         (A.upd>=3)&(A.vol20<=2)&(A.fw5>=1),
 "모멘텀 60일+10~40·저변동·침체·외인60≥1":  A.ret60.between(10,40)&(A.vol20<=2)&(A.r16<120)&(A.fw60>=1)&(A.fromhi>=-10),
 "MACD골든·60선위·RSI45~65·외인5≥1":     (A.mgold2)&up&A.rsi.between(45,65)&(A.fw5>=1),
 # 참고: 현행 [외인 매집] 본체 (겹침 기준선)
 "참고 P7본체(내부자 포함)":              (A.marcap>=1e4)&(A.marcap<1e5)&(A.fw20>=1)&(A.ow60<0.4)&A.r16.between(100,150)&(A.fromhi>=-15)&(A.fromlo>=70)&(A.ins60>0),
}
GATES = {"G0 60일선 위": (A.ixdev>0), "G5 이격+5%↑": (A.ixdev>5)}
keep = A["reg"].copy(); hits = []
for gn, gm in GATES.items():
    A["reg"] = np.where(gm.fillna(False), "X", "-")
    for mk in ("KOSPI", None):
        for hold in (20, 40, 60):
            print(f"\n━━ {gn} · {mk or '코스피+코스닥'} · 고정 {hold}일 · 유니버스 {base(hold, mk=mk, reg='X'):+.2f}% ━━"); hdr()
            for tag, c in C.items():
                if mk is None and tag.startswith("참고"): continue
                Y = go(tag, c, hold=hold, mk=mk, reg="X", minn=30)
                if Y.attrs.get("ok"): hits.append((gn, mk or "both", hold, tag, len(Y), round(Y.r.mean(),2), round(Y.alpha.mean(),2)))
    A["reg"] = keep
# 코스닥 전용 축
A["reg"] = np.where((A.ixdev>0).fillna(False), "X", "-")
print(f"\n━━ 코스닥 전용 · G0 · 고정 40/60일 ━━"); hdr()
for hold in (40, 60):
    for tag, c in {"코스닥1 ins≥1·추세·외인20≥1·저점+50": (A.ins60>=1)&up&(A.fw20>=1)&(A.fromlo>=50)&(A.amt20>=20),
                   "코스닥2 자사주·추세·외인≥0": A.bb&up&(A.fw20>=0)&(A.amt20>=20)}.items():
        Y = go(f"{tag} [{hold}일]", c, hold=hold, mk="KOSDAQ", reg="X", minn=30)
        if Y.attrs.get("ok"): hits.append(("G0","KOSDAQ",hold,tag,len(Y),round(Y.r.mean(),2),round(Y.alpha.mean(),2)))
A["reg"] = keep
print("\n\n=== 1단계 게이트 통과 목록 ===")
for h in hits: print("  ", h)
print(f"  합계 {len(hits)}건" if hits else "  없음")
