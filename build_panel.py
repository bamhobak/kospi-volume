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

# 업종 이력 — KRX 업종 지수의 분기별 구성 종목(collect_sector_hist.py 가 쌓는다).
# 예전엔 현재 스냅샷 하나를 전 기간에 소급했는데, 그러면 그 사이 상장폐지된 종목은
# 업종을 몰라 판정에서 통째로 빠진다(2016년 종목의 98%). 각 행의 날짜에 대해
# '그 시점 이전의 가장 가까운 스냅샷' 을 적용한다.
_sc = sqlite3.connect(f"file:{BASE}/data/kospi.db?mode=ro", uri=True, timeout=600)
try:
    SH = pd.read_sql("SELECT snap,ticker,gname FROM sector WHERE kind='upjong'", _sc)
except Exception:
    SH = pd.DataFrame(columns=["snap","ticker","gname"])
_sc.close()
SNAPS = np.array(sorted(SH.snap.unique())) if len(SH) else np.array([])
SHMAP = {(s, t): g for s, t, g in zip(SH.snap, SH.ticker, SH.gname)} if len(SH) else {}
log.info(f"업종 이력: 스냅샷 {len(SNAPS)}개 · 매핑 {len(SHMAP):,}건")

def sector_of(dates, tickers):
    """행마다 '그 날짜 이전의 가장 가까운 스냅샷' 기준 업종. 없으면 현재 분류로 보완."""
    if not len(SNAPS):
        return pd.Series(tickers).map(SECT).values
    i = np.clip(np.searchsorted(SNAPS, np.asarray(dates), side="right") - 1, 0, len(SNAPS) - 1)
    snap = SNAPS[i]
    out = [SHMAP.get((s, t)) for s, t in zip(snap, tickers)]
    return [o if o is not None else SECT.get(t) for o, t in zip(out, tickers)]

_d = sqlite3.connect(f"file:{BASE}/data/dart/disclosures.db?mode=ro", uri=True, timeout=600)
dz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE "
   "replace(report_nm,' ','') LIKE '%유상증자결정%' "
   "OR replace(report_nm,' ','') LIKE '%전환사채권발행결정%' "
   "OR replace(report_nm,' ','') LIKE '%신주인수권부사채권발행결정%'", _d); _d.close()
DIL = defaultdict(list)
for r in dz.itertuples(): DIL[r.t].append(r.rcept_dt)
log.info(f"희석 공시 {len(dz):,}건 · {dz.rcept_dt.min()}~{dz.rcept_dt.max()}")

# 자사주 취득결정 — [자사주 낙폭](A1) 이 쓴다. 신탁계약은 실제 매입 시점이 흩어져
# 효과가 다르고, 정정공시는 원본과 중복되므로 뺀다(기존 규칙 정의와 동일).
_d = sqlite3.connect(f"file:{BASE}/data/dart/disclosures.db?mode=ro", uri=True, timeout=600)
bz = pd.read_sql("SELECT stock_code t, rcept_dt, report_nm FROM disclosure WHERE "
                 "length(stock_code)=6 AND replace(report_nm,' ','') LIKE '%자기주식취득결정%'", _d)
_nm = bz.report_nm.str.replace(" ", "", regex=False)
bz = bz[~_nm.str.contains("신탁") & ~_nm.str.contains("정정")]
BBSET = set(zip(bz.t, bz.rcept_dt))
log.info(f"자사주 취득결정 {len(BBSET):,}건 · {bz.rcept_dt.min()}~{bz.rcept_dt.max()}")
# 임원·주요주주 소유상황보고 — [외인 매집](P1) 이 '최근 60거래일 1건 이상' 으로 쓴다
iz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE length(stock_code)=6 AND "
                 "replace(report_nm,' ','') LIKE '%임원ㆍ주요주주특정증권등소유상황보고서%'", _d)
if not len(iz):
    iz = pd.read_sql("SELECT stock_code t, rcept_dt FROM disclosure WHERE length(stock_code)=6 AND "
                     "report_nm LIKE '%주요주주%소유상황보고%'", _d)
