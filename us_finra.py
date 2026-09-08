# -*- coding: utf-8 -*-
"""FINRA 일별 공매도 거래량 수집 (2019~).

한국에서 공매도 비중(sr20·srd)이 여러 규칙의 재료로 쓰인다. 미국도 같은 축을 만들려면
이게 필요하다. FINRA 는 일별 '공매도 거래량' 을 무료로 공시한다(잔고가 아니라 거래량).
2018년 이전 파일은 403 이라 2019-01-01 부터 받는다.

파일 하나가 그날 거래된 전 종목 명단이기도 해서 **과거 시점 유니버스 복원**에도 쓴다.
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, requests
OUT = Path("data/us/finra"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "bamhobak-research microjun98@gmail.com"}
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
days = pd.bdate_range("2019-01-01", pd.Timestamp.today())
log(f"영업일 후보 {len(days):,}일 (2019-01-01 ~)")
ok = skip = miss = 0; rows = 0
buf = []
for i, d in enumerate(days):
    s = d.strftime("%Y%m%d")
    yr = s[:4]
    p = OUT / f"{yr}.pkl"
    if p.exists() and i % 250 != 0:
        pass
    try:
        r = requests.get(f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{s}.txt",
                         headers=UA, timeout=20)
        if not r.ok or len(r.text) < 200:
            miss += 1; continue
        t = pd.read_csv(io.StringIO(r.text), sep="|")
        t = t[t.Symbol.notna()]
        t["date"] = s
        buf.append(t[["date", "Symbol", "ShortVolume", "TotalVolume"]]
                   .rename(columns={"Symbol": "ticker", "ShortVolume": "shortvol",
                                    "TotalVolume": "totvol"}))
        ok += 1; rows += len(t)
    except Exception:
        miss += 1
    if len(buf) >= 250:
        y = buf[0].date.iloc[0][:4]
        f = OUT / f"part_{ok:05d}.pkl"
        pd.concat(buf, ignore_index=True).to_pickle(f)
        log(f"  {ok:>5}일 저장 · 누적 {rows:,}행 · 최근 {s}")
        buf = []
    time.sleep(0.12)
if buf:
    pd.concat(buf, ignore_index=True).to_pickle(OUT / f"part_{ok:05d}.pkl")
log(f"끝. 성공 {ok:,}일 · 없음 {miss:,}일 · {rows:,}행 → {OUT}")
