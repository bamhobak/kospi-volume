"""day_alert.open_guard 가짜 시험(2026-10-26 사용자 "후보 많아질 걸 미리 대비") — python research/test_open_guard.py [종목 수] — 토스 호출 없이 M.get(시세·1분봉)·AT.call(취소)을 바꿔 끼운다(실주문 없음).
N종목 · 시가 단일가는 t=T_OPEN 초에 한꺼번에 찍힘(실제처럼) · 종목마다 그 뒤 0~8초에 다음 체결(시세 시각이 09:00:05 를 넘어감)
· 1분봉 09:01 봉은 시가 뒤 0~2초에 나타남 · 5% 확률로 429 · 3종목은 거래 없음."""
import sys, time, random, threading, datetime as dt
sys.path.insert(0, r"C:\vscode\kospi-volume"); sys.path.insert(0, r"C:\temp\dg")
import autotrade as AT
import day_alert as DA
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120
T_OPEN = 1.0
AT.DRY = False
calls = {"prices": 0, "candles": 0, "cancel": 0}
lock = threading.Lock()
t0 = time.time()
S = {}
for i in range(N):
    s = "S%03d" % i
    S[s] = dict(op=1000 + random.choice([-20, 0, 20]), nxt=T_OPEN + random.uniform(0, 8), bar=T_OPEN + random.uniform(0, 2), dead=i < 3)
def ts_of(sec):
    return "2026-10-27T09:00:%02d.000+09:00" % min(59, int(sec))
def fake_get(path, **q):
    AT._pace()
    if random.random() < 0.05: raise RuntimeError("HTTP 429 가짜")
    el = time.time() - t0
    if path == "/api/v1/prices":
        with lock: calls["prices"] += 1
        out = []
        for s in q["symbols"].split(","):
            x = S[s]
            if x["dead"] or el < T_OPEN: out.append({"symbol": s, "timestamp": "2026-10-27T08:59:59.000+09:00", "lastPrice": "999"}); continue
            sec = el - T_OPEN if el < x["nxt"] else el - T_OPEN + 6          # 다음 체결 뒤엔 시각이 05초를 넘김
            out.append({"symbol": s, "timestamp": ts_of(sec), "lastPrice": str(x["op"] if el < x["nxt"] else x["op"] + 10)})
        return out
    if path == "/api/v1/candles":
        with lock: calls["candles"] += 1
        x = S[q["symbol"]]
        if x["dead"] or el < x["bar"]: return {"candles": []}
        return {"candles": [{"timestamp": "2026-10-27T09:01:00.000+09:00", "openPrice": str(x["op"]), "volume": "100"}]}
    raise RuntimeError(path)
CT = []
def fake_call(method, path, acct=False, body=None, **q):
    with lock: calls["cancel"] += 1; CT.append(time.time() - t0 - T_OPEN)
    AT._pace(); return {}
DA.M.get = fake_get
AT.call = fake_call
placed = []
for i, s in enumerate(S):
    for rid in (["T1", "T2"] if i % 4 == 0 else ["T1"]):
        placed.append({"oid": "%s-%s" % (s, rid), "t": s, "lim": 1000, "rid": rid, "name": s})
placed.append({"oid": "MKT", "t": "S010", "lim": None, "rid": "T1", "name": "시장가"})
DA.open_guard(placed, "20261027", until_s=40)
el = time.time() - t0
canc = [o for o in placed if o.get("canceled")]
should = [o for o in placed if o.get("lim") and S[o["t"]]["op"] > 1000 and not S[o["t"]]["dead"]]
wrong_open = [o["oid"] for o in placed if "open" in o and o["open"] != S[o["t"]]["op"]]
print("종목 %d · 주문 %d · 걸린 %.1f초 · 시세 묶음 %d번 · 1분봉 %d번 · 취소 %d번 · 취소 %d / 해야 할 것 %d · 시가 못 본 주문 %d(거래 없는 3종목 몫 %d) · 시가 틀림 %d" % (
    N, len(placed), el, calls["prices"], calls["candles"], calls["cancel"], len(canc), len(should),
    sum(1 for o in placed if "open" not in o), sum(1 for o in placed if S[o["t"]]["dead"]), len(wrong_open)))
print("잘못 취소:", [o["oid"] for o in canc if o not in should][:5], "· 놓친 취소:", [o["oid"] for o in should if o not in canc][:5])
print("취소 시각(시가 뒤 초): 처음 %.1f · 중앙 %.1f · 마지막 %.1f" % (min(CT), sorted(CT)[len(CT) // 2], max(CT)) if CT else "취소 없음")
