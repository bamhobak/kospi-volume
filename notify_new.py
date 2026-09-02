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
    ("P1", "조용한 신고가 (코스피·40일 보유·손절 -15%)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and r.get("fromhi") is not None and r["fromhi"] >= -10
     and r.get("a1") and r.get("a6") and r.get("aw")
     and r["a1"] / r["a6"] * 100 < 120 and r["aw"] / r["a1"] * 100 <= 120
     and r.get("fw5") is not None and r["fw5"] >= 3
     and r.get("fw60") is not None and r["fw60"] >= 1
     and r.get("vol20") is not None and r["vol20"] <= 2
     and r.get("sr20") is not None and r["sr20"] <= 0.5
     and r.get("ret20") is not None and r["ret20"] <= 5
     and (r.get("amt20") or 0) >= 200
     and not ((r.get("above20") or 0) > 70 and (r.get("ret250") or 0) > 120)
     and r.get("dilu") is not True and r.get("disc") is not True),
    ("P2", "조정매집 (코스피·10일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSPI" and (r.get("streak") or 0) >= 1 and fwp(r) >= 2 and not r["pref"]
     and (r.get("amt") or 0) >= 3 and r["a1"] / r["a6"] < 0.3
     and r.get("ret3") is not None and r["ret3"] <= -5
     and r.get("ret10") is not None and r["ret10"] <= 0
     and not bool(kospi.get("up20"))
     and r.get("srDown") is True and r.get("dilu") is not True and r.get("disc") is not True),
    ("P3", "폭락반등 (코스피·20일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and r.get("ret20") is not None and r["ret20"] <= -20
     and r.get("vs1") is not None and r["vs1"] >= 1.5
     and r.get("fw60") is not None and r["fw60"] >= 1
     and (r.get("amt20") if r.get("amt20") is not None else (r.get("amt") or 0)) >= 3
     and r.get("crc") is not None and r["crc"] <= -20
     and kospi.get("up60") is False
     and (r.get("sr60") is not None and r["sr60"] <= -10)
     and r.get("srDown") is True and r.get("dilu") is not True and r.get("disc") is not True),
    ("P4", "업종붕괴 이탈 (코스피·5일 보유·손절 -15%·하락장)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and kospi.get("up60") is False
     and (r.get("sr60") is not None and r["sr60"] <= -20)
     and r.get("dma20") is not None and r["dma20"] <= -10
     and r.get("mdd60") is not None and r["mdd60"] <= -40
     and r.get("srDown") is True
     and (r.get("amt20") or 0) >= 10 and (r.get("c") or 0) >= 1000
     and r.get("dilu") is not True and r.get("disc") is not True),
    ("D2", "저PBR 낙폭 (코스닥·40일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSDAQ" and not r["pref"]
     and r.get("pbrd") is not None and r["pbrd"] <= 0.5
     and r.get("ret20") is not None and r["ret20"] <= -10
     and r.get("vs1") is not None and r["vs1"] >= 2
     and (r.get("sr60") is not None and r["sr60"] <= -10)
     and kospi.get("up60") is False
     and r.get("ow20") is not None and r["ow20"] >= 0
     and r.get("srDown") is True
     and (r.get("amt20") or 0) >= 5 and (r.get("c") or 0) >= 1000
     and r.get("dilu") is not True and r.get("disc") is not True),
    ("D1", "낙폭과대 (코스닥·20일 보유·손절 없음)",
     lambda r: r.get("mk") == "KOSDAQ" and not r["pref"]
     and r.get("ret20") is not None and r["ret20"] <= -20
     and r.get("vs1") is not None and r["vs1"] >= 1.5
     and r.get("fw60") is not None and r["fw60"] >= 1
     and (r.get("amt20") or 0) >= 2
     and kospi.get("up60") is False
     and (r.get("sr60") is not None and r["sr60"] <= -20)
     and r.get("srDown") is True and (r.get("dbt") is None or r["dbt"] <= 200)
     and r.get("ow20") is not None and r["ow20"] >= 0
     and (r.get("c") or 0) >= 1000
     and r.get("dilu") is not True and r.get("disc") is not True),

    ("P7", "외인 매집 (코스피·60일 보유·상승장·내부자)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and kospi.get("up60") is True
     and r.get("cap") is not None and 10000 <= r["cap"] < 100000
     and r.get("fw20") is not None and r["fw20"] >= 1
     and r.get("ow60") is not None and r["ow60"] < 0.4
     and (r.get("a1") and r.get("a6") and 100 <= r["a1"] / r["a6"] * 100 < 150)
     and r.get("fromhi") is not None and r["fromhi"] >= -15
     and r.get("fromlo") is not None and r["fromlo"] >= 70
     and (r.get("ins60") or 0) > 0
     and r.get("dilu") is not True and r.get("disc") is not True),

    ("P6", "깊은 이격 (코스피·5일 보유·손절 -10%·하락장)",
     lambda r: r.get("mk") == "KOSPI" and not r["pref"]
     and kospi.get("up60") is False
     and r.get("dev25") is not None and r["dev25"] <= -25
     and r.get("sr60") is not None and r["sr60"] <= -20
     and (r.get("amt20") or 0) >= 10 and (r.get("c") or 0) >= 1000
     and r.get("dilu") is not True and r.get("disc") is not True),

    ("P5", "자사주 낙폭 (공통·10일 보유)",
     lambda r: not r["pref"] and r.get("bb") is True
     and r.get("r3m") is not None and r["r3m"] <= -20
     and kospi.get("up60") is False),
]

