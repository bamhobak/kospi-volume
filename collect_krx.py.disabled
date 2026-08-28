"""KRX 수집 — 공매도 + 기관 세부 투자자 (일자별 전종목 1회 호출)
- 공매도 거래량/비중 (get_shorting_volume_by_ticker)
- 공매도 잔고/비중 (get_shorting_balance_by_ticker)
- 투자자별 순매수 금액: 연기금·투신·사모·보험·금융투자·기타법인
환경변수 KRX_ID / KRX_PW 필요
사용:  python collect_krx.py            최근 10영업일
       python collect_krx.py --from 2023-01-01   백필
"""
import os, sqlite3, sys, time
from datetime import datetime, timedelta
import pandas as pd
import collect

log = collect.log
if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
    log.error("KRX_ID / KRX_PW 환경변수가 필요합니다"); sys.exit(1)
from pykrx import stock

FROM = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else None
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
today = datetime.today()
start = FROM.replace("-", "") if FROM else (today - timedelta(days=DAYS * 2)).strftime("%Y%m%d")
end = today.strftime("%Y%m%d")

SLEEP = float(os.environ.get("KRX_SLEEP", "1.0"))   # 요청 간격(초) — 과도한 요청 시 KRX 차단됨
MAX_DAYS = int(os.environ.get("KRX_MAX_DAYS", "0"))  # 0=제한 없음, 백필은 나눠서 실행 권장
INVESTORS = [("연기금", "pension"), ("투신", "trust"), ("사모", "private"),
             ("보험", "insurance"), ("금융투자", "fininv"), ("기타법인", "corp")]
COLS = [("short_vol", "INTEGER"), ("short_ratio", "REAL"), ("short_bal", "INTEGER"), ("short_bal_ratio", "REAL")] \
       + [(c, "INTEGER") for _, c in INVESTORS]

con = sqlite3.connect(collect.DB, timeout=300)
collect.init_db(con)
have = {r[1] for r in con.execute("PRAGMA table_info(daily)")}
for c, t in COLS:
    if c not in have: con.execute(f"ALTER TABLE daily ADD COLUMN {c} {t}")
con.commit()

days = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily WHERE date BETWEEN ? AND ? ORDER BY date", (start, end))]   # 실제 거래일만
# 이미 채워진 날짜는 건너뜀
done_short = {r[0] for r in con.execute("SELECT date FROM daily WHERE short_vol IS NOT NULL GROUP BY date")}
done_inv = {r[0] for r in con.execute("SELECT date FROM daily WHERE pension IS NOT NULL GROUP BY date")}
if MAX_DAYS: days = [d for d in days if d not in done_short][:MAX_DAYS] or days[:MAX_DAYS]
log.info(f"KRX 수집 {start}~{end} · 대상 {len(days)}영업일 (공매도 완료 {len(done_short)}일, 투자자 {len(done_inv)}일)")

n_s = n_i = 0
for i, d in enumerate(days):
    # ---- 공매도 ----
    if d not in done_short:
        try:
            v = stock.get_shorting_volume_by_ticker(d, "KOSPI")
            if v is not None and len(v):
                rows = [(int(r["공매도"]), float(r["비중"]), d, str(t).zfill(6)) for t, r in v.iterrows() if pd.notna(r["공매도"])]
                con.executemany("UPDATE daily SET short_vol=?, short_ratio=? WHERE date=? AND ticker=?", rows)
                try:
                    b = stock.get_shorting_balance_by_ticker(d, "KOSPI")
                    if b is not None and len(b):
                        br = [(int(r["공매도잔고"]), float(r["비중"]), d, str(t).zfill(6)) for t, r in b.iterrows() if pd.notna(r["공매도잔고"])]
                        con.executemany("UPDATE daily SET short_bal=?, short_bal_ratio=? WHERE date=? AND ticker=?", br)
                except Exception as e:
                    log.warning(f"잔고 {d}: {str(e)[:50]}")
                con.commit(); n_s += 1
        except Exception as e:
            log.warning(f"공매도 {d}: {str(e)[:50]}")
        time.sleep(SLEEP)
    # ---- 투자자별 ----
    if d not in done_inv:
        got = False
        for name, col in INVESTORS:
            try:
                df = stock.get_market_net_purchases_of_equities(d, d, "KOSPI", name)
                if df is None or len(df) == 0: continue
                rows = [(int(r["순매수거래대금"]), d, str(t).zfill(6)) for t, r in df.iterrows() if pd.notna(r["순매수거래대금"])]
                con.executemany(f"UPDATE daily SET {col}=? WHERE date=? AND ticker=?", rows)
                got = True
            except Exception as e:
                log.warning(f"{name} {d}: {str(e)[:50]}")
            time.sleep(SLEEP)
        if got: con.commit(); n_i += 1
    if i % 20 == 0:
        log.info(f"진행 {i}/{len(days)} · 공매도 {n_s}일 · 투자자 {n_i}일")

r = con.execute("SELECT count(*), sum(short_vol IS NOT NULL), sum(pension IS NOT NULL) FROM daily WHERE date>=?", (start,)).fetchone()
log.info(f"완료: {start} 이후 {r[0]:,}행 중 공매도 {r[1]:,}행 · 기관세부 {r[2]:,}행")
con.close()
