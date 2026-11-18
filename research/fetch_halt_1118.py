# -*- coding: utf-8 -*-
"""생산중단 공시 원문 받기(2026-11-18, 코덱스 제안 3번 — 경쟁사 생산중단 뒤 대체 공급업체 매수).
DART document.xml(공시 원문 zip) → 본문 글자. 2016~ · 정정·자회사 공시는 표시만 하고 같이 받는다.
→ research/cache/halt_kr_1118.pkl (rcept_no, ticker, corp, date, report_nm, text)
    python research/fetch_halt_1118.py"""
import io, re, sqlite3, sys, time, urllib.request, zipfile
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
env = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
KEY = env["DART_API_KEY"].strip().strip('"')
c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
D = pd.read_sql("select rcept_no, stock_code ticker, corp_name corp, rcept_dt date, report_nm from disclosure "
                "where report_nm like '%생산중단%' and rcept_dt >= '20160101' and stock_code != ''", c); c.close()
D["report_nm"] = D.report_nm.str.strip()
out = ROOT / "cache" / "halt_kr_1118.pkl"
rows = pd.read_pickle(out).to_dict("records") if out.exists() else []
rows = [r for r in rows if r.get("text")]
done = {r["rcept_no"] for r in rows}
todo = D[~D.rcept_no.isin(done)]
print("대상 %d건 · 받은 것 %d · 남은 것 %d" % (len(D), len(done), len(todo)), flush=True)

def dec(raw):
    for enc in ("utf-8", "cp949"):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode("cp949", "ignore")

bad = 0
for n, r in enumerate(todo.itertuples()):
    u = "https://opendart.fss.or.kr/api/document.xml?crtfc_key=%s&rcept_no=%s" % (KEY, r.rcept_no)
    try: b = urllib.request.urlopen(u, timeout=30).read()
    except Exception: time.sleep(3); bad += 1; continue
    if not b.startswith(b"PK"):
        msg = b[:300].decode("utf-8", "ignore")
        if "020" in msg or "한도" in msg: print("하루 한도 — 멈춤", flush=True); break
        bad += 1; continue
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
        txt = " ".join(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dec(z.read(x)))) for x in z.namelist())
    except Exception: bad += 1; continue
    rows.append(dict(rcept_no=r.rcept_no, ticker=r.ticker, corp=r.corp, date=r.date, report_nm=r.report_nm, text=txt[:6000]))
    if n % 100 == 0: print(" ", n, len(rows), flush=True)
    time.sleep(0.08)
pd.DataFrame(rows).to_pickle(out)
X = pd.DataFrame(rows)
print("끝 · 저장 %d건 · 못 받음 %d · 글자 수 중앙 %d" % (len(X), bad, X.text.str.len().median()))
print(X.report_nm.value_counts().head(8).to_string())
print("본보기:", X.iloc[len(X) // 2].text[:900])
