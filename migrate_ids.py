# -*- coding: utf-8 -*-
"""규칙 id 마이그레이션: 숫자(1~4) → 코드(P1/P2/P3/D1)
   대상 ① 보유종목 positions[].filters  ② notify_new 의 __filters__ 신규판정 상태
   ②를 안 옮기면 다음 실행에서 모든 신호를 '신규'로 보고 알림이 쏟아진다.
"""
import io, json, re, sys, urllib.request
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = Path(__file__).parent
sb = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", sb).group(1)
KEY = re.search(r"key:'([^']+)'", sb).group(1)
PIN = re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)
MAP = {1: "P1", 2: "P2", 3: "P3", 4: "D1", "1": "P1", "2": "P2", "3": "P3", "4": "D1"}

def rpc(fn, body):
    req = urllib.request.Request(f"{URL}/rest/v1/rpc/{fn}", method="POST",
        data=json.dumps(body).encode(),
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip() else None

# ── ① 보유종목 ───────────────────────────────────────────────
st = rpc("kospi_state_get", {"p_pin": PIN}) or {}
pos = st.get("positions") or []
n = 0
for p in pos:
    old = p.get("filters") or []
    new = [MAP.get(f, f) for f in old]
    if new != old: p["filters"] = new; n += 1
if n:
    rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"positions": pos}})
print(f"① 보유종목: {len(pos)}건 중 {n}건 변환")
for p in pos[:10]:
    print(f"   {p.get('name')} ({p.get('code')}) filters={p.get('filters')}")

# ── ② 신규판정 상태 ──────────────────────────────────────────
fs = rpc("kospi_state_get", {"p_pin": "__filters__"}) or {}
old = fs.get("filters") or {}
new = {MAP.get(k, k): v for k, v in old.items()}
if new != old:
    fs["filters"] = new
    rpc("kospi_state_set", {"p_pin": "__filters__", "p_data": fs})
    print(f"② __filters__ 키 변환: {sorted(old)} → {sorted(new)}")
else:
    print(f"② __filters__ 변환 불필요 (현재 키 {sorted(old) or '없음'})")
print(f"   기준일 {fs.get('date','-')} · 각 규칙 신호수 " +
      ", ".join(f"{k}={len(v)}" for k, v in sorted(new.items())) if new else "   (비어 있음)")
