# -*- coding: utf-8 -*-
"""2026-10-02 사용자 제안 12개 실측 결과 등록(한 번만)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import registry as RG

S = "사용자 제안 12개(2026-10-02)"
X = [
    dict(name="국내 인적분할 재상장 + 21·40일 뒤 매수(분사주 국내판) [KR]", family=["이벤트"], market="KR", status="기각",
         mechanism="모회사 주주가 원치 않은 신설회사 주식을 판 뒤 되돌림", data="분할 공시 + 이름 줄기 + 패널 첫 거래일(105건)",
         result="재상장 +21일·250일 학습 중앙 -9.8%·승률 39% · 옛날 -7.2% · 양수 해 9/21 — 같은 날 대비 초과는 +이나 절대 수익 음수",
         reason="국내 분할 재상장은 미장 분사와 달리 절대 수익이 음수", scripts=["research/event_lab.py"]),
    dict(name="S&P 500 편출 21거래일 뒤 매수, 20~60일 보유 [US]", family=["이벤트", "유동성"], market="US", status="후보",
         mechanism="지수 펀드 강제 매도가 끝난 뒤 되돌림", data="data/us/sp500/ticker_start_end.csv(fja05680) · 편출 뒤 30거래일↑ 거래 158건",
         result="+21일·20일: 옛날 중앙 +1.44/초과 +2.36 · 학습 +3.25/+1.29(65%) · 검증 +2.84/+3.61(57%) · t 2.9(문턱 2.81) · 14/19해. "
                "+21일·60일: 세 구간 모두 플러스(검증 +8.21·71%) t 2.1 · +5·10일·120일도 세 구간 플러스",
         reason="연 8~9건으로 표본 적음 · 실시간 편출 목록 공급처 필요(지금 자료는 공개 저장소 갱신 의존)", scripts=["research/sp500_del.py"]),
    dict(name="물량 폭탄 뒤(추가상장·전환청구·합병 신주) 5~40일 뒤 매수 [KR]", family=["이벤트", "수급"], market="KR", status="기각",
         mechanism="차익 매도 물량 소화 뒤 반등", data="공시 제목", result="전환청구 +21~40일 학습·검증 중앙 -3~-10% · 추가상장 제목은 2008년까지만 있음",
         reason="전부 절대 수익 음수", scripts=["research/event_lab.py"]),
    dict(name="거래정지 해제·관리종목 해제 뒤 매수 [KR]", family=["이벤트"], market="KR", status="기각", mechanism="정지 중 쌓인 매도가 끝난 뒤",
         data="공시 제목", result="사건성 정지 해제 +21일·20일 학습 -2.9 · 검증 -1.4(중앙) · 관리종목 해제 제목은 2008년까지만(표본 부족)",
         reason="절대 수익 음수 · 관리종목 해제 자료 부족", scripts=["research/event_lab.py"]),
    dict(name="공모주 보호예수 해제(1·3·6·12개월) 전후 매수 [KR]", family=["이벤트", "수급"], market="KR", status="기각",
         mechanism="해제 전 선반영 하락 뒤 실제 매도가 적으면 반등", data="상장일(KIND+폐지) · 세이브로 일정 대신 표준 기간",
         result="해제일 -10~+10일 진입 전부 학습·검증 중앙 음수(검증 1개월 해제 60일 -15%)", reason="절대 수익 음수",
         scripts=["research/event_lab.py"]),
    dict(name="공시 42유형 지연 진입(공시 + 5·10·21·40일) [KR]", family=["이벤트"], market="KR", status="기각",
         mechanism="사건 직후가 아니라 소화된 뒤(분사주에서 배운 원리)", data="disc_scan TYPES",
         result="336칸 통과 0 · 기업설명회(IR)는 같은 날 대비 초과가 세 구간 모두 +1.2~3.8%p(t 15)지만 절대 중앙 -1~-3%",
         reason="절대 수익 음수(국내 중앙 종목이 비용 포함 20일 -2%대라 초과만 플러스)", scripts=["research/event_lab.py"]),
    dict(name="우리 국내 신호가 몰린 날(4개↑) 진입분은 120일 보유 [KR]", family=["청산·손절", "국면"], market="KR", status="후보",
         mechanism="신호 몰림 = 시장 투매 바닥 → 반등을 끝까지", data="rule_scan.kr_signals",
         result="몰린 날 해별 17개 중 14개에서 120일 보유가 원래 청산보다 나음(2008 +63 vs +9 · 2020 +93 vs +18 · 2018 +37 vs +18). 진 해 2007·2012·2015. "
                "평범한 날도 120일이 원래 청산보다 +3~8%p 높아 '몰린 날에만' 인지는 경계",
         reason="몰린 날 대부분이 2008·2020 두 폭락 · 청산 규칙 변경이라 계좌·자금 회전 확인 필요", scripts=["research/crowd_hold.py"]),
    dict(name="행동주의·가치 운용사 5% 신규 보고 [KR]", family=["수급", "이벤트"], market="KR", status="그림자",
         mechanism="행동주의 펀드 진입 뒤 지배구조 개선 기대", data="공시 신고자 이름(flr_nm) · 그 보고자의 그 종목 첫 보고",
         result="같은 날 대비 초과 학습 +2.6~10.6 · 검증 +1.7~10.4 · t 3.9~4.3(문턱 3.70 근처) 그러나 절대 중앙 대부분 음수 · 검증 37~68건",
         reason="표본 적고 절대 수익 음수 → shadow.py S2 로 매일 기록", scripts=["research/event_lab.py", "shadow.py"]),
    dict(name="국민연금 5% 신규 보고 [KR]", family=["수급"], market="KR", status="기각", mechanism="연기금 진입", data="공시 신고자",
         result="검증 중앙 -3~-16% · 옛날만 플러스", reason="최근 구간 음수", scripts=["research/event_lab.py"]),
    dict(name="자사주 신탁계약 체결 + 20일 -10% 낙폭, 다음날 매수 20일 [KR]", family=["자사주", "낙폭반전"], market="KR", status="후보",
         mechanism="회사가 신탁으로 꾸준히 사들이는데 주가가 빠진 자리", data="DART tsstkAqTrctrCnsDecsn(계약금액) · research/cache/buyback_kr.pkl",
         result="학습 419건 중앙 +6.44%·승률 70% · 검증 206건 +2.15%·57% · 옛날(2015) +6.44 · 12/12해 · 본페로니 통과(t 6.3) · 기존 규칙과 ±5일 겹침 6.6% · "
                "코스피 60일선 아래 470건 중앙 +5.94 / 위 155건 +2.74(양쪽 다 플러스). 규모 3%↑는 학습 +15.2%·80% 이나 표본 적음",
         reason="채택 여부 사용자 결정 · 그동안 shadow.py S1 로 기록", scripts=["research/buyback_size.py", "research/fetch_buyback_kr.py", "shadow.py"]),
    dict(name="자사주 직접 취득 규모 1%↑ / 소각 목적 [KR]", family=["자사주"], market="KR", status="기각",
         mechanism="규모가 큰·소각 목적 자사주는 진짜 주주환원", data="DART tsstkAqDecsn(금액·목적)",
         result="규모 1%↑ 20·60일 통과(학습 +2.8~3.1 · 검증 +0.1~0.5 중앙 — 검증이 0 근처) · 소각 목적은 근접(학습 표본 22~50건) · 주식소각결정 공시는 통과 없음",
         reason="검증 중앙이 0 근처 — 신탁+낙폭 쪽이 더 강함", scripts=["research/buyback_size.py"]),
]
for x in X:
    x.setdefault("source", S); x["date"] = "2026-10-02"
    print(RG.add(**x), x["name"][:30])
