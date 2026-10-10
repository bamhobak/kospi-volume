# -*- coding: utf-8 -*-
"""새 가설 14개 중 지금 자료로 되는 것 (2026-10-11 사용자 "이거 할 수 있는 거 해볼래") — H0321~.

  D 지수 편입 소형주 × 미장 하락일 갭     (index_members 2018~ · 전이표 tr_us)
  E 자사주 취득 기간 중 갭 하락           (DART 자사주 취득·신탁 결정 기간)
  F 펀드 청산 꼬리                        (flow11 투신+사모+연기금 3~5일 연속 순매도 뒤)
  K 공개매수 차익                         (DART 공개매수신고서 189건, 대상 종목)
  L 신규 상장 60일 안 갭 하락 데이
  M T1 청산 변형 — 다음날 시가/종가까지 보유 · NXT 장후(토스 통합 종가) 매도
잣대 = 공장 패널(lab.hist) 시가→종가 비용 0.23 · 학습 2016~22 · 검증 2023~ (D·F 는 자료가 2018~·2017~).
    python research/new14.py [D E F K L M]
"""
import sys, re, json, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

BASE = C.BASE
ARGS = set(sys.argv[1:]) or set("DEFKLM")
U = lab.hist().sort_values(["ticker", "date"]).reset_index(drop=True)
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
OK = U.oc.notna()
T1 = U.t1 & OK
TR, VA = lab.TR, lab.VA
P = pd.read_pickle(C.CACHE / "factory_px.pkl").sort_values(["ticker", "date"]).reset_index(drop=True)


def st(m, a, b, col="ret"):
    return lab.stats(U.loc[m & (U.date >= a) & (U.date <= b), ["date", col]].rename(columns={col: "ret"}))


def f(s):
    return ("%5d %+6.2f %4.1f%% t%4.1f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "    0      -"


def row(name, m, per=(TR, VA), col="ret"):
    print("%-48s | 학습 %s | 검증 %s" % (name[:48], f(st(m, *per[0], col=col)), f(st(m, *per[1], col=col))), flush=True)


def ymd(s):
    d = re.findall(r"\d+", str(s))
    return "%04d%02d%02d" % tuple(map(int, d[:3])) if len(d) >= 3 else None


def part_D():
    print("\n==== D 지수 편입 × 미장 하락일 — T1 쪼개기 (2018-02~, 편입 명단 스냅샷 78번)")
    c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "index_members.db"), uri=True)
    M = pd.read_sql("SELECT idx, date, ticker FROM members WHERE idx IN ('1028','2203')", c)   # 코스피200·코스닥150
    snaps = sorted(M.date.unique())
    S = {d: set(M[M.date == d].ticker) for d in snaps}
    sd = np.searchsorted(snaps, U.date.values, side="right") - 1
    U["mem"] = [(i >= 0 and t in S[snaps[i]]) for t, i in zip(U.ticker.values, sd)]
    per = (("20180201", "20221231"), VA)
    usdn = U.tr_us <= -1.0
    row("T1 (2018-02~)", T1, per)
    row("T1 & 코스피200·코스닥150 편입", T1 & U.mem, per)
    row("T1 & 편입 안 됨", T1 & ~U.mem, per)
    row("T1 & 편입 & 짝 미장 -1%↓ 밤", T1 & U.mem & usdn, per)
    row("T1 & 편입 안 됨 & 짝 미장 -1%↓ 밤", T1 & ~U.mem & usdn, per)
    sm = U.mem & (U.liq <= 0.5) & (U.q_gap <= 0.10) & usdn
    row("[풀기] 편입·유동성 아래 절반·갭 하위10%·미장 -1%↓", OK & sm, per)
    row("[풀기] 위 & 시장 대비 -1%p↓", OK & sm & (U.rgap <= -1), per)


