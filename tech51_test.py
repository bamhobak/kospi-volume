# -*- coding: utf-8 -*-
"""유튜브 51편 매매법 1단계 — 단독 실측 (전 국면 · 코스피+코스닥 · 고정 5/20/60일 보유).
판정은 techlib ✅(학습CI>0·붐제외CI>0·중앙>0·붐제외중앙>0·상위5%제거>0).
사용: python tech51_test.py [KOSPI]
"""
import sys
from tech51_ind import *
MK = sys.argv[1] if len(sys.argv)>1 and sys.argv[1] in ("KOSPI","KOSDAQ") else None
O,Hh,Ll,C,V = A.open,A.high,A.low,A.close,A.volume
up_c = C>O
print(f"패널 {len(A):,}행 · 시장 {MK or '코스피+코스닥'} · 유니버스 20일 기준 {base(20, mk=MK):+.2f}%\n")

# ── 규칙 정의 ─────────────────────────────────────────────────────
downtrend = A.ret20 < -10                 # '하락 추세 끝' 근사
uptrend   = (A.dma60>0) & (A.ma60>A.ma60_5)
small_body = A.body <= 0.3*A.rngc
long_body  = A.body/C >= A.body_avg*1.5
R = {}
# 1~5 거래량
R["V01 거래량 5/20 골든크로스"]        = (A.v5>A.v20)&(A.v5p<=A.v20p)
R["V02 횡보 중 거래량 침체→증가"]       = A.ret20.between(-5,5)&(A.v5_5<0.6*A.v60_5)&(A.v5>A.v20)&(A.v5p<=A.v20p)
R["V03 껌딱지 탈출(20/120 ≤0.5→2배)"]  = (A.v20p<=0.5*A.v120)&(V>=2*A.v20)&up_c
R["V04 거래량 동반 전고(120일) 돌파"]    = (C>A.hi120p)&(V>=1.5*A.v20)
R["V04r 거래량 없는 전고 돌파(뒤집기)"]   = (C>A.hi120p)&(V<A.v20)
R["V05 고가놀이: 눌림≤1/3·거래량 급감→증가"] = (A.ret60>=30)&(A.retr<=0.34)&(A.v5p<0.5*A.v20)&(V>A.v20)&(C>A.ma5)&(A.pclose<=A.pma5)
R["V06 거래량 급감 후 증가+5일선 돌파"]   = (A.v5_5<0.5*A.v60_5)&(V>=1.5*A.v5p)&(C>A.ma5)&(A.pclose<=A.pma5)
R["V07 20주선 지지·얕은 조정·거래량 급감"] = (C>=A.ma100)&(C<=A.ma100*1.05)&(A.fromhi>=-15)&(A.v5<0.5*A.v60)&up_c
R["V08 바닥권 거래량 이평 수평화(5주·20주)"] = (A.ret120<=-20)&((A.v25/A.v25_10-1).abs()<0.05)&((A.v100/A.v100_10-1).abs()<0.05)&(V>=1.5*A.v20)&up_c
R["V09 6개월 최저 거래량→3배 급증"]     = (A.v20min120_5>=A.v20p*0.9)&(V>=3*A.v20)&up_c
R["V10 대량거래(5배) 우량주(1조↑)"]     = (V>=5*A.v20)&(A.marcap>=1e4)&up_c
R["V11 OBV 60일 전고 돌파(U마크)"]      = (A.obv>A.obv_hi60p)&(C<A.hi60p)
R["V12 OBV 상승 다이버전스"]           = (A.lo20<A.lo20_20)&(A.obv_lo20>A.obv_lo20_20)&up_c
R["V13 VR(25) ≤70 침체"]              = (A.vr<=70)&up_c
R["V13r VR(25) ≥300 과열(뒤집기)"]     = (A.vr>=300)
# 6~12 추세
R["T01 하락추세선 돌파(120일 -20%↓ 후 60일 고점 돌파)"] = (A.ret120<=-20)&(C>A.hi60p)&(V>=1.5*A.v20)
R["T02 추세대 하단 지지(상승 60선 ±3%·10일 하락 후 양봉)"] = uptrend&(C/A.ma60).between(0.97,1.03)&(A.ret10<0)&up_c
R["T03 피보나치 38.2~50% 눌림(스윙 ≥20%)"] = (A.swing_pct>=20)&A.retr.between(0.382,0.5)&up_c&(A.dma60>0)
R["T03b 피보나치 50~61.8% 눌림"]       = (A.swing_pct>=20)&A.retr.between(0.5,0.618)&up_c&(A.dma60>0)
R["T03r 61.8% 초과 깊은 되돌림(뒤집기)"] = (A.swing_pct>=20)&(A.retr>0.618)&(A.retr<=1)&up_c&(A.dma60>0)
R["T04 약세함정: 20일 저점 이탈 후 3일 내 복귀"] = (A.brk_lo20_3>0)&(C>A.lo20p)&up_c
R["T04b 약세함정: 20일선 이탈 후 3일 내 복귀"] = (A.below20_3>0)&(C>A.ma20)&(A.dma60>0)&up_c
R["T05 달리는 말: 52주 신고가+거래량"]   = (C>A.hi250p)&(V>=1.5*A.v20)&(A.fromhi>=-1)
R["T06 이중바닥 넥라인 돌파"]           = (A.ret60<=-10)&(A.lo10>=A.lo60*0.97)&(A.lo10<=A.lo60*1.03)&(C>A.hi20p)&(V>=1.5*A.v20)
# 21~25 이평·그랜빌
R["G01 그랜빌1: 200선 하락→수평·주가 상향돌파"] = (A.ma200>=A.ma200_20*0.995)&(A.pclose<=A.pma200)&(C>A.ma200)
R["G01b 그랜빌1(120선)"]               = (A.ma120>=A.ma120_20*0.995)&(A.pclose<=A.pma120)&(C>A.ma120)
R["G02 그랜빌2: 상승 200선 일시 이탈 후 복귀"] = (A.ma200>A.ma200_20)&(A.below200_5>0)&(C>A.ma200)&up_c
R["G03 그랜빌3: 상승 200선 위 조정 후 지지"] = (A.ma200>A.ma200_20)&(C/A.ma200).between(1.0,1.05)&(A.ret10<0)&up_c
R["G04 그랜빌4: 200선 -20% 급락 후 반등"]  = (C<=0.8*A.ma200)&up_c&(A.ret1>=2)
R["G04b 60선 -20% 급락 후 반등"]        = (C<=0.8*A.ma60)&up_c&(A.ret1>=2)
R["G04r 200선 +25% 과열(뒤집기)"]       = (C>=1.25*A.ma200)
R["M01 정배열 초기(5>20>60 전환 5일 내)"] = A.arr&(A.arr5==0)
R["M02 5/20 골든크로스"]              = (A.ma5>A.ma20)&(A.pma5<=A.pma20)
R["M02b 20/60 골든크로스"]            = (A.ma20>A.ma60)&(A.pma20<=A.pma60)
R["M03 상승 20일선 지지 매수"]          = (A.ma20>A.ma20_5)&(Ll<=A.ma20*1.01)&(C>A.ma20)&up_c
R["M04 눌림 후 60일선 지지 반등"]       = uptrend&(Ll<=A.ma60*1.02)&(C>A.ma60)&(A.ret10<0)&up_c
R["M05 이격도 20일 ≤95 매수"]          = (C/A.ma20<=0.95)&up_c
R["M05b 이격도 60일 ≤90 매수"]         = (C/A.ma60<=0.90)&up_c
R["M05r 이격도 20일 ≥105(뒤집기)"]     = (C/A.ma20>=1.05)
# 13~20 캔들
R["C01 망치형(하락 후)"]              = downtrend&(A.lsh>=2*A.body)&(A.ush<=0.3*A.body.clip(lower=1e-9)+0.1*A.rngc)&(A.body<=0.35*A.rngc)
R["C02 역망치(하락 후)"]              = downtrend&(A.ush>=2*A.body)&(A.lsh<=0.1*A.rngc)&(A.body<=0.35*A.rngc)
R["C03 잠자리 도지(하락 후)"]           = downtrend&(A.body<=0.05*A.rngc)&(A.lsh>=0.7*A.rngc)
R["C04 상승 장악형"]                  = downtrend&(A.pgreen==0)&up_c&(O<=A.pclose)&(C>=A.popen)&(A.body>A.pbody)
R["C05 관통형"]                      = downtrend&(A.pgreen==0)&up_c&(O<A.plow)&(C>(A.popen+A.pclose)/2)&(C<A.popen)
R["C06 샛별(갭 별+장대양봉)"]           = (A.pclose2<A.popen2)&(A.pbody<=0.3*A.body_avg*C)&(A.phigh<A.pclose2)&up_c&(C>(A.popen2+A.pclose2)/2)&(A.ret20.groupby(A.ticker).shift(2)<-10)
R["C07 적삼병(바닥권)"]               = A.red3&(A.ret20<-5)&(V>=A.v20)
R["C08 상승 잉태형+익일 양봉 확인"]      = (A.pclose2<A.popen2)&(A.pgreen==1)&(A.phigh<=A.popen2)&(A.plow>=A.pclose2)&up_c&(A.ret20.groupby(A.ticker).shift(2)<-10)
R["C09 상승삼법(장대양봉·3일 조정·재돌파)"] = (C>A.hi5p)&up_c&(A.ret5.groupby(A.ticker).shift(1)<=0)&(A.body/C>=A.body_avg*1.5)&((C.groupby(A.ticker).shift(4)-O.groupby(A.ticker).shift(4))/C>=A.body_avg*1.5)
R["C10 돌파갭(갭↑3%·거래량 2배·20일 고점 돌파)"] = (O>=A.pclose*1.03)&(V>=2*A.v20)&(C>A.hi20p)&up_c
R["C11 상승 타스키갭"]                = (A.pgap_up==1)&(A.pgreen==1)&(~up_c)&(C<A.popen)&(C>A.phigh2)&(A.dma20>0)
R["C12 섬꼴반전 바닥(갭↓ 후 갭↑)"]     = (A.pgap_dn>0)&A.gap_up&(O>A.phigh)&(A.ret20<-10)
# 26~39 보조지표
R["O01 스토 20 이하 K>D 교차"]         = (A.pstk<=20)&(A.pstk<=A.pstkd)&(A.stk>A.stkd)
R["O02 RSI 30 상향돌파"]              = (A.rsi_prev<30)&(A.rsi>=30)
R["O02b RSI 50 상향돌파"]             = (A.rsi_prev<50)&(A.rsi>=50)
R["O03 RSI 상승 다이버전스"]           = (A.lo20<A.lo20_20)&(A.rsi>A.rsi.groupby(A.ticker).shift(20))&(A.rsi<45)&up_c
R["O04 CCI -100 상향돌파"]            = (A.pcci<-100)&(A.cci>=-100)
R["O04b CCI 0선 상향돌파"]            = (A.pcci<0)&(A.cci>=0)
R["O05 DMI +DI 교차 익일 확인(고가 돌파)"] = (A.dmi_x_p==1)&(C>A.phigh)
R["O05b DMI 교차+ADX 상승"]           = (A.pdi>A.ndi)&(A.ppdi<=A.pndi)&(A.adx>A.adx5)
R["O06 파라볼릭 상승 전환+DMI 일치"]    = (A.sar_bull)&(A.psar_bull==0)&(A.pdi>A.ndi)
R["O07 볼린저 수축→상단 확장"]         = (A.bbw<=A.bbw_p20)&(C>A.bb_up)&up_c
R["O07b 볼린저 중심선 지지(상승 추세)"]   = uptrend&(Ll<=A.bb_mid*1.01)&(C>A.bb_mid)&up_c
R["O07c 볼린저 하단 이탈 후 재진입"]     = (A.plow<A.bb_dn.groupby(A.ticker).shift(1))&(C>A.bb_dn)&up_c
R["O08 MACD 0선 상향돌파"]            = (A.pmacd<0)&(A.macd>=0)
R["O08b MACD 시그널 골든크로스"]        = (A.phist<=0)&(A.mhist>0)
R["O08c MACD 오실레이터 반전(음→상승)"]  = (A.mhist<0)&(A.mhist>A.phist)&(A.phist<=A.phist2)
R["O09 삼선전환도 양전환"]             = (A.tlb==1)
R["O10 모멘텀(10) 100 상향돌파"]        = (A.pmom10<100)&(A.mom10>=100)
R["O10b ROC(12) 0선 상향돌파"]         = (A.proc<0)&(A.roc>=0)
R["O10c SROC 선행 반전 후 ROC 0 돌파"]   = (A.proc<0)&(A.roc>=0)&(A.sroc>A.psroc)&(A.psroc<=A.psroc2)
R["O11 투자심리선 ≤25"]               = (A.psy<=25)&up_c
R["O11r 투자심리선 ≥75(뒤집기)"]       = (A.psy>=75)
# 40~51 패턴
R["P01 원형바닥(120일 사발·거래량 증가)"]  = (A.ret120.abs()<=8)&(A.lo60<A.lo250*1.05)&(A.ret40>=8)&(A.v20>A.v60)&(C>A.ma60)
R["P02 V바닥: 10일 -20%↓ 첫 반등일"]    = (A.ret10<=-20)&up_c&(A.ret1>=3)
R["P03 깃발/패넌트 수렴 돌파(깃대 +30%·수축·거래량)"] = (A.ret60>=30)&((A.hi20p-A.lo20p)/C<=0.15)&(A.v5p<0.6*A.v60)&(C>A.hi20p)&(V>=2*A.v20)
R["P04 상승삼각형 돌파"]              = ((A.hi10p/A.hi20p-1).abs()<=0.01)&(A.lo10>A.lo20p*1.03)&(C>A.hi20p)&(V>=1.5*A.v20)
R["P05 박스 돌파(20일 폭≤15%·거래량)"]   = ((A.hi20p-A.lo20p)/C<=0.15)&(C>A.hi20p)&(V>=1.5*A.v20)&(A.dma60>0)
R["P06 박스 하단 매수(20일 폭 5~25%)"]   = ((A.hi20p-A.lo20p)/C).between(0.05,0.25)&(Ll<=A.lo20p*1.02)&(C>A.lo20p)&up_c
R["P07 주봉 밀집(120일 폭≤25%·거래량 최저)→상승"] = ((A.hi120p/A.lo250-1)<=0.25)&(A.v20p<=A.vmin120*1.1)&(V>=2*A.v20)&up_c
R["P08 이평선 수렴(5·20·60 3% 이내)→위로"] = ((np.maximum(np.maximum(A.ma5,A.ma20),A.ma60)/np.minimum(np.minimum(A.ma5,A.ma20),A.ma60)-1)<=0.03)&(C>A.ma5)&(C>A.ma20)&(C>A.ma60)&(V>=1.5*A.v20)&up_c
R["P09 N자: 상승 후 눌림 재상승(5일선 재돌파)"] = (A.ret40>=20)&(A.ret10.groupby(A.ticker).shift(1)<0)&(A.pclose<=A.pma5)&(C>A.ma5)&(V>A.v5p)
R["P10 하락쐐기 돌파(60일 +20% 후 15일 하락·5일 고점 돌파)"] = (A.ret60>=20)&(A.ret15<0)&(C>A.hi5p)&(A.v5p<0.7*A.v60)&up_c
# 매도 신호 — '그 뒤 정말 떨어지나' (기대: 유니버스보다 낮음)
S = {}
S["S01 5/20 데드크로스"]              = (A.ma5<A.ma20)&(A.pma5>=A.pma20)
S["S02 전고점 돌파 실패+거래량 터짐+하락"] = (A.phigh>=A.hi60p*0.98)&(C<A.pclose*0.97)&(V>=2*A.v20)
S["S03 흑운형"]                      = (A.ret20>10)&(A.pgreen==1)&(~up_c)&(O>A.phigh)&(C<(A.popen+A.pclose)/2)
S["S04 저녁별"]                      = (A.ret20.groupby(A.ticker).shift(2)>10)&(A.pgreen2==1)&(A.pbody<=0.3*A.body_avg*C)&(A.plow>A.pclose2)&(~up_c)&(C<(A.popen2+A.pclose2)/2)
S["S05 유성(상승 후 긴 윗꼬리)"]        = (A.ret20>10)&(A.ush>=2*A.body)&(A.lsh<=0.1*A.rngc)&(A.body<=0.35*A.rngc)
S["S06 흑삼병(고점권)"]               = A.blk3&(A.ret20.groupby(A.ticker).shift(3)>10)
S["S07 이격도 20일 ≥105"]             = (C/A.ma20>=1.05)
S["S08 RSI 70 하향돌파"]              = (A.rsi_prev>=70)&(A.rsi<70)
S["S09 스토 80 하향 교차"]             = (A.pstk>=80)&(A.pstk>=A.pstkd)&(A.stk<A.stkd)
S["S10 VR ≥300 과열"]                = (A.vr>=300)
S["S11 대량거래(3배) 급락"]            = (V>=3*A.v20)&(A.ret1<=-5)
S["S12 상승 추세선(60선) 이탈"]         = (A.pclose>=A.pma60)&(C<A.ma60)&(A.ma60>A.ma60_5)
S["S13 파라볼릭 하락 전환"]            = (~A.sar_bull)&(A.psar_bull==1)
S["S14 MACD 시그널 데드크로스"]         = (A.phist>=0)&(A.mhist<0)

