# -*- coding: utf-8 -*-
"""미국 데이터 — 공짜로 어디까지 받아지나 실제로 찔러본다(추정 금지).

한국 패널을 만들며 배운 것: **폐지 종목이 빠지면 백테스트가 통째로 거짓말이 된다.**
우리 코스피 패널은 폐지 77종목·코스닥 435종목을 따로 붙여서야 정상이 됐다.
그러니 미국도 ① 얼마나 옛날까지 ② 폐지 종목이 되나 ③ 재무·수급이 되나 를 순서대로 본다.

확인 항목
  A 일봉 OHLCV — 시작 연도, 수정주가 여부, 거래량
  B **폐지·상장폐지 종목** — 생존편향을 없앨 수 있나 (가장 중요)
  C 주식수·시가총액 이력 — 시총 조건과 분할 보정에 필요
  D 재무(PBR/PER) — SEC XBRL companyfacts (무료·키 불필요)
  E 공매도 — FINRA 무료 공시
  F 지수·매크로
"""
import io, sys, warnings, json, time
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, requests

UA = {"User-Agent": "bamhobak-research contact@example.com"}


def line(k, v):
    print(f"  {k:<34}{v}")


print("=" * 100)
print("A. 일봉 OHLCV — 얼마나 옛날까지 오나 (yfinance, 무료·키 불필요)")
print("=" * 100)
import yfinance as yf
for t in ("AAPL", "IBM", "KO", "MSFT", "SPY", "QQQ"):
    try:
        d = yf.Ticker(t).history(period="max", auto_adjust=False)
        line(t, f"{d.index[0].date()} ~ {d.index[-1].date()} · {len(d):,}행 · "
                f"컬럼 {list(d.columns)}")
    except Exception as e:
        line(t, f"실패 {type(e).__name__}")

print("\n" + "=" * 100)
print("B. 폐지 종목 — 생존편향을 없앨 수 있나 (가장 중요)")
print("=" * 100)
DEAD = {"LEHMQ": "리먼브라더스(2008 파산)", "ENRNQ": "엔론(2001 파산)",
        "SHLDQ": "시어스(2018 파산)", "BBBYQ": "베드배스앤비욘드(2023 파산)",
        "FRCB": "퍼스트리퍼블릭(2023 파산)", "SIVBQ": "SVB(2023 파산)",
        "TWTR": "트위터(2022 상장폐지·인수)", "ATVI": "액티비전(2023 인수)"}
ok = 0
for t, nm in DEAD.items():
    try:
        d = yf.Ticker(t).history(period="max", auto_adjust=False)
        if len(d):
            ok += 1
            line(f"{t} {nm}", f"✅ {d.index[0].date()} ~ {d.index[-1].date()} · {len(d):,}행")
        else:
            line(f"{t} {nm}", "❌ 0행")
    except Exception as e:
        line(f"{t} {nm}", f"❌ {type(e).__name__}")
print(f"\n  → 폐지 종목 {ok}/{len(DEAD)} 개 조회됨")
print("  ⚠ 조회가 되더라도 **현재 상장목록(StockListing)에는 없다**. 즉 '과거 어느 시점에")
print("    상장돼 있던 전체 목록' 을 만들 방법이 따로 필요하다. 그게 없으면 생존편향이 남는다.")

print("\n" + "=" * 100)
print("C. 주식수·시가총액 이력")
print("=" * 100)
try:
    t = yf.Ticker("AAPL")
    si = t.get_shares_full(start="2000-01-01")
    line("get_shares_full(AAPL)", f"{si.index[0].date()} ~ {si.index[-1].date()} · {len(si):,}행"
         if si is not None and len(si) else "없음")
except Exception as e:
    line("get_shares_full", f"실패 {type(e).__name__}")
try:
    fi = yf.Ticker("AAPL").fast_info
    line("fast_info 시총", f"{fi.get('market_cap'):,}" if fi.get("market_cap") else "없음")
except Exception as e:
    line("fast_info", f"실패 {type(e).__name__}")

print("\n" + "=" * 100)
print("D. 재무 — SEC XBRL companyfacts (무료·API 키 불필요·시점정보 포함)")
print("=" * 100)
try:
    r = requests.get("https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/"
                     "us-gaap/StockholdersEquity.json", headers=UA, timeout=30)
    if r.ok:
        j = r.json()
        u = j["units"]["USD"]
        yrs = sorted({x["fy"] for x in u if x.get("fy")})
        line("자본총계(AAPL)", f"{len(u):,}건 · 회계연도 {yrs[0]}~{yrs[-1]}")
        line("  공시일(filed) 포함", "예 — 시점 기준(point-in-time) 구성 가능")
    else:
        line("companyconcept", f"HTTP {r.status_code}")
except Exception as e:
    line("companyconcept", f"실패 {type(e).__name__}")
try:
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=30)
    line("티커↔CIK 매핑", f"{len(r.json()):,}개" if r.ok else f"HTTP {r.status_code}")
except Exception as e:
    line("티커↔CIK", f"실패 {type(e).__name__}")
print("  ※ SEC Financial Statement Data Sets(분기 벌크 zip)는 2009Q2 부터 제공된다.")

print("\n" + "=" * 100)
print("E. 공매도 — FINRA 무료 공시")
print("=" * 100)
try:
    r = requests.get("https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260902.txt",
                     headers=UA, timeout=30)
    line("FINRA 일별 공매도 거래량", f"HTTP {r.status_code} · {len(r.text.splitlines()):,}행"
         if r.ok else f"HTTP {r.status_code}")
except Exception as e:
    line("FINRA daily", f"실패 {type(e).__name__}")
print("  ※ 일별 공매도 '거래량' 은 무료(2009~). 격주 '공매도 잔고' 는 거래소 파일로 별도.")

print("\n" + "=" * 100)
print("F. 지수·매크로")
print("=" * 100)
for t, nm in (("^GSPC", "S&P500"), ("^IXIC", "나스닥"), ("^VIX", "VIX"), ("^TNX", "미10년물")):
    try:
        d = yf.Ticker(t).history(period="max")
        line(nm, f"{d.index[0].date()} ~ {d.index[-1].date()} · {len(d):,}행")
    except Exception as e:
        line(nm, f"실패 {type(e).__name__}")
