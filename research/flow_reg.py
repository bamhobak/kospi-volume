# -*- coding: utf-8 -*-
"""수급 급증 가설 등록 + 명세 (2026-10-02 · 한 번만)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry as RG

S = "사용자 제안(2026-10-02) — 최근 5거래일 대비 1일 수급 3·5배"
H = [
    ("외국인 1일 순매수 급증(직전 5일 평균의 3·5배) [KR]", ["외인", "수급"], "외국인이 평소보다 몇 배 크게 사들인 날 = 정보를 가진 큰손 진입",
     "(fnet > 0) & (fx >= 3)",
     [("5배", "(fnet > 0) & (fx >= 5)"), ("3배 + 거래대금 1%↑", "(fnet > 0) & (fx >= 3) & (famt >= 1)"),
      ("5배 + 거래대금 1%↑", "(fnet > 0) & (fx >= 5) & (famt >= 1)"), ("3배 + 거래대금 3%↑", "(fnet > 0) & (fx >= 3) & (famt >= 3)")]),
    ("개인 1일 순매도 급증(직전 5일 평균의 3·5배) [KR]", ["수급"], "개인이 평소보다 몇 배 크게 던진 날 = 투매·손절 물량을 받는 자리",
     "(inet < 0) & (ix >= 3)",
     [("5배", "(inet < 0) & (ix >= 5)"), ("3배 + 거래대금 1%↑", "(inet < 0) & (ix >= 3) & (iamt >= 1)"),
      ("5배 + 거래대금 1%↑", "(inet < 0) & (ix >= 5) & (iamt >= 1)"), ("3배 + 거래대금 3%↑", "(inet < 0) & (ix >= 3) & (iamt >= 3)")]),
    ("외국인 급매수 + 개인 급매도 같은 날 [KR]", ["외인", "수급"], "개인이 던진 물량을 외국인이 받아 간 날",
     "(fnet > 0) & (fx >= 3) & (inet < 0) & (ix >= 3)",
     [("둘 다 5배", "(fnet > 0) & (fx >= 5) & (inet < 0) & (ix >= 5)"),
      ("둘 다 3배 + 외국인 거래대금 1%↑", "(fnet > 0) & (fx >= 3) & (inet < 0) & (ix >= 3) & (famt >= 1)")]),
]
ids = []
for name, fam, mech, cond, var in H:
    hid = RG.add(name=name, family=fam, market="KR", source=S, mechanism=mech, data="data/investor.db flow11(2018~)",
                 status="시험중", trials=["run_spec"], scripts=["research/run_flow.py"], date="2026-10-02")
    spec = {"id": hid, "market": "KR", "derive": {}, "cond": cond, "holds": [5, 10, 20], "main_hold": 10,
            "variants": [{"label": l, "cond": c} for l, c in var],
            "differs_from": "[외인 매집] P7(20·60일 누적 순매수)과 달리 하루 급증 사건"}
    (ROOT / "specs" / (hid + ".json")).write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    ids.append(hid)
print(" ".join(ids))
