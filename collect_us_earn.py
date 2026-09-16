# -*- coding: utf-8 -*-
"""미국 실적 서프라이즈 수집 — 사이트 [실적 서프라이즈] 규칙이 쓰는 재료.

`data/us/buyback_recent.csv` 와 같은 자리다. 주 1회(월요일)만 돌린다.

왜 주 1회인가: yfinance 는 **종목당** 호출이라 6천 종목에 1~3시간이 걸린다. 매일은 못 돈다.
그래서 신호가 며칠 늦는데, **그 대가를 재 봤다**(`us_pead_delay.py`):

  | 매수 시점 | 평균 | 중앙 | 절삭 |
  |---|---|---|---|
  | D+1(발표 다음날) | +4.10% | +2.83% | +0.63% |
  | D+7 | +3.73% | **+2.88%** | +0.61% |
  | D+9 | +3.54% | +2.43% | +0.44% |

**D+7 까지는 사실상 그대로**다(중앙값은 오히려 높다). PEAD 는 60일에 걸쳐 천천히 흐르는
현상이라 하루이틀 늦게 사는 게 큰 차이가 없다. D+8 부터 꺾이므로 **주 1회면 충분**하다.
매일 증분 수집을 만들어 얻는 건 5% 남짓인데 고장 날 곳만 는다.

산출: `data/us/earn_recent.csv` — ticker,edate,surprise (최근 400일치만)
  edate    = 실적 발표일(ET 기준 YYYYMMDD)
  surprise = Surprise(%) 원값. **백분위는 사이트가 그날 발표분 안에서 매긴다**
             (±769,900% 같은 극단값이 있어 원값을 그대로 쓰면 안 된다)

    python collect_us_earn.py            # 파일이 최근이면 건너뛴다
    python collect_us_earn.py --force    # 무조건 새로 받는다
"""
import argparse
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd

BASE = Path(__file__).parent
US = BASE / "data" / "us"
OUT = US / "earn_recent.csv"
KEEP_DAYS = 400          # 규칙이 보는 건 최근 발표뿐 — 파일을 작게 유지한다
CH = 200


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    if OUT.exists() and not a.force:
        age = (time.time() - OUT.stat().st_mtime) / 86400
        if age < 6:
            log("%s 가 %.1f일 전 것이다 — 건너뛴다 (--force 로 강제)" % (OUT.name, age))
            return

    import logging
    import yfinance as yf
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)

    syms = [x for x in pd.read_csv(US / "tickers.csv", dtype=str).Symbol.tolist()
            if isinstance(x, str) and x.strip()]
    if a.limit:
        syms = syms[:a.limit]
    log("종목 %s개" % f"{len(syms):,}")

    cut = (datetime.utcnow() - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    rows = []
    t0 = time.time()
    for i in range(0, len(syms), CH):
        for s in syms[i:i + CH]:
            try:
                d = yf.Ticker(s).get_earnings_dates(limit=12)
            except Exception:
                continue
            if d is None or not len(d):
                continue
            try:
                d = d.reset_index()
                d.columns = [str(x) for x in d.columns]
                if "Surprise(%)" not in d.columns or "Earnings Date" not in d.columns:
                    continue
                dt = pd.to_datetime(d["Earnings Date"], utc=True, errors="coerce")
                d = d[dt.notna() & d["Surprise(%)"].notna()].copy()
                if not len(d):
                    continue
                # ET 기준 날짜. 장전(06~09시)·장후(16시~)가 섞여 있어 사이트가 **다음 거래일**에 산다.
                d["edate"] = pd.to_datetime(d["Earnings Date"], utc=True).dt.tz_convert(
                    "US/Eastern").dt.strftime("%Y%m%d")
                d = d[d.edate >= cut]
                for e, v in zip(d.edate.values, d["Surprise(%)"].astype(float).values):
                    rows.append((s, e, round(float(v), 2)))
            except Exception:
                continue
        el = time.time() - t0
        done = min(i + CH, len(syms))
        log("  %s/%s · 누적 %s건 · 남은시간 약 %.0f분"
            % (f"{done:,}", f"{len(syms):,}", f"{len(rows):,}",
               (len(syms) - done) * el / max(done, 1) / 60))

    if not rows:
        log("받은 게 없다 — 기존 파일을 지키고 끝낸다")
        return
    A = pd.DataFrame(rows, columns=["ticker", "edate", "surprise"])
    # ── 기존 파일과 **합친다** — 덮어쓰지 않는다 ────────────────────────────
    # ⚠ yfinance 는 종목당 호출이라 6천 번을 부르는 사이 레이트리밋(YFRateLimitError)이
    #   걸리기 쉽다. 이 스크립트는 실패한 종목을 조용히 건너뛰므로, 절반만 받은 판이
    #   멀쩡한 파일을 통째로 덮어쓸 수 있다. 그러면 [실적 서프라이즈] 가 조용히 죽는다.
    #   발표 기록은 **한 번 확정되면 안 바뀌는** 자료라 합치는 게 언제나 옳다.
    #   같은 (종목, 발표일) 이 겹치면 새로 받은 값을 쓴다.
    _old = None
    if OUT.exists():
        try:
            _old = pd.read_csv(OUT, dtype={"edate": str})
            A = pd.concat([_old, A], ignore_index=True)
        except Exception as e:
            log("기존 파일을 못 읽었다 — 새로 받은 것만 쓴다: %r" % (e,))
    A["edate"] = A.edate.astype(str)
    A = A.drop_duplicates(["ticker", "edate"], keep="last")
    A = A[A.edate >= cut].sort_values(["edate", "ticker"])
    if _old is not None:
        _new = len(A) - len(_old[_old.edate.astype(str) >= cut].drop_duplicates(["ticker", "edate"]))
        log("  기존 %s건 + 새로 받은 %s건 → 합쳐서 %s건 (순증 %+d)"
            % (f"{len(_old):,}", f"{len(rows):,}", f"{len(A):,}", _new))
    US.mkdir(parents=True, exist_ok=True)
    A.to_csv(OUT, index=False, encoding="utf-8")
    log("저장 %s (%s건 · %s종목 · %s~%s)"
        % (OUT.name, f"{len(A):,}", f"{A.ticker.nunique():,}", A.edate.min(), A.edate.max()))


if __name__ == "__main__":
    main()
