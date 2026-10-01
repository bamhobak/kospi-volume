# -*- coding: utf-8 -*-
"""국내 자사주 결정 상세(금액·목적) — DART 주요사항보고서 API (2026-10-02, 사용자 제안 10번).
  tsstkAqDecsn          자기주식 취득 결정  → 취득예정금액(보통주)·목적(aq_pp: 이익 소각 / 주가 안정 …)·방법
  tsstkAqTrctrCnsDecsn  자기주식취득 신탁계약 체결 결정 → 계약금액(ctr_prc)
회사마다 2010~ 전 기간을 한 번에 받는다 → research/cache/buyback_kr.pkl. 키는 .env(DART_API_KEY).
    python research/fetch_buyback_kr.py
"""
import json, sqlite3, sys, time, urllib.request
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
env = dict(l.split("=", 1) for l in (BASE / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
KEY = env["DART_API_KEY"].strip().strip('"')
c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
J = {"tsstkAqDecsn": "자기주식취득결정", "tsstkAqTrctrCnsDecsn": "자기주식취득신탁계약체결결정"}
out = ROOT / "cache" / "buyback_kr.pkl"
rows = pd.read_pickle(out).to_dict("records") if out.exists() else []
done = {(r["_api"], r["corp_code"]) for r in rows}
for api, kw in J.items():
    corps = [r[0] for r in c.execute("select distinct corp_code from disclosure where report_nm like ? and rcept_dt >= '20100101'", ("%" + kw + "%",))]
    print(api, len(corps), "회사", flush=True)
    for n, cc in enumerate(corps):
        if (api, cc) in done:
            continue
        u = "https://opendart.fss.or.kr/api/%s.json?crtfc_key=%s&corp_code=%s&bgn_de=20100101&end_de=20261231" % (api, KEY, cc)
        for att in range(3):
            try:
                j = json.loads(urllib.request.urlopen(u, timeout=30).read().decode()); break
            except Exception as e:
                time.sleep(3 * (att + 1)); j = {}
        if j.get("status") == "020":
            print("한도 초과 — 멈춤", flush=True); break
        for x in j.get("list", []) or []:
            x["_api"] = api; rows.append(x)
        rows.append({"_api": api, "corp_code": cc, "rcept_no": None})      # 받았다는 표시
        if n % 100 == 0:
            pd.DataFrame(rows).to_pickle(out); print(" ", api, n, len(rows), flush=True)
        time.sleep(0.12)
pd.DataFrame(rows).to_pickle(out)
print("끝", len(rows))
