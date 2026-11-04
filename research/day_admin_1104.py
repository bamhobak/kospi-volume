# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 관리종목이면 안 사야 하나 (2026-11-04 사용자 "오늘 매수한 프롬바이오 같은 관리종목은 안 사야 하는 거 아니야?").
관리종목 기간 = KIND 거래소 공시(제목에 '관리종목') 월별 검색 → 종목마다 '관리종목지정'(우려·예고·해제·해소·일부 빼고) 다음 거래일부터
'관리종목 해제'(일부해제 빼고) 공시일까지. 지금 목록(KRX-ADMIN)으로 끝이 열린 기간을 맞춰 본다. 우선주 지정은 뺀다.
그물 = 지금 설정(4/9 · 갭 하위 40% · 거래량 하위 30% · 실제 시장 대비 -1.5%p) · 시가→종가 · 비용 0.23 뒤.
    python research/day_admin_1104.py        (KIND 받기는 data/kind_admin.csv 에 모아 두고 다시 안 받음)
"""
import sys, time, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd, requests
import FinanceDataReader as fdr
import lab, feats as FT

F = BASE / "data" / "kind_admin.csv"
URL = "https://kind.krx.co.kr/disclosure/details.do"
HD = {"User-Agent": "Mozilla/5.0", "Referer": URL + "?method=searchDetailsMain"}
ROW = re.compile(r'<td class="txc">(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}</td>.*?companysummary_open\(\'(\w+)\'\).*?title=\'([^\']*)\'>.*?openDisclsViewer\(\'\d+\',\'\'\)" title=\'([^\']*)\'', re.S)


def page(a, b, pi):
    d = dict(method="searchDetailsSub", currentPageSize="100", pageIndex=str(pi), orderMode="1", orderStat="D", forward="details_sub",
             **{"disclosureType%02d" % i: "" for i in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 20)}, pDisclosureType01="",
             reportNm="관리종목", reportNmTemp="관리종목", fromDate=a, toDate=b, marketType="", searchCorpName="", repIsuSrtCd="",
             isurCd="", bfrDsclsType="on", searchCodeType="", tockCode="")
    for att in range(5):
        r = requests.post(URL, data=d, headers=HD, timeout=60)
        if "잠시 후 다시" not in r.text: return ROW.findall(r.text)
        time.sleep(30 * (att + 1))
    raise RuntimeError("KIND 막힘 %s" % a)


def fetch():
    if F.exists(): return pd.read_csv(F, dtype=str)
    rows = []
    for m in pd.period_range("2010-01", "2026-11", freq="M"):
        a, b = m.start_time.strftime("%Y-%m-%d"), m.end_time.strftime("%Y-%m-%d")
        pi = 1
        while True:
            R = page(a, b, pi); rows += R; time.sleep(3)                  # KRX 는 저속·순차
            if len(R) < 100: break
            pi += 1
        print(m, len(rows), flush=True)
    D = pd.DataFrame(rows, columns=["date", "c5", "name", "title"]).drop_duplicates()
    D.to_csv(F, index=False, encoding="utf-8-sig"); return D


def intervals(D, today):
    D = D.copy(); D["t"] = D.title.str.replace(r"\s+", "", regex=True)
    D = D[~D.t.str.contains("우선주|우B|ETF|ETN|스팩|SPAC") & ~D.name.str.contains("우$|우B$|ETF|스팩")]
    on = D.t.str.match(r"^(\[\S+\])?관리종목지정") & ~D.t.str.contains("우려|예고|해제|해소")
    off = D.t.str.contains("관리종목해제|관리종목지정해제") & ~D.t.str.contains("일부")
    ev = pd.concat([D[on].assign(k=1), D[off].assign(k=0)]).sort_values(["c5", "date", "k"])
    out = []
    for c5, g in ev.groupby("c5"):
        st = None
        for r in g.itertuples():
            if r.k == 1 and st is None: st = r.date
            elif r.k == 0 and st is not None: out.append((c5, st, r.date)); st = None
        if st is not None: out.append((c5, st, today))
    return pd.DataFrame(out, columns=["c5", "a", "b"])


def main():
    D = fetch()
    print("KIND '관리종목' 공시 %d건 · %s~%s" % (len(D), D.date.min(), D.date.max()))
    today = time.strftime("%Y-%m-%d")
    I = intervals(D, today)
    cur = fdr.StockListing("KRX-ADMIN"); cur = set(cur.Symbol.astype(str).str.zfill(6).str[:5])
    open_ = set(I[I.b == today].c5)
    print("관리 기간 %d개 · 지금 열린 기간 %d · 지금 목록 %d 중 맞음 %d · 목록에 없는데 열림 %d" % (
        len(I), len(open_), len(cur), len(open_ & cur), len(open_ - cur)))
    H = lab.hist()[["ticker", "date", "oc", "rgap", "q_gap", "q_vm", "liq"]].dropna(subset=["oc", "rgap", "q_gap", "liq"])
    W = H[(H.rgap <= -1.5) & (H.q_gap <= 0.40) & (H.q_vm.fillna(1) <= 0.30) & (H.liq <= 4 / 9) & (H.date >= "20100101")].copy()
    W["oc"] -= FT.COST; W["c5"] = W.ticker.str[:5]; W["d"] = pd.to_datetime(W.date).dt.strftime("%Y-%m-%d")
    W["adm"] = False
    for r in I.itertuples():                                            # 지정 공시 다음 거래일 ~ 해제 공시일
        m = (W.c5 == r.c5) & (W.d > r.a) & (W.d <= r.b)
        if m.any(): W.loc[m, "adm"] = True
    per = (("옛날 2010~15", "20100101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
    cell = lambda z: "%d건 · %+.2f%% · 승 %.0f%% · 중앙 %+.2f%%" % (len(z), z.oc.mean(), (z.oc > 0).mean() * 100, z.oc.median()) if len(z) else "0건"
    print("\n| 구간 | 관리종목 | 아님 | 관리종목 비율 |"); print("|---|---|---|---|")
    for nm, lo, hi in per:
        z = W[(W.date >= lo) & (W.date <= hi)]
        print("| %s | %s | %s | %.1f%% |" % (nm, cell(z[z.adm]), cell(z[~z.adm]), z.adm.mean() * 100))
    z = W[W.adm]
    print("\n관리종목 거래 해별 건당:", " · ".join("%s %d건 %+.2f" % (y, len(g), g.oc.mean()) for y, g in z.groupby(z.date.str[:4])))
    print("관리종목 거래 손익 하위 5:", ", ".join("%s %s %+.1f" % (r.date, r.ticker, r.oc) for r in z.nsmallest(5, "oc").itertuples()))
    W[["ticker", "date", "oc", "rgap", "adm"]].to_pickle(BASE / "data" / "day" / "admin_1104.pkl")


if __name__ == "__main__":
    main()
