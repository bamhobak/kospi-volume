# 11-23 사용자 "지워줘" — 사이트 데이 완료 기록 중 실금액 전환(11-18 17:00) 전 시험 때 것(2~3주짜리 포함) 전부. 원장은 그대로.
import json, sys, time, collections
from pathlib import Path
sys.path.insert(0, r"C:\vscode\kospi-volume"); sys.stdout.reconfigure(encoding="utf-8")
import autotrade as AT
BASE = Path(r"C:\vscode\kospi-volume"); DO = "--do" in sys.argv
A = AT.site_state().get("positions_scalp") or []
rid = lambda p: (p.get("filters") or ["?"])[0]
real_era = lambda p: str(p["date"]) >= "20261119" or (str(p["date"]) == "20261118" and rid(p) == "T6")     # 11-18 저녁 [장후 낙폭]부터 실금액
drop = [p for p in A if p.get("sell") and not real_era(p)]; keep = [p for p in A if p.get("sell") and real_era(p)]
real = [p for p in drop if not p.get("paper")]
print("지울 것 %d(실제 %d·가상 %d) 날짜 %s~%s 수량 %s · 남는 완료 %d(날짜 %s~, 실제 %d·가상 %d)" % (
    len(drop), len(real), len(drop) - len(real), min(str(p["date"]) for p in drop), max(str(p["date"]) for p in drop), dict(collections.Counter(int(float(p.get("qty") or 0)) for p in drop)),
    len(keep), min(str(p["date"]) for p in keep), sum(1 for p in keep if not p.get("paper")), sum(1 for p in keep if p.get("paper"))))
if not DO: sys.exit(0)
bk = BASE / "data" / "day" / ("positions_scalp_backup_%s.json" % time.strftime("%Y%m%d_%H%M")); bk.write_text(json.dumps(A, ensure_ascii=False), encoding="utf-8")
ids = {p["id"] for p in drop}; n = {"k": 0}
def mut(X):
    before = len(X); X[:] = [x for x in X if not (x.get("id") in ids and x.get("sell"))]; n["k"] = before - len(X); return n["k"] > 0
AT.state_update("positions_scalp", mut, "시험 때 완료 데이 기록 %d건 삭제(사용자 11-23)" % len(ids))
H = AT.HIDDEN; cur = json.loads(H.read_text(encoding="utf-8")) if H.exists() else {}
hid = set(cur.get("ids") or []) | {p["id"] for p in real}
cur["ids"] = sorted(hid); cur["why"] = str(cur.get("why") or "") + " · 2026-11-23 사용자 지시: 실금액 전 시험 때 완료 데이 실제 %d건 — 사이트에서 지움, 원장은 그대로" % len(real)
H.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
print("지움 %d · 백업 %s · 되살림 막기 +%d (전체 %d)" % (n["k"], bk.name, len(real), len(hid)))
