# -*- coding: utf-8 -*-
"""KRX 날짜별 전종목 수집 — 밸류에이션 / 공매도 잔고 / 공매도 거래량.
   날짜당 시장별 1콜(0.2~0.8초)로 전종목을 받는다. data/krx_daily.db, 재개 가능.
사용: python collect_krx_daily.py fund|shortbal|shortvol [--gap 1.5] [--from 20180102]
받을 수 있는 시작점(실측): fund 2005~ · shortvol 2005~ · shortbal 2016~
"""
import os, sqlite3, sys, time, logging, warnings
from pathlib import Path
import pandas as pd
warnings.filterwarnings("ignore")
BASE = Path(__file__).parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(BASE/"krx_daily.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)])
log = logging.getLogger()
for l in (BASE/".env").read_text(encoding="utf-8").splitlines():
    if "=" in l: k, v = l.split("=", 1); os.environ[k.strip()] = v.strip()
from pykrx import stock

arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
MODE = sys.argv[1]
GAP = float(arg("--gap", "1.5"))          # KRX 재차단 방지: 콜 사이 대기
FROM = arg("--from", "20180102")

SPEC = {
 "fund": dict(table="fundamental", fn=lambda d, mk: stock.get_market_fundamental(d, market=mk),
              cols=[("bps","BPS"),("per","PER"),("pbr","PBR"),("eps","EPS"),("div","DIV"),("dps","DPS")]),
 "shortvol": dict(table="short_volume", fn=lambda d, mk: stock.get_shorting_volume_by_ticker(d, mk),
              cols=[("short_vol","공매도"),("total_vol","매수"),("vol_rto","비중")]),   # 실측 컬럼 3개
 "shortbal": dict(table="short_balance", fn=lambda d, mk: stock.get_shorting_balance_by_ticker(d, mk),
              cols=[("bal_qty","공매도잔고"),("shrs","상장주식수"),("bal_amt","공매도금액"),
                    ("mktcap","시가총액"),("bal_rto","비중")]),
}
S = SPEC[MODE]; CN = [c for c, _ in S["cols"]]
c = sqlite3.connect(BASE/"data"/"krx_daily.db", timeout=600)
c.executescript(f"""
create table if not exists {S['table']}(date text, ticker text, {', '.join(x+' real' for x in CN)}, primary key(date,ticker));
create index if not exists ix_{S['table']} on {S['table']}(ticker,date);
create table if not exists done(mode text, date text, mk text, n integer, primary key(mode,date,mk));""")
c.commit()
done = {(r[0], r[1]) for r in c.execute("select date,mk from done where mode=?", (MODE,))}

days = [d.strftime("%Y%m%d") for d in pd.bdate_range(pd.Timestamp(FROM), pd.Timestamp(time.strftime("%Y-%m-%d")))]
todo = [(d, mk) for d in days for mk in ("KOSPI", "KOSDAQ") if (d, mk) not in done]
log.info(f"[{MODE}] 남은 {len(todo):,} (완료 {len(done):,}) · 콜간격 {GAP}s · 예상 {len(todo)*(GAP+0.4)/3600:.1f}h")
ph = ",".join("?"*(2+len(CN))); n = tot = 0; t0 = time.time()
for d, mk in todo:
    try:
        r = S["fn"](d, mk)
        if r is not None and len(r):
            r = r.reset_index(); tk = r.columns[0]
            rows = [(d, str(x[tk]), *[float(x.get(src, 0) or 0) for _, src in S["cols"]]) for _, x in r.iterrows()]
            c.executemany(f"insert or ignore into {S['table']} values({ph})", rows); tot += len(rows)
            c.execute("insert or replace into done values(?,?,?,?)", (MODE, d, mk, len(rows)))
        else:                                   # 휴장일 등 — 빈 날도 완료로 기록
            c.execute("insert or replace into done values(?,?,?,?)", (MODE, d, mk, 0))
    except Exception as e:
        log.warning(f"  {d} {mk} 실패 {type(e).__name__} {str(e)[:60]}"); time.sleep(5)
    n += 1
    if n % 100 == 0:
        c.commit(); el = time.time()-t0
        log.info(f"  [{MODE}] {n:,}/{len(todo):,} ({tot:,}행, {el/60:.0f}분, 남은 {(el/n*(len(todo)-n))/60:.0f}분)")
    time.sleep(GAP)
c.commit()
r = c.execute(f"select count(*),count(distinct ticker),min(date),max(date) from {S['table']}").fetchone()
log.info(f"[{MODE}] 완료 {r[0]:,}행 · {r[1]}종목 · {r[2]}~{r[3]}")
