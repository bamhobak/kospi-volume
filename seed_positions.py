# -*- coding: utf-8 -*-
"""테스트용 샘플 보유종목 생성 — 1·2·3·4번 필터별로 실제 신호가 났던 종목을 넣는다.
   사이트와 같은 Supabase 상태(kospi_state_set)에 저장하므로 브라우저에서 바로 보인다.
사용: python seed_positions.py [--clear]   (--clear 는 보유종목 전체 삭제)
"""
import io, json, re, sys, time, urllib.request
from pathlib import Path
import pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = Path(__file__).parent
sb = (BASE / "assets" / "sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", sb).group(1)
KEY = re.search(r"key:'([^']+)'", sb).group(1)
PIN = re.search(r"DEFAULT_PIN='([^']+)'", (BASE / "index.html").read_text(encoding="utf-8")).group(1)

def rpc(fn, body):
    req = urllib.request.Request(f"{URL}/rest/v1/rpc/{fn}", method="POST",
        data=json.dumps(body).encode(), headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                                                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t.strip() else None

if "--clear" in sys.argv:
    rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"positions": []}})
    print("보유종목 전체 삭제 완료"); sys.exit()

# 백테스트에서 실제 신호가 났던 거래를 필터별로 뽑는다
PICKS = []
def take(csv_path, fid, n, market, src_label=None):
    """src_label: CSV 안의 필터 라벨(코스닥 파일은 4번을 '3번 폭락반등'으로 적어둠)"""
    try:
        t = pd.read_csv(csv_path, dtype={"date": str, "ticker": str, "t": str, "d": str})
    except Exception as e:
        print(f"  [{fid}번] {csv_path} 없음 — 건너뜀 ({str(e)[:40]})"); return
    t.columns = [c.lstrip("﻿") for c in t.columns]
    dc = "date" if "date" in t.columns else "d"
    tc = "ticker" if "ticker" in t.columns else "t"
    lab = src_label or f"{fid}번"
    if "F" in t.columns and t.F.str.startswith(lab).any():   # 합쳐진 파일이면 해당 필터만
        t = t[t.F.str.startswith(lab)]
    t = t[t[dc] >= "20250101"] if (t[dc] >= "20250101").any() else t
    t = t.sort_values(dc).tail(n)
    for r in t.itertuples():
        PICKS.append(dict(code=getattr(r, tc), date=getattr(r, dc), fid=fid, market=market,
                          name=getattr(r, "name", None) or getattr(r, "nm", None),
                          close=getattr(r, "close", None)))

take("data/kp_full_trades.csv", 1, 2, "KOSPI")
take("data/kp_full_trades.csv", 2, 2, "KOSPI")
take("data/kp_full_trades.csv", 3, 2, "KOSPI")
take("data/kd_full_trades.csv", 4, 2, "KOSDAQ", src_label="3번")   # 코스닥 파일은 4번을 3번으로 라벨링

# 종목명·매수가는 사이트 데이터에서 채운다
T = json.load(open("site/data/table.json", encoding="utf-8"))
INFO = {r["t"]: r for r in T["rows"]}
rows = []
for i, p in enumerate(PICKS):
    r = INFO.get(p["code"])
    nm = (r or {}).get("n") or p["name"] or p["code"]
    price = (r or {}).get("c") or p.get("close")   # 사이트에 없으면 거래 CSV의 종가
    if not price or price != price: continue
    rows.append({"code": p["code"], "name": nm, "date": p["date"], "price": int(price),
                 "qty": max(1, round(3_000_000 / price)), "filters": [p["fid"]],
                 "id": int(time.time() * 1000) + i})

if not rows:
    print("샘플을 만들 수 없습니다 (거래 CSV 또는 table.json 확인)"); sys.exit(1)
cur = rpc("kospi_state_get", {"p_pin": PIN}) or {}
old = cur.get("positions") or []
rpc("kospi_state_set", {"p_pin": PIN, "p_data": {"positions": old + rows}})
print(f"샘플 {len(rows)}건 추가 (기존 {len(old)}건 유지)\n")
print("| 필터 | 종목 | 매수일 | 매수가 | 수량 |\n|---|---|---|---|---|")
for r in rows:
    print(f"| {r['filters'][0]}번 | {r['name']} ({r['code']}) | {r['date']} | {r['price']:,}원 | {r['qty']:,}주 |")
print("\n브라우저에서 '보유 종목' 탭을 열면 보입니다 (PIN 기본값 자동 동기화).")
print("지우려면: python seed_positions.py --clear")