LEGACY_ID = {1: "P0", 2: "P2", 3: "P3", 4: "P1"}          # 예전 숫자 id 호환
POSI = rpc("kospi_state_positions", {}) or []
# 종목별 "어느 규칙으로 샀는지". 같은 규칙에 다시 걸린 건 새 신호가 아니지만,
# 다른 규칙에 걸린 건 추가 매수 후보라 따로 알린다.
held_by = {}
for _p in POSI:
    held_by.setdefault(_p["code"], set()).update(
        str(LEGACY_ID.get(f, f)) for f in (_p.get("filters") or []))
held = set(held_by)
cur = {}
for fid, name, fn in FILTERS:
    cur[str(fid)] = sorted(r["t"] for r in rows
                           if fn(r) and str(fid) not in held_by.get(r["t"], set()))

prev_state = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
prev = prev_state.get("filters", {})
prev_date = prev_state.get("date", "")
info = {r["t"]: r for r in rows}

lines = []
for fid, name, _ in FILTERS:
    k = str(fid)
    new = [t for t in cur[k] if t not in set(prev.get(k, []))]
    if not new: continue
    lines.append(f"\n<b>[{name}]</b>")
    for t in new:
        r = info[t]
        chp = (r["ch"] / (r["c"] - r["ch"]) * 100) if r.get("c") and r.get("ch") and r["c"] != r["ch"] else 0
        # 🔁 = 다른 규칙으로 이미 보유 중(추가 매수하면 한 종목 비중이 두 배가 된다)
        mark = "  🔁" if t in held_by else ""
        lines.append(f"• <b>{r['n']}</b> ({t}) {r['c']:,}원 ({chp:+.1f}%){mark}")

if lines and prev_date:   # 첫 실행(비교 대상 없음)에는 보내지 않음
    # 알림은 '무엇이 새로 들어왔나'만 전한다. 지표·매수 안내는 사이트에서 본다.
    telegram(f"🆕 <b>신규 편입 종목</b> ({last_date[4:6]}/{last_date[6:]})"
             + "".join(lines)
             + f"\n\nhttps://bamhobak.github.io/kospi-volume/")
elif lines:
    print("첫 실행 — 기준 목록만 저장:", cur)
else:
    print("신규 편입 없음:", {k: len(v) for k, v in cur.items()})

rpc("kospi_state_set", {"p_pin": "__filters__", "p_data": {"filters": cur, "date": last_date, "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
print("저장:", {k: len(v) for k, v in cur.items()}, "held", len(held))
