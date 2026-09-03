# -*- coding: utf-8 -*-
"""과거 백필 (KRX/pykrx) — 2016~2017 구간을 코스피·코스닥 모두 채운다.

왜 pykrx 인가: 네이버 trend API 는 최근 60행(3개월)만 주고, frgn 페이지는 2005년까지
가지만 개인 순매수를 안 준다. FinanceDataReader 는 3,000행 상한이라 2014년까지다.
KRX 는 로그인만 하면 '하루치 전 종목' 을 한 번에 주고 개인까지 포함한다.

생존편향: 날짜별 전 종목 조회라 그날 상장돼 있던 종목이 그대로 들어온다. 지금은
사라진 종목도 자동으로 포함되므로 따로 폐지 목록을 챙길 필요가 없다.

속도: KRX 는 빠르게 때리면 막는다(실측). gap 을 두고 순차로만 돈다. 동시 실행 금지.
세션은 1시간이면 만료되므로 실패하면 다시 로그인하고 재시도한다.

재개: 이미 DB 에 있는 날짜는 건너뛴다. 중간에 끊겨도 다시 돌리면 이어서 한다.

사용: python backfill_krx.py --from 20160101 --to 20171231 [--gap 2.0] [--market KOSPI]
"""
import io, sys, time, sqlite3, logging, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import pandas as pd
from pykrx import stock
import collect

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("backfill")
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
FROM, TO = arg("--from", "20160101"), arg("--to", "20171231")
GAP = float(arg("--gap", "2.0"))
MARKETS = [arg("--market", None)] if "--market" in sys.argv else ["KOSPI", "KOSDAQ"]

con = sqlite3.connect(collect.DB, timeout=600)
collect.init_db(con)
have = {r[0] for r in con.execute(
    "SELECT DISTINCT date FROM daily WHERE date BETWEEN ? AND ?", (FROM, TO))}

def call(fn, what, tries=4):
    """KRX 호출 한 번. 실패하면 쉬었다 다시 — 세션 만료도 여기서 흡수된다."""
    for i in range(tries):
        try:
            time.sleep(GAP)
            r = fn()
            if r is not None and len(r): return r
            if i == tries - 1: return None
        except Exception as e:
            log.warning(f"  {what} 실패({i+1}/{tries}): {str(e)[:70]}")
            time.sleep(GAP * (i + 2) * 2)     # 물러섰다 다시 — 막힌 것일 수 있다
    return None

def one_day(d, mkt):
    o = call(lambda: stock.get_market_ohlcv(d, market=mkt), f"{d} {mkt} ohlcv")
    # 휴장일에도 pykrx 는 종목 목록을 값 0 으로 채워 돌려준다(2017-12-29 폐장일에 실측).
    # 그대로 저장하면 종가 0 인 가짜 거래일이 생겨 지표가 통째로 망가진다.
    if o is None or not len(o) or float(o["종가"].sum()) == 0: return None
    fr = call(lambda: stock.get_exhaustion_rates_of_foreign_investment(d, market=mkt), f"{d} {mkt} 외인지분")
    sh = call(lambda: stock.get_shorting_volume_by_ticker(d, market=mkt), f"{d} {mkt} 공매도")
    inv = {}
    for who, col in (("개인", "indiv"), ("기관합계", "organ"), ("외국인", "frgn")):
        r = call(lambda w=who: stock.get_market_net_purchases_of_equities(d, d, mkt, w), f"{d} {mkt} {who}")
        if r is not None and len(r): inv[col] = r
    df = pd.DataFrame(index=o.index)
    df["open"], df["high"], df["low"], df["close"] = o["시가"], o["고가"], o["저가"], o["종가"]
    df["volume"], df["amount"] = o["거래량"], o["거래대금"]
    df["marcap"] = o["시가총액"] if "시가총액" in o.columns else None
    # 등락률에서 전일 종가를 되짚어 전일대비를 만든다(화면 표시용 · 규칙은 쓰지 않는다).
    # pandas 의 Int64(널 허용 정수)를 그대로 넣으면 sqlite 에 BLOB 으로 박히므로 파이썬 int 로 만든다.
    prev = o["종가"] / (1 + o["등락률"] / 100)
    df["change"] = [None if pd.isna(x) or abs(x) == float("inf") else int(round(x))
                    for x in (o["종가"] - prev)]
    if fr is not None:
        df["shares"] = fr["상장주식수"].reindex(df.index)
        df["foreign_ratio"] = fr["지분율"].reindex(df.index).round(2)
    if sh is not None:
        df["short_vol"] = sh["공매도"].reindex(df.index)
        df["short_ratio"] = sh["비중"].reindex(df.index)
    name = None
    for col, r in inv.items():
        df[col] = r["순매수거래량"].reindex(df.index)
        if name is None and "종목명" in r.columns: name = r["종목명"].reindex(df.index)
    df["name"] = name if name is not None else None
    df["date"], df["market"] = d, mkt
    df["ticker"] = df.index
    return df

COLS = ["date","ticker","name","close","change","volume","indiv","organ","frgn","foreign_ratio",
        "open","high","low","amount","marcap","shares","short_vol","short_ratio","market"]
days = [d.strftime("%Y%m%d") for d in pd.bdate_range(FROM, TO)]
todo = [d for d in days if d not in have]
log.info(f"대상 {FROM}~{TO} · 영업일(주말 제외) {len(days)}일 · 이미 있음 {len(days)-len(todo)}일 "
         f"→ 받을 날 {len(todo)}일 · 시장 {MARKETS} · gap {GAP}s")
log.info(f"예상 소요 약 {len(todo)*len(MARKETS)*6*GAP/3600:.1f}시간")
done = rows = 0
for i, d in enumerate(todo, 1):
    got = []
    for mkt in MARKETS:
        df = one_day(d, mkt)
        if df is not None and len(df): got.append(df)
    if not got:
        log.info(f"[{i}/{len(todo)}] {d} 휴장(또는 데이터 없음)"); continue
    A = pd.concat(got)
    for c in COLS:
        if c not in A.columns: A[c] = None
    A = A[COLS].where(pd.notna(A[COLS]), None)
    con.executemany(f"INSERT OR REPLACE INTO daily({','.join(COLS)}) VALUES({','.join('?'*len(COLS))})",
                    A.itertuples(index=False, name=None))
    con.commit(); done += 1; rows += len(A)
    if done % 10 == 0 or i == len(todo):
        log.info(f"[{i}/{len(todo)}] {d} 까지 저장 · 누적 {rows:,}행")
log.info(f"완료: {done}일 · {rows:,}행")
for r in con.execute("SELECT min(date),max(date),count(*) FROM daily"): log.info(f"DB 전체: {r}")
con.close()
