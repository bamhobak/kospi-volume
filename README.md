# kospi-volume — 코스피 전종목 거래량 · 투자자(개인/기관/외국인) 동향 (웹/모바일)

- 웹: GitHub Pages (https://bamhobak.github.io/kospi-volume/) — 휴대폰에서도 조회
- 자동 수집: GitHub Actions 크론 매일 **18:30 KST(평일)** → 네이버에 당일 데이터 뜰 때까지 대기 → 수집 → `data/YYYY-MM.csv` 커밋 → Pages 배포
- 데이터원: 네이버 증권 API(거래량·종가·투자자 순매수), 종목목록 FinanceDataReader
- 로컬 실행(선택): `app.bat` → 수집+빌드 후 http://127.0.0.1:8765
- 구조: `collect.py`(수집) → `pipeline.py`(CSV 이력 복원/저장 + `site/` 빌드) → `index.html`(화면, 정적 JSON 사용)
