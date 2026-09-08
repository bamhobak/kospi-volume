# -*- coding: utf-8 -*-
"""미국에만 있는 데이터 축 찾기 — 무엇이 무료로 받아지나 실제로 찔러본다.

한국 규칙을 그대로 옮기는 건 실패했다(`us_acct.py` — 어떤 구성도 S&P500 을 못 이김).
원인 중 하나가 '한국 규칙의 힘이 수급 조건에서 나왔는데 미국엔 없다' 였다.
그러면 반대로 가야 한다 — **미국에만 있는 재료로 미국용 축을 새로 찾는다.**

한국에 없거나 훨씬 부실한 것들
  A 실적 발표일·서프라이즈  — 한국은 발표일이 들쭉날쭉하고 컨센서스가 유료다
  B 애널리스트 추정·등급변경 — 한국은 커버리지가 얇고 데이터가 유료
  C 옵션(내재변동성·스큐)   — 한국은 개별종목 옵션이 사실상 없다. **가장 미국다운 축**
  D 기관 보유(13F)         — 분기 지연이지만 '누가 들고 있나' 가 종목별로 보인다
  E 내부자 거래(Form 4)    — SEC 구조화 XML, 실시간, 무료
  F 공매도 잔고·미결제      — FINRA 격주 잔고 + SEC 결제불이행(FTD)
  G 지수 편입·제외         — S&P·러셀 리밸런싱 이벤트
"""
import io, sys, time, warnings, json
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd, requests

UA = {"User-Agent": "bamhobak-research microjun98@gmail.com"}
def line(k, v): print(f"  {k:<38}{v}")

import yfinance as yf
T = yf.Ticker("AAPL")

print("=" * 104)
print("A. 실적 발표일 · 서프라이즈 (PEAD 축 — 금융에서 가장 오래 살아남은 이상현상)")
print("=" * 104)
for nm, fn in (("earnings_dates", lambda: T.get_earnings_dates(limit=40)),
               ("earnings_history", lambda: T.earnings_history),
               ("quarterly_income_stmt", lambda: T.quarterly_income_stmt)):
    try:
        d = fn()
        if d is None or not len(d):
            line(nm, "없음")
        else:
            line(nm, f"{len(d)}행 · 컬럼 {list(d.columns)[:5] if hasattr(d,'columns') else '-'}")
            if nm == "earnings_dates":
                line("  범위", f"{d.index.min().date()} ~ {d.index.max().date()}")
    except Exception as e:
        line(nm, f"실패 {type(e).__name__}")

print("\n" + "=" * 104)
print("B. 애널리스트 — 추정치·등급 변경")
print("=" * 104)
for nm in ("recommendations", "recommendations_summary", "upgrades_downgrades",
           "analyst_price_targets", "earnings_estimate", "revenue_estimate",
           "eps_trend", "eps_revisions", "growth_estimates"):
    try:
        d = getattr(T, nm)
        if d is None or (hasattr(d, "__len__") and not len(d)):
            line(nm, "없음")
        else:
            n = len(d) if hasattr(d, "__len__") else 1
            line(nm, f"{n}행 " + (f"· {list(d.columns)[:4]}" if hasattr(d, "columns") else str(d)[:60]))
    except Exception as e:
        line(nm, f"실패 {type(e).__name__}")

print("\n" + "=" * 104)
print("C. 옵션 — 개별종목 내재변동성. 한국엔 사실상 없는 축")
print("=" * 104)
try:
    ex = T.options
    line("만기 목록", f"{len(ex)}개 · {ex[0]} ~ {ex[-1]}" if ex else "없음")
    if ex:
        ch = T.option_chain(ex[min(3, len(ex)-1)])
        c, p = ch.calls, ch.puts
        line("콜/풋 행 수", f"{len(c)} / {len(p)}")
        line("컬럼", f"{list(c.columns)[:8]}")
        atm = c.iloc[(c.strike - T.fast_info['last_price']).abs().argsort()[:1]]
        line("ATM 콜 내재변동성", f"{float(atm.impliedVolatility.iloc[0]):.3f}")
        line("⚠ 한계", "현재 시점 체인만 온다 — 과거 IV 시계열은 무료로 안 나온다")