def part_E():
    print("\n==== E 자사주 취득(직접·신탁) 기간 중 갭 하락")
    b = pd.read_pickle(C.CACHE / "buyback_kr.pkl")
    cc = json.loads((BASE / "data" / "dart" / "corp_code.json").read_text(encoding="utf-8"))
    c2t = {v["corp_code"]: k for k, v in cc.items()}
    rows = []
    for r in b.itertuples():
        t = c2t.get(r.corp_code)
        if not t: continue
        for a, z in ((r.aqexpd_bgd, r.aqexpd_edd), (r.ctr_pd_bgd, r.ctr_pd_edd)):
            a, z = ymd(a), ymd(z)
            if a and z and a <= z: rows.append((t, a, z))
    B = pd.DataFrame(rows, columns=["ticker", "a", "z"])
    print("기간 %d개 · 종목 %d · %s~%s" % (len(B), B.ticker.nunique(), B.a.min(), B.z.max()))
    inb = np.zeros(len(U), bool)
    idx = U.groupby("ticker").indices
    for r in B.itertuples():
        ii = idx.get(r.ticker)
        if ii is None: continue
        d = U.date.values[ii]
        inb[ii[(d >= r.a) & (d <= r.z)]] = True
    U["bb"] = inb
    per = (("20160101", "20221231"), VA)
    row("T1", T1, per)
    row("T1 & 자사주 취득 기간 중", T1 & U.bb, per)
    row("T1 & 기간 아님", T1 & ~U.bb, per)
    g = OK & U.bb & (U.q_gap <= 0.10) & (U.rgap <= -2)
    row("[풀기] 기간 중 · 갭 하위10% · 시장 대비 -2%p↓", g, per)
    row("[풀기] 위 & 유동성 아래 절반", g & (U.liq <= 0.5), per)
    row("[풀기] 기간 중 · 갭 -3%↓ (아무 크기)", OK & U.bb & (U.gap <= -3), per)
    row("[대조] 기간 아님 · 갭 -3%↓", OK & ~U.bb & (U.gap <= -3), per)


def part_F():
    print("\n==== F 펀드 청산 꼬리 — 투신+사모+연기금 순매도 연속(어제까지) 뒤 (flow11 2017~)")
    c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "investor.db"), uri=True)
    Fl = pd.read_sql("SELECT ticker, date, COALESCE(tru,0)+COALESCE(pef,0)+COALESCE(pens,0) AS fund, COALESCE(tru,0) AS tru FROM flow11 WHERE date >= '20170101'", c)
    Fl = Fl.sort_values(["ticker", "date"])
    for col in ("fund", "tru"):
        neg = (Fl[col] < 0).astype(int)
        grp = (neg != neg.groupby(Fl.ticker).shift()).cumsum()
        Fl[col + "_run"] = neg.groupby([Fl.ticker, grp]).cumsum() * neg
        Fl[col + "_run_y"] = Fl.groupby("ticker")[col + "_run"].shift(1)       # 어제까지 연속
    W = U[["ticker", "date"]].merge(Fl[["ticker", "date", "fund_run_y", "tru_run_y"]], how="left", on=["ticker", "date"])
    U["frun"] = W.fund_run_y.values; U["trun"] = W.tru_run_y.values
    per = (("20170101", "20221231"), VA)
    h = U.frun.notna()
    row("T1 (수급 있음)", T1 & h, per)
    for lo, hi in ((0, 0), (1, 2), (3, 4), (5, 99)):
        row("T1 & 투신+사모+연기금 %d~%d일 연속 순매도 뒤" % (lo, hi), T1 & (U.frun >= lo) & (U.frun <= hi), per)
    row("T1 & 투신만 3일↑ 연속 순매도 뒤", T1 & (U.trun >= 3), per)
    g = OK & (U.frun >= 3) & (U.q_gap <= 0.10) & (U.rgap <= -2)
    row("[풀기] 3일↑ 연속 순매도 · 갭 하위10% · 시장 대비 -2%p↓", g, per)
    row("[풀기] 위 & 거래량 하위 30%", g & (U.q_vm <= 0.3), per)


