# -*- coding: utf-8 -*-
"""2018년 이전 보조자료를 어디까지 받을 수 있나 — 실제로 호출해서 확인만 한다(저장 안 함).

시세는 2005년까지 백필했는데 규칙이 쓰는 보조자료(신용잔고·공매도·밸류에이션·11분할·지수편입)는
전부 2018년부터다. 그래서 2008·2011년 폭락 구간에서 규칙 검증이 반쪽이다.
어느 해까지 실제로 데이터가 나오는지 연도별로 한 번씩 찔러 본다.
⚠ KRX 는 과속하면 차단된다 — 호출 간격 2초, 순차.
사용: python probe_history.py
"""
import os, sys, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).parent
for l in (BASE/".env").read_text(encoding="utf-8").splitlines():
    if "=" in l and not l.startswith("#"): k, v = l.split("=", 1); os.environ[k.strip()] = v.strip()
from pykrx import stock
import kis

GAP = 2.0
YEARS = ["20050705", "20081015", "20101015", "20130703", "20160705", "20170703", "20180702"]

def probe(name, fn):
    print(f"\n■ {name}")
    for d in YEARS:
        time.sleep(GAP)
        try:
            r = fn(d)
            n = len(r) if r is not None else 0
            print(f"   {d[:4]}  {'○' if n else '×':<2} {n:>5}건")
        except Exception as e:
            print(f"   {d[:4]}  ×  오류 {str(e)[:60]}")

probe("밸류에이션 PER/PBR/DIV (get_market_fundamental)",
      lambda d: stock.get_market_fundamental(d, market="KOSPI"))
probe("공매도 거래량 (get_shorting_volume_by_ticker)",
      lambda d: stock.get_shorting_volume_by_ticker(d, market="KOSPI"))
probe("공매도 잔고 (get_shorting_balance_by_ticker)",
      lambda d: stock.get_shorting_balance_by_ticker(d, market="KOSPI"))
probe("투자자 11분할 (get_market_net_purchases_of_equities_by_ticker · 연기금)",
      lambda d: stock.get_market_net_purchases_of_equities_by_ticker(d, d, "KOSPI", "연기금"))
probe("지수 구성종목 코스피200 (get_index_portfolio_deposit_file)",
      lambda d: stock.get_index_portfolio_deposit_file("1028", d))

# KIS 신용잔고 — 종목별. 삼성전자로 과거 어디까지 나오나
print("\n■ KIS 신용잔고 (daily-credit-balance · 005930)")
tok = kis.get_token()
for anchor in ("20051231", "20081231", "20101231", "20131231", "20161231", "20171231"):
    time.sleep(0.3)
    p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930",
         "FID_COND_SCR_DIV_CODE": "20476", "FID_INPUT_DATE_1": anchor}
    try:
        st, d, _ = kis.call("/uapi/domestic-stock/v1/quotations/daily-credit-balance", "FHPST04760000", p, token=tok)
        o = d.get("output2") or d.get("output") or []
        o = o if isinstance(o, list) else [o]
        ds = [x.get("deal_date") for x in o if x.get("deal_date")]
        print(f"   {anchor[:4]}  {'○' if ds else '×':<2} {len(ds):>3}건  {min(ds) if ds else ''}~{max(ds) if ds else ''}")
    except Exception as e:
        print(f"   {anchor[:4]}  ×  {str(e)[:60]}")

print("\n■ KIS 공매도 (daily-short-sale · 005930)")
for a, b in (("20050101","20051231"), ("20080101","20081231"), ("20100101","20101231"),
             ("20130101","20131231"), ("20160101","20161231"), ("20170101","20171231")):
    time.sleep(0.3)
    p = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930",
         "FID_INPUT_DATE_1": a, "FID_INPUT_DATE_2": b}
    try:
        st, d, _ = kis.call("/uapi/domestic-stock/v1/quotations/daily-short-sale", "FHPST04830000", p, token=tok)
        o = d.get("output2") or d.get("output") or []
        o = o if isinstance(o, list) else [o]
        ds = [x.get("stck_bsop_date") for x in o if x.get("stck_bsop_date")]
        print(f"   {a[:4]}  {'○' if ds else '×':<2} {len(ds):>3}건  {min(ds) if ds else ''}~{max(ds) if ds else ''}")
    except Exception as e:
        print(f"   {a[:4]}  ×  {str(e)[:60]}")