except Exception as e:
    line("옵션", f"실패 {type(e).__name__}: {str(e)[:60]}")

print("\n" + "=" * 104)
print("D. 기관 보유 (13F)")
print("=" * 104)
for nm in ("institutional_holders", "major_holders", "mutualfund_holders"):
    try:
        d = getattr(T, nm)
        line(nm, f"{len(d)}행 · {list(d.columns)[:4]}" if d is not None and len(d) else "없음")
    except Exception as e:
        line(nm, f"실패 {type(e).__name__}")
print("  ※ SEC 13F 벌크: https://www.sec.gov/dera/data/form-13f (분기별, 무료)")

print("\n" + "=" * 104)
print("E. 내부자 거래 (SEC Form 4) — 한국 내부자 축이 +8.63→+10.30% 였던 그 재료")
print("=" * 104)
try:
    r = requests.get("https://data.sec.gov/submissions/CIK0000320193.json", headers=UA, timeout=30)
    j = r.json()
    rec = j["filings"]["recent"]
    f4 = [i for i, t in enumerate(rec["form"]) if t == "4"]
    line("submissions API", f"HTTP {r.status_code} · 최근 공시 {len(rec['form']):,}건 중 Form 4 {len(f4)}건")
    if f4:
        i = f4[0]
        line("  최근 Form 4", f"{rec['filingDate'][i]} · accession {rec['accessionNumber'][i]}")
except Exception as e:
    line("submissions", f"실패 {type(e).__name__}")
try:
    r = requests.get("https://www.sec.gov/Archives/edgar/full-index/2026/QTR3/form.idx",
                     headers=UA, timeout=60)
    n4 = sum(1 for x in r.text.splitlines() if x.startswith("4  "))
    line("분기 전체 색인(form.idx)", f"HTTP {r.status_code} · {len(r.text.splitlines()):,}줄 · Form 4 약 {n4:,}건")
    line("  → 전 종목 Form 4 를 분기 색인으로 훑을 수 있다", "무료·키 불필요")
except Exception as e:
    line("form.idx", f"실패 {type(e).__name__}")

print("\n" + "=" * 104)
print("F. 공매도 잔고 · 결제불이행(FTD)")
print("=" * 104)
try:
    r = requests.get("https://cdn.finra.org/equity/otcmarket/biweekly/shrt20260815.csv",
                     headers=UA, timeout=30)
    line("FINRA 격주 공매도 잔고", f"HTTP {r.status_code} · {len(r.text.splitlines()):,}행")
except Exception as e:
    line("FINRA 잔고", f"실패 {type(e).__name__}")
for u, nm in (("https://www.sec.gov/files/data/fails-deliver-data/cnsfails202608a.zip",
               "SEC 결제불이행(FTD) 2026-08 전반기"),):
    try:
        r = requests.head(u, headers=UA, timeout=30, allow_redirects=True)
        line(nm, f"HTTP {r.status_code} · {int(r.headers.get('Content-Length',0))/1e6:.1f}MB")
    except Exception as e:
        line(nm, f"실패 {type(e).__name__}")

print("\n" + "=" * 104)
print("G. 지수 편입·제외")
print("=" * 104)
try:
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                     headers={"User-Agent": "Mozilla/5.0 bamhobak-research"}, timeout=30)
    t = pd.read_html(io.StringIO(r.text))
    line("위키 현재 구성", f"{len(t[0]):,}종목")
    line("위키 편입·편출 이력", f"{len(t[1]):,}건 · {list(t[1].columns)[:3]}")
except Exception as e:
    line("S&P500 이력", f"실패 {type(e).__name__}: {str(e)[:50]}")
