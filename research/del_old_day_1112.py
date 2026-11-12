# 11-12 사용자 "지금 규칙이면 안 샀을 거래들 다 기록 삭제해줘" — 완료 데이 [갭하락]·+·++ 중 새 규칙(그물 -1.0 · 지정가 -2.0, 11-11~)이면 안 사졌을 것
import json, sys, time
from pathlib import Path
sys.path.insert(0, r"C:\vscode\kospi-volume"); sys.stdout.reconfigure(encoding="utf-8")
import autotrade as AT
BASE = Path(r"C:\vscode\kospi-volume")
DO = "--do" in sys.argv


def tick(p):
    t = 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000
    return int(p // t * t)


S = AT.site_state()
P = [p for p in S.get("positions_scalp") or [] if p.get("sell") and (p.get("filters") or ["?"])[0] in ("T1", "T2", "T3") and str(p.get("date")) < "20261111"]
snaps, drop, keep, unk = {}, [], [], []
for p in P:
    d = str(p["date"])
    if d not in snaps:
        f = BASE / "data" / "day" / ("snap_%s.json" % d)
        snaps[d] = {x["t"]: x for x in json.loads(f.read_text(encoding="utf-8")).get("cand") or []} if f.exists() else {}
    x = snaps[d].get(p["code"])
    if not x or not x.get("lim"): unk.append(p); continue
    thr_then = -1.5 if d >= "20261013" else (-0.75 if d >= "20261012" else -1.0)
    newlim = tick(float(x["lim"]) * (1 + (-2.0 - thr_then) / 100)); op = x.get("open") or float(p["price"])
    ok = x.get("rel") is not None and float(x["rel"]) <= -1.0 and op <= newlim
    (keep if ok else drop).append(p)
r = lambda L: sum((float(p["sell"]) / float(p["price"]) - 1) * 100 - 0.23 for p in L) / max(len(L), 1)
real = [p for p in drop if not p.get("paper")]
print("완료 데이(11-10까지) %d건 · 남김 %d(건당 %+.2f%%) · 지움 %d(실제 %d·가상 %d, 건당 %+.2f%%) · 판단 못 함 %d(남김)" % (
    len(P), len(keep), r(keep), len(drop), len(real), len(drop) - len(real), r(drop), len(unk)))
if not DO: sys.exit(0)
bk = BASE / "data" / "day" / ("positions_scalp_backup_%s.json" % time.strftime("%Y%m%d_%H%M"))
bk.write_text(json.dumps(S.get("positions_scalp"), ensure_ascii=False), encoding="utf-8")
ids = {p["id"] for p in drop}
n = {"k": 0}
def mut(X):
    before = len(X); X[:] = [x for x in X if x.get("id") not in ids]; n["k"] = before - len(X); return n["k"] > 0
AT.state_update("positions_scalp", mut, "지금 규칙이면 안 샀을 완료 데이 %d건 삭제(사용자 11-12)" % len(ids))
H = AT.HIDDEN; cur = json.loads(H.read_text(encoding="utf-8")) if H.exists() else {}
hid = set(cur.get("ids") or []) | {p["id"] for p in real}
cur["ids"] = sorted(hid); cur["why"] = str(cur.get("why") or "") + " · 2026-11-12 사용자 지시: " + "지금 규칙(그물 -1.0·지정가 -2.0)이면 안 샀을 완료 데이 실제 %d건 — 사이트에서 지움, 원장은 그대로" % len(real)
H.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
print("지움 %d · 백업 %s · 되살림 막기 목록 +%d (전체 %d)" % (n["k"], bk.name, len(real), len(hid)))
