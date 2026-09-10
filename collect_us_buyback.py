# -*- coding: utf-8 -*-
"""미국 자사주 집행 수집 — 사이트 [자사주 낙폭] 규칙이 쓰는 재료.

국내 data/buyback_recent.csv 와 같은 자리다. 다른 점은 자료의 성격이다.
  국내: 자기주식취득 **결정 공시**(DART) — 사건이 일어난 날 바로 안다.
  미국: 8-K 로 즉시 알리긴 하지만 **금액이 담긴 XBRL 숫자는 그 뒤 10-Q/10-K** 에 실린다.
        그래서 이건 '공시 반응' 이 아니라 **'자사주를 사고 있는 회사' 라는 상태**다.
        실측에서 값어치가 나온 것도 그 상태였다(us_buyback*.py).

SEC companyfacts 벌크(약 1GB)에서 PaymentsForRepurchaseOfCommonStock 만 뽑는다.
분기 보고서라 하루 단위로 바뀌지 않는다 — **주 1회면 충분**하고, 파일이 최근이면 건너뛴다.

    python collect_us_buyback.py            # 7일 넘었으면 새로 받는다
    python collect_us_buyback.py --force    # 무조건 새로 받는다
"""
import argparse, json, sys, time, warnings, zipfile
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, requests

BASE = Path(__file__).parent
OUT = BASE / "data" / "us"; OUT.mkdir(parents=True, exist_ok=True)
ZIP = OUT / "companyfacts.zip"
CSV = OUT / "buyback_recent.csv"
UA = {"User-Agent": "bamhobak-research microjun98@gmail.com"}
URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
TAG = "PaymentsForRepurchaseOfCommonStock"
KEEP_DAYS = 500          # 최근 것만 쓴다 — 규칙은 60거래일(≈88일) 창만 본다


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


def download(force=False):
    stale = (not ZIP.exists() or ZIP.stat().st_size < 1e8
             or (time.time() - ZIP.stat().st_mtime) > 7 * 86400)
    if not (force or stale):
        age = (time.time() - ZIP.stat().st_mtime) / 86400
        log(f"companyfacts.zip 최근 것({age:.1f}일 전) — 내려받기 건너뜀"); return
    log("SEC companyfacts 벌크 내려받는 중 (약 1GB)")
    r = requests.get(URL, headers=UA, stream=True, timeout=1800); r.raise_for_status()
    tmp = ZIP.with_suffix(".part"); got = 0; t0 = time.time()
    with open(tmp, "wb") as f:
        for c in r.iter_content(1 << 20):
            f.write(c); got += len(c)
    tmp.replace(ZIP)
    log(f"저장 {got/1e9:.2f}GB · {time.time()-t0:.0f}초")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    try:
        download(a.force)
    except Exception as e:
        log(f"내려받기 실패({type(e).__name__}) — 기존 파일로 진행한다: {e}")
    if not ZIP.exists():
        log("companyfacts.zip 이 없다 — 이전 CSV 를 그대로 둔다"); return 1

    ct = json.loads((OUT / "company_tickers.json").read_text())
    C2T = {}
    for v in (ct.values() if isinstance(ct, dict) else ct):
        C2T.setdefault(int(v["cik_str"]), str(v["ticker"]).upper())
    cut = (pd.Timestamp.today() - pd.Timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    z = zipfile.ZipFile(ZIP)
    names = [n for n in z.namelist() if n.endswith(".json")]
    rows = []; t0 = time.time()
    for i, nm in enumerate(names, 1):
        if i % 4000 == 0: log(f"  {i:,}/{len(names):,} · {len(rows):,}건 · {time.time()-t0:.0f}초")
        try: d = json.load(z.open(nm))
        except Exception: continue
        tk = C2T.get(int(d.get("cik", -1)))
        if not tk: continue
        f = d.get("facts", {}).get("us-gaap", {}).get(TAG)
        if not f: continue
        for o in f.get("units", {}).get("USD", []):
            fl, val = o.get("filed"), o.get("val")
            if not fl or fl < cut or not val or val <= 0: continue
            # 같은 (기간) 이 여러 서류에 반복 보고된다 — 기간 길이로 분기분만 남긴다
            s, e = o.get("start"), o.get("end")
            if not s or not e: continue
            days = (pd.Timestamp(e) - pd.Timestamp(s)).days
            if not (60 <= days <= 200): continue
            rows.append((fl.replace("-", ""), tk, int(val)))
    if not rows:
        log("한 건도 못 뽑았다 — 이전 CSV 를 그대로 둔다"); return 1
    A = pd.DataFrame(rows, columns=["filed", "ticker", "val"])
    # 종목·공시일이 같으면 한 줄로. 규칙은 '언제 마지막으로 보고했나' 만 본다.
    A = A.sort_values("val", ascending=False).drop_duplicates(["ticker", "filed"], keep="first")
    A = A.sort_values(["ticker", "filed"])
    A.to_csv(CSV, index=False, encoding="utf-8")
    log(f"저장 {CSV} — {len(A):,}건 · 티커 {A.ticker.nunique():,} · {A.filed.min()}~{A.filed.max()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
