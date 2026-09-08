# -*- coding: utf-8 -*-
"""SEC 재무 수집 — companyfacts 벌크 zip 한 방.

미국 밸류 축(PBR/PER/부채비율)을 쓰려면 재무가 필요하다. SEC XBRL 은 무료·키 불필요이고
**공시일(filed)이 들어 있어 시점 기준(point-in-time) 구성이 된다** — 한국 DART 에서
공시 지연을 손으로 맞춰준 것과 같은 일을 여기선 데이터가 직접 해준다.

종목별로 6,085번 부르는 대신 벌크 zip 을 한 번 받는다(SEC 초당 10회 제한도 피한다).
"""
import io, sys, time, warnings, zipfile
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import requests
OUT = Path("data/us"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "bamhobak-research microjun98@gmail.com"}
URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
p = OUT / "companyfacts.zip"
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
if p.exists() and p.stat().st_size > 1e8:
    log(f"이미 있음 {p} ({p.stat().st_size/1e9:.2f}GB)")
else:
    log("SEC companyfacts 벌크 내려받는 중 (1GB 넘을 수 있다)")
    r = requests.get(URL, headers=UA, stream=True, timeout=120)
    r.raise_for_status()
    tot = int(r.headers.get("Content-Length", 0))
    got = 0; t0 = time.time()
    with open(p, "wb") as f:
        for c in r.iter_content(1 << 20):
            f.write(c); got += len(c)
            if got % (100 << 20) < (1 << 20):
                log(f"  {got/1e9:.2f}GB / {tot/1e9:.2f}GB · {got/1e6/(time.time()-t0):.0f}MB/s")
    log(f"저장 완료 {got/1e9:.2f}GB")
with zipfile.ZipFile(p) as z:
    n = len(z.namelist())
log(f"압축 안에 회사 파일 {n:,}개 — CIK 별 전체 재무 항목")
# 티커↔CIK 매핑도 같이 받아둔다
r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=UA, timeout=60)
(OUT / "company_tickers.json").write_bytes(r.content)
log(f"티커↔CIK 매핑 저장 {len(r.json()):,}개")
