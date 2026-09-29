# -*- coding: utf-8 -*-
"""H 등록 + 명세 — 네이버 검색 관심 없는 매집(2026-09-29). 한 번만 돌린다."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry as RG

hid = RG.add(name="관심 없는 매집 (네이버 검색량 식음 + 외인 20일 순매수 + 52주 고점 근처)",
             family=["외인", "수급"], market="KR", source="사용자 제안 1번(2026-09-29)",
             mechanism="개인 관심(검색량)이 자기 1년 평균보다 식었는데 외인이 사 모으고 가격은 고점 근처 — 아직 대중이 모르는 매집",
             data="data/naver_trend.db(네이버 데이터랩, 2016~) → research/cache/naver_att.pkl",
             status="시험중", trials=["run_spec"], scripts=["research/trend_feat.py", "research/att_scan.py", "research/run_extra.py"],
             date="2026-09-29")
base = "(att <= 0.5) & (zfrac <= 0.2) & (q_frgn20 > 0) & (fromhi >= -10)"
spec = {"id": hid, "market": "KR", "derive": {}, "cond": base, "holds": [20, 40, 60], "main_hold": 40,
        "variants": [
            {"label": "관심 더 식음 0.3", "cond": base.replace("att <= 0.5", "att <= 0.3")},
            {"label": "관심 0.7", "cond": base.replace("att <= 0.5", "att <= 0.7")},
            {"label": "외인 대신 기관", "cond": base.replace("q_frgn20", "q_org20")},
            {"label": "고점 -15%", "cond": base.replace("fromhi >= -10", "fromhi >= -15")},
            {"label": "수급 조건 없음", "cond": "(att <= 0.5) & (zfrac <= 0.2) & (fromhi >= -10)"},
        ],
        "differs_from": "[외인 매집] P7·[조정매집] P2 와 달리 개인 관심(검색량) 식음이 핵심 조건"}
(ROOT / "specs" / (hid + ".json")).write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
print(hid)
