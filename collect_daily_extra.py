# -*- coding: utf-8 -*-
"""일일 파이프라인용 보조 데이터 (최근 구간만) — GitHub Actions 에서도 동작
   ① 공매도 비중 최근 40거래일 → data/short_recent.csv
   ② 유상증자·CB 공시 최근 120일 → data/dilution_recent.csv
   둘 다 작아서 리포지토리에 커밋 가능. 과거 전체는 로컬 DB(백테스트용)에만 둔다.
사용: python collect_daily_extra.py   (KIS_APP_KEY/KIS_APP_SECRET/DART_API_KEY 환경변수 또는 .env)
"""
import csv, os, sqlite3, sys, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
import collect

BASE = Path(__file__).parent
log = collect.log
today = dt.date.today()
num = lambda s: None if s in (None, "", "-") else float(s)

def env(k):
    v = os.environ.get(k)
    if v: return v.strip()
    f = BASE / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.startswith(k + "="): return l.split("=", 1)[1].strip()
    return None

# ── ① 공매도 (KIS) ─────────────────────────────────────────
def short_recent():
    try:
        import kis
        if not kis.APP_KEY: log.warning("KIS 키 없음 — 공매도 건너뜀"); return
        T = kis.get_token()
    except Exception as e:
        log.warning(f"KIS 토큰 실패 — 공매도 건너뜀: {str(e)[:60]}"); return
    con = sqlite3.connect(f"file:{BASE/'data'/'kospi.db'}?mode=ro", uri=True)
    codes = [r[0] for r in con.execute(
        "SELECT DISTINCT ticker FROM daily WHERE market='KOSPI' AND date=(SELECT max(date) FROM daily)")]
    con.close()
    d1 = (today - dt.timedelta(days=80)).strftime("%Y%m%d"); d2 = today.strftime("%Y%m%d")
    rows = []
    def one(tk):
        for _ in range(4):
            try:
                st, d, _ = kis.call("/uapi/domestic-stock/v1/quotations/daily-short-sale", "FHPST04830000",
                    {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": tk,
                     "FID_INPUT_DATE_1": d1, "FID_INPUT_DATE_2": d2}, token=T)
                if d.get("rt_cd") == "0":
                    return [(x.get("stck_bsop_date"), tk, x.get("ssts_vol_rlim"))
                            for x in (d.get("output2") or []) if x.get("stck_bsop_date")]
            except Exception: pass
            time.sleep(1)
        return []
    n = 0
    with ThreadPoolExecutor(4) as ex:
        for f in as_completed([ex.submit(one, c) for c in codes]):
            rows += f.result(); n += 1
            if n % 200 == 0: log.info(f"공매도 {n}/{len(codes)}")
    out = BASE / "data" / "short_recent.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["date", "ticker", "short_ratio"])
        w.writerows(sorted(r for r in rows if r[2] not in (None, "")))
    log.info(f"공매도 최근 저장: {out.name} ({len(rows):,}행)")

# ── ② 유상증자·CB 공시 (DART) ──────────────────────────────
def dilution_recent():
    K = env("DART_API_KEY")
    if not K: log.warning("DART 키 없음 — 공시 건너뜀"); return
    pats = ("유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정")
    rows, bgn = [], (today - dt.timedelta(days=130)).strftime("%Y%m%d")
    for off in (0, 65, 130):        # 3개월 제한 → 구간 분할
        b = (today - dt.timedelta(days=130 - off)).strftime("%Y%m%d")
        e = (today - dt.timedelta(days=max(0, 130 - off - 65))).strftime("%Y%m%d")
        page = 1
        while page <= 60:
            try:
                d = requests.get("https://opendart.fss.or.kr/api/list.json",
                    params={"crtfc_key": K, "bgn_de": b, "end_de": e, "corp_cls": "Y",
                            "pblntf_ty": "B", "page_no": page, "page_count": 100}, timeout=30).json()
            except Exception as ex_:
                log.warning(f"DART {b}~{e} p{page}: {str(ex_)[:40]}"); break
            if d.get("status") != "000": break
            for x in d.get("list") or []:
                nm = (x.get("report_nm") or "").replace(" ", "")
                if any(p in nm for p in pats) and x.get("stock_code"):
                    rows.append((x["rcept_dt"], x["stock_code"], x.get("report_nm", "")[:60]))
            if page >= int(d.get("total_page") or 1): break
            page += 1
    out = BASE / "data" / "dilution_recent.csv"
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh); w.writerow(["rcept_dt", "ticker", "report_nm"])
        w.writerows(sorted(set(rows)))
    log.info(f"희석 공시 저장: {out.name} ({len(set(rows)):,}건)")

if "--dart-only" not in sys.argv: short_recent()
if "--kis-only" not in sys.argv: dilution_recent()
