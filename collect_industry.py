# -*- coding: utf-8 -*-
"""표준산업분류(Industry) 매핑 → data/industry.csv
   코스닥 업종 조건(4번 필터)용. 코스피는 sector.csv 의 업종을 쓰고, 코스닥은 이 파일을 쓴다.
   분류는 거의 바뀌지 않으므로 가끔만 갱신하면 된다(collect_sector 와 같은 주기).
"""
import csv, sys
from pathlib import Path
import FinanceDataReader as fdr
import collect

log = collect.log
OUT = Path(__file__).parent / "data" / "industry.csv"
d = fdr.StockListing("KRX-DESC")
rows = [(r.Code, r.Market, r.Industry) for r in d.itertuples()
        if isinstance(r.Code, str) and len(r.Code) == 6 and isinstance(r.Industry, str) and r.Industry.strip()]
with open(OUT, "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh); w.writerow(["ticker", "market", "industry"]); w.writerows(rows)
from collections import Counter
c = Counter(m for _, m, _ in rows)
log.info(f"industry.csv 저장: {len(rows):,}종목 · {dict(c)} · 고유 업종 {len({i for _,_,i in rows})}개")
