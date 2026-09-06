# -*- coding: utf-8 -*-
"""지금 보유 중인 종목의 진행 상황 — 매수가·현재가·경과일·예정 매도일·손절선."""
import io, json, os, sys, urllib.request, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
BASE = Path(__file__).parent
# 접속 정보는 assets/sb.js 와 index.html 에 있다(selftest.py 와 같은 방식)
import re
sb = (BASE/"assets"/"sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", sb).group(1); KEY = re.search(r"key:'([^']+)'", sb).group(1)
HTML = (BASE/"index.html").read_text(encoding="utf-8")
PIN = re.search(r"DEFAULT_PIN='([^']+)'", HTML).group(1)
def rpc(fn, body):
    r = urllib.request.Request(f"{URL}/rest/v1/rpc/{fn}", data=json.dumps(body).encode(),
        headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=40).read().decode())
st = rpc("kospi_state_get", {"p_pin": PIN}) or {}
pos = st.get("positions") or []
print(f"보유 {len(pos)}건 · 상태 저장 시각 {st.get('updated','-')}\n")
print(json.dumps(pos, ensure_ascii=False, indent=1)[:2000])
