# -*- coding: utf-8 -*-
"""A — '강제로 팔아야 하는 사람이 다 판 뒤' 원리 넓히기 (2026-10-03, 사용자: a b c 다 해줘).
분사주(N8)·자사주 신탁 급락(P8)·S&P 편출(N9)에 이어 국내 사건 넷:
  A1 코스피200·코스닥150 정기변경 편출 — index_members.db 월별 스냅샷 차이 · 효력일 = 6·12월 둘째 목요일(만기일) 다음 거래일
  A2 주주배정·일반공모 유상증자 발행 완료(증권발행결과) — 신주 상장·차익 매도 뒤 (제3자배정은 보호예수라 따로)
  A3 대주주 블록딜(내부자 시간외매매(-)·장외매도(-) · 시총 대비 1%↑ · 같은 날 시간외 매수(+)가 있으면 그룹 내부 이동이라 뺌) — 공시일 기준
  A4 자기주식 처분 결정(물량 부담) 뒤
진입 = 사건일 + k거래일의 다음날 시가 · 보유 H · 판정은 event_lab(같은 날 유니버스 대비 초과·본페로니·학습/검증 절대 중앙).
    python research/forced_sell.py
"""
import sqlite3, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import event_lab as E

P = E.P


def second_thu(y, m):
    d = pd.Timestamp(y, m, 1)
    th = [d + pd.Timedelta(days=i) for i in range(31) if (d + pd.Timedelta(days=i)).month == m and (d + pd.Timedelta(days=i)).weekday() == 3]
    return th[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time(); E.OUT.clear()
    L = E.Lab(); A = L.A
    D = E.disclosures()
    # A1 지수 편출
    c = sqlite3.connect("file:" + str(BASE / "data" / "index_members.db") + "?mode=ro", uri=True)
    M = pd.read_sql("select idx, date, ticker from members where idx in ('1028','2203')", c)
    snaps = sorted(M.date.unique())
    ev1 = []
    for idx, nm in (("1028", "코스피200"), ("2203", "코스닥150")):
        S = {d: set(M[(M.idx == idx) & (M.date == d)].ticker) for d in snaps}
        for a, b in zip(snaps[:-1], snaps[1:]):
            ya, ma = int(a[:4]), int(a[4:6])
            # a 스냅샷과 b 스냅샷 사이에 6·12월 정기변경 효력일이 있으면
            for y, m in ((ya, 6), (ya, 12), (ya + 1, 6)):
                eff = second_thu(y, m) + pd.Timedelta(days=1)
                if pd.Timestamp(a) < eff <= pd.Timestamp(b) + pd.Timedelta(days=1):
                    gone = S[a] - S[b]
                    for t in gone:
                        ev1.append((t, eff.strftime("%Y%m%d"), nm))
    ev1 = sorted(set(ev1))
    P("# A — 강제 매도가 끝난 뒤 · 국내 사건 넷 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- A1 지수 정기변경 편출 %d건(코스피200 %d · 코스닥150 %d · 2018~)" % (len(ev1), sum(1 for x in ev1 if x[2] == "코스피200"), sum(1 for x in ev1 if x[2] == "코스닥150")))
    for nm in ("코스피200", "코스닥150"):
        e = [(t, d) for t, d, n in ev1 if n == nm]
        for k in (0, 5, 10, 21, 40):
            for h in (20, 60, 120):
                L.cell("A1 지수 편출", nm + " 편출", e, k, h)
    # A2 유상증자 발행 완료
    X = D[D.t.str.contains("증권발행결과")]
    for nm, rx in (("주주배정·일반공모 유상증자 완료", r"주주배정|일반공모"), ("제3자배정 유상증자 완료(참고)", r"제3자배정")):
        z = X[X.t.str.contains(rx, regex=True)]
        P("- A2 %s %d건" % (nm, len(z)))
        for k in (5, 10, 21, 40):
            for h in (20, 60):
                L.cell("A2 유상증자 뒤", nm, list(zip(z.stock_code, z.rcept_dt)), k, h)
    # A3 블록딜
    ic = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "insider.db") + "?mode=ro", uri=True)
    I = pd.read_sql("select ticker, rcept_dt, chg_dt, reason_cd, delta, price from tx where kind='보통주' and reason_cd in ('82','12','81','11')", ic)
    buy = set(zip(I[I.reason_cd.isin(["81", "11"])].ticker, I[I.reason_cd.isin(["81", "11"])].chg_dt))
    S3 = I[I.reason_cd.isin(["82", "12"]) & (I.delta < 0)].copy()
    S3["internal"] = [(t, d) in buy for t, d in zip(S3.ticker, S3.chg_dt)]
    S3 = S3[~S3.internal]
    S3["amt"] = -S3.delta * pd.to_numeric(S3.price, errors="coerce")
    S3 = S3.groupby(["ticker", "rcept_dt"]).amt.sum().reset_index()
    mc = dict(zip(A.ticker + "|" + A.date, A.marcap))
    S3["sd"] = [L.shift(d, 0) for d in S3.rcept_dt]
    S3["pct"] = [a / mc.get("%s|%s" % (t, d), np.nan) * 100 if d else np.nan for t, a, d in zip(S3.ticker, S3.amt, S3.sd)]
    for nm, z in (("블록딜(시총 1%↑)", S3[S3.pct >= 1]), ("블록딜(시총 3%↑)", S3[S3.pct >= 3])):
        P("- A3 %s %d건" % (nm, len(z)))
        for k in (0, 5, 10, 21):
            for h in (20, 60):
                L.cell("A3 블록딜 뒤", nm, list(zip(z.ticker, z.rcept_dt)), k, h)
    # A4 자기주식 처분
    z = D[D.t.str.contains("자기주식처분결정") & ~D.t.str.contains("자회사")]
    P("- A4 자기주식 처분 결정 %d건" % len(z)); P("")
    for k in (5, 10, 21, 40):
        for h in (20, 60):
            L.cell("A4 자사주 처분 뒤", "자기주식 처분 결정", list(zip(z.stock_code, z.rcept_dt)), k, h)
    G, zc = L.judge()
    G.to_pickle(ROOT / "cache" / "forced_sell.pkl")
    P("칸 %d개 · 본페로니 t ≥ %.2f · 통과 %d칸 · 근접 %d칸" % (len(G), zc, G["pass"].sum(), G.near.sum())); P("")
    f = lambda v: "%+.2f" % v if v == v else "-"
    for grp, g in G.groupby("group", sort=False):
        P("## %s" % grp); P("")
        P("| 사건 | 진입 | 보유 | 건수(옛·학·검) | 학습 중앙·초과·승률 | 검증 중앙·초과·승률 | t | 양수 해 | 판정 |"); P("|---|---|---|---|---|---|---|---|---|")
        for _, x in g.sort_values(["med2"], ascending=False).head(8).iterrows():
            P("| %s | +%d일 | %d일 | %d·%d·%d | %s · %s · %s | %s · %s · %s | %s | %d/%d | %s |" % (
                x["name"], x.k, x.h, x.n0, x.n1, x.n2, f(x.med1), f(x.ex1), ("%.0f%%" % x.win1) if x.win1 == x.win1 else "-",
                f(x.med2), f(x.ex2), ("%.0f%%" % x.win2) if x.win2 == x.win2 else "-", ("%.1f" % x.t) if x.t == x.t else "-", x.ypos, x.ny,
                "✅ 통과" if x["pass"] else ("△ 근접" if x.near else "")))
        P("")
    P("(%.0f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("forced_sell_%s" % time.strftime("%Y%m%d"), len(G))
    (ROOT / "reports" / ("forced_sell_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(E.OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
