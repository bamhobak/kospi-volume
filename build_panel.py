# -*- coding: utf-8 -*-
"""규칙용 패널을 DB 에서 직접 만든다 → data/panel_kp.pkl · data/panel_kq.pkl

왜 만들었나: 규칙이 읽는 kp_ow.pkl 은 kp_cap → kp_hz → kp_hz2 → kp_ow 로 이어지는
네 단계 체인의 산물인데, 마지막 단계를 만드는 코드가 리포지토리에 없었다(대화 중
일회성으로 만들어진 것). 그래서 2016~2017 백필을 받아 놓고도 패널에 넣을 수가
없었다(2026-09-03). 앞으로 재현 가능하도록 한 스크립트로 합친다.

계산은 bull_feat.py 의 정의를 그대로 따른다. 없는 보조 데이터(자사주·내부자·
신용잔고 등)는 portfolio.py 가 따로 붙이므로 여기서는 만들지 않는다.
폐지 종목도 함께 넣는다 — 빼면 생존편향이 생긴다.

사용: python build_panel.py [--from 20160101] [--market KOSPI|KOSDAQ]
"""
import io, sys, csv, sqlite3, logging
from collections import defaultdict
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("panel")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FROM = arg("--from", "20160101")
MKTS = [arg("--market", None)] if "--market" in sys.argv else ["KOSPI", "KOSDAQ"]
HZ = [1,2,3,4,5,7,10,12,15,20,25,30,40,50,60]

# 업종: 운영 기준은 industry.csv(KRX 표준산업분류)다 — 사이트(pipeline.fill_sr60)와
# 백테스트가 이걸로 통일돼 있다. 다만 폐지 종목은 industry.csv 에 없어서(현재 상장분만)
# ksic.csv(DART · 앞 3자리 중분류)로 메운다. 폐지 종목을 빼면 생존편향이 생긴다.
IND = {}
for r in csv.DictReader(open(BASE/"data"/"industry.csv", encoding="utf-8-sig")):
    if r.get("ticker") and r.get("industry"): IND[r["ticker"]] = r["industry"]
KS = {}
for r in csv.DictReader(open(BASE/"data"/"ksic.csv", encoding="utf-8-sig")):
    k = r.get("ksic") or ""
    if r.get("ticker") and k: KS[r["ticker"]] = "KSIC" + k[:3]
SECT = dict(KS); SECT.update(IND)      # industry.csv 가 우선, 없으면 ksic
log.info(f"업종: industry.csv {len(IND):,} + ksic 보완 {len(set(KS)-set(IND)):,} = {len(SECT):,}종목")

_d = sqlite3.connect(f"file:{BASE}/data/dart/disclosures.db?mode=ro", uri=True, timeout=600)
dz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE "
   "replace(report_nm,' ','') LIKE '%유상증자결정%' "
   "OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%' "
   "OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'", _d); _d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
log.info(f"희석 공시 {len(dz):,}건 · {dz.rcept_dt.min()}~{dz.rcept_dt.max()}")

IX = fdr.DataReader("KS11", "2014-06-01"); IX = IX[IX.Close > 0]
IX.index = IX.index.strftime("%Y%m%d")

