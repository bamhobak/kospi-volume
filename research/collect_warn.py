# -*- coding: utf-8 -*-
"""KIND 시장경보(투자주의·경고·위험) 지정 이력 받기 → data/krx_warn.pkl (2026-10-15, H0339 시장경보 지정 뒤 매물 소진).

KIND investattentwarnrisky.do (menuIndex 1=주의 · 2=경고 · 3=위험) 를 해마다 천천히(요청 사이 2초) 받는다.
칸: 번호 · 종목명 · (빈칸) · 공시일 · 지정일. 종목코드가 없어서 월별 CSV(date·ticker·name)로 그 무렵 이름 → 코드 매칭.
    python research/collect_warn.py [주의도]   (기본 경고·위험만 — 주의는 건수가 많아 따로)
"""
import re, sys, time, glob
from pathlib import Path
import pandas as pd
from curl_cffi import requests as R

BASE = Path(__file__).resolve().parent.parent
URL = "https://kind.krx.co.kr/investwarn/investattentwarnrisky.do"
KIND = {1: "주의", 2: "경고", 3: "위험"}
ROW = re.compile(r'<td class="first txc" scope="row">\d+</td>\s*<td title="([^"]*)">(.*?)</td>\s*<td>(.*?)</td>\s*<td class="txc">([\d-]*)</td>\s*<td class="txc">([\d-]*)</td>', re.S)


def fetch(s, menu, y):
    out = []; page = 1
    while True:
        d = dict(method="investattentwarnriskySub", currentPageSize="500", pageIndex=str(page), menuIndex=str(menu), marketType="",
                 startDate="%d-01-01" % y, endDate="%d-12-31" % y, orderMode="", orderStat="", searchCodeType="", searchCorpName="", repIsuSrtCd="", forward="")
        for k in range(4):
            try:
                t = s.post(URL, data=d, timeout=40, headers={"Referer": URL + "?method=investattentwarnriskyMain"}).text; break
            except Exception as ex:
                print("  재시도", y, page, ex, flush=True); time.sleep(10 * (k + 1))
        else: raise RuntimeError("KIND 실패 %d %d" % (y, page))
        rows = ROW.findall(t)
        for nm, cell, extra, a, b in rows:
            mk = "KOSPI" if "유가증권" in cell else "KOSDAQ" if "코스닥" in cell else "기타"
            out.append(dict(kind=KIND[menu], name=nm.strip(), mk=mk, extra=re.sub(r"<[^>]+>", "", extra).strip(), dt_pub=a, dt=b))
        time.sleep(2.0)
        if len(rows) < 500: break
        page += 1
    return out


def main():
    menus = [1, 2, 3] if (len(sys.argv) > 1 and sys.argv[1] == "주의도") else [2, 3]
    s = R.Session(impersonate="chrome")
    s.get(URL + "?method=investattentwarnriskyMain", timeout=30)
    rows = []
    for menu in menus:
        for y in range(2005, 2027):
            r = fetch(s, menu, y); rows += r
            print(KIND[menu], y, len(r), flush=True)
    W = pd.DataFrame(rows)
    W["date"] = W.dt.str.replace("-", "")
    # 이름 → 코드: 월별 CSV 의 (월, 이름) → 코드
    fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
    N = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "name"], dtype={"ticker": str, "date": str}) for f in fs], ignore_index=True)
    N["ym"] = N.date.str[:6]; N = N.drop_duplicates(["ym", "name"])[["ym", "name", "ticker"]]
    W["ym"] = W.date.str[:6]
    W = W.merge(N, on=["ym", "name"], how="left")
    miss = W.ticker.isna()
    if miss.any():                                                    # 그 달에 이름이 없으면 전체 기간 마지막 매칭
        last = N.drop_duplicates("name", keep="last").set_index("name").ticker
        W.loc[miss, "ticker"] = W.loc[miss, "name"].map(last)
    print("매칭 %d / %d" % (W.ticker.notna().sum(), len(W)))
    W.drop(columns=["ym"]).to_pickle(BASE / "data" / ("krx_warn%s.pkl" % ("_all" if len(menus) == 3 else "")))


if __name__ == "__main__":
    main()
