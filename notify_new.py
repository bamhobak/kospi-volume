"""신규 편입 종목 텔레그램 알림
- site/data/table.json(빌드 결과)을 사이트와 동일한 기준으로 판정
- 어제 목록(Supabase '__filters__')과 비교해 새로 들어온 종목만 알림
- 보유 중(미매도) 종목은 사이트와 동일하게 제외
매일 수집(18:30) 워크플로 마지막에 실행
"""
import re, os, io, json, sys, datetime as dt
from pathlib import Path
import requests

# 윈도우 콘솔은 기본이 cp949 라 이모지가 섞이면 print 에서 죽는다(텔레그램 미설정 시
# 메시지를 그대로 찍기 때문에 로컬 점검이 항상 실패했다). 표준출력을 UTF-8 로 고정한다.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = Path(__file__).parent
js = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", js).group(1); KEY = re.search(r"key:'([^']+)'", js).group(1)
H = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
TG_TOKEN, TG_CHAT = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
# --dry: 판정만 보고 텔레그램도 상태 저장도 하지 않는다(재전송 워크플로의 점검용).
# 상태를 저장해 버리면 오늘 걸린 종목이 '이미 알린 것' 이 되어 진짜 알림이 사라진다.
DRY = "--dry" in sys.argv
if DRY: TG_TOKEN = TG_CHAT = None
now_kst = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)

def rpc(fn, body):
    r = requests.post(f"{URL}/rest/v1/rpc/{fn}", headers=H, json=body, timeout=20); r.raise_for_status()
    return r.json() if r.text else None

def telegram(text):
    if not (TG_TOKEN and TG_CHAT): print("텔레그램 미설정:", text.replace("\n", " | ")); return
    # 전송 실패가 이 스크립트를 죽이면 안 된다 — 알림은 부가 기능인데 그것 때문에
    # 워크플로가 실패하면 그날 수집 데이터가 통째로 커밋되지 않는다(2026-09-03 발생).
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=30)
        print("텔레그램:", r.status_code, r.text[:200])
    except Exception as e:
        print("텔레그램 전송 실패(무시하고 계속):", repr(e)[:200])

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
     lambda r: r.get("mk") == "KOSPI" and fwp(r) >= 2 and not r["pref"]
     # a1(2개월 평균)·a6(1년 평균)은 신규 상장주에서 None 이다. 사이트는 r16=null 로
     # 두고 비교에서 걸러내는데 여기만 바로 나눠서, 그런 종목이 하나라도 끼면
     # 스크립트가 통째로 죽어 그날 알림이 전부 사라졌다(2026-09-04 코리아써키트).
     and r.get("a1") and r.get("a6") and r["a1"] / r["a6"] < 0.3
     # 최근 3거래일 거래량 >= 2개월 평균의 200%. 사이트(rw1>=200)에는 있는데 여기만
     # 빠져 있어 알림이 더 헐겁게 나갔다(2026-09-03 selftest 로 발견).
     and r.get("aw") and r.get("a1") and r["aw"] / r["a1"] >= 2
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
     and r.get("crc") is not None and r["crc"] <= -15
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
# 보유 종목. kospi_state_positions RPC 는 filters 를 버리고 돌려주기 때문에 쓸 수 없다
# (그러면 held_by 가 늘 비어, 이미 그 규칙으로 산 종목이 계속 '신규 편입' 으로 알림이 간다).
# anon 키로는 테이블을 직접 못 읽으므로 사이트가 쓰는 PIN 의 상태를 그대로 읽는다.
# ⚠ 다른 PIN 의 보유 종목은 보지 못한다 — 여러 PIN 을 쓰게 되면 RPC 를 고쳐야 한다.
PIN = re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)
POSI = [p for p in ((rpc("kospi_state_get", {"p_pin": PIN}) or {}).get("positions") or [])
        if p and p.get("code") and not p.get("sell")]
# 종목별 "어느 규칙으로 샀는지". 같은 규칙에 다시 걸린 건 새 신호가 아니지만,
# 다른 규칙에 걸린 건 추가 매수 후보라 따로 알린다.
held_by = {}
for _p in POSI:
    held_by.setdefault(_p["code"], set()).update(
        str(LEGACY_ID.get(f, f)) for f in (_p.get("filters") or []))
held = set(held_by)
# 한 종목의 결측값 때문에 규칙 전체가 죽으면 그날 알림이 통째로 사라진다.
# 데이터가 이상한 종목 하나는 건너뛰고 나머지는 정상적으로 알린다.
BROKEN = []
def ok(fn, r, fid):
    try: return bool(fn(r))
    except Exception as e:
        BROKEN.append(f"{fid}:{r['t']}({type(e).__name__})"); return False

cur = {}
for fid, name, fn in FILTERS:
    cur[str(fid)] = sorted(r["t"] for r in rows
                           if ok(fn, r, fid) and str(fid) not in held_by.get(r["t"], set()))
# 연속 일수용은 보유 여부로 거르지 않은 '조건 충족' 그대로다 — 신호가 이어지는지가
# 보유 여부에 좌우되면 안 된다.
hits = {str(fid): {r["t"] for r in rows if ok(fn, r, fid)} for fid, name, fn in FILTERS}
if BROKEN:
    print(f"⚠ 판정 중 예외 {len(BROKEN)}건(해당 종목만 제외):", ", ".join(BROKEN[:10]))

prev_state = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
prev = prev_state.get("filters", {})
prev_date = prev_state.get("date", "")

# 규칙별·종목별 '신호가 며칠째 이어지는가'. [외인 매집] 추가매수 판정이 쓴다.
# 과거를 소급 계산할 수 없어(그날의 지표를 다시 만들어야 한다) 매일 하루씩 누적한다.
# 같은 날 두 번 돌아도 늘지 않게 날짜가 바뀐 경우에만 갱신한다.
prev_stk = prev_state.get("streaks") or {}
if prev_date == last_date:
    streaks = prev_stk                      # 같은 날 재실행 — 그대로 둔다
else:
    streaks = {f"{fid}:{t}": prev_stk.get(f"{fid}:{t}", 0) + 1
               for fid, ts in hits.items() for t in ts}
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

if DRY: print("--dry — 기준 목록을 저장하지 않는다")
else:
    rpc("kospi_state_set", {"p_pin": "__filters__", "p_data": {"filters": cur, "streaks": streaks,
                                                              "date": last_date, "updated": now_kst.strftime("%Y-%m-%d %H:%M")}})
print("저장:", {k: len(v) for k, v in cur.items()}, "held", len(held),
      "연속2일+", sum(1 for v in streaks.values() if v >= 2))
