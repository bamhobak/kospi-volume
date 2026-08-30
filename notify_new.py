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
    ("P1", "P1 · 상승초입 (코스피·10일 보유·익절 +20%·손절 없음)",
     lambda r: r.get("mk") == "KOSPI" and (r.get("streak") or 0) >= 1 and fwp(r) >= 3 and not r["pref"]
     and (r.get("amt") or 0) >= 50 and r["a1"] / r["a6"] < 0.5
     and r.get("ret10") is not None and 0 <= r["ret10"] <= 20
     and bool(kospi.get("up20")) and bool(kospi.get("up"))
     and r.get("rs") is not None and r["rs"] > 0 and r.get("srDown") is True
     and r.get("disc") is not True),
    ("P2", "P2 · 조정매집 (코스피·10일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSPI" and (r.get("streak") or 0) >= 1 and fwp(r) >= 2 and not r["pref"]
     and (r.get("amt") or 0) >= 3 and r["a1"] / r["a6"] < 0.3
     and r.get("ret3") is not None and r["ret3"] <= -5
     and r.get("ret10") is not None and r["ret10"] <= 0
     and not bool(kospi.get("up20"))
     and r.get("srDown") is True and r.get("dilu") is not True and r.get("disc") is not True),
    ("P3", "P3 · 폭락반등 (코스피·20일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and r.get("ret20") is not None and r["ret20"] <= -20
     and r.get("vs1") is not None and r["vs1"] >= 2
     and r.get("fw60") is not None and r["fw60"] >= 1
     and (r.get("amt20") if r.get("amt20") is not None else (r.get("amt") or 0)) >= 3
     and kospi.get("up60") is False
     and (r.get("sr60") is None or r["sr60"] <= -10)
     and r.get("srDown") is True and r.get("dilu") is not True and r.get("disc") is not True),
    ("D1", "D1 · 낙폭과대 (코스닥·20일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSDAQ" and not r["pref"]
     and r.get("ret20") is not None and r["ret20"] <= -20
     and r.get("vs1") is not None and r["vs1"] >= 2
     and r.get("fw60") is not None and r["fw60"] >= 1
     and (r.get("amt20") or 0) >= 2
     and kospi.get("up60") is False
     and (r.get("sr60") is None or r["sr60"] <= -15)
     and r.get("srDown") is True and r.get("dilu") is not True and r.get("disc") is not True),
]

held = {p["code"] for p in (rpc("kospi_state_positions", {}) or [])}
cur = {}
for fid, name, fn in FILTERS:
    cur[str(fid)] = sorted(r["t"] for r in rows if fn(r) and r["t"] not in held)

prev_state = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
prev = prev_state.get("filters", {})
prev_date = prev_state.get("date", "")
info = {r["t"]: r for r in rows}
kmark = ("▲ 20일선 위" if kospi.get("up20") else "▼ 20일선 아래") + ("" if kospi.get("up60") is None else " · " + ("▲ 60일선 위" if kospi.get("up60") else "▼ 60일선 아래"))

lines = []
for fid, name, _ in FILTERS:
    k = str(fid)
    new = [t for t in cur[k] if t not in set(prev.get(k, []))]
    if not new: continue
    lines.append(f"\n<b>[{name}]</b>")
    for t in new:
        r = info[t]
        chp = (r["ch"] / (r["c"] - r["ch"]) * 100) if r.get("c") and r.get("ch") and r["c"] != r["ch"] else 0
        lines.append(f"• <b>{r['n']}</b> ({t}) {r['c']:,}원 ({chp:+.1f}%)")
        if fid in ("P3", "D1"):
            lines.append(f"   20일 {(r.get('ret20') or 0):+.1f}% · 외인 60일 {(r.get('fw60') or 0):+.1f}% · "
                         f"당일 거래량 {(r.get('vs1') or 0):.1f}배 · 거래대금 {(r.get('amt20') or r.get('amt') or 0):.0f}억"
                         + (f" · 업종 60일 {r['sr60']:+.1f}%" if r.get('sr60') is not None else ""))
        else:
            lines.append(f"   외인 {fwp(r):.1f}% · 3일 {(r.get('ret3') or 0):+.1f}% · 10일 {(r.get('ret10') or 0):+.1f}% · "
                         f"거래대금 {r.get('amt', 0):.0f}억 · 급등 {(r['aw']/r['a1']):.1f}배")
        TR = T.get("themeRet") or {}
        th = [f"{g} {TR[g]:+.1f}%" if g in TR else g for g in (r.get("th") or [])[:3]]
        if r.get("up") or th:
            lines.append(f"   🏷 {r.get('up') or ''}{' · ' if r.get('up') and th else ''}{' / '.join(th)}")

if lines and prev_date:   # 첫 실행(비교 대상 없음)에는 보내지 않음
    guide = ("\n\n💡 <b>매수 안내</b>\n"
             "• P1: <b>지금 NXT 야간거래로 종가 매수</b>가 유리 (실측 +3.57% vs 다음날 시가 +3.44%)\n"
             "• P2: <b>다음날 시가 매수</b>가 유리 (급락 직후라 시초에 더 빠짐)\n"
             "• 공통: 다음날 시가가 <b>+5% 이상 갭상승</b>이면 매수 보류\n"
             "• P3·D1: <b>다음날 시가 매수</b> · <b>20거래일</b> 보유 (폭락 반등 — 흔들려도 손절 금지)\n"
             "• 보유: P1·P2 10거래일 / P3·D1 20거래일 · 손절 없음 · 1번만 +20% 익절")
    telegram(f"🆕 <b>신규 편입 종목</b> ({last_date[4:6]}/{last_date[6:]} 기준 · 코스피 {kmark})"
             + "".join(lines) + guide
             + f"\n\nhttps://bamhobak.github.io/kospi-volume/")
elif lines:
    print("첫 실행 — 기준 목록만 저장:", cur)
else:
    print("신규 편입 없음:", {k: len(v) for k, v in cur.items()})

rpc("kospi_state_set", {"p_pin": "__filters__", "p_data": {"filters": cur, "date": last_date, "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
print("저장:", {k: len(v) for k, v in cur.items()}, "held", len(held))