def build(mkt):
    log.info(f"── {mkt} ──")
    c = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True, timeout=600)
    q = ("SELECT date,ticker,name,open,high,low,close,volume,frgn,organ,marcap,shares,short_ratio "
         "FROM daily WHERE market=? AND close>0 AND open>0 AND date>=? ORDER BY ticker,date")
    df = pd.read_sql(q, c, params=(mkt, FROM)); c.close()
    # 코스닥 2018~ 은 kosdaq.db 에 따로 있다(리포지토리 용량 때문에 분리). 합치지 않으면
    # 코스닥 패널이 백필분(2016~17)만 담긴 반쪽이 된다.
    if mkt == "KOSDAQ" and (BASE/"data"/"kosdaq.db").exists():
        c = sqlite3.connect(f"file:{BASE}/data/kosdaq.db?mode=ro", uri=True, timeout=600)
        cols = {r[1] for r in c.execute("PRAGMA table_info(daily)")}
        sel = "date,ticker,name,open,high,low,close,volume,frgn,organ"
        for extra in ("marcap","shares","short_ratio"):
            sel += "," + extra if extra in cols else ",NULL AS " + extra
        E = pd.read_sql("SELECT " + sel + " FROM daily WHERE close>0 AND open>0 AND date>=?",
                        c, params=(FROM,)); c.close()
        have = set(zip(df.ticker, df.date))
        E = E[[(t,d) not in have for t,d in zip(E.ticker, E.date)]]
        if len(E): df = pd.concat([df, E], ignore_index=True)
        log.info(f"  kosdaq.db 에서 {len(E):,}행 추가")
    df["grp"] = "생존"
    for dbf in ("delisted.db", "delisted_kd.db"):
        p = BASE/"data"/dbf
        if not p.exists(): continue
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=600)
        try:
            cols = {r[1] for r in c.execute("PRAGMA table_info(daily)")}
            sel = "date,ticker,name,open,high,low,close,volume,frgn,organ"
            for extra in ("marcap","shares","short_ratio"):
                sel += "," + extra if extra in cols else ",NULL AS " + extra
            D = pd.read_sql("SELECT " + sel + " FROM daily WHERE close>0 AND open>0 AND date>=?",
                            c, params=(FROM,))
            D = D[~D.ticker.isin(set(df.ticker))]
            if len(D):
                D["grp"] = "폐지"; df = pd.concat([df, D], ignore_index=True)
                log.info(f"  폐지 {dbf}: {D.ticker.nunique()}종목 {len(D):,}행 추가")
        except Exception as e: log.warning(f"  {dbf} 건너뜀: {str(e)[:70]}")
        c.close()
    df = df.sort_values(["ticker","date"]).reset_index(drop=True)
    dates = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(dates)}
    log.info(f"  {df.ticker.nunique()}종목 {len(df):,}행 {dates[0]}~{dates[-1]}")

    g = df.groupby("ticker", sort=False)
    V, C = df.volume.astype(float), df.close
    sr = df.short_ratio.astype(float)
    df["sr20"] = sr.groupby(df.ticker).transform(lambda x: x.rolling(20).mean())
    df["srd"] = (sr.groupby(df.ticker).transform(lambda x: x.rolling(5).mean()) < df.sr20)
    few = sr.groupby(df.ticker).transform(lambda x: x.rolling(20).count()) < 20
    df.loc[few, "srd"] = np.nan
    df["vm1"] = V; df["vm3"] = g["volume"].transform(lambda x: x.rolling(3).mean())
    df["a40"] = g["volume"].transform(lambda x: x.shift(3).rolling(40).mean())
    df["a240"] = g["volume"].transform(lambda x: x.shift(43).rolling(240).mean())
    df["r16"] = df.a40/df.a240*100
    df["rw1"] = df.vm3/df.a40*100
    df["su1"] = df.vm1/g["volume"].transform(lambda x: x.shift(1).rolling(20).mean())
    amt = V*C
    df["amt20"] = amt.groupby(df.ticker).transform(lambda x: x.rolling(20).mean())/1e8
    df["amt"] = amt.groupby(df.ticker).transform(lambda x: x.rolling(40).mean()).shift(3)/1e8
    for w in (5,20,60):
        vs = g["volume"].transform(lambda x, w=w: x.rolling(w).sum()).replace(0, np.nan)
        df["fw%d" % w] = g["frgn"].transform(lambda x, w=w: x.fillna(0).rolling(w).sum())/vs*100
        df["ow%d" % w] = g["organ"].transform(lambda x, w=w: x.fillna(0).rolling(w).sum())/vs*100
    for n in (3,5,10,20,60,120):
        df["ret%d" % n] = g.close.transform(lambda x, n=n: x/x.shift(n)-1)*100
    for w in (5,20,60,120):
        df["ma%d" % w] = g.close.transform(lambda x, w=w: x.rolling(w).mean())
        df["dma%d" % w] = (C/df["ma%d" % w]-1)*100
    df["hi250"] = g.close.transform(lambda x: x.rolling(250, min_periods=60).max())
    df["lo250"] = g.close.transform(lambda x: x.rolling(250, min_periods=60).min())
    df["fromhi"] = (C/df.hi250-1)*100
    df["fromlo"] = (C/df.lo250-1)*100
    df["vol20"] = g.close.transform(lambda x: (x/x.shift(1)-1).rolling(20).std())*100
    df["rng"] = (df.high-df.low)/C*100
    df["clv"] = np.where(df.high > df.low, (C-df.low)/(df.high-df.low), 0.5)
    df["hi60"] = g.close.transform(lambda x: x.rolling(60, min_periods=20).max())
    df["dd"] = (C/df.hi60-1)*100                      # 60일 고점 대비 현재 낙폭
    # mdd60 = 최근 60일 중 겪은 가장 깊은 낙폭(dd 의 60일 최소값). 현재 낙폭이 아니다.
    df["mdd60"] = df.dd.groupby(df.ticker).transform(lambda x: x.rolling(60, min_periods=20).min())
    df["y"] = df.date.str[:4].astype(int)
    df["buy"] = g.open.shift(-1)
    df["gap"] = (df.buy/C-1)*100
    df["cost"] = 0.18 + np.select([df.amt20>=100, df.amt20>=50, df.amt20>=20, df.amt20>=10],
                                  [.20,.30,.50,.70], default=1.00)
    ds = pd.to_datetime(df.date); dil = np.zeros(len(df), bool)
    for t, idx in df.groupby("ticker").indices.items():
        L = pd.to_datetime(DIL.get(t, []))
        if len(L) == 0: continue
        v = ds.values[idx]
        dil[idx] = ((L.values[None,:] >= v[:,None]-np.timedelta64(90,"D")) &
                    (L.values[None,:] <= v[:,None])).any(axis=1)
    df["dil"] = dil
    pc = g.close.shift(1); jj = (C/pc).where(pc > 0)
    badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
    bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
    for t, sub in df[badday].groupby("ticker"):
        idx = df.index[df.ticker == t].values
        bp = np.sort(sub.date.map(DI).values); p = pos[idx]
        qq = np.searchsorted(bp, p, side="right")
        bad[idx[(qq < len(bp)) & (bp[np.minimum(qq, len(bp)-1)] - p <= 42)]] = True
    df["bad"] = bad
    df["up"] = df.ticker.map(SECT)
    d2 = df[df.up.notna()].dropna(subset=["ret60"])
    gm = d2.groupby(["date","up"]).ret60
    m = gm.median()[gm.size() >= 5]
    df["u"] = pd.MultiIndex.from_arrays([df.date, df.up]).map(m)
    lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last")
    mypos = df.date.map(DI)
    for h in HZ:
        sell = g.close.shift(-h).where(~(mypos+h > lastpos), lastclose)
        df["n%d" % h] = (sell/df.buy-1)*100 - df.cost
    fn = "panel_kp.pkl" if mkt == "KOSPI" else "panel_kq.pkl"
    df.to_pickle(BASE/"data"/fn)
    log.info(f"  저장 {fn} · {len(df):,}행 {len(df.columns)}컬럼")

for mkt in MKTS: build(mkt)
