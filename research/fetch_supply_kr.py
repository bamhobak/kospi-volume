# -*- coding: utf-8 -*-
"""국내 단일판매·공급계약 공시의 '매출액 대비 %' 뽑기 (2026-10-02 사용자 제안 9번).
DART document.xml(공시 원문 zip) → '매출액대비(%) 20.4' · 계약금액 · 최근매출액. 2016~ · 정정 제외 ·
공시일 20일 평균 거래대금 3억↑ 종목만(실측과 같은 유동성). 하루 한도(2만 건)에 걸리면 멈추고 다음 실행이 이어 받는다.
→ research/cache/supply_kr.pkl (rcept_no, ticker, date, pct, amt, sales)
    python research/fetch_supply_kr.py
"""
import io, re, sqlite3, sys, time, urllib.request, zipfile
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
env = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
KEY = env["DART_API_KEY"].strip().strip('"')
c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
D = pd.read_sql("select rcept_no, stock_code ticker, rcept_dt date from disclosure where report_nm like '%단일판매ㆍ공급계약체결%' "
                "and report_nm not like '%정정%' and report_nm not like '%해지%' and rcept_dt >= '20160101' and stock_code != ''", c)
K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "amt20"]]
cal = np.array(sorted(K.date.unique()))
D["sd"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, D.date.values, "left")]
D = D.merge(K.rename(columns={"date": "sd"}), on=["ticker", "sd"], how="left")
D = D[D.amt20 >= 3]
out = ROOT / "cache" / "supply_kr.pkl"
rows = pd.read_pickle(out).to_dict("records") if out.exists() else []
done = {r["rcept_no"] for r in rows}
todo = D[~D.rcept_no.isin(done)]
print("대상 %d건 · 받은 것 %d · 남은 것 %d" % (len(D), len(done), len(todo)), flush=True)
num = lambda s: float(s.replace(",", "")) if s else np.nan
for n, (rn, t, d) in enumerate(zip(todo.rcept_no, todo.ticker, todo.date)):
    u = "https://opendart.fss.or.kr/api/document.xml?crtfc_key=%s&rcept_no=%s" % (KEY, rn)
    try:
        b = urllib.request.urlopen(u, timeout=30).read()
    except Exception as e:
        time.sleep(5); continue
    if not b.startswith(b"PK"):
        msg = b[:300].decode("utf-8", "ignore")
        if "020" in msg or "한도" in msg:
            print("하루 한도 — 멈춤", flush=True); break
        rows.append(dict(rcept_no=rn, ticker=t, date=d, pct=np.nan, amt=np.nan, sales=np.nan)); continue
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
        txt = " ".join(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", z.read(x).decode("utf-8", "ignore"))) for x in z.namelist())
    except Exception:
        txt = ""
    m = re.search(r"매출액\s*대비\s*\(%\)\s*([\d.,]+)", txt)
    a = re.search(r"계약금액[^0-9]{0,20}([\d,]{4,})", txt)
    s = re.search(r"최근\s*매출액[^0-9]{0,20}([\d,]{4,})", txt)
    rows.append(dict(rcept_no=rn, ticker=t, date=d, pct=num(m.group(1)) if m else np.nan,
                     amt=num(a.group(1)) if a else np.nan, sales=num(s.group(1)) if s else np.nan))
    if n % 500 == 0:
        pd.DataFrame(rows).to_pickle(out); print(" ", n, len(rows), flush=True)
    time.sleep(0.08)
pd.DataFrame(rows).to_pickle(out)
print("끝 · 저장 %d건" % len(rows))
