# -*- coding: utf-8 -*-
"""SEC 결제불이행(FTD) 수집 — 한국에 아예 없는 축.

결제불이행(fails-to-deliver)은 정해진 날짜에 주식이 인도되지 않은 수량이다.
무차입 공매도·유동성 압박의 대용 지표로 쓰이고, 스퀴즈 직전에 치솟는 경향이 있다.
한국에는 종목별 공개 데이터가 없다. SEC 가 격주로 무료 공시한다(2009~).

우리 스타일과 맞는 이유: 우리는 '떨어진 것' 을 산다. FTD 가 급증한 종목은
공매도 압력이 극에 달한 자리라 반등 재료가 될 수 있다.
"""
import io, sys, time, zipfile, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import pandas as pd, requests
OUT=Path("data/us/ftd"); OUT.mkdir(parents=True, exist_ok=True)
UA={"User-Agent":"bamhobak-research microjun98@gmail.com"}
def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
ok=miss=0; rows=0
for y in range(2009, 2027):
    for m in range(1, 13):
        for half in ("a","b"):
            p=OUT/f"{y}{m:02d}{half}.pkl"
            if p.exists(): ok+=1; continue
            u=f"https://www.sec.gov/files/data/fails-deliver-data/cnsfails{y}{m:02d}{half}.zip"
            try:
                r=requests.get(u,headers=UA,timeout=60)
                if not r.ok or len(r.content)<5000: miss+=1; continue
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    n=z.namelist()[0]
                    t=pd.read_csv(z.open(n),sep="|",encoding="latin-1",on_bad_lines="skip")
                t.columns=[c.strip().upper() for c in t.columns]
                need=[c for c in ("SETTLEMENT DATE","SYMBOL","QUANTITY (FAILS)","PRICE") if c in t.columns]
                t=t[need].rename(columns={"SETTLEMENT DATE":"date","SYMBOL":"ticker",
                                          "QUANTITY (FAILS)":"ftd","PRICE":"px"})
                t["date"]=t.date.astype(str).str.replace("-","",regex=False).str[:8]
                t.to_pickle(p); ok+=1; rows+=len(t)
                if ok%24==0: log(f"  {y}{m:02d}{half} · 누적 {ok}개 파일 {rows:,}행")
            except Exception as e:
                miss+=1
            time.sleep(0.2)
log(f"끝. 파일 {ok}개 · 없음 {miss}개 · {rows:,}행 → {OUT}")
