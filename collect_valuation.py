# -*- coding: utf-8 -*-
"""밸류에이션 수집 — PER / PBR / PCR / EV·EBITDA / EPS / BPS / 배당수익률 / 업종PER
   출처: 네이버가 임베드하는 FnGuide 스냅샷 (navercomp.wisereport.co.kr)
   저장: data/valuation.csv  (하루 1회 스냅샷, 리포지토리에 커밋)
사용: python collect_valuation.py [--workers 8] [--market ALL|KOSPI|KOSDAQ]
"""
import csv, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
import FinanceDataReader as fdr
import collect

log = collect.log
BASE = Path(__file__).parent
OUT = BASE / "data" / "valuation.csv"
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
W = int(arg("--workers", "8"))
MKT = arg("--market", "ALL")
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://finance.naver.com/"}
URL = "https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={}"

TAG = re.compile(r"<[^>]+>")
SP = re.compile(r"\s+")
def num(s):
    if s is None: return None
    s = s.replace(",", "").replace("배", "").replace("%", "").replace("원", "").strip()
    if s in ("", "-", "N/A", "완전잠식"): return None
    try: return float(s)
    except ValueError: return None

def grab(t, key, after=1):
    """'PER 11.53 업종PER 16.91' 같은 평문에서 key 다음 after번째 숫자"""
    m = re.search(re.escape(key) + r"\s+((?:[-\d.,]+|N/A|-|완전잠식)(?:\s+(?:[-\d.,]+|N/A|-|완전잠식)){0,3})", t)
    if not m: return None
    parts = m.group(1).split()
    return num(parts[after - 1]) if len(parts) >= after else None

def one(code):
    for attempt in range(3):
        try:
            r = requests.get(URL.format(code), headers=HDR, timeout=25)
            if r.status_code != 200: time.sleep(1); continue
            r.encoding = r.apparent_encoding or "utf-8"
            t = SP.sub(" ", TAG.sub(" ", r.text))
            d = dict(ticker=code)
            d["per"] = grab(t, "PER", 1)
            d["upjong_per"] = grab(t, "업종PER", 1)
            d["pbr"] = grab(t, "PBR", 1)
            d["div_yield"] = grab(t, "현금배당수익률", 1)
            d["pcr"] = grab(t, "PCR", 1)              # 첫 값 = 해당 종목, 둘째 = 업종/비교
            d["ev_ebitda"] = grab(t, "EV/EBITDA", 1)
            d["eps"] = grab(t, "EPS", 1)
            d["bps"] = grab(t, "BPS", 1)
            if any(v is not None for k, v in d.items() if k != "ticker"): return d
            return None
        except Exception:
            time.sleep(1 + attempt)
    return None

if __name__ == "__main__":
    codes = []
    for m in (("KOSPI", "KOSDAQ") if MKT == "ALL" else (MKT,)):
        try:
            L = fdr.StockListing(m)
            codes += [(r.Code, m) for r in L.itertuples() if isinstance(r.Code, str) and len(r.Code) == 6]
        except Exception as e:
            log.warning(f"{m} 목록 실패: {str(e)[:60]}")
    log.info(f"밸류에이션 수집 대상 {len(codes):,}종목 · 워커 {W}")
    rows = []; n = 0; t0 = time.time()
    with ThreadPoolExecutor(W) as ex:
        fut = {ex.submit(one, c): (c, mk) for c, mk in codes}
        for f in as_completed(fut):
            c, mk = fut[f]
            d = f.result()
            if d: d["market"] = mk; rows.append(d)
            n += 1
            if n % 300 == 0:
                el = time.time() - t0
                log.info(f"{n}/{len(codes)} · 성공 {len(rows)} ({el:.0f}s, 남은 {el/n*(len(codes)-n)/60:.0f}분)")
    COLS = ["ticker", "market", "per", "pbr", "pcr", "upjong_per", "ev_ebitda", "eps", "bps", "div_yield"]
    rows.sort(key=lambda x: x["ticker"])
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    have = lambda k: sum(1 for r in rows if r.get(k) is not None)
    log.info(f"저장 {OUT.name}: {len(rows):,}종목 ({time.time()-t0:.0f}s) · "
             f"PER {have('per')} · PBR {have('pbr')} · PCR {have('pcr')} · 배당 {have('div_yield')}")
