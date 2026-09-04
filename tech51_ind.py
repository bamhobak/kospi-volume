# -*- coding: utf-8 -*-
"""유튜브 51편(거래량·추세·캔들·보조지표·패턴) 실측용 지표 — techlib 패널에 붙여 캐시한다.
사용: from tech51_ind import *   (A 에 열이 채워진 채로 돌아온다)
"""
import sys, time
import numpy as np, pandas as pd
from techlib import *
IND2 = BASE/"data/tech_ind2.pkl"
t0 = time.time()
def log(m): print(f"[{(time.time()-t0)/60:5.1f}분] {m}", flush=True)

# 이미 있는 캐시(스토·RSI·MACD·볼린저)
I0 = pd.read_pickle(BASE/"data/tech_ind.pkl"); assert len(I0)==len(A)
for c in ("stk","stk_min3","rsi","rsi_prev","mgold2","bb_dn","bbw","bbw_p20","hi20p","lo20p","lo10p"): A[c] = I0[c].values
del I0

def build():
    gg = A.groupby("ticker", sort=False)
    I = pd.DataFrame(index=A.index); I["ticker"]=A.ticker.values; I["date"]=A.date.values
    O,Hh,Ll,C,V = A.open,A.high,A.low,A.close,A.volume
    tk = A.ticker
    def sh(s,n=1): return s.groupby(tk).shift(n)
    def roll(s,n,fn="mean",minp=None):
        return s.groupby(tk).transform(lambda x: getattr(x.rolling(n, min_periods=minp),fn)())
    def ema(s,n): return s.groupby(tk).transform(lambda x: x.ewm(span=n, adjust=False).mean())
    # ── 거래량 ──
    I["v5p"]=sh(A.v5); I["v20p"]=sh(A.v20); I["v25"]=roll(V,25); I["v100"]=roll(V,100)
    I["v25_10"]=sh(I.v25,10); I["v100_10"]=sh(I.v100,10)
    I["vmin120"]=roll(A.v20,120,"min"); I["v20min120_5"]=sh(I.vmin120,5)
    I["v5_5"]=sh(A.v5,5); I["v60_5"]=sh(A.v60,5)
    I["pclose"]=sh(C); I["popen"]=sh(O); I["phigh"]=sh(Hh); I["plow"]=sh(Ll); I["pvol"]=sh(V)
    I["pclose2"]=sh(C,2); I["popen2"]=sh(O,2); I["phigh2"]=sh(Hh,2); I["plow2"]=sh(Ll,2)
    I["pclose3"]=sh(C,3); I["popen3"]=sh(O,3)
    log("거래량·전일값")
    # OBV
    sgn = np.sign(C.groupby(tk).diff()).fillna(0)
    obv = (sgn*V).groupby(tk).cumsum(); I["obv"]=obv
    I["obv_hi60p"]=sh(roll(obv,60,"max")); I["obv_lo20"]=roll(obv,20,"min"); I["obv_lo20_20"]=sh(I.obv_lo20,20)
    I["lo20_20"]=sh(A.lo20,20)
    # VR(25): 상승일 거래량 / 하락일 거래량 (보합은 반씩)
    upv = V.where(sgn>0,0.0); dnv = V.where(sgn<0,0.0); eqv = V.where(sgn==0,0.0)
    I["vr"] = (roll(upv,25,"sum")+roll(eqv,25,"sum")/2)/(roll(dnv,25,"sum")+roll(eqv,25,"sum")/2).replace(0,np.nan)*100
    log("OBV·VR")
    # ── 이평·추세 ──
    I["ma100"]=roll(C,100); I["ma200"]=roll(C,200,minp=150); I["ma10"]=roll(C,10)
    I["ma200_20"]=sh(I.ma200,20); I["ma120_20"]=sh(A.ma120,20); I["ma60_5"]=sh(A.ma60,5); I["ma20_5"]=sh(A.ma20,5)
    I["pma5"]=sh(A.ma5); I["pma20"]=sh(A.ma20); I["pma60"]=sh(A.ma60); I["pma200"]=sh(I.ma200); I["pma120"]=sh(A.ma120)
    I["hi60p"]=sh(roll(Hh,60,"max")); I["hi120p"]=sh(A.hi120); I["hi250p"]=sh(A.hi250)
    I["hi10p"]=sh(roll(Hh,10,"max")); I["lo10"]=roll(Ll,10,"min"); I["lo60"]=roll(Ll,60,"min"); I["lo60p"]=sh(I.lo60)
    I["hi5p"]=sh(roll(Hh,5,"max")); I["lo5p"]=sh(roll(Ll,5,"min"))
    # 60일 저점→20일 고점 스윙과 되돌림(피보나치)
    swing = (A.hi20-I.lo60); I["retr"] = (A.hi20-C)/swing.replace(0,np.nan)      # 0=고점, 1=저점
    I["swing_pct"] = (A.hi20/I.lo60-1)*100
    # 20일선 아래 있었나(최근 5일 중 종가<20일선인 날), 이탈 후 3일 내 복귀(약세함정)
    below20 = (C<A.ma20).astype(float); I["below20_3"]=sh(roll(below20,3,"max"))
    belowlo20 = (C<A.lo20p).astype(float); I["brk_lo20_3"]=sh(roll(belowlo20,3,"max"))
    below60 = (C<A.ma60).astype(float); I["below60_5"]=sh(roll(below60,5,"max"))
    below200 = (C<I.ma200).astype(float); I["below200_5"]=sh(roll(below200,5,"max"))
    arr = (A.ma5>A.ma20)&(A.ma20>A.ma60); I["arr"]=arr; I["arr5"]=sh(arr.astype(float),5)
    I["ret15"]=(C/sh(C,15)-1)*100; I["ret40"]=(C/sh(C,40)-1)*100
    log("이평·추세")
    # ── 캔들 ──
    body=(C-O).abs(); rng=(Hh-Ll).replace(0,np.nan)
    I["body"]=body; I["lsh"]=np.minimum(O,C)-Ll; I["ush"]=Hh-np.maximum(O,C); I["rngc"]=rng
    I["pbody"]=sh(body); I["pgreen"]=sh((C>O).astype(float)); I["pgreen2"]=sh((C>O).astype(float),2)
    I["body_avg"]=roll(body/C,20)   # 평균 몸통 비율 — '긴 몸통' 판단
    I["gap_up"]=(O>sh(Hh)); I["gap_dn"]=(O<sh(Ll)); I["pgap_dn"]=sh(I.gap_dn.astype(float)); I["pgap_up"]=sh(I.gap_up.astype(float))
    I["pgap_dn2"]=sh(I.gap_dn.astype(float),2)
    # 적삼병: 3일 연속 양봉·종가 상승
    grn=(C>O).astype(float); upc=(C>sh(C)).astype(float)
    I["red3"]=(roll(grn,3,"sum")==3)&(roll(upc,3,"sum")==3)
    I["blk3"]=(roll((C<O).astype(float),3,"sum")==3)&(roll((C<sh(C)).astype(float),3,"sum")==3)
    log("캔들")
    # ── 보조지표 ──
    # 스토 %D(3일)
    I["stkd"]=roll(A.stk,3); I["pstk"]=sh(A.stk); I["pstkd"]=sh(I.stkd)
    # CCI 14
    tp=(Hh+Ll+C)/3; tpm=roll(tp,14); md=(tp-tpm).abs().groupby(tk).transform(lambda x: x.rolling(14).mean())
    cci=(tp-tpm)/(0.015*md.replace(0,np.nan)); I["cci"]=cci; I["pcci"]=sh(cci)
    # DMI/ADX 14 (Wilder)
    upm=Hh-sh(Hh); dnm=sh(Ll)-Ll
    pdm=pd.Series(np.where((upm>dnm)&(upm>0),upm,0.0),index=A.index); ndm=pd.Series(np.where((dnm>upm)&(dnm>0),dnm,0.0),index=A.index)
    tr=np.maximum(Hh-Ll,np.maximum((Hh-sh(C)).abs(),(Ll-sh(C)).abs()))
    def wilder(s): return s.groupby(tk).transform(lambda x: x.ewm(alpha=1/14, adjust=False).mean())
    atr=wilder(tr); pdi=100*wilder(pdm)/atr.replace(0,np.nan); ndi=100*wilder(ndm)/atr.replace(0,np.nan)
    dx=100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan); adx=wilder(dx)
    I["pdi"]=pdi; I["ndi"]=ndi; I["adx"]=adx; I["ppdi"]=sh(pdi); I["pndi"]=sh(ndi); I["adx5"]=sh(adx,5); I["atr"]=atr
    # DMI 교차 익일 확인용: 어제 교차 & 어제 고가
    I["dmi_x_p"]=sh(((pdi>ndi)&(sh(pdi)<=sh(ndi))).astype(float))
    log("스토·CCI·DMI")
    # MACD
    e12=ema(C,12); e26=ema(C,26); macd=e12-e26; sig=ema(macd,9); hist=macd-sig
    I["macd"]=macd; I["pmacd"]=sh(macd); I["msig"]=sig; I["hist"]=hist; I["phist"]=sh(hist); I["phist2"]=sh(hist,2)
    # 모멘텀·ROC·SROC
    I["mom10"]=C/sh(C,10)*100; I["pmom10"]=sh(I.mom10)
    roc=(C/sh(C,12)-1)*100; I["roc"]=roc; I["proc"]=sh(roc); sroc=ema(roc,13); I["sroc"]=sroc; I["psroc"]=sh(sroc); I["psroc2"]=sh(sroc,2)
    # 투자심리선 12
    I["psy"]=roll(upc,12,"sum")/12*100
    # 볼린저 상단·중심
    m20=roll(C,20); s20=C.groupby(tk).transform(lambda x: x.rolling(20).std()); I["bb_up"]=m20+2*s20; I["bb_mid"]=m20; I["pbb_up"]=sh(I.bb_up)
    log("MACD·모멘텀·심리선")
    # 파라볼릭 SAR (0.02/0.2) — 종목별 루프
    log("파라볼릭 SAR 계산(루프)")
    o=O.to_numpy(float); h=Hh.to_numpy(float); l=Ll.to_numpy(float); c=C.to_numpy(float); t=tk.to_numpy()
    n=len(A); sar=np.full(n,np.nan); bull=np.zeros(n,bool)
    start=np.r_[0,np.flatnonzero(t[1:]!=t[:-1])+1, n]
    for a,b in zip(start[:-1],start[1:]):
        if b-a<3: continue
        up=True; af=0.02; ep=h[a]; s=l[a]
        for i in range(a+1,b):
            if not (h[i]==h[i] and l[i]==l[i]): sar[i]=s; bull[i]=up; continue
            s = s+af*(ep-s)
            if up:
                s=min(s,l[i-1],l[i-2] if i-2>=a else l[i-1])
                if l[i]<s: up=False; s=ep; ep=l[i]; af=0.02
                elif h[i]>ep: ep=h[i]; af=min(af+0.02,0.2)
            else:
                s=max(s,h[i-1],h[i-2] if i-2>=a else h[i-1])
                if h[i]>s: up=True; s=ep; ep=h[i]; af=0.02
                elif l[i]<ep: ep=l[i]; af=min(af+0.02,0.2)
            sar[i]=s; bull[i]=up
    I["sar"]=sar; I["sar_bull"]=bull; I["psar_bull"]=sh(pd.Series(bull.astype(float),index=A.index))
    log("파라볼릭 SAR")
    # 삼선전환도 — 종목별 루프 (종가 기준)
    log("삼선전환도 계산(루프)")
    tlb=np.zeros(n,np.int8)   # +1 양전환 발생일, -1 음전환 발생일
    for a,b in zip(start[:-1],start[1:]):
        if b-a<5: continue
        lines=[]  # (lo,hi,dir)
        d=0
        for i in range(a,b):
            x=c[i]
            if x!=x: continue
            if not lines: lines.append((x,x,0)); continue
            lo,hi,_=lines[-1]
            if d>=0 and x>hi:            # 상승선 추가
                lines.append((hi,x,1)); d=1
            elif d<=0 and x<lo:
                lines.append((x,lo,-1)); d=-1
            elif d==1:
                k=[q for q in lines[-3:] if q[2]==1]
                if len(k)==3 and x<min(q[0] for q in k): lines.append((x,k[0][0],-1)); d=-1; tlb[i]=-1
            elif d==-1:
                k=[q for q in lines[-3:] if q[2]==-1]
                if len(k)==3 and x>max(q[1] for q in k): lines.append((k[0][1],x,1)); d=1; tlb[i]=1
            if len(lines)>10: lines=lines[-10:]
    I["tlb"]=tlb
    log("삼선전환도")
    I.to_pickle(IND2); log(f"캐시 저장 {IND2.name}")
    return I

if IND2.exists() and "--rebuild" not in sys.argv:
    I=pd.read_pickle(IND2); assert len(I)==len(A) and I.date.iloc[-1]==A.date.iloc[-1], "캐시가 패널과 안 맞음 — --rebuild"
    log("지표 캐시 로드")
else:
    I=build()
for c in I.columns:
    if c not in ("ticker","date"): A["mhist" if c=="hist" else c]=I[c].values   # hist 는 DataFrame.hist 와 충돌
del I
