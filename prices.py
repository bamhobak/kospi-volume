"""장중 현재가 수집 + 매도 신호 텔레그램 알림
- Supabase 보유 종목 코드 → 네이버 실시간 시세 → Supabase '__prices__' 저장
- 신호: (1) 매수가 대비 -10% 손절선 이탈  (2) 보유 15거래일째 아침
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
STOP, HOLD_DAYS = 0.10, 15   # 매수가 대비 -10% 손절, 15거래일 보유
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
    full = {}   # code -> [(date, close, volume, frgn)]  (신호 유지 일수 계산용)
    for f in sorted((BASE / "data").glob("20??-??.csv")):
        with open(f, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["ticker"] in codes and r["close"]:
                    hist.setdefault(r["ticker"], []).append((r["date"], float(r["close"])))
                    full.setdefault(r["ticker"], []).append((r["date"], float(r["close"]), float(r["volume"] or 0), float(r["frgn"]) if r["frgn"] else None))
    W, Q, B = 3, 40, 240
    def streak_of(code):
        """1번 기본조건(2M<1Y 50%, 3D≥2M 200%, 외인5일≥2%, 거래대금≥3억, 보통주) 연속 충족 일수 (최근 수집일 기준)"""
        if code[-1] != "0": return 0
        rows = full.get(code, []); v = [r[2] for r in rows]; fr = [r[3] for r in rows]; am = [r[1] * r[2] for r in rows]
        avg = lambda a: sum(a) / len(a) if a else None
        def cond(k):
            vv = v[:len(v) - k] if k else v; ff = fr[:len(fr) - k] if k else fr; aa = am[:len(am) - k] if k else am
            if len(vv) < W + Q + B // 2: return False
            aw, a1, a6 = avg(vv[-W:]), avg(vv[-(W + Q):-W]), avg(vv[-(W + Q + B):-(W + Q)])
            if not (aw and a1 and a6): return False
            f5 = ff[-5:]
            if any(x is None for x in f5): return False
            return a1 / a6 < .5 and aw / a1 >= 2 and sum(f5) > 0 and sum(f5) >= .02 * sum(vv[-5:]) and (avg(aa[-(W + Q):-W]) or 0) >= 3e8
        n = 0
        for k in range(10):
            if cond(k): n += 1
            else: break
        return n
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
        line = price * (1 - STOP); now = lv["now"]; ret = (now / price - 1) * 100
        name = p.get("name", c)
        key_trail, key_hold = f"{p.get('id', c)}:stop", f"{p.get('id', c)}:hold{HOLD_DAYS}"
        if now <= line and key_trail not in sent:
            telegram(f"🛑 <b>{name}</b> 손절선 이탈 (-10%)\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n손절선 {line:,.0f} · 보유 {days}거래일 · 고점 {hi:,.0f}\n{now_kst:%m/%d %H:%M}")
            sent.add(key_trail)
        key_add = f"{p.get('id', c)}:add"
        if ret > 0 and key_add not in sent:
            stk = streak_of(c)
            if stk >= 4:
                telegram(f"🔥 <b>{name}</b> 추가매수 고려 — 이익 중 + 신호 {stk}일 연속 유지\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n백테스트: 이 상태 11건 최초분 +19%/91%, 추가분 +8%/64% (표본 작음) · {now_kst:%m/%d %H:%M}")
                sent.add(key_add)
        if days >= HOLD_DAYS and key_hold not in sent:
            telegram(f"⏰ <b>{name}</b> 보유 {days}거래일째 — 추천 규칙상 매도일\n현재가 {now:,.0f} (매수 {price:,.0f}, {ret:+.1f}%)\n고점 {hi:,.0f} · 손절선 {line:,.0f} · {now_kst:%m/%d %H:%M}")
            sent.add(key_hold)
    rpc("kospi_state_set", {"p_pin": "__alerts__", "p_data": {"sent": sorted(sent), "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