def part_K():
    print("\n==== K 공개매수 — 대상 종목, 첫 신고서 접수일 D 기준 (DART 2005~)")
    c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "disclosures.db"), uri=True)
    K = pd.read_sql("SELECT stock_code ticker, corp_name, flr_nm, rcept_dt d, report_nm FROM disclosure WHERE report_nm LIKE '%공개매수신고서%'", c)
    K = K[~K.report_nm.str.contains("정정") & K.ticker.str.len().eq(6)].sort_values("d").drop_duplicates("ticker", keep="first")
    K = K[K.corp_name != K.flr_nm]                                  # 자기 회사 공개매수(자사주)는 따로 — 남 회사 인수만
    g = P.groupby("ticker", sort=False)
    rows = []
    for r in K.itertuples():
        x = P[P.ticker == r.ticker]
        if not len(x): continue
        dd = x.date.values
        i = np.searchsorted(dd, r.d)                                 # 접수일(장중·장후 접수 섞임) 당일 또는 다음 거래일
        if i + 21 >= len(dd) or i < 1: continue
        o, cl = x.open.values, x.close.values
        rows.append(dict(t=r.ticker, d=r.d, name=r.corp_name, pre=(cl[i - 1] / cl[max(i - 6, 0)] - 1) * 100,
                         d0=(cl[i] / cl[i - 1] - 1) * 100, j1=(o[i + 1] / cl[i] - 1) * 100,
                         h1=(cl[i + 20] / o[i + 1] - 1) * 100 - FT.COST, h2=(cl[i + 20] / cl[i + 1] - 1) * 100 - FT.COST,
                         h3=(cl[i + 10] / cl[i + 1] - 1) * 100 - FT.COST))
    R = pd.DataFrame(rows)
    print("대상 %d건 (%s~%s)" % (len(R), R.d.min(), R.d.max()))
    print("| 구간 | 평균 | 중앙 | 승률 |")
    for k, nm in (("pre", "접수 전 5일"), ("d0", "접수일 등락"), ("j1", "다음날 시가 갭"), ("h1", "다음날 시가 매수 → 20일 뒤 종가"),
                  ("h2", "다음날 종가 매수 → 20일 뒤 종가"), ("h3", "다음날 종가 매수 → 10일 뒤 종가")):
        print("| %s | %+.2f%% | %+.2f%% | %.0f%% |" % (nm, R[k].mean(), R[k].median(), (R[k] > 0).mean() * 100))
    for a, b in (("20050101", "20151231"), ("20160101", "20221231"), ("20230101", "20991231")):
        x = R[(R.d >= a) & (R.d <= b)]
        if len(x): print("  %s~%s %d건: 다음날 종가 → 20일 %+.2f%%(중앙 %+.2f, 승률 %.0f%%)" % (a[:4], b[:4], len(x), x.h2.mean(), x.h2.median(), (x.h2 > 0).mean() * 100))
    R.to_pickle(C.CACHE / "new14_tender.pkl")


def part_L():
    print("\n==== L 신규 상장 60거래일 안 갭 하락 데이 (age = 상장 뒤 거래일 수, 유니버스 진입은 20일 거래대금 필요해 15일~)")
    per = (TR, VA)
    new = U.age <= 60
    row("T1 & 상장 60일 안", T1 & new, per)
    row("T1 & 그 밖", T1 & ~new, per)
    for g in (-3, -5):
        row("[풀기] 상장 60일 안 · 갭 %d%%↓" % g, OK & new & (U.gap <= g), per)
        row("[풀기] 상장 60일 안 · 갭 %d%%↓ · 시장 대비 -2%%p↓ · 거래량 하위30%%" % g, OK & new & (U.gap <= g) & (U.rgap <= -2) & (U.q_vm <= 0.3), per)
    row("[풀기] 상장 60일 안 · 갭 하위10% · 시장 대비 -2%p↓", OK & new & (U.q_gap <= 0.1) & (U.rgap <= -2), per)
    row("[대조] 상장 120일↑ · 갭 하위10% · 시장 대비 -2%p↓", OK & (U.age > 120) & (U.q_gap <= 0.1) & (U.rgap <= -2), per)


