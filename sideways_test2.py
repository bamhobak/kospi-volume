# -*- coding: utf-8 -*-
"""횡보장 매매법 2단계 — 조이기(변형) + 우리 재료(수급·공매도·유동성)와 조합.

1단계(sideways_test.py)에서 5개 기법 단독은 횡보장에서 전부 마이너스였고, 유니버스
대비 초과도 ±0.3%p 안에서 놀았다. 즉 기법이 '아무 종목' 과 구분을 못 한다.
그래서 두 갈래로 다시 본다.
  변형: 원본 조건을 더 빡빡하게(같은 날 3중 교차, 박스 하단을 2번 이상 확인한 진짜 박스,
        거래량 3배·몸통 3% 돌파, 60일선이 오르는 중일 때만, 기준선 위에서만)
  조합: 각 기법에 우리 규칙이 검증한 재료를 얹는다 — 외인 5일 순매수, 기관 순매수,
        공매도 감소(srd), 거래대금 100억↑, 외인+공매도

판정은 1단계와 같다(techlib.go 의 ✅ 게이트). 국면은 SIDE 가 핵심이고 전체도 찍는다.
사용: python sideways_test2.py   (지표 캐시 data/tech_ind.pkl 필요 — 1단계가 만든다)
"""
import sys, time
import numpy as np, pandas as pd
from techlib import *
IND = BASE/"data/tech_ind.pkl"
t0 = time.time()
I = pd.read_pickle(IND)
assert len(I)==len(A), "지표 캐시가 패널과 안 맞음 — python sideways_test.py --rebuild"
for c in I.columns:
    if c not in ("ticker","date"): A[c] = I[c].values
del I
gg = A.groupby("ticker", sort=False)
# 2단계에서만 쓰는 지표 몇 개
A["kijun"] = (gg.high.transform(lambda s: s.rolling(26).max())+gg.low.transform(lambda s: s.rolling(26).min()))/2
A["ma60_20ago"] = gg.ma60.shift(20)
touch = (A.low<=A.lo20p*1.02).astype(float)
A["floor_touch20"] = touch.groupby(A.ticker).transform(lambda s: s.rolling(20).sum()).groupby(A.ticker).shift(1)
A["mhist_prev"] = A.groupby("ticker").apply(lambda d: None) if False else None   # 자리표시
hist_prev_gold = None
print(f"[{(time.time()-t0)/60:4.1f}분] 준비 완료", flush=True)

up = (A.close>A.open); body = (A.close-A.open)/A.open
box_w = (A.hi20p-A.lo20p)/A.close
BASEM = {
 "M1 스토+RSI+MACD":  (A.stk_min3<=20)&(A.rsi_prev<50)&(A.rsi>=50)&(A.mgold2)&(A.stk<80),
 "M2a 박스 지지반등":   box_w.between(0.05,0.25)&(A.low<=A.lo20p*1.02)&(A.close>A.lo20p)&up,
 "M2b 압축 돌파":     (A.bbw<=A.bbw_p20)&(A.close>A.hi20p)&(A.volume>2*A.v20)&(body>=0.02),
 "M3 볼린저 하단반등":  ((A.low<=A.bb_dn)|(A.lo_prev<=A.bb_dn_prev))&(A.close>A.bb_dn)&(A.close>A.ma60),
 "M5 일목 구름지지":    (A.cgreen)&(A.close>A.ctop)&(A.ctop_touch3)&up,
}
VARIANT = {
 "M1' 3중 교차 같은 날":     (A.stk_min3<=20)&(A.rsi_prev<50)&(A.rsi>=50)&(A.mgold2)&(A.stk<80)&(A.stk>A.stk_min3),
 "M2a' 진짜 박스(하단 2회+)":  box_w.between(0.05,0.15)&(A.floor_touch20>=2)&(A.low<=A.lo20p*1.02)&(A.close>A.lo20p)&(body>=0.01),
 "M2b' 강한 돌파(3배·3%)":    (A.bbw<=A.bbw_p20)&(A.close>A.hi20p)&(A.volume>3*A.v20)&(body>=0.03),
 "M3' 60일선 상승 중":        BASEM["M3 볼린저 하단반등"]&(A.ma60>A.ma60_20ago),
 "M5' 기준선 위":            BASEM["M5 일목 구름지지"]&(A.close>A.kijun),
}
COMBO = {
 "+외인5일≥1%":      (A.fw5>=1),
 "+기관5일≥0":       (A.ow5>=0),
 "+공매도 감소":       (A.srd==True),
 "+외인≥1%·공매도감소": (A.fw5>=1)&(A.srd==True),
 "+거래대금≥100억":    (A.amt20>=100),
}
hits = []
for reg in ("SIDE", None):
    for hold in (10, 20):
        print(f"\n━━ 변형 · 고정 {hold}일 · 국면 {reg or '전체'} · 유니버스 {base(hold, reg=reg):+.2f}% ━━"); hdr()
        for tag, c in VARIANT.items():
            Y = go(tag, c, hold=hold, reg=reg)
            if Y.attrs.get("ok"): hits.append((tag, hold, reg))
        print(f"\n━━ 조합 · 고정 {hold}일 · 국면 {reg or '전체'} ━━"); hdr()
        for mt, mc in BASEM.items():
            for ct, cc in COMBO.items():
                tag = f"{mt.split()[0]} {ct}"
                Y = go(tag, mc&cc, hold=hold, reg=reg, minn=40)
                if Y.attrs.get("ok"): hits.append((tag, hold, reg))
print(f"\n[{(time.time()-t0)/60:4.1f}분] 게이트 통과: {hits if hits else '없음'}")