_d.close()
INS = defaultdict(list)
for r in iz.itertuples(): INS[r.t].append(r.rcept_dt)
log.info(f"내부자 보고 {len(iz):,}건 · 종목 {len(INS):,}개")

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
    # 자사주: 그날 취득결정 공시가 있었나(규칙은 '공시 다음날 시가 매수' 로 실측했다)
    df["bb"] = [(t, d) in BBSET for t, d in zip(df.ticker, df.date)]
    # 내부자: 최근 60거래일 안의 보고 건수. 거래일 인덱스로 세어 휴장을 건너뛴다.
    ins = np.zeros(len(df), np.int32)
    pos60 = df.date.map(DI).values
    for t, idx in df.groupby("ticker").indices.items():
        L = INS.get(t)
        if not L: continue
        lp = np.sort([DI[x] for x in L if x in DI])
        if not len(lp): continue
        v = pos60[idx]
        hi = np.searchsorted(lp, v, side="right")
        lo = np.searchsorted(lp, v - 60, side="left")
        ins[idx] = hi - lo
    df["ins60"] = ins
    pc = g.close.shift(1); jj = (C/pc).where(pc > 0)
    badday = ((jj > 1.32) | (jj < 0.68)).fillna(False)
    bad = np.zeros(len(df), bool); pos = df.date.map(DI).values
    for t, sub in df[badday].groupby("ticker"):
        idx = df.index[df.ticker == t].values
        bp = np.sort(sub.date.map(DI).values); p = pos[idx]
        qq = np.searchsorted(bp, p, side="right")
        bad[idx[(qq < len(bp)) & (bp[np.minimum(qq, len(bp)-1)] - p <= 42)]] = True
    df["bad"] = bad
    df["up"] = sector_of(df.date.values, df.ticker.values)
    d2 = df[df.up.notna()].dropna(subset=["ret60"])
    gm = d2.groupby(["date","up"]).ret60
    m = gm.median()[gm.size() >= 5]
    df["u"] = pd.MultiIndex.from_arrays([df.date, df.up]).map(m)
    lastpos = g.date.transform("max").map(DI); lastclose = g.close.transform("last")
    mypos = df.date.map(DI)
    for h in HZ:
        sell = g.close.shift(-h).where(~(mypos+h > lastpos), lastclose)
        df["n%d" % h] = (sell/df.buy-1)*100 - df.cost
    # 2018~ 의 공매도는 DB(daily)가 아니라 기존 패널에만 있다(과거 파이프라인이 별도
    # 경로로 관리해 왔다). 2016~17 은 백필 때 KRX 에서 직접 받아 DB 에 있으므로,
    # 비어 있는 구간만 기존 패널에서 채운다. 이걸 빌드 안에서 하지 않으면 패널을
    # 다시 만들 때마다 공매도가 사라져 관련 규칙이 통째로 0건이 된다(2026-09-04 실측).
    _oldf = BASE/"data"/("kp_ow.pkl" if mkt == "KOSPI" else "kq_ow.pkl")
    if _oldf.exists() and (df.srd.isna().any() or df.marcap.isna().any()):
        _O = pd.read_pickle(_oldf)[["ticker","date","sr20","srd","marcap","shares"]]
        _n = len(df)
        df = df.merge(_O, on=["ticker","date"], how="left", suffixes=("","_o"))
        assert len(df) == _n, "공매도 병합에서 행이 늘었다 — 키 중복"
        # marcap·shares 도 같은 사정이다. DB 는 2023 년부터 넣기 시작해서 2018~2022 가
        # 통째로 비어 있고, 그러면 시총 조건을 쓰는 [외인 매집] 이 그 구간 0건이 된다.
        for _c in ("sr20","srd","marcap","shares"):
            df[_c] = df[_c].where(df[_c].notna(), df[_c+"_o"]); df.drop(columns=[_c+"_o"], inplace=True)
        log.info(f"  기존 패널로 보완: srd 결측 {df.srd.isna().mean()*100:.0f}% · marcap 결측 {df.marcap.isna().mean()*100:.0f}%")
    fn = "panel_kp.pkl" if mkt == "KOSPI" else "panel_kq.pkl"
    df.to_pickle(BASE/"data"/fn)
    log.info(f"  저장 {fn} · {len(df):,}행 {len(df.columns)}컬럼")

for mkt in MKTS: build(mkt)
