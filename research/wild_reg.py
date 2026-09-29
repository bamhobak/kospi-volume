# -*- coding: utf-8 -*-
"""wild.py ⑤ 무작위 난사·④ 모양 군집에서 나온 후보를 정식 판정(run_spec)에 올린다 — 2026-09-30. 한 번만 돌린다.
발견은 난사(3천 규칙)였으므로 여기 명세는 **확인용**이다. 문턱은 난사 결과 그대로 옮기고 사후 조정하지 않는다."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry as RG

SRC = "wild.py 무작위 규칙 난사(2026-09-30, 사용자 '평소라면 안 할 방법')"
C = [
    dict(name="조용한 저PBR (하루 변동폭 하위 20% + PBR 하위 10%)", family=["재무·밸류", "변동성"],
         mech="움직임 없는 싼 종목 — 저변동성·가치 이상현상의 교집합", cond="(xrank(rng) <= 0.2) & (PBR > 0) & (xrank(PBR) <= 0.1)",
         var=[("변동폭 30%", "(xrank(rng) <= 0.3) & (PBR > 0) & (xrank(PBR) <= 0.1)"),
              ("PBR 20%", "(xrank(rng) <= 0.2) & (PBR > 0) & (xrank(PBR) <= 0.2)"),
              ("20일 변동성으로", "(xrank(vol20) <= 0.2) & (PBR > 0) & (xrank(PBR) <= 0.1)")]),
    dict(name="공매도 몰린 저PBR (PBR 하위 10% + 공매도 비중 상위 20%)", family=["재무·밸류", "공매도"],
         mech="싼데 공매도가 몰린 종목 — 공매도 쪽이 틀리는 자리(상환 매수)", cond="(PBR > 0) & (xrank(PBR) <= 0.1) & (xrank(sr20) >= 0.8)",
         var=[("공매도 상위 10%", "(PBR > 0) & (xrank(PBR) <= 0.1) & (xrank(sr20) >= 0.9)"),
              ("PBR 20%", "(PBR > 0) & (xrank(PBR) <= 0.2) & (xrank(sr20) >= 0.8)")]),
    dict(name="대형주 1년 낙오 (시총 상위 30% + 6개월·1년 수익 하위 10%)", family=["낙폭반전"],
         mech="큰 회사가 반년·1년 내내 제일 못 간 자리 — 장기 반전", cond="(xrank(marcap) >= 0.7) & (xrank(ret120) <= 0.1) & (xrank(ret250) <= 0.1)",
         var=[("시총 상위 20%", "(xrank(marcap) >= 0.8) & (xrank(ret120) <= 0.1) & (xrank(ret250) <= 0.1)"),
              ("1년만", "(xrank(marcap) >= 0.7) & (xrank(ret250) <= 0.1)")]),
    dict(name="대형주 짧은 눌림 (시총 상위 20% + 5일 하위 30% + 60일선 이격 하위 30%)", family=["눌림"],
         mech="큰 회사의 단기 눌림 — 대형주는 과잉반응이 되돌려진다", cond="(xrank(marcap) >= 0.8) & (xrank(ret5) <= 0.3) & (xrank(dma60) <= 0.3)",
         var=[("5일 하위 20%", "(xrank(marcap) >= 0.8) & (xrank(ret5) <= 0.2) & (xrank(dma60) <= 0.3)"),
              ("시총 상위 10%", "(xrank(marcap) >= 0.9) & (xrank(ret5) <= 0.3) & (xrank(dma60) <= 0.3)")]),
    dict(name="조용한 제자리 (20일 변동성 하위 20% + 20일 수익 ±5% + 거래량 줄어듦)", family=["변동성", "박스권"],
         mech="④ 모양 군집 학습 상위 묶음(평평·거래량 0.5~0.9배)을 조건식으로 옮김", cond="(xrank(vol20) <= 0.2) & (ret20.abs() <= 5) & (vm3 < 1)",
         var=[("변동성 30%", "(xrank(vol20) <= 0.3) & (ret20.abs() <= 5) & (vm3 < 1)"),
              ("거래량 조건 없음", "(xrank(vol20) <= 0.2) & (ret20.abs() <= 5)")]),
]
ids = []
for c in C:
    hid = RG.add(name=c["name"] + " [KR]", family=c["family"], market="KR", source=SRC, mechanism=c["mech"],
                 data="data/kr_scan.pkl", status="시험중", trials=["run_spec"], scripts=["research/wild.py", "research/wild_reg.py"],
                 date="2026-09-30")
    spec = {"id": hid, "market": "KR", "derive": {}, "cond": c["cond"], "holds": [20, 40, 60], "main_hold": 40,
            "variants": [{"label": l, "cond": v} for l, v in c["var"]],
            "differs_from": "무작위 난사에서 나온 조합 — 기존 규칙은 낙폭·수급 중심, 이건 순위(백분위) 조합"}
    (ROOT / "specs" / (hid + ".json")).write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    ids.append(hid)
print(" ".join(ids))