# ── 실행 ─────────────────────────────────────────────────────────
HOLDS = (5,20,60)
print("=== 매수 규칙 (전 국면 · 고정 보유) ===")
hits=[]
for tag, cond in R.items():
    print(f"\n{tag}"); hdr()
    for h in HOLDS:
        Y = go(f"  {h}일", cond, hold=h, mk=MK, minn=40)
        if Y.attrs.get("ok"): hits.append((tag,h,len(Y),round(Y.r.mean(),2),round(Y.alpha.mean(),2),round(Y.r.median(),2)))
print("\n\n=== 매도 신호 — 신호 후 20일 절대수익 · 유니버스 대비 (음수 = 매도 신호가 맞다) ===")
b20 = base(20, mk=MK)
for tag, cond in S.items():
    u = BASEU.copy()
    if MK: u &= (A.mk==MK)
    Y = A[(u&cond).fillna(False)].dropna(subset=["n20"])
    if len(Y)<40: print(f"  {tag:<34} {len(Y):>6} (부족)"); continue
    print(f"  {tag:<34} {len(Y):>6}건  20일 {Y.n20.mean():>+6.2f}%  유니버스 {b20:>+5.2f}  차이 {Y.n20.mean()-b20:>+6.2f}  승률 {(Y.n20>0).mean():>4.0%}  중앙 {Y.n20.median():>+5.1f}")
print("\n\n=== 1단계 게이트 통과 ===")
for h in hits: print("  ", h)
print(f"  합계 {len(hits)}건" if hits else "  없음")
