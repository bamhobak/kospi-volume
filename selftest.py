# -*- coding: utf-8 -*-
"""전체 자체 테스트 — 실제로 돌려 보고 어긋난 곳을 찾는다.

왜 만들었나: 조건이 사이트(index.html) · 알림(notify_new.py) · 백테스트(portfolio.py)
세 곳에 각각 적혀 있는데, 지금까지 '글자' 로만 비교했다(audit_rules.py). 그래서
표기가 다르면 오탐이 나고, 한쪽에만 조건이 빠지면 침묵 목록에 가려 놓쳤다.
여기서는 같은 데이터를 넣고 **같은 종목이 나오는지 실제로 실행해서** 본다.

검사 항목
  1) 데이터      table.json 최신성 · 규칙이 쓰는 필드가 살아 있는가
  2) 판정 일치    사이트와 알림이 같은 종목을 뽑는가 (실행 비교 — 이게 핵심)
  3) 알림 경로    Edge Function 이 보유 종목의 규칙을 읽는가 · 규칙표가 사이트와 맞는가
  4) 동기화      상태 저장/조회 왕복 · 보유 종목 구조
  5) 스케줄      장중 시세 크론 · 수집 최신일
  6) 화면        JS 문법 · 매도일 계산

사용: python selftest.py
"""
import io, re, sys, json, subprocess, datetime as dt, urllib.request, urllib.error
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
FAIL = []
def ok(msg): print(f"    ✅ {msg}")
def ng(msg): FAIL.append(msg); print(f"    ❌ {msg}")
def warn(msg): print(f"    ⚠  {msg}")

sb = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", sb).group(1); KEY = re.search(r"key:'([^']+)'", sb).group(1)
HTML = (BASE / "index.html").read_text(encoding="utf-8")
PIN = re.search(r"DEFAULT_PIN='([^']+)'", HTML).group(1)
def rpc(fn, body, timeout=25):
    r = urllib.request.Request(f"{URL}/rest/v1/rpc/{fn}", data=json.dumps(body).encode(),
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as x:
        t = x.read().decode(); return json.loads(t) if t.strip() else None
now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=9)
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}

print("\n## 1) 데이터")
tj = BASE / "site" / "data" / "table.json"
if not tj.exists(): ng("table.json 이 없다 — 사이트가 빈다"); sys.exit(1)
T = json.loads(tj.read_text(encoding="utf-8"))
rows, last = T["rows"], T["dates"][-1]
age = (now.date() - dt.datetime.strptime(last, "%Y%m%d").date()).days
(ok if age <= 4 else warn)(f"최신 거래일 {last} ({age}일 전) · {len(rows):,}종목")
used = set(re.findall(r"r\.([A-Za-z_]\w*)", HTML[HTML.find("const FILTERS="):HTML.find("const LEGACY_ID")]))
SAFE = {"mk","pref","ticker","name","close","change","th","vols","avg","total","indiv","organ",
        "frgn","last","chpct","fwp","fw","v5","r16","rw1","streak","dilu","get","ratio"}
# 이벤트성 필드는 '오늘 그 일이 있었나' 라서 값이 전부 비어도 정상일 수 있다
# (bb 는 마지막 거래일 당일 자사주 공시만 켠다 — 공시 없는 날이 대부분이다).
# 그래서 이 필드들은 table.json 이 아니라 원본 파일이 비었는지로 판단한다.
EVENT = {"bb": "buyback_recent.csv", "dilu": "dilution_recent.csv",
         "disc": "dilution_recent.csv", "ins60": "insider_recent.csv",
         "crc": "credit_recent.csv"}
for fn in sorted(set(EVENT.values())):
    f = BASE / "data" / fn
    n = sum(1 for _ in f.open(encoding="utf-8")) if f.exists() else 0
    if n <= 1: ng(f"data/{fn} 이 비어 있다({n}줄) — 이 파일을 쓰는 규칙이 조용히 0건이 된다")
    else: ok(f"data/{fn} {n-1:,}행")
