# -*- coding: utf-8 -*-
"""FINRA 공매도 잔고(2주마다 · consolidatedShortInterest · 인증 불필요) — 결제일별로 전 종목 (2026-10-03, 사용자 'C 미장 공매도').
티커별로 받으면 6천 번 × 2초 = 4시간이라, 결제일 하나에 전 종목(약 2만 행 · 5천씩 페이지)을 받는다 — 약 1천 요청.
→ research/cache/finra_si.pkl (ticker, sdate, si, si_prev, adv, dtc, chg) · 결제일 단위로 이어 받기
    python research/fetch_finra_si.py
"""
import json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")
OUT = ROOT / "cache" / "finra_si.pkl"
URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
F = ["settlementDate", "symbolCode", "currentShortPositionQuantity", "previousShortPositionQuantity", "averageDailyVolumeQuantity",
     "daysToCoverQuantity", "changePercent"]


def post(body):
    for att in range(5):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Accept": "application/json"})
            r = urllib.request.urlopen(req, timeout=60)
            return json.loads(r.read().decode() or "[]"), int(r.headers.get("record-total") or 0)
        except Exception:
            time.sleep(3 * (att + 1))
    return None, 0


def one_date(sd):
    rows, off, tot = [], 0, 1
    while off < tot:
        d, tot = post({"limit": 5000, "offset": off, "fields": F,
                       "compareFilters": [{"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": sd}]})
        if d is None:
            return None
        rows += d; off += 5000
    return [dict(ticker=x["symbolCode"].replace(".", "-"), sdate=sd.replace("-", ""), si=x.get("currentShortPositionQuantity"),
                 si_prev=x.get("previousShortPositionQuantity"), adv=x.get("averageDailyVolumeQuantity"),
                 dtc=x.get("daysToCoverQuantity"), chg=x.get("changePercent")) for x in rows]


dates, _ = post({"limit": 5000, "fields": ["settlementDate"], "compareFilters": [{"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": "AAPL"}]})
dates = sorted({x["settlementDate"] for x in dates})
old = pd.read_pickle(OUT) if OUT.exists() else pd.DataFrame()
done = set(old.sdate) if len(old) else set()
todo = [d for d in dates if d.replace("-", "") not in done]
print("결제일 %d개 · 남은 %d" % (len(dates), len(todo)), flush=True)
parts = [old] if len(old) else []
with ThreadPoolExecutor(4) as ex:
    for n, (sd, r) in enumerate(zip(todo, ex.map(one_date, todo))):
        if r:
            parts.append(pd.DataFrame(r))
        else:
            print("  실패", sd, flush=True)
        if n % 20 == 19:
            pd.concat(parts).to_pickle(OUT); print(" ", n + 1, sd, flush=True)
pd.concat(parts).to_pickle(OUT)
print("끝", sum(len(p) for p in parts))
