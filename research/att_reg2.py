# -*- coding: utf-8 -*-
"""H0247 판정 기록 + 관심 쏠림 회피 기록(H0248) — 2026-09-29. 한 번만 돌린다."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry as RG

RG.update("H0247", status="기각",
          result="40일 중앙 학습 -7.92%·검증 -1.09%(208건, 0/5해) · 폐지 비중 17.8% vs 유니버스 9.9% · 시장 10분위에서도 관심 가장 식은 1분위가 60일 -0.67%p(9/11해 음수)",
          reason="관심이 1년 평균의 절반 밑으로 식은 종목은 '숨은 매집'이 아니라 잊혀 가는 종목 — 가장 좋은 건 3~6분위(적당히 식음, 60일 +1.2~1.8%p)",
          scripts=["research/trend_feat.py", "research/att_scan.py", "research/att_reg.py", "research/run_extra.py"])
hid = RG.add(name="관심 쏠림 회피 (네이버 검색량 28일/1년 상위 10% 종목) [KR]",
             family=["국면", "거래량"], market="KR", source="H0247 부산물(att_scan)",
             mechanism="개인 검색이 평소보다 몰린 종목은 이후 60일 부진 — 오른 폭·거래량을 통제해도 남는다",
             data="data/naver_trend.db → research/cache/naver_att.pkl",
             status="기록",
             result="시장 전체 60일 10분위 -5.36%p(11/11해) · ret20×vm3 25칸 통제 후에도 -4.05%p(학습 -2.99·검증 -5.58, 11/11해) · 우리 규칙 안 상위 10% 신호 중앙 +10.83% vs 나머지 +14.01%(593건, 여전히 크게 플러스)",
             reason="회피 신호는 시장 전체엔 진짜지만 우리 규칙이 산 종목에선 빼면 버는 신호를 버린다(과거 mat_overlay 교훈) — 새 규칙 설계 때 재료 후보로만",
             trials=[], scripts=["research/att_scan.py", "research/att_scan2.py"], date="2026-09-29")
print(hid)
