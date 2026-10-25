# -*- coding: utf-8 -*-
"""ⓑ NXT 그림자 픽에 '다양한 시각'을 소급 조인 (2026-10-26 사용자).
라이브 픽(data/nxt/log.csv)은 사라지는 것(호가·체결가)만 기록 → 축/공시/이벤트일은 과거 저장소로 언제든 붙인다.
  · lab.hist 축: 시총·120일선·52주저점·변동성·상장나이
  · DART 악재 공시(event_lab): 유증·CB·거래정지·상폐·감사의견·횡령·배임·조회·불성실 (pick 당일·전일)
  · 이벤트일: 만기(둘째 목)·월말·분기말
→ data/nxt/axis.csv 저장 + 축별 다음날 시가 수익(r_vwap) 요약. 자료 쌓이면 주간 성적표에서 이걸로 썬다.
    py314 research/nxt_enrich.py
"""
import sys, time, csv, datetime as dt
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research'); BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd

LOG = BASE / "data" / "nxt" / "log.csv"
AXIS = BASE / "data" / "nxt" / "axis.csv"
BAD = "유상증자|전환사채|신주인수권|교환사채|거래정지|상장폐지|감사의견|횡령|배임|조회공시|불성실공시|관리종목"


def event_day(d):
    dd = dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))
    tags = []
    # 둘째 목요일(만기 근사)
    first = dt.date(dd.year, dd.month, 1)
    thu = [first + dt.timedelta(days=i) for i in range(31) if (first + dt.timedelta(days=i)).month == dd.month and (first + dt.timedelta(days=i)).weekday() == 3]
    if len(thu) >= 2 and dd == thu[1]:
        tags.append("만기")
    return tags


def main():
    t0 = time.time()
    if not LOG.exists():
        print("아직 log.csv 없음 — 그림자 데이터가 쌓이면(10-26~) 이 분석이 채워진다. 코드는 준비됨.")
        print("과거 캐시 기준 축 효과는 research/nxt_axis_1026.py 참고(이미 실측).")
        return
    R = pd.DataFrame(list(csv.DictReader(open(LOG, encoding="utf-8"))))
    if not len(R):
        print("log.csv 비어 있음 — 아직 픽 기록 없음."); return
    R["t"] = R.t.astype(str); R["d"] = R.pick_day.astype(str)
    for c in ("r_vwap", "r_ask", "rel"):
        if c in R: R[c] = pd.to_numeric(R[c], errors="coerce")

    import lab
    H = lab.hist()[["ticker", "date", "mcap", "q_mcap", "q_d120", "q_lo250", "q_vol20", "age"]].rename(columns={"ticker": "t", "date": "d"})
    R = R.merge(H, on=["t", "d"], how="left")

    # 공시
    try:
        import event_lab
        D = event_lab.disclosures()
        D = D[D.t.str.contains(BAD, na=False)] if "t" in D.columns else D[D.get("title", pd.Series(dtype=str)).str.contains(BAD, na=False)]
        badset = set(zip(D.stock_code.astype(str), D.rcept_dt.astype(str))) if "stock_code" in D.columns else set()
        cal = sorted(H.d.unique()); prev = dict(zip(cal[1:], cal[:-1]))
        R["bad_disc"] = [(t, d) in badset or (t, prev.get(d)) in badset for t, d in zip(R.t, R.d)]
    except Exception as e:
        print("공시 조인 건너뜀:", e); R["bad_disc"] = False

    R["ev"] = [",".join(event_day(d)) for d in R.d]
    R.to_csv(AXIS, index=False, encoding="utf-8")

    col = "r_vwap" if "r_vwap" in R and R.r_vwap.notna().any() else "r_ask"
    print("# NXT 축 소급 분석 ·", time.strftime("%Y-%m-%d"), "· 수익열", col, "· 픽", len(R))

    def cell(z):
        z = z.dropna(subset=[col])
        return "-" if len(z) < 5 else "%d건·건%+.2f·승%.0f" % (len(z), z[col].mean(), (z[col] > 0).mean() * 100)

    def tert(name, c):
        r = R[c]
        print("| %s | %s | %s | %s |" % (name, cell(R[r <= .3]), cell(R[(r > .3) & (r <= .7)]), cell(R[r > .7])))
    print("| 축 (하위30↔상위30) | 하위30% | 중간 | 상위30% |"); print("|---|---|---|---|")
    tert("시총(작을수록 왼쪽)", "q_mcap"); tert("120일선(아래일수록)", "q_d120")
    tert("52주저점(가까울수록)", "q_lo250"); tert("변동성(낮을수록)", "q_vol20")
    print("| 악재공시 | 있음 %s | 없음 %s |" % (cell(R[R.bad_disc]), cell(R[~R.bad_disc])))
    print("| 신규상장 age<250 | %s | 그외 %s |" % (cell(R[R.age < 250]), cell(R[R.age >= 250])))
    print("| 만기일 | %s | 그외 %s |" % (cell(R[R.ev.str.contains("만기")]), cell(R[~R.ev.str.contains("만기")])))
    print("기준 전체:", cell(R), "· (%.0fs)" % (time.time() - t0))


if __name__ == "__main__":
    main()
