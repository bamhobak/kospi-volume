# -*- coding: utf-8 -*-
"""2026-11-12 사용자 "응 사이트에서 빼줘" — 지금 규칙이면 안 샀을 미장 스윙 완료 4건(DJCO·BP·VRSN·XOM, [상승장 신고가] 10-02 좁힘 전 매수,
research/recheck_done_us_1112) 사이트 positions 에서 빼고 site_hidden.json 에 id. 원장은 그대로. 백업 positions_backup_20261112_done4.json"""
import json, sys
sys.path.insert(0, r"C:\vscode\kospi-volume")
sys.stdout.reconfigure(encoding="utf-8")
import autotrade as AT
from pathlib import Path
T = {("DJCO", "20260911"), ("BP", "20260911"), ("VRSN", "20260915"), ("XOM", "20260917")}
ST = AT.site_state()
P = ST.get("positions") or []
(Path(r"C:\vscode\kospi-volume\data\autotrade") / "positions_backup_20261112_done4.json").write_text(json.dumps(P, ensure_ascii=False), encoding="utf-8")
ids = {p["id"] for p in P if (p.get("code"), str(p.get("date"))) in T and p.get("sell") and (p.get("filters") or [None])[0] == "N1"}
print("대상", len(ids))
def drop(L):
    n0 = len(L); L[:] = [p for p in L if p.get("id") not in ids]; return len(L) != n0
AT.site_update(drop, "미장 완료 4건 사이트에서 빼기")
h = json.loads(AT.HIDDEN.read_text(encoding="utf-8")) if AT.HIDDEN.exists() else {"ids": []}
h["ids"] = sorted(set(h.get("ids") or []) | ids)
AT.HIDDEN.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
left = [p["code"] for p in AT.site_state().get("positions") or [] if p.get("id") in ids]
done = len([p for p in AT.site_state().get("positions") or [] if p.get("sell")])
print("남은 대상", left, "· 숨김 id", len(h["ids"]), "· 사이트 스윙 완료", done)
