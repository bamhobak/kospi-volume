# -*- coding: utf-8 -*-
"""미국 일봉 수집 — 2005년부터, 재개 가능하게.

사용자 결정(2026-09-09): 미국으로 확장한다. 가격은 2005년부터 받고 판정은 2016년부터
(한국과 같은 학습 2016~22 / 검증 2023~26 구간을 써야 두 시장을 나란히 놓을 수 있다).

생존편향은 `surv_bias.py` 로 직접 재봤다 — 우리 규칙 구조(주가 하한·거래대금 하한)에서는
폐지 종목을 빼도 계좌가 오히려 -8.7~-13.1% **나빠진다**(우리가 잡는 폐지 종목은
0원으로 간 잡주가 아니라 인수·합병 쪽이다). 그래서 yfinance 가 폐지 종목을 거의 안 주는
한계를 안고도 시작할 수 있다고 판단했다. 다만 이건 **하한**이라는 걸 기억해 둔다.

설계
  · 종목 목록: FinanceDataReader NASDAQ+NYSE+AMEX (ETF·펀드 추정분 제외)
  · 조각(chunk) 단위로 받아 data/us/raw/*.pkl 로 저장 → **이미 받은 조각은 건너뛴다**
  · 실패한 조각은 실패 목록에 남겨 나중에 다시 시도
  · auto_adjust=False — 원주가(하한 조건용)와 수정주가(수익 계산용) 둘 다 필요하다

  python us_collect.py --pilot        # 200종목만 시험
  python us_collect.py                # 전체
  python us_collect.py --retry        # 실패한 조각만 다시
"""
import io, sys, os, json, time, argparse, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, numpy as np

BASE = Path(__file__).parent
OUT = BASE / "data" / "us"
RAW = OUT / "raw"
RAW.mkdir(parents=True, exist_ok=True)
TICK = OUT / "tickers.csv"
FAIL = OUT / "failed.json"
START = "2005-01-01"
CHUNK = 120


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def build_tickers():
    if TICK.exists():
        t = pd.read_csv(TICK, dtype=str)
        log(f"종목 목록 재사용 {len(t):,}개 ({TICK.name})")
        return t
    import FinanceDataReader as fdr
    D = []
    for m in ("NASDAQ", "NYSE", "AMEX"):
        d = fdr.StockListing(m)
        d["mk"] = m
        D.append(d)
        log(f"  {m} {len(d):,}개")
    U = pd.concat(D, ignore_index=True).drop_duplicates("Symbol")
    # ETF·펀드·신탁 추정분 제외 — 업종이 비었거나 이름에 표시가 있는 것
    etf = (U.Industry.isna() |
           U.Name.str.contains("ETF|Trust|Fund|Index|ETN|Bond|Portfolio|Depositary",
                               case=False, na=False))
    U = U[~etf].copy()
    # 티커에 특수문자가 있는 것(우선주·워런트 등)은 뺀다 — yfinance 조회가 잘 안 된다
    U = U[U.Symbol.notna() & U.Symbol.astype(str).str.fullmatch(r"[A-Z]{1,5}")]
    U = U[["Symbol", "Name", "mk", "Industry"]].reset_index(drop=True)
    U.to_csv(TICK, index=False, encoding="utf-8")
    log(f"종목 목록 저장 {len(U):,}개 (ETF·특수티커 제외) → {TICK.name}")
    return U


def fetch(syms):
    import yfinance as yf
    d = yf.download(syms, start=START, auto_adjust=False, progress=False,
                    threads=True, group_by="ticker", timeout=60)
    if d is None or not len(d):
        return None
    rows = []
    cols = {c[0] for c in d.columns} if isinstance(d.columns, pd.MultiIndex) else set(syms)
    for s in syms:
        if s not in cols:
            continue
        try:
            x = d[s] if isinstance(d.columns, pd.MultiIndex) else d
        except Exception:
            continue
        x = x.dropna(subset=["Close"])
        if not len(x):
            continue
        try:
            _d = x.index.strftime("%Y%m%d")
        except Exception:
            continue                       # 인덱스가 깨진 종목은 건너뛴다(조각 전체를 죽이지 않는다)
        z = pd.DataFrame({
            "ticker": s,
            "date": _d,
            "open": x["Open"].astype("float32"),
            "high": x["High"].astype("float32"),
            "low": x["Low"].astype("float32"),
            "close": x["Close"].astype("float32"),
            "adj": x["Adj Close"].astype("float32"),
            "volume": x["Volume"].astype("float64"),
        })
        rows.append(z)
    return pd.concat(rows, ignore_index=True) if rows else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--retry", action="store_true")
    ap.add_argument("--chunk", type=int, default=CHUNK)
    a = ap.parse_args()

    U = build_tickers()
    syms = U.Symbol.tolist()
    if a.pilot:
        syms = syms[:200]
        log("시험 모드 — 앞 200종목만")

    chunks = [syms[i:i + a.chunk] for i in range(0, len(syms), a.chunk)]
    failed = json.load(open(FAIL, encoding="utf-8")) if FAIL.exists() else []
    if a.retry:
        chunks = [c for c in chunks if str(chunks.index(c)) in map(str, failed)]
        log(f"재시도 모드 — 실패 조각 {len(chunks)}개")
        failed = []

    done = t0 = 0
    t0 = time.time()
    nrow = 0
    for i, c in enumerate(chunks):
        p = RAW / f"chunk_{i:04d}.pkl"
        if p.exists() and not a.retry:
            done += 1
            continue
        try:
            df = fetch(c)
            if df is None or not len(df):
                failed.append(i)
                log(f"  조각 {i:>3} 비었음 ({c[0]}~{c[-1]})")
                continue
            df.to_pickle(p)
            nrow += len(df)
            done += 1
            el = time.time() - t0
            rem = (len(chunks) - i - 1) * el / max(i + 1 - 0, 1)
            log(f"  조각 {i:>3}/{len(chunks)-1} · {df.ticker.nunique():>3}종목 "
                f"{len(df):>7,}행 · 누적 {nrow:,}행 · 남은시간 약 {rem/60:.0f}분")
        except Exception as e:
            failed.append(i)
            log(f"  조각 {i:>3} 실패 {type(e).__name__}: {str(e)[:80]}")
        time.sleep(0.4)                       # 예의상 간격
    json.dump(sorted(set(failed)), open(FAIL, "w"), indent=1)
    log(f"끝. 조각 {done}/{len(chunks)} 성공 · 실패 {len(set(failed))}개 · "
        f"이번에 {nrow:,}행 · 저장 {RAW}")
    if failed:
        log("  실패분은 'python us_collect.py --retry' 로 다시 받는다")


if __name__ == "__main__":
    main()
