"""장중 현재가 수집: Supabase에 저장된 보유 종목 코드 → 네이버 실시간 시세 → Supabase '__prices__' 에 저장
(GitHub Actions에서 평일 장중 10분마다 실행)"""
import re, json, sys, time, datetime as dt
from pathlib import Path
import requests

BASE = Path(__file__).parent
js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", js).group(1); KEY = re.search(r"key:'([^']+)'", js).group(1)
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
NAVER = {"User-Agent": "Mozilla/5.0"}
num = lambda s: float(str(s).replace(",", "")) if s not in (None, "") else None

def rpc(fn, body):
    r = requests.post(f"{URL}/rest/v1/rpc/{fn}", headers=H, json=body, timeout=20); r.raise_for_status()
    return r.json() if r.text else None

codes = rpc("kospi_state_codes", {}) or []
print("보유 종목:", codes)
prices = {}
for c in codes:
    try:
        d = requests.get(f"https://polling.finance.naver.com/api/realtime/domestic/stock/{c}", headers=NAVER, timeout=10).json()["datas"][0]
        prices[c] = {"now": num(d["closePrice"]), "open": num(d.get("openPrice")), "high": num(d.get("highPrice")), "low": num(d.get("lowPrice")),
                     "chg": num(d.get("compareToPreviousClosePrice")), "vol": num(d.get("accumulatedTradingVolume")),
                     "at": d.get("localTradedAt", ""), "status": d.get("marketStatus", "")}
    except Exception as e:
        print("실패", c, e)
    time.sleep(0.2)
now_kst = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
rpc("kospi_state_set", {"p_pin": "__prices__", "p_data": {"updated": now_kst, "prices": prices}})
print("저장:", now_kst, {c: p["now"] for c, p in prices.items()})
