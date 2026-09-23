# -*- coding: utf-8 -*-
"""SEC 회사 목록(submissions.zip)에서 회사번호·이름·옛 이름·업종(SIC)을 뽑는다 (2026-09-23).

왜: 폐지 종목을 SEC 재무(companyfacts, 폐지 회사 포함)와 잇고 업종을 붙이려면 **티커 → 회사번호**가
필요한데, SEC 는 폐지 회사의 티커를 지운다(BBBY·SIVB·TWTR 모두 tickers=[]). 대신 **이름과 옛 이름**은
남는다 — 베드배스는 현재 이름이 '20230930-DK-Butterfly-1, Inc.' 이고 'BED BATH & BEYOND INC' 는
옛 이름에만 있다. 그래서 둘 다 뽑아 두고 Tiingo 회사명과 짝을 맞춘다.

대상: entityType 이 operating·other(외국 기업) 이고 SIC 가 있는 회사(펀드·개인·신탁 제외).
출력: data/us/sec_cik.pkl — cik · name · former(옛 이름 목록) · tickers · exchanges · sic · sicDesc · last_filed
    python build_sec_cik.py
"""
import io, json, os, sys, time, zipfile
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8")
ZIP = BASE / "data" / "us" / "submissions.zip"
OUT = BASE / "data" / "us" / "sec_cik.pkl"

t0 = time.time()
z = zipfile.ZipFile(ZIP)
names = [x for x in z.namelist() if x.startswith("CIK") and "-submissions-" not in x]
print(f"{len(names):,}개 파일", flush=True)
rows = []
for i, nm in enumerate(names, 1):
    try:
        j = json.loads(z.read(nm))
    except Exception:
        continue
    # 'other' 도 넣는다 — 외국 기업(ASML·HSBC·알리바바 등 20-F 제출사)이 여기로 분류된다.
    #   처음엔 operating 만 받았다가 정답 아는 상장사의 20% 가 표에서 빠져 있었다(2026-09-23).
    if j.get("entityType") not in ("operating", "other") or not j.get("sic"):
        continue
    rec = (j.get("filings") or {}).get("recent") or {}
    fd = rec.get("filingDate") or []
    rows.append((int(nm[3:13]), j.get("entityType"), j.get("name"), [f.get("name") for f in j.get("formerNames") or []],
                 j.get("tickers") or [], j.get("exchanges") or [], j.get("sic"), j.get("sicDescription"),
                 max(fd) if fd else None))
    if i % 100000 == 0:
        print(f"  {i:,}/{len(names):,} · 회사 {len(rows):,} · {(time.time() - t0) / 60:.1f}분", flush=True)
D = pd.DataFrame(rows, columns=["cik", "etype", "name", "former", "tickers", "exchanges", "sic", "sicDesc", "last_filed"])
D.to_pickle(OUT)
print(f"끝: {len(D):,}개사 · 티커 있음 {(D.tickers.str.len() > 0).sum():,} · 옛 이름 있음 "
      f"{(D.former.str.len() > 0).sum():,} · {(time.time() - t0) / 60:.1f}분 → {OUT.name}", flush=True)
