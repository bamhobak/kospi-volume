# -*- coding: utf-8 -*-
"""횡보장 매매법 5종 실측 — 유튜브 기법을 국내 일봉·롱온리로 옮겨 잰다.

왜: 우리 9규칙은 시간의 73% 인 횡보장에서 사실상 본전이다(324건 중앙 +0.94%).
그 구멍을 메울 규칙이 있는지 본다. 원본은 대부분 선물·코인·분봉·양방향이라
국내 현물에 맞게 바꿨다 — 롱만, 일봉, 다음날 시가 매수, 우리 유니버스(대형·중형).

방법
  M1 스토캐스틱+RSI+MACD   최근 3일 내 %K<20 · RSI 50 상향돌파 · MACD 골든(2일 내) · %K<80
  M2a 박스 지지 반등        20일 박스폭 5~25% · 저가가 박스 하단 2% 이내 · 양봉
  M2b 변동성 압축 돌파       볼린저폭 120일 하위 20% · 전 20일 고점 돌파 · 거래량 2배 · 몸통 2%+
  M3 볼린저 하단 반등        저가가 하단 터치(오늘/어제) · 종가는 하단 위 · 60일선 위
  M5 일목 구름 지지          양운 · 종가가 구름 위 · 3일 내 구름 상단 터치 · 양봉
  (3번의 '시그널'·5번의 '번개구름' 은 비공개 지표라 표준 지표로 대체했다)

청산 두 가지를 다 본다
  고정 보유(10·20일)      우리 규칙과 같은 잣대 → techlib.go() 의 게이트로 판정
  손절/익절 경로 청산      영상이 말한 방식 → 전저점 손절 · 손절폭×1.5(M3 은 ×3) 익절 · 최장 20일

판정은 techlib 과 같다: 학습CI>0 · 붐제외CI>0 · 중앙>0 · 붐제외중앙>0 · 상위5%제거>0.
국면은 코스피 60일선 이격 ±5% (SIDE/UP/DN). 횡보(SIDE)에서 통하는지가 핵심이다.
지표는 한 번 계산해 data/tech_ind.pkl 에 캐시한다.
사용: python sideways_test.py [--rebuild]
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
from techlib import *          # A, BASEU, base, go, boot, f, hdr, BASE
IND = BASE/"data/tech_ind.pkl"
t0 = time.time()
def log(m): print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

# ── 지표 ──────────────────────────────────────────────────────────
def build_ind():
    log("지표 계산 시작")
    gg = A.groupby("ticker", sort=False)
    I = pd.DataFrame(index=A.index)
    I["ticker"] = A.ticker.values; I["date"] = A.date.values
    C, L = A.close, A.low
    # 스토캐스틱 14/3
    l14 = gg.low.transform(lambda s: s.rolling(14).min()); h14 = gg.high.transform(lambda s: s.rolling(14).max())
    K = (C-l14)/(h14-l14).replace(0,np.nan)*100
    I["stk"] = K; I["stk_min3"] = K.groupby(A.ticker).transform(lambda s: s.rolling(3).min())
    log("  스토캐스틱")
    # RSI 14 (Wilder)
    d = gg.close.diff(); up = d.clip(lower=0); dn = (-d).clip(lower=0)
    au = up.groupby(A.ticker).transform(lambda s: s.ewm(alpha=1/14, adjust=False).mean())
    ad = dn.groupby(A.ticker).transform(lambda s: s.ewm(alpha=1/14, adjust=False).mean())
    rsi = 100 - 100/(1+au/ad.replace(0,np.nan)); I["rsi"] = rsi
    I["rsi_prev"] = rsi.groupby(A.ticker).shift(1)
    log("  RSI")
    # MACD 12/26/9
    e12 = gg.close.transform(lambda s: s.ewm(span=12, adjust=False).mean())
    e26 = gg.close.transform(lambda s: s.ewm(span=26, adjust=False).mean())
    macd = e12-e26; sig = macd.groupby(A.ticker).transform(lambda s: s.ewm(span=9, adjust=False).mean())
    hist = macd-sig
    hp = hist.groupby(A.ticker).shift(1); hp2 = hist.groupby(A.ticker).shift(2)
    I["mgold2"] = (((hist>0)&(hp<=0)) | ((hp>0)&(hp2<=0))).fillna(False)   # 2일 내 골든크로스
    log("  MACD")
    # 볼린저 20/2
    m20 = gg.close.transform(lambda s: s.rolling(20).mean()); s20 = gg.close.transform(lambda s: s.rolling(20).std())
    I["bb_dn"] = m20-2*s20
    I["bb_dn_prev"] = I.bb_dn.groupby(A.ticker).shift(1)
    bbw = (4*s20)/m20; I["bbw"] = bbw
    I["bbw_p20"] = bbw.groupby(A.ticker).transform(lambda s: s.rolling(120, min_periods=60).quantile(0.2))
    I["lo_prev"] = L.groupby(A.ticker).shift(1)
    log("  볼린저")
    # 일목 9/26/52 (선행스팬은 26일 앞으로 — 오늘 보는 구름은 26일 전 계산값)
    t9 = (gg.high.transform(lambda s: s.rolling(9).max())+gg.low.transform(lambda s: s.rolling(9).min()))/2
    k26 = (gg.high.transform(lambda s: s.rolling(26).max())+gg.low.transform(lambda s: s.rolling(26).min()))/2
    sa = ((t9+k26)/2).groupby(A.ticker).shift(26)
    sb = ((gg.high.transform(lambda s: s.rolling(52).max())+gg.low.transform(lambda s: s.rolling(52).min()))/2).groupby(A.ticker).shift(26)
    I["ctop"] = np.maximum(sa,sb); I["cbot"] = np.minimum(sa,sb); I["cgreen"] = (sa>sb).fillna(False)
    I["ctop_touch3"] = ((L<=I.ctop).astype(float).groupby(A.ticker).transform(lambda s: s.rolling(3).max())>0)
    log("  일목")
    # 손절 기준: 전 10일 저점(오늘 제외) · 박스 상하단(오늘 제외)
    I["lo10p"] = gg.low.transform(lambda s: s.rolling(10).min()).groupby(A.ticker).shift(1)
    I["lo20p"] = A.lo20.groupby(A.ticker).shift(1); I["hi20p"] = A.hi20.groupby(A.ticker).shift(1)
    I.to_pickle(IND); log(f"지표 캐시 저장 {IND.name}")
    return I
if IND.exists() and "--rebuild" not in sys.argv:
    I = pd.read_pickle(IND)
    assert len(I)==len(A) and I.ticker.iloc[0]==A.ticker.iloc[0] and I.date.iloc[-1]==A.date.iloc[-1], "캐시가 패널과 안 맞음 — --rebuild"
    log("지표 캐시 로드")
else:
    I = build_ind()
for c in I.columns:
    if c not in ("ticker","date"): A[c] = I[c].values
del I

# ── 조건 ──────────────────────────────────────────────────────────
up_candle = (A.close>A.open)
box_w = (A.hi20p-A.lo20p)/A.close
M = {
 "M1 스토+RSI+MACD":  (A.stk_min3<=20)&(A.rsi_prev<50)&(A.rsi>=50)&(A.mgold2)&(A.stk<80),
 "M2a 박스 지지반등":   box_w.between(0.05,0.25)&(A.low<=A.lo20p*1.02)&(A.close>A.lo20p)&up_candle,
 "M2b 압축 돌파":     (A.bbw<=A.bbw_p20)&(A.close>A.hi20p)&(A.volume>2*A.v20)&(((A.close-A.open)/A.open)>=0.02),
 "M3 볼린저 하단반등":  ((A.low<=A.bb_dn)|(A.lo_prev<=A.bb_dn_prev))&(A.close>A.bb_dn)&(A.close>A.ma60),
 "M5 일목 구름지지":    (A.cgreen)&(A.close>A.ctop)&(A.ctop_touch3)&up_candle,
}
# 손절/익절 기준 (경로 청산용)
STOP = {"M1 스토+RSI+MACD": A.lo10p, "M2a 박스 지지반등": A.lo20p*0.97, "M2b 압축 돌파": A.close*0.93,
        "M3 볼린저 하단반등": A.bb_dn*0.98, "M5 일목 구름지지": A.cbot}
RR   = {"M1 스토+RSI+MACD": 1.5, "M2a 박스 지지반등": None, "M2b 압축 돌파": None, "M3 볼린저 하단반등": 3.0, "M5 일목 구름지지": None}
TGT  = {"M2a 박스 지지반등": A.hi20p}     # 박스는 상단이 익절

# ── 경로 청산 ──────────────────────────────────────────────────────
O = A.open.to_numpy(); Hh = A.high.to_numpy(); Ll = A.low.to_numpy(); Cc = A.close.to_numpy()
TK = A.ticker.to_numpy(); COST = A.cost.to_numpy()
def path_ret(idx, stop, tgt, max_hold=20):
    """idx 행에서 신호 → 다음날 시가 매수 → 손절/익절/최장보유 중 먼저 오는 것으로 청산. 수익률(%)"""
    out = np.full(len(idx), np.nan)
    for n,i in enumerate(idx):
        e = i+1
        if e>=len(O) or TK[e]!=TK[i] or not O[e]>0: continue
        buy = O[e]; s = stop[n]; t = tgt[n]
        if s==s and s>=buy: s = buy*0.97           # 손절선이 진입가 위면 -3% 로
        r = None; last = e
        for j in range(e, min(e+max_hold, len(O))):
            if TK[j]!=TK[i]: break
            last = j
            if s==s and Ll[j]<=s: r = (s/buy-1)*100; break
            if t==t and Hh[j]>=t: r = (t/buy-1)*100; break
        if r is None: r = (Cc[last]/buy-1)*100
        out[n] = r - COST[i]
    return out
def report_path(tag, cond, reg, hold=20):
    u = BASEU & (A.reg==reg) if reg else BASEU
    X = A[(u&cond).fillna(False)].sort_values("di")
    keep,last=[],{}
    for r in X.itertuples():
        if last.get(r.ticker,-10**9)>=r.di: continue
        last[r.ticker]=r.di+hold; keep.append(r.Index)
    Y = X.loc[keep].copy()
    if len(Y)<40: print(f"  {tag:<34} {len(Y):>5} (부족)"); return
    stop = STOP[tag].loc[Y.index].to_numpy(dtype=float); buy = Y.buy.to_numpy(dtype=float)
    if tag in TGT: tgt = TGT[tag].loc[Y.index].to_numpy(dtype=float)
    elif RR[tag]:
        s_eff = np.where(np.isnan(stop)|(stop>=buy), buy*0.97, stop)
        tgt = buy + RR[tag]*(buy-s_eff)
    else: tgt = np.full(len(Y), np.nan)
    Y["r"] = path_ret(Y.index.to_numpy(), stop, tgt, hold)
    Y = Y.dropna(subset=["r"]); Y["ym"]=Y.date.str[:6]; Y["yr"]=Y.date.str[:4]
    IS=Y[Y.date<"20230101"]; OS=Y[Y.date>="20230101"]; NB=Y[Y.yr<"2025"]
    ca=boot(IS.r.values,IS.ym.values); cn=boot(NB.r.values,NB.ym.values) if len(NB)>=25 else None
    trim=Y[Y.r<Y.r.quantile(.95)].r.mean(); top=Y.yr.value_counts().max()/len(Y)
    ok=(ca is not None and ca[0]>0 and cn is not None and cn[0]>0 and Y.r.median()>0 and NB.r.median()>0 and trim>0)
    print(f"  {tag:<34} {len(Y):>5} {Y.r.mean():>6.2f} {'':>6} {IS.r.mean():>6.2f} {OS.r.mean():>6.2f} {NB.r.mean():>6.2f} "
          f"{(Y.r>0).mean():>4.0%} {Y.r.median():>6.1f} {trim:>6.2f} {top:>5.0%} {f(ca):>13} {f(cn):>13}{'  ✅' if ok else ''}")

# ── 실행 ──────────────────────────────────────────────────────────
print(f"\n유니버스: 보통주 · 주가≥1000 · 희석공시 없음 · 거래대금≥30억 · {A.date.min()}~{A.date.max()}")
print(f"국면: SIDE {int((A.reg=='SIDE').sum()/len(A)*100)}% / UP / DN (코스피 60일선 이격 ±5%)")
for reg in ("SIDE", None, "DN", "UP"):
    for hold in (10, 20):
        print(f"\n━━ 고정 {hold}일 보유 · 국면 {reg or '전체'} · 유니버스 평균 {base(hold, reg=reg):+.2f}% ━━"); hdr()
        for tag, cond in M.items(): go(tag, cond, hold=hold, reg=reg)
print(f"\n━━ 손절/익절 경로 청산 (영상 방식) · 국면 SIDE · 최장 20일 ━━")
print(f"  {'조건':<34} {'n':>5} {'전체':>6} {'':>6} {'IS':>6} {'OS':>6} {'붐제외':>6} {'승률':>4} {'중앙':>6} {'상5뺀':>6} {'최다年':>5} {'IS절대CI':>13} {'붐제외CI':>13}")
for tag, cond in M.items(): report_path(tag, cond, "SIDE")
print(f"\n━━ 손절/익절 경로 청산 · 국면 전체 ━━")
for tag, cond in M.items(): report_path(tag, cond, None)
log("끝")