dead = []
for f in sorted(used - SAFE - set(EVENT)):
    vals = [r.get(f) for r in rows]
    if all(v in (None, 0, False, "") for v in vals): dead.append(f)
(ok if not dead else ng)("규칙이 쓰는 필드가 살아 있다" if not dead
                        else f"값이 전부 빈 필드 {dead} — 수집 실패")

print("\n## 2) 사이트와 알림이 같은 종목을 뽑는가 (실행 비교)")
try:
    out = subprocess.run([r"node", "site_eval.js"], cwd=str(BASE), capture_output=True, timeout=180)
    SITE = json.loads(out.stdout.decode("utf-8"))
except Exception as e:
    ng(f"사이트 규칙을 실행하지 못했다: {e}"); SITE = None
if SITE:
    # 알림(notify_new.py)의 FILTERS 를 같은 데이터로 실행한다
    src = (BASE / "notify_new.py").read_text(encoding="utf-8")
    seg = src[src.index("T = json.loads"):src.index("LEGACY_ID = ")]
    g = {"json": json, "BASE": BASE, "re": re}
    try:
        exec(compile(seg, "notify_new.py(FILTERS)", "exec"), g)
        NOTI = {str(fid): sorted(r["t"] for r in g["rows"] if fn(r)) for fid, nm, fn in g["FILTERS"]}
    except Exception as e:
        ng(f"알림 규칙을 실행하지 못했다: {e}"); NOTI = None
    if NOTI is not None:
        bad = 0
        for rid in SITE["meta"]["ids"]:
            a, b = set(SITE["rules"][rid]), set(NOTI.get(rid, []))
            if a != b:
                bad += 1
                ng(f"[{NAME.get(rid,rid)}] 판정 불일치 — 사이트만 {sorted(a-b) or '없음'} · 알림만 {sorted(b-a) or '없음'}")
        if not bad: ok(f"9규칙 모두 같은 종목을 뽑는다 (오늘 신호 "
                       f"{sum(len(v) for v in SITE['rules'].values())}건)")

print("\n## 3) 알림 경로")
ts = (BASE / "supabase" / "functions" / "prices" / "index.ts").read_text(encoding="utf-8")
ER = {m[0]: (m[1], m[3]) for m in re.findall(
    r"(\w+):\s*\{\s*stop:\s*([\d.]+|null),\s*target:\s*([\d.]+|null),\s*hold:\s*(\d+)", ts)}
if SITE:  # 화면에 적힌 보유기간·손절이 알림의 규칙표와 같은가
    bad = 0
    for rid in SITE["meta"]["ids"]:
        h, s_ = SITE["meta"]["hold"].get(rid), SITE["meta"]["stop"].get(rid)
        if rid not in ER: ng(f"[{NAME.get(rid,rid)}] 이 알림 규칙표에 없다 — 청산 알림이 안 간다"); bad += 1; continue
        eh, es = int(ER[rid][1]), (None if ER[rid][0] == "null" else float(ER[rid][0]) * 100)
        if h != eh or (s_ or None) != (es if es is None else round(es)):
            ng(f"[{NAME.get(rid,rid)}] 보유/손절 다름 — 사이트 {h}일·{s_} vs 알림 {eh}일·{es}"); bad += 1
    if not bad: ok("9규칙의 보유기간·손절이 사이트와 알림에서 같다")
