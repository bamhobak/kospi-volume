# -*- coding: utf-8 -*-
"""Tiingo 재무 메타(회사 목록)를 받아 둔다 — 폐지 회사까지 이름·상태가 들어 있다 (2026-09-23).

왜: 폐지 종목 시세(collect_tiingo_dead.py)를 패널에 합치려면 **업종과 재무**가 붙어야 한다.
재무는 SEC companyfacts(무료, 폐지 회사 포함)에 있는데 티커↔회사번호 대응표가 현재 상장사뿐이다.
이 목록의 **정식 회사명**으로 SEC 회사 목록(submissions.zip)과 짝을 맞춘다.

한 번 호출로 전부 온다(티커를 안 주면 전체): 2026-09-23 기준 20,319개사 · 비활성(폐지) 12,517.

Power 요금제에서 실제로 열리는 필드(직접 확인):
  ✅ permaTicker · ticker · name · isActive · isADR · reportingCurrency · dataProviderPermaTicker
     · statementLastUpdated · dailyLastUpdated
  ❌ sector · industry · sicCode · sicSector · sicIndustry · location · companyWebsite · secFilingWebsite
     — "Field not available for free/evaluation" 로 가려져 온다(다우 30종목만 보임). 빈 값으로 바꿔 저장한다.

출력: data/us/tiingo_fund_meta.pkl · .csv (fetched 열에 받은 날짜)
    python collect_tiingo_meta.py
"""
import io, os, sys, time
from pathlib import Path
import pandas as pd, requests

BASE = Path(__file__).parent
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is None:
        setattr(sys, _n, io.open(os.devnull, "w", encoding="utf-8"))
    else:
        try: _f.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

OUT = BASE / "data" / "us" / "tiingo_fund_meta"
MASK = "not available"


def token():
    for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("TIINGO_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env 에 TIINGO_TOKEN 이 없다")


def main():
    r = requests.get("https://api.tiingo.com/tiingo/fundamentals/meta",
                     params={"token": token()}, timeout=180)
    j = r.json()
    if not isinstance(j, list):
        raise SystemExit(f"이상 응답 {r.status_code}: {str(j)[:200]}")
    a = pd.DataFrame(j)
    masked = []
    for c in a.columns:
        m = a[c].astype(str).str.contains(MASK, case=False, na=False)
        if m.any():
            a.loc[m, c] = None
            masked.append(f"{c}({m.mean() * 100:.0f}%)")
    a["ticker"] = a.ticker.astype(str).str.upper()
    a["isActive"] = a.isActive.astype(bool)
    a["isADR"] = a.isADR.astype(bool)
    a["fetched"] = time.strftime("%Y%m%d")
    a.to_pickle(OUT.with_suffix(".pkl"))
    a.to_csv(OUT.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"{len(a):,}개사 · 활성 {a.isActive.sum():,} · 비활성(폐지) {(~a.isActive).sum():,} · "
          f"ADR {a.isADR.sum():,} · 이름 있음 {a.name.notna().sum():,}")
    print("가려져 빈 값으로 바꾼 필드: " + (", ".join(masked) or "없음"))
    print(f"저장 {OUT.with_suffix('.pkl').name} · {OUT.with_suffix('.csv').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
