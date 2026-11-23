# 11-23 사용자 "데이규칙 완료건 중에 수량이 1건인 것들은 다 없애줘" — 사이트 데이 완료 기록(positions_scalp, 판 것) 중 수량 1 전부(실제·가상). 원장(ledger)은 그대로.
import json, sys, time, collections
from pathlib import Path
sys.path.insert(0, r"C:\vscode\kospi-volume"); sys.stdout.reconfigure(encoding="utf-8")
import autotrade as AT
BASE = Path(r"C:\vscode\kospi-volume")
DO = "--do" in sys.argv
S = AT.site_state()
A = S.get("positions_scalp") or []
done = [p for p in A if p.get("sell")]
drop = [p for p in done if float(p.get("qty") or 0) == 1]
keep = [p for p in done if float(p.get("qty") or 0) != 1]
real = [p for p in drop if not p.get("paper")]
r = lambda L: sum((float(p["sell"]) / float(p["price"]) - 1) * 100 - 0.23 for p in L) / max(len(L), 1)
print("데이 전체 %d(보유 %d · 완료 %d) · 지울 것(완료·수량 1) %d(실제 %d·가상 %d, 건당 %+.2f%%) · 남는 완료 %d(건당 %+.2f%%)" % (
    len(A), len(A) - len(done), len(done), len(drop), len(real), len(drop) - len(real), r(drop), len(keep), r(keep)))
print("지울 것 규칙별:", dict(collections.Counter((p.get("filters") or ["?"])[0] for p in drop)))
print("지울 것 날짜:", min(str(p["date"]) for p in drop) if drop else "-", "~", max(str(p["date"]) for p in drop) if drop else "-",
      "· 실금액 뒤(11-18 저녁~) 산 것 %d건" % sum(1 for p in drop if str(p["date"]) >= "20261119" or (str(p["date"]) == "20261118" and (p.get("filters") or ["?"])[0] == "T6")))
print("남는 완료 수량 분포:", dict(collections.Counter("2주↑" if float(p.get("qty") or 0) > 1 else "기타" for p in keep)), "· 날짜", min(str(p["date"]) for p in keep) if keep else "-", "~")
if not DO: sys.exit(0)
bk = BASE / "data" / "day" / ("positions_scalp_backup_%s.json" % time.strftime("%Y%m%d_%H%M"))
bk.write_text(json.dumps(A, ensure_ascii=False), encoding="utf-8")
ids = {p["id"] for p in drop}; n = {"k": 0}
def mut(X):
    before = len(X); X[:] = [x for x in X if not (x.get("id") in ids and x.get("sell"))]; n["k"] = before - len(X); return n["k"] > 0
AT.state_update("positions_scalp", mut, "완료 데이 수량 1 기록 %d건 삭제(사용자 11-23)" % len(ids))
H = AT.HIDDEN; cur = json.loads(H.read_text(encoding="utf-8")) if H.exists() else {}
hid = set(cur.get("ids") or []) | {p["id"] for p in real}
cur["ids"] = sorted(hid); cur["why"] = str(cur.get("why") or "") + " · 2026-11-23 사용자 지시: 완료 데이 수량 1 기록 실제 %d건 — 사이트에서 지움, 원장은 그대로" % len(real)
H.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
print("지움 %d · 백업 %s · 되살림 막기 목록 +%d (전체 %d)" % (n["k"], bk.name, len(real), len(hid)))
