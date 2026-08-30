"""장중 현재가 수집 + 매도 신호 텔레그램 알림
- Supabase 보유 종목 코드 → 네이버 실시간 시세 → Supabase '__prices__' 저장
- 신호: 필터별 — 1번 10일·익절20%(손절 없음) / 2번 10일(손절 없음)
- 알림 중복 방지: Supabase '__alerts__' 에 보낸 키 기록
- 텔레그램: 환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GitHub Secrets) 없으면 알림 생략
(GitHub Actions에서 평일 장중 5분마다 실행, push 시 설정 확인 핑)
"""
import re, os, csv, sys, time, datetime as dt
from pathlib import Path
import requests

BASE = Path(__file__).parent
js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", js).group(1); KEY = re.search(r"key:'([^']+)'", js).group(1)
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
NAVER = {"User-Agent": "Mozilla/5.0"}
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
HOLD_DAYS = 10
RULES = {"P1": {"stop": 0.15, "target": None, "hold": 40}, "P2": {"stop": None, "target": None, "hold": 10},
         "P3": {"stop": None, "target": None, "hold": 20}, "D1": {"stop": None, "target": None, "hold": 20},
         # 옛 P1(상승초입)은 2026-08-31 폐기. 이름을 새 규칙이 물려받아 이력은 P0 으로 분리 보관.
         "P0": {"stop": None, "target": 0.20, "hold": 10}}
LEGACY_ID = {1: "P0", 2: "P2", 3: "P3", 4: "P1"}      # 예전에 저장된 숫자 id 호환   # 필터별 청산 규칙
DEFAULT_RULE = RULES["P1"]
num = lambda s: float(str(s).replace(",", "")) if s not in (None, "") else None
now_kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
today = now_kst.strftime("%Y%m%d")

def rpc(fn, body):
    r = requests.post(f"{URL}/rest/v1/rpc/{fn}", headers=H, json=body, timeout=20); r.raise_for_status()
    return r.json() if r.text else None

def telegram(text):
    if not (TG_TOKEN and TG_CHAT): print("텔레그램 미설정 → 알림 생략:", text.replace("\n", " | ")); return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}, timeout=15)
    print("텔레그램:", r.status_code)

if "--ping" in sys.argv:
    telegram(f"🔔 GitHub Actions 알림 설정 확인 OK ({now_kst:%m/%d %H:%M})\n평일 09:00~15:55 5분마다 보유 종목 시세를 확인합니다.")

# 1) 보유 종목 (모든 PIN, 미매도)
positions = rpc("kospi_state_positions", {}) or []
codes = sorted({p["code"] for p in positions})
print("보유 종목:", codes)

# 2) 실시간 시세
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
rpc("kospi_state_set", {"p_pin": "__prices__", "p_data": {"updated": now_kst.strftime("%Y-%m-%d %H:%M"), "prices": prices}})
print("저장:", now_kst.strftime("%H:%M"), {c: p["now"] for c, p in prices.items()})

# 3) 매도 신호 — 일별 종가 이력(data/*.csv)으로 고점·보유일 계산 + 장중 고가 반영
if positions:
    hist = {}   # code -> [(date, close)]
    for f in sorted((BASE / "data").glob("20??-??.csv")):
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["ticker"] in codes and r["close"]:
                    hist.setdefault(r["ticker"], []).append((r["date"], float(r["close"])))
    alerts = rpc("kospi_state_get", {"p_pin": "__alerts__"}) or {}
    sent = set(alerts.get("sent", []))
    for p in positions:
        c, buy, price = p["code"], str(p["date"]), float(p["price"])
        lv = prices.get(c) or {}
        if not lv.get("now"): continue
        rows = [x for x in hist.get(c, []) if x[0] >= buy]
        live_today = lv.get("at", "")[:10].replace("-", "") == today
        days = len([x for x in rows if x[0] < today]) + (1 if live_today else 0)   # 매수일 포함 보유 거래일수
        hi = max([price] + [x[1] for x in rows] + ([lv["high"]] if live_today and lv.get("high") else []))
        fids = [LEGACY_ID.get(f, f) for f in (p.get("filters") or [])]
        rule = next((RULES[f] for f in fids if f in RULES), DEFAULT_RULE)
        line = price * (1 - rule["stop"]) if rule["stop"] else None
        tgt = price * (1 + rule["target"]) if rule["target"] else None
        now = lv["now"]; ret = (now / price - 1) * 100
        name = p.get("name", c)
        key_trail, key_hold = f"{p.get('id', c)}:stop", f"{p.get('id', c)}:hold"
        if line and now <= line and key_trail not in sent:
            telegram(f"🛑 <b>{name}</b> 손절선 이탈 (-{rule['stop']*100:.0f}%)\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n손절선 {line:,.0f} · 보유 {days}거래일 · 고점 {hi:,.0f}\n{now_kst:%m/%d %H:%M}")
            sent.add(key_trail)
        key_tgt = f"{p.get('id', c)}:target"
        if tgt and now >= tgt and key_tgt not in sent:
            telegram(f"🎯 <b>{name}</b> 익절 목표 도달 (+{rule['target']*100:.0f}%)\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n보유 {days}거래일 · {now_kst:%m/%d %H:%M}")
            sent.add(key_tgt)
        key_add = f"{p.get('id', c)}:add"
        if days >= 3 and ret > 0 and key_add not in sent:
            telegram(f"🔥 <b>{name}</b> 추가매수 고려 — 매수 후 {days}거래일째 이익 중 ({ret:+.1f}%)\n현재가 {now:,.0f} (매수 {price:,.0f})\n백테스트: 3일째 이익 중이면 최종 승률 78~81% · 추가분도 +2.4~5.7% / PF 2.6~3.8\n{now_kst:%m/%d %H:%M}")
            sent.add(key_add)
        hold_n = rule.get("hold", HOLD_DAYS)
        if days >= hold_n and key_hold not in sent:
            telegram(f"⏰ <b>{name}</b> 보유 {days}거래일째 — 추천 규칙상 매도일\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n고점 {hi:,.0f} · {now_kst:%m/%d %H:%M}")
            sent.add(key_hold)
    rpc("kospi_state_set", {"p_pin": "__alerts__", "p_data": {"sent": sorted(sent), "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