def part_M():
    print("\n==== M T1 청산 변형 — 시가 매수 뒤 언제 파나")
    g = P.groupby("ticker", sort=False)
    P["no"] = g.open.shift(-1); P["nc"] = g.close.shift(-1)
    W = U[["ticker", "date"]].merge(P[["ticker", "date", "open", "close", "no", "nc"]], how="left", on=["ticker", "date"])
    o, cl, no, nc = W.open.values, W.close.values, W.no.values, W.nc.values
    U["r_no"] = np.clip((no / o - 1) * 100, -60, 60) - FT.COST
    U["r_nc"] = np.clip((nc / o - 1) * 100, -60, 60) - FT.COST
    U["r_on"] = np.clip((no / cl - 1) * 100, -30, 30)
    row("T1 시가 → 그날 종가(지금)", T1)
    row("T1 시가 → 다음날 시가", T1 & U.r_no.notna(), col="r_no")
    row("T1 시가 → 다음날 종가", T1 & U.r_nc.notna(), col="r_nc")
    row("T1 종가 → 다음날 시가(덧붙는 부분만, 비용 없이)", T1 & U.r_on.notna(), col="r_on")
    T3 = T1 & (U.tr_pred <= -0.5)
    row("T3(T1 & 짝 미장 예상 갭 ≤ -0.5) 시가 → 종가", T3)
    row("T3 시가 → 다음날 시가", T3 & U.r_no.notna(), col="r_no")
    row("T3 시가 → 다음날 종가", T3 & U.r_nc.notna(), col="r_nc")
    up = U.oc >= 2
    row("T1 & 그날 +2%↑ 마감 → 종가 대신 다음날 시가", T1 & up & U.r_no.notna(), col="r_no")
    row("T1 & 그날 +2%↑ 마감 → 그날 종가(비교)", T1 & up)
    row("T1 & 그날 0%↓ 마감 → 다음날 시가", T1 & (U.oc <= 0) & U.r_no.notna(), col="r_no")
    row("T1 & 그날 0%↓ 마감 → 그날 종가(비교)", T1 & (U.oc <= 0))
    try:
        T = pd.read_pickle(C.CACHE / "toss_daily_kr.pkl")
        X = U[["ticker", "date"]].merge(T[["ticker", "date", "tc"]], how="left", on=["ticker", "date"])
        U["r_ah"] = np.clip((X.tc.values / o - 1) * 100, -60, 60) - FT.COST
        nx = (np.abs(X.tc.values / cl - 1) > 0.0001) & (np.abs(X.tc.values / cl - 1) < 0.10) & (U.date >= "20250304").values
        per = (("20250304", "20251231"), ("20260101", "20991231"))
        print("  NXT 장후 매도(토스 통합 종가 ≈ 20:00 마지막 체결) — NXT 에서 장후 거래 있었던 T1 만, 앞 2025-03~12 / 뒤 2026")
        row("  같은 줄: KRX 종가 매도", T1 & nx, per)
        row("  같은 줄: NXT 장후 마지막 가격 매도", T1 & nx, per, col="r_ah")
    except Exception as ex:
        print("NXT 부분 건너뜀:", ex)


if __name__ == "__main__":
    for k, fn in (("D", part_D), ("E", part_E), ("F", part_F), ("K", part_K), ("L", part_L), ("M", part_M)):
        if k in ARGS:
            try: fn()
            except Exception as ex:
                import traceback; traceback.print_exc()