try:
    r = urllib.request.Request(f"{URL}/functions/v1/prices?alerts=0", data=b"{}",
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    m = (json.loads(urllib.request.urlopen(r, timeout=40).read().decode()) or {}).get("_meta") or {}
    held, ruled = m.get("held", 0), m.get("ruled", 0)
    if held and not ruled: ng(f"보유 {held}종목인데 규칙이 붙은 건 0 — 청산 알림이 나가지 않는다")
    elif held: ok(f"보유 {held}종목 중 {ruled}종목에 규칙이 붙어 있다 (알림 대상)")
    else: warn("보유 종목이 없어 알림 경로를 끝까지 확인하지 못했다")
except Exception as e: ng(f"시세 함수 호출 실패: {e}")

print("\n## 4) 동기화")
try:
    st = rpc("kospi_state_get", {"p_pin": PIN}) or {}
    pos = st.get("positions") or []
    bad = [p for p in pos if not (p.get("code") and p.get("date") and p.get("price"))]
    (ok if not bad else ng)(f"보유 {len(pos)}건 구조 정상" if not bad else f"필수 항목이 빠진 보유 {len(bad)}건")
    (ok if ("updated" in st or not pos) else warn)(
        "저장 시각(updated)이 있다 — 기기 간 최신본 판별 가능" if "updated" in st
        else "저장 시각이 없다 — 예전에 저장된 상태다(다음 저장 때 생긴다)")
    f = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
    # 알림 기준일이 최신 거래일보다 뒤처져 있으면 그 사이 알림이 통째로 유실된 것이다.
    # 워크플로가 continue-on-error 라 초록불이어도 이 값은 정직하다(2026-09-04 유실 사례).
    fd = f.get("date") or ""
    (ok if fd == last else ng)(
        f"알림 기준일이 최신 거래일과 같다 ({fd})" if fd == last
        else f"알림 기준일 {fd or "없음"} < 최신 거래일 {last} — 그 사이 신규 편입 알림이 나가지 않았다")
    ok(f"신호 연속 일수 {len(f.get('streaks') or {})}건 기록")
except Exception as e: ng(f"상태 조회 실패: {e}")

print("\n## 5) 스케줄")
try:
    p = rpc("kospi_state_get", {"p_pin": "__prices__"}) or {}
    u = p.get("updated") or ""
    mins = (now - dt.datetime.strptime(u, "%Y-%m-%d %H:%M").replace(tzinfo=now.tzinfo)).total_seconds() / 60 if u else 9e9
    trading = now.weekday() < 5 and dt.time(9, 0) <= now.time() <= dt.time(15, 45)
    if trading and mins > 25: ng(f"장중인데 시세가 {mins:.0f}분째 갱신되지 않았다 (마지막 {u}) — 크론 확인")
    else: ok(f"장중 시세 크론 정상 (마지막 갱신 {u}{'' if trading else ' · 지금은 장외'})")
except Exception as e: ng(f"시세 상태 확인 실패: {e}")

print("\n## 6) 화면")
try:
    js = subprocess.run([r"node", "-e", """
      const fs=require('fs'),h=fs.readFileSync('index.html','utf8');
      const m=[...h.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)];
      let bad=0; m.forEach(x=>{try{new Function(x[1])}catch(e){bad++;console.log(e.message)}});
      process.exit(bad?1:0);"""], cwd=str(BASE), capture_output=True, timeout=120)
    (ok if js.returncode == 0 else ng)("JS 문법 정상" if js.returncode == 0
                                       else "JS 문법 오류: " + js.stdout.decode('utf-8')[:120])
except Exception as e: ng(f"JS 검사 실패: {e}")
if SITE:
    hol = re.search(r"const HOLIDAY=new Set\(\[([^\]]*)\]\)", HTML)
    days = re.findall(r"'(\d{8})'", hol.group(1)) if hol else []
    fut = [d for d in days if d >= now.strftime("%Y%m%d")]
    (ok if len(fut) >= 3 else warn)(f"휴장일 목록에 앞으로의 날짜 {len(fut)}건 — 매도일 추정에 쓴다"
        if len(fut) >= 3 else f"휴장일 목록이 {len(fut)}건뿐 — 매도일이 밀려 보일 수 있다(갱신 필요)")

print(f"\n{'='*60}")
if FAIL:
    print(f"❌ 문제 {len(FAIL)}건")
    for m in FAIL: print(f"   · {m}")
else:
    print("✅ 전체 통과")
sys.exit(1 if FAIL else 0)
