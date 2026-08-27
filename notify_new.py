"""신규 편입 종목 텔레그램 알림
- site/data/table.json(빌드 결과)을 사이트와 동일한 기준으로 판정
- 어제 목록(Supabase '__filters__')과 비교해 새로 들어온 종목만 알림
- 보유 중(미매도) 종목은 사이트와 동일하게 제외
매일 수집(18:30) 워크플로 마지막에 실행
"""
import re, os, json, sys, datetime as dt
from pathlib import Path
import requests

BASE = Path(__file__).parent
js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", js).group(1); KEY = re.search(r"key:'([^']+)'", js).group(1)
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
now_kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)

def rpc(fn, body):
    r = requests.post(f"{URL}/rest/v1/rpc/{fn}", headers=H, json=body, timeout=20); r.raise_for_status()
    return r.json() if r.text else None

def telegram(text):
    if not (TG_TOKEN and TG_CHAT): print("텔레그램 미설정:", text.replace("\n", " | ")); return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
    print("텔레그램:", r.status_code, r.text[:120])

T = json.loads((BASE / "site" / "data" / "table.json").read_text(encoding="utf-8"))
rows, kospi = T["rows"], T.get("kospi") or {}
last_date = T["dates"][-1] if T["dates"] else ""
s5 = lambda a: sum(x or 0 for x in a[-5:])

def fwp(r):
    v = s5(r["v"]); return (s5(r["f"]) / v * 100) if v else 0

# 사이트 index.html 의 FILTERS 와 동일
FILTERS = [
    (1, "1번 · 거래량 급등(2일 연속)", lambda r: (r.get("streak") or 0) >= 2),
    (2, "2번 · 급등+외인5%+상승초입", lambda r: (r.get("streak") or 0) >= 1 and fwp(r) >= 5
        and r.get("ret3") is not None and 0 < r["ret3"] <= 10 and bool(kospi.get("up"))),
]

held = {p["code"] for p in (rpc("kospi_state_positions", {}) or [])}
cur = {}
for fid, name, fn in FILTERS:
    cur[str(fid)] = sorted(r["t"] for r in rows if fn(r) and r["t"] not in held)

prev_state = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
prev = prev_state.get("filters", {})
prev_date = prev_state.get("date", "")
info = {r["t"]: r for r in rows}
kmark = "▲ 5일선 위" if kospi.get("up") else "▼ 5일선 아래"

lines = []
for fid, name, _ in FILTERS:
    k = str(fid)
    new = [t for t in cur[k] if t not in set(prev.get(k, []))]
    if not new: continue
    lines.append(f"\n<b>[{name}]</b>")
    for t in new:
        r = info[t]
        chp = (r["ch"] / (r["c"] - r["ch"]) * 100) if r.get("c") and r.get("ch") and r["c"] != r["ch"] else 0
        lines.append(f"• <b>{r['n']}</b> ({t}) {r['c']:,}원 ({chp:+.1f}%)\n"
                     f"   연속 {r.get('streak', 0)}일 · 외인 {fwp(r):.1f}% · 3일 {(r.get('ret3') or 0):+.1f}% · 거래대금 {r.get('amt', 0):.0f}억")

if lines and prev_date:   # 첫 실행(비교 대상 없음)에는 보내지 않음
    telegram(f"🆕 <b>신규 편입 종목</b> ({last_date[4:6]}/{last_date[6:]} 기준 · 코스피 {kmark})"
             + "".join(lines)
             + f"\n\nhttps://bamhobak.github.io/kospi-volume/")
elif lines:
    print("첫 실행 — 기준 목록만 저장:", cur)
else:
    print("신규 편입 없음:", {k: len(v) for k, v in cur.items()})

rpc("kospi_state_set", {"p_pin": "__filters__", "p_data": {"filters": cur, "date": last_date, "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
print("저장:", {k: len(v) for k, v in cur.items()}, "held", len(held))
