# -*- coding: utf-8 -*-
"""재무·밸류에이션·컨센서스 스냅샷 수집 (네이버 모바일 API)
   - integration : PER/PBR/EPS/BPS/추정PER/외인소진율/시총/52주고저 + 컨센서스(목표주가·투자의견)
   - finance/quarter, finance/annual : 매출액·영업이익·ROE·부채비율 등 16개 항목
   결과는 data/fundamental/YYYYMMDD.json 으로 날짜별 저장(시점 데이터 축적 → 미래참조 방지)
   DB는 건드리지 않음.
사용: python collect_fundamental.py [--codes 005930,000660]
"""
import json, sqlite3, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import requests
import collect

BASE = Path(__file__).parent
OUT = BASE / "data" / "fundamental"; OUT.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://m.stock.naver.com/"}
log = collect.log
def num(s):
    if s in (None, "", "-", "N/A"): return None
    t = str(s).replace(",", "").replace("%", "").replace("배", "").replace("원", "").strip()
    try: return float(t)
    except ValueError: return None

if "--codes" in sys.argv:
    codes = [(c, c) for c in sys.argv[sys.argv.index("--codes") + 1].split(",")]
else:
    con = sqlite3.connect(collect.DB, timeout=300)
    codes = con.execute("SELECT ticker, max(name) FROM daily WHERE market='KOSPI' "
                        "GROUP BY ticker HAVING max(date)=(SELECT max(date) FROM daily)").fetchall()
    con.close()
log.info(f"재무 스냅샷 수집: {len(codes)}종목")

WANT = {"매출액": "sales", "영업이익": "op", "당기순이익": "ni", "영업이익률": "opm", "순이익률": "nim",
        "ROE": "roe", "부채비율": "debt", "당좌비율": "quick", "유보율": "reserve",
        "EPS": "eps", "PER": "per", "BPS": "bps", "PBR": "pbr", "주당배당금": "dps"}

def get(url):
    for _ in range(3):
        try:
            r = requests.get(url, headers=H, timeout=15)
            if r.status_code == 200: return r.json()
        except Exception: time.sleep(1)
    return None

def fin(code, period):
    d = get(f"https://m.stock.naver.com/api/stock/{code}/finance/{period}")
    if not d or "financeInfo" not in d: return None
    fi = d["financeInfo"]
    # 확정 실적만 (컨센서스 컬럼 제외)
    keys = [x["key"] for x in fi.get("trTitleList", []) if x.get("isConsensus") != "Y"]
    out = {}
    for r in fi.get("rowList", []):
        k = WANT.get(r.get("title"))
        if not k: continue
        cols = r.get("columns") or {}
        out[k] = {kk: num((cols.get(kk) or {}).get("value")) for kk in keys if kk in cols}
    return {"periods": keys, "items": out}

def one(code, name):
    o = {"code": code, "name": name}
    g = get(f"https://m.stock.naver.com/api/stock/{code}/integration")
    if g:
        ti = {x.get("code"): x.get("value") for x in (g.get("totalInfos") or [])}
        for k in ("per", "pbr", "eps", "bps", "cnsPer", "cnsEps", "foreignRate",
                  "highPriceOf52Weeks", "lowPriceOf52Weeks", "accumulatedTradingValue"):
            o[k] = num(ti.get(k)) if k not in ("accumulatedTradingValue",) else ti.get(k)
        ci = g.get("consensusInfo") or {}
        o["recommMean"] = num(ci.get("recommMean"))
        o["priceTargetMean"] = num(ci.get("priceTargetMean"))
        o["consensusDate"] = ci.get("createDate")
        o["industryCode"] = g.get("industryCode")
    o["quarter"] = fin(code, "quarter")
    o["annual"] = fin(code, "annual")
    return o

res, n, t0 = {}, 0, time.time()
with ThreadPoolExecutor(6) as ex:
    futs = {ex.submit(one, c, nm): c for c, nm in codes}
    for f in as_completed(futs):
        try: d = f.result(); res[d["code"]] = d
        except Exception as e: log.warning(f"{futs[f]}: {str(e)[:50]}")
        n += 1
        if n % 100 == 0: log.info(f"{n}/{len(codes)} ({time.time()-t0:.0f}s)")

today = datetime.now().strftime("%Y%m%d")
p = OUT / f"{today}.json"
json.dump({"date": today, "count": len(res), "stocks": res}, open(p, "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
ok = sum(1 for v in res.values() if v.get("per") is not None)
tgt = sum(1 for v in res.values() if v.get("priceTargetMean"))
q = sum(1 for v in res.values() if v.get("quarter") and v["quarter"]["items"])
print(f"저장: {p} ({p.stat().st_size/1024:.0f}KB)")
print(f"  종목 {len(res)} · PER 있음 {ok} · 목표주가 있음 {tgt} · 분기실적 있음 {q}")
