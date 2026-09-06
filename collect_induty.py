# -*- coding: utf-8 -*-
"""업종 결측 메우기 — 옛 폐지 종목의 표준산업분류를 DART 에서 받는다.

왜: 업종 유효율이 2005년 44% · 2010년 70% 밖에 안 된다. industry.csv 는 현재 상장분만이고
    ksic.csv 로도 옛 폐지 종목을 다 못 메운다. 그 탓에 업종 조건을 쓰는 다섯 규칙
    ([업종붕괴 이탈]·[깊은 이격]·[폭락반등]·[낙폭과대]·[저PBR 낙폭])의 2005~2011 성적이
    반쪽 유니버스 기준이 된다(2026-09-06 발견).
어떻게: DART corpcode.zip 에는 폐지 포함 종목코드 3,988개가 있다. company.json 이 종목마다
    induty_code(표준산업분류)를 준다. 이미 아는 종목은 건너뛰고 모르는 것만 받아 ksic.csv 에 합친다.
⚠ DART 는 분당 호출 제한이 있다 — 간격 0.12초, 실패는 건너뛰고 다음 실행에서 재시도한다.
사용: python collect_induty.py [--gap 0.12]
"""
import csv, io, json, os, sys, time, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
GAP = float(arg("--gap", "0.12"))
for l in (BASE/".env").read_text(encoding="utf-8").splitlines():
    if "=" in l and not l.startswith("#"): k, v = l.split("=", 1); os.environ[k.strip()] = v.strip()
KEY = os.environ["DART_API_KEY"]

KSF = BASE/"data"/"ksic.csv"
ks = {r["ticker"]: r["ksic"] for r in csv.DictReader(open(KSF, encoding="utf-8-sig")) if r.get("ksic")}
ind = {r["ticker"] for r in csv.DictReader(open(BASE/"data"/"industry.csv", encoding="utf-8-sig"))
       if r.get("industry")}
z = zipfile.ZipFile(BASE/"data"/"dart"/"corpcode.zip")
x = ET.fromstring(z.read(z.namelist()[0]).decode("utf-8"))
CORP = {t: e.findtext("corp_code") for e in x.iter("list")
        if (t := (e.findtext("stock_code") or "").strip())}
todo = sorted(t for t in CORP if t not in ks and t not in ind)
print(f"업종 모르는 종목 {len(todo):,}개 · 간격 {GAP}s · 예상 {len(todo)*GAP/60:.0f}분")

got = fail = 0; t0 = time.time()
for i, t in enumerate(todo, 1):
    time.sleep(GAP)
    try:
        r = requests.get("https://opendart.fss.or.kr/api/company.json",
                         params={"crtfc_key": KEY, "corp_code": CORP[t]}, timeout=20).json()
        code = (r.get("induty_code") or "").strip()
        if r.get("status") == "000" and code: ks[t] = code; got += 1
        else: fail += 1
    except Exception: fail += 1
    if i % 100 == 0:
        el = time.time()-t0
        print(f"  {i}/{len(todo)} · 획득 {got} · 실패 {fail} · {el/60:.0f}분", flush=True)
        with open(KSF, "w", encoding="utf-8-sig", newline="") as f:   # 중간 저장
            w = csv.writer(f); w.writerow(["ticker", "ksic"]); w.writerows(sorted(ks.items()))
with open(KSF, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f); w.writerow(["ticker", "ksic"]); w.writerows(sorted(ks.items()))
print(f"완료 · 새로 얻음 {got}개 · 실패 {fail}개 · ksic.csv 총 {len(ks):,}개 · {(time.time()-t0)/60:.0f}분")
