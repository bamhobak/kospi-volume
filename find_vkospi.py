# -*- coding: utf-8 -*-
"""KRX 정보데이터시스템에서 VKOSPI(코스피200 변동성지수) 시계열이 나오는 통계를 찾는다.

배경: 주가지수 finder(finder_equidx)에는 변동성지수가 없고, 파생상품 finder 에는 '변동성지수 선물' 만 있다.
      그래서 MDCSTAT 통계 번호를 좁은 범위로 훑어 '변동성' 이 들어간 응답을 찾는다.
⚠ KRX 는 과속하면 차단된다 — 요청 사이 2초 이상 쉬고, 백필이 끝난 뒤에만 돌린다.
사용: python find_vkospi.py [--from 100] [--to 140]
"""
import json, sys, time, urllib.request, urllib.parse

U = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
     "X-Requested-With": "XMLHttpRequest"}
GAP = 2.2
arg = lambda k, d: sys.argv[sys.argv.index(k)+1] if k in sys.argv else d
LO, HI = int(arg("--from", "100")), int(arg("--to", "140"))

def post(q, timeout=20):
    r = urllib.request.Request(U, data=urllib.parse.urlencode(q).encode(), headers=H)
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read().decode())

BASEQ = {"locale": "ko_KR", "trdDd": "20240102", "strtDd": "20240102", "endDd": "20240110",
         "share": "1", "money": "1", "csvxls_isNo": "false", "mktId": "ALL",
         "indTpCd": "1", "idxIndMidclssCd": "01", "tboxindIdx_finder_equidx0_0": "코스피",
         "indIdx": "1", "indIdx2": "001", "codeNmindIdx_finder_equidx0_0": "코스피",
         "param1indIdx_finder_equidx0_0": ""}
hits = []
print(f"MDCSTAT{LO:03d}xx ~ MDCSTAT{HI:03d}xx 훑는 중 (요청 간격 {GAP}s)\n", flush=True)
for n in range(LO, HI+1):
    for sub in ("01", "02", "03"):
        bld = f"dbms/MDC/STAT/standard/MDCSTAT{n:03d}{sub}"
        try:
            d = post({**BASEQ, "bld": bld})
        except Exception as e:
            code = getattr(e, "code", "")
            if code != 400: print(f"  {bld}  오류 {code} {str(e)[:40]}", flush=True)
            time.sleep(GAP); continue
        s = json.dumps(d, ensure_ascii=False)
        rows = next((v for v in d.values() if isinstance(v, list)), [])
        tag = ""
        if "변동성" in s: tag = "  ★ 변동성 포함"; hits.append((bld, d))
        if rows or tag:
            keys = list(rows[0].keys())[:8] if rows else []
            print(f"  {bld}  {len(rows):>4}행 {keys}{tag}", flush=True)
        time.sleep(GAP)
print("\n=== 변동성 포함 통계 ===")
for bld, d in hits:
    rows = next((v for v in d.values() if isinstance(v, list)), [])
    print(bld)
    for r in rows[:5]:
        if "변동성" in json.dumps(r, ensure_ascii=False): print("   ", r)
if not hits: print("  없음 — 다른 번호대를 훑거나 다른 경로가 필요하다")
