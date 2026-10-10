# -*- coding: utf-8 -*-
"""장 구조 가설 6개 실측 (2026-10-11 사용자 "이것들 실측해봐") — H0315~H0320.

  A 반대매매 예보(H0315)   신용잔고율 높은 종목이 20일 고점 대비 -20%(담보 붕괴 추정일 E) → E+1~3 의 T1·시가→종가
  B NXT 없는 종목(H0316)   T1 을 NXT 거래 종목 / 아닌 종목 · NXT 개장(2025-03-04) 전후로 쪼갬           (토스 통합 일봉 필요)
  C 종가 단일가 쏠림(H0317) 15:19 → 종가(단일가) 등락 ca. ⓐ 어제 단일가에서만 빠진 T1 ⓑ 단일가 매수 → 다음날 시가
  E NXT 장후 그림자(H0319) 토스 통합 종가 - KRX 종가 = NXT 장후 움직임 → 다음날 T1 쪼갬 + 실전 T1(어제 종가=토스) 비교
  F 가짜 갭(H0320)         연말 배당락일 T1 · 무상증자/분할/유상 권리락일 시가→종가(조정주가 기준)
  (D VI 되돌림 H0318 은 research/vi_rebound.py)
잣대: 공장 패널(lab.hist, 시가→종가 비용 0.23%) 학습 2016~22 · 검증 2023~. 1분봉·NXT 쪽은 학습 ~2024 · 검증 2025~.
    python research/micro6.py A C F      (B E 는 nxt_fetch.py 뒤)
"""
import sys, sqlite3, glob
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import numpy as np, pandas as pd
import lab, feats as FT, common as C

BASE = C.BASE
ARGS = set(sys.argv[1:]) or set("ACF")
U = lab.hist().sort_values(["ticker", "date"]).reset_index(drop=True)
U["ret"] = U.oc.astype(float).clip(-60, 60) - FT.COST
U["ret_on"] = U.on.astype(float).clip(-30, 30) - FT.COST
OK = U.oc.notna()
BASEM = U.t1 & OK
TR, VA = lab.TR, lab.VA
M1TR, M1VA = ("20221201", "20241231"), ("20250101", "20991231")
P = pd.read_pickle(C.CACHE / "factory_px.pkl").sort_values(["ticker", "date"]).reset_index(drop=True)


def st(m, a, b, col="ret"):
    T = U.loc[m & (U.date >= a) & (U.date <= b), ["date", col]].rename(columns={col: "ret"})
    return lab.stats(T)


def f(s):
    return ("%5d %+6.2f %4.1f%% t%4.1f %d/%d" % (s["n"], s["mean"], s["win"], s["t"], s["ypos"], s["ny"])) if s else "    0      -"


def row(name, m, per=(TR, VA), col="ret"):
    a, b = st(m, *per[0], col=col), st(m, *per[1], col=col)
    print("%-50s | 학습 %s | 검증 %s" % (name[:50], f(a), f(b)), flush=True)
    return a, b


def onP(col, k):
    """P(전 종목 일봉 길) 기준으로 k 거래일 미룬 값을 U 에 붙인다."""
    s = P.groupby("ticker", sort=False)[col].shift(k)
    m = P[["ticker", "date"]].assign(v=s.values)
    return U[["ticker", "date"]].merge(m, how="left", on=["ticker", "date"]).v.values


# ───────────────────────── A 반대매매 예보 ─────────────────────────
def part_A():
    print("\n==== A 반대매매 예보 — 신용잔고율(KIS, 2008~) · 20일 고점 대비 낙폭 → 담보 붕괴 추정일 E")
    con = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "kis" / "market.db"), uri=True)
    Cr = pd.read_sql("SELECT date, ticker, loan_rmnd_rate AS cr FROM credit WHERE date >= '20090101'", con)
    global P
    P = P.merge(Cr, how="left", on=["ticker", "date"])
    g = P.groupby("ticker", sort=False)
    P["cr2"] = g.cr.shift(2)                                          # 이틀 전 잔고율(발표 늦음 감안)
    P["peak"] = g.close.transform(lambda s: s.shift(1).rolling(20, min_periods=10).max())
    P["dd"] = P.close / P.peak
    P["dd_y"] = g.dd.shift(1)
    print("신용잔고율 분포(값 있는 줄): 중앙 %.2f%% · 상위10%% %.2f%% · 상위3%% %.2f%%" % tuple(P.cr2.quantile([.5, .9, .97])))
    print("시장 대비: 유니버스 아무 종목 시가→종가 학습 %+.2f · 검증 %+.2f" % (st(OK, *TR)["mean"], st(OK, *VA)["mean"]))
    print("기준 T1:", "학습", f(st(BASEM, *TR)), "| 검증", f(st(BASEM, *VA)))
    for crt in (3.0, 5.0, 8.0):
        for ddt in (0.80, 0.75):
            P["E"] = (P.dd <= ddt) & (P.dd_y > ddt) & (P.cr2 >= crt)
            print("\n-- 잔고율 ≥ %.0f%% · 20일 고점 대비 ≤ %d%% 처음 닿은 날 E (전체 %d번)" % (crt, round((ddt - 1) * 100), int(P.E.sum())))
            for k in (1, 2, 3):
                e = onP("E", k).astype(float) == 1
                row("E+%d 유니버스 그 종목 시가→종가" % k, OK & e)
                row("E+%d T1 겹침" % k, BASEM & e)
            ee = np.zeros(len(U), bool)
            for k in (1, 2, 3): ee |= onP("E", k).astype(float) == 1
            row("T1 중 E+1~3 아닌 것(대조)", BASEM & ~ee)
            row("E+2 & 갭 -2% 이하(T1 아니어도) 시가→종가", OK & (onP("E", 2).astype(float) == 1) & (U.gap <= -2))


# ───────────────────────── C 종가 단일가 쏠림 ─────────────────────────
def part_C():
    print("\n==== C 종가 단일가 쏠림 — 1분봉 단면(상위 1,000, 2022-12~) 15:19 가격 → 종가 ca")
    Mp = pd.read_pickle(C.CACHE / "m1_panel_KR.pkl")[["ticker", "date", "c", "p1519", "pc"]]
    Mp["ca"] = (Mp.c / Mp.p1519 - 1) * 100
    Mp["pre"] = (Mp.p1519 / Mp.pc - 1) * 100
    Mp.loc[(Mp.ca.abs() > 15) | (Mp.pre.abs() > 30), ["ca", "pre"]] = np.nan
    global P
    P = P.merge(Mp[["ticker", "date", "ca", "pre"]], how="left", on=["ticker", "date"])
    U["ca"] = onP("ca", 0); U["pre"] = onP("pre", 0)
    U["ca_y"] = onP("ca", 1); U["pre_y"] = onP("pre", 1)
    have = U.ca.notna()
    print("ca 분포(유니버스·값 있는 줄 %d): 1%% %.2f · 10%% %.2f · 중앙 %.2f · 90%% %.2f · 99%% %.2f" %
          ((have.sum(),) + tuple(U.loc[have, "ca"].quantile([.01, .1, .5, .9, .99]))))
    per = (M1TR, M1VA)
    print("\n-- ⓐ 다음날 T1 덧조건 (T1 중 어제 1분봉 있는 것)")
    hy = U.ca_y.notna()
    row("T1 (어제 ca 있음)", BASEM & hy, per)
    for lo, hi in ((-99, -2), (-2, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 99)):
        row("T1 & 어제 단일가 %+.1f < ca ≤ %+.1f" % (lo, hi), BASEM & (U.ca_y > lo) & (U.ca_y <= hi), per)
    row("T1 & 어제 15:19까지 -1%↑ 인데 단일가 ≤ -1", BASEM & (U.pre_y > -1) & (U.ca_y <= -1), per)
    print("\n-- ⓑ 종가 단일가 매수 → 다음날 시가 매도(on, 비용 0.23) — 유니버스·1분봉 있는 날")
    row("아무 종목(ca 있음)", OK & have, per, "ret_on")
    for lo, hi in ((-99, -3), (-3, -2), (-2, -1), (-1, -0.3), (-0.3, 0.3), (0.3, 1), (1, 99)):
        row("단일가 %+.1f < ca ≤ %+.1f" % (lo, hi), have & (U.ca > lo) & (U.ca <= hi), per, "ret_on")
    q = U.q_vmt <= 0.3
    row("조용(오늘 거래량배수 하위30%) & 15:19까지 -1%↑ & ca ≤ -1", q & (U.pre > -1) & (U.ca <= -1), per, "ret_on")
    row("조용 & 15:19까지 -1%↑ & ca ≤ -2", q & (U.pre > -1) & (U.ca <= -2), per, "ret_on")
    row("유동성 아래 1/3 & ca ≤ -1.5", (U.liq <= 1 / 3) & (U.ca <= -1.5), per, "ret_on")
    print("  (on 은 다음날 시가에 판다 — 그 다음날 시가→종가까지 들고 가면:)")
    U["ret_nx"] = onP("oc", -1) if "oc" in P.columns else np.nan
    nxt = U.groupby("ticker", sort=False).ret.shift(-1)
    U["ret_on2"] = U.on.astype(float).clip(-30, 30) + nxt.where(U.groupby("ticker", sort=False).date.shift(-1).notna())
    row("조용 & 15:19까지 -1%↑ & ca ≤ -1 → 다음날 종가", q & (U.pre > -1) & (U.ca <= -1), per, "ret_on2")


# ───────────────────────── F 가짜 갭 ─────────────────────────
def part_F():
    print("\n==== F-1 연말 배당락일(12월 끝에서 둘째 거래일) — 갭에 배당이 섞인 T1")
    days = sorted(P.date.unique())
    exd = {}
    for y in range(2009, 2026):
        dd = [d for d in days if d.startswith("%d12" % y)]
        if len(dd) >= 2: exd[dd[-2]] = y
    con = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "krx_daily.db"), uri=True)
    prev = {d: days[days.index(d) - 1] for d in exd}
    Fd = pd.read_sql("SELECT date, ticker, div, dps FROM fundamental WHERE date IN (%s)" % ",".join("'%s'" % d for d in prev.values()), con)
    inv = {v: k for k, v in prev.items()}
    Fd["date"] = Fd.date.map(inv)
    W = U[["ticker", "date"]].merge(Fd, how="left", on=["ticker", "date"])
    U["dy"] = W["div"].values; U["dps"] = W["dps"].values
    isx = U.date.isin(exd)
    print("배당락일:", ", ".join(sorted(exd)))
    print("배당락일 T1 %d건 (전체 T1 의 %.1f%%)" % ((BASEM & isx).sum(), (BASEM & isx).sum() / BASEM.sum() * 100))
    row("T1 배당락일 아님", BASEM & ~isx)
    row("T1 배당락일 전체", BASEM & isx)
    row("T1 배당락일 & 배당수익률 ≥ 2%", BASEM & isx & (U.dy >= 2))
    row("T1 배당락일 & 0 < 배당수익률 < 2%", BASEM & isx & (U.dy > 0) & (U.dy < 2))
    row("T1 배당락일 & 무배당", BASEM & isx & ~(U.dy > 0))
    U["gapc"] = U.gap + (U.dps / U.px * 100).where(isx & (U.dps > 0), 0).fillna(0)   # 배당만큼 되돌린 갭(연 배당 전체 — 위 한도)
    mg = U[OK].groupby("date").gapc.median()
    U["rgapc"] = U.gapc - U.date.map(mg)
    row("T1 배당락일 & 배당 빼도 시장 대비 -2%p↓", BASEM & isx & (U.rgapc <= -2))
    row("T1 배당락일 & 배당 빼면 T1 아님(가짜 갭)", BASEM & isx & (U.rgapc > -2))
    print("  해마다(배당락일 T1): ", " ".join("%s:%d건 %+.2f" % (y, len(g), g.ret.mean()) for y, g in U[BASEM & isx].groupby(U.date.str[:4])))

    print("\n==== F-2 권리락·분할일(조정주가 vs 원주가 = 시총÷주식수) — 그날 시가→종가")
    fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
    R = pd.concat([pd.read_csv(x, usecols=["date", "ticker", "close", "volume", "marcap", "shares", "open"], dtype={"ticker": str, "date": str})
                   for x in fs if Path(x).stem >= "2010-01"], ignore_index=True)
    R = R[(R.volume > 0) & (R.shares > 0) & (R.marcap > 0)].drop(columns=["close", "open"])
    R = R.merge(P[["ticker", "date", "close"]], on=["ticker", "date"]).sort_values(["ticker", "date"])   # 조정주가 = kr_scan(한 시점 기준)
    R["fac"] = R.close / (R.marcap / R.shares)
    R["jump"] = R.fac / R.groupby("ticker").fac.shift(1)
    R["sh_r"] = R.groupby("ticker").shares.shift(-25) / R.shares          # 신주 상장은 권리락 몇 주 뒤
    ev = R[(R.jump > 1.05) | (R.jump < 0.95)][["ticker", "date", "jump", "sh_r"]].copy()
    dc = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "disclosures.db"), uri=True)
    Ds = pd.read_sql("SELECT stock_code ticker, rcept_dt, report_nm FROM disclosure WHERE report_nm LIKE '%증자결정%' OR report_nm LIKE '%분할결정%' OR report_nm LIKE '%병합결정%'", dc)
    Ds = Ds[~Ds.report_nm.str.contains("자회사|종속회사|정정|철회")]

    def kind(r):
        d0 = (pd.Timestamp(r.date) - pd.Timedelta(days=120)).strftime("%Y%m%d")
        x = Ds[(Ds.ticker == r.ticker) & (Ds.rcept_dt >= d0) & (Ds.rcept_dt <= r.date)].report_nm
        s = " ".join(x)
        if "유무상" in s: return "유무상"
        if "무상증자" in s: return "무상증자"
        if "주식분할" in s: return "액면분할"
        if "유상증자" in s: return "유상증자"
        if "병합" in s: return "병합"
        return "모름"
    ev["kind"] = [kind(r) for r in ev.itertuples()]
    print("조정 사건 %d개:" % len(ev), dict(ev.kind.value_counts()))
    E = ev.merge(P[["ticker", "date", "open", "close"]], on=["ticker", "date"])
    g = P.groupby("ticker", sort=False)
    P["pcl"] = g.close.shift(1); P["nopen"] = g.open.shift(-1); P["nclose"] = g.close.shift(-1)
    E = ev.merge(P[["ticker", "date", "open", "close", "pcl", "nopen", "nclose"]], on=["ticker", "date"])
    E["gap"] = (E.open / E.pcl - 1) * 100; E["oc"] = (E.close / E.open - 1) * 100 - FT.COST
    E["on"] = (E.nopen / E.close - 1) * 100; E["oc2"] = (E.nclose / E.open - 1) * 100 - FT.COST
    E["raw_gap"] = ((1 + E.gap / 100) / E.jump - 1) * 100
    E = E[E.gap.abs() < 30]
    base = U.loc[OK, "ret"].mean()
    print("(대조: 유니버스 아무 종목 시가→종가 평균 %+.2f%%)" % base)
    print("| 종류 | 건수 | 원주가 갭(착시) | 조정 갭 | 시가→종가 | 승률 | 다음날 종가까지 | 2016~22 | 2023~ |")
    for k, x in E.groupby("kind"):
        a = x[x.date <= "20221231"].oc.mean(); b = x[x.date >= "20230101"].oc.mean()
        print("| %s | %d | %+.1f%% | %+.2f%% | %+.2f%% | %.0f%% | %+.2f%% | %+.2f(%d) | %+.2f(%d) |" % (
            k, len(x), x.raw_gap.median(), x.gap.mean(), x.oc.mean(), (x.oc > 0).mean() * 100, x.oc2.mean(),
            a, (x.date <= "20221231").sum(), b, (x.date >= "20230101").sum()))
    fr = E[E.kind == "무상증자"]
    print("무상증자 권리락일 해마다:", " ".join("%s:%d %+.1f" % (y, len(g_), g_.oc.mean()) for y, g_ in fr.groupby(fr.date.str[:4])))
    for lo, hi in ((1.0, 1.5), (1.5, 2.5), (2.5, 99)):
        x = fr[(fr.jump >= lo) & (fr.jump < hi)]
        if len(x): print("  무상 비율(원주가 대비) %.1f~%.1f배: %d건 시가→종가 %+.2f%% 승률 %.0f%% · 다음날까지 %+.2f%%" % (lo, hi, len(x), x.oc.mean(), (x.oc > 0).mean() * 100, x.oc2.mean()))
    x = fr[fr.gap <= -2]
    print("  무상 권리락일 & 조정 갭 -2%%↓: %d건 %+.2f%%" % (len(x), x.oc.mean()))
    x = fr[fr.gap >= 2]
    print("  무상 권리락일 & 조정 갭 +2%%↑: %d건 %+.2f%%" % (len(x), x.oc.mean()))
    print("  착시 쪽: 권리락 전날 종가 매수 → 권리락일 시가 매도(조정 갭 - 비용): 무상 %+.2f%%(승률 %.0f%%) · 유상 %+.2f%% · 모름 %+.2f%%" % (
        fr.gap.mean() - FT.COST, (fr.gap > FT.COST).mean() * 100, E[E.kind == "유상증자"].gap.mean() - FT.COST, E[E.kind == "모름"].gap.mean() - FT.COST))
    print("  무상 해마다 조정 갭:", " ".join("%s:%d %+.1f" % (y, len(g_), g_.gap.mean()) for y, g_ in fr.groupby(fr.date.str[:4])))
    E.to_pickle(C.CACHE / "micro6_rights.pkl")
    tk = U[["ticker", "date"]].merge(E[["ticker", "date", "kind"]], how="left", on=["ticker", "date"]).kind
    print("T1 중 권리락·분할일: %d건" % (BASEM & tk.notna().values).sum())


# ───────────────────────── B·E NXT ─────────────────────────
def part_BE():
    import json
    T = pd.read_pickle(C.CACHE / "toss_daily_kr.pkl")
    nxt = json.loads((C.CACHE / "toss_nxt_kr.json").read_text(encoding="utf-8"))
    vol = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "volume"]]
    vol = vol[vol.date >= "20241101"]
    global P
    X = P[P.date >= "20241101"][["ticker", "date", "open", "close"]].merge(T, on=["ticker", "date"]).merge(vol, on=["ticker", "date"], how="left")
    X["ah"] = (X.tc / X.close - 1) * 100
    X["pm"] = (X.to / X.open - 1) * 100
    X["nx_d"] = X.tv > X.volume * 1.002                                 # 그날 NXT 에서도 거래됨(통합 거래량이 KRX 보다 큼)
    X.loc[X.ah.abs() > 25, "ah"] = np.nan
    pre = X[X.date < "20250304"]
    print("\n==== 토스 통합 일봉 대조: NXT 개장 전 종가 차이 0 비율 %.1f%% (조정 방식 같은지 확인용)" % ((pre.ah.abs() < 0.01).mean() * 100))
    post = X[X.date >= "20250304"]
    print("개장 뒤: NXT 거래된 줄 %.1f%% · 장후 움직임 |ah|≥1%% 인 줄(거래된 것 중) %.1f%%" % (post.nx_d.mean() * 100, (post[post.nx_d].ah.abs() >= 1).mean() * 100))
    P = P.merge(X[["ticker", "date", "ah", "pm", "nx_d", "tc"]], how="left", on=["ticker", "date"])
    U["ah_y"] = onP("ah", 1); U["nx_y"] = onP("nx_d", 1); U["tc_y"] = onP("tc", 1); U["pm"] = onP("pm", 0)
    U["nxt_now"] = U.ticker.map(lambda t: (nxt.get(t) or {}).get("nxt", False))
    per = (("20230101", "20250303"), ("20250304", "20991231"))
    print("\n==== B NXT 거래 종목(지금 토스 기준 %d개) vs 아닌 종목 — 앞: 2023-01~2025-03-03 / 뒤: 2025-03-04~2026-08" % sum(v["nxt"] for v in nxt.values()))
    print("%-50s | %-36s | %s" % ("", "NXT 개장 전", "NXT 개장 뒤"))
    row("T1 전체", BASEM, per)
    row("T1 & NXT 거래 종목", BASEM & U.nxt_now, per)
    row("T1 & NXT 없는 종목", BASEM & ~U.nxt_now, per)
    row("T1 & 어제 NXT 에서 실제 거래됨", BASEM & (U.nx_y == True), per)
    row("T1 & 어제 NXT 거래 없음(개장 뒤)", BASEM & (U.nx_y == False), per)
    print("  분기별(개장 뒤) NXT 있음/없음:")
    Tq = U[BASEM & (U.date >= "20250101")].copy()
    Tq["q"] = Tq.date.str[:4] + "Q" + ((Tq.date.str[4:6].astype(int) - 1) // 3 + 1).astype(str)
    for k, gq in Tq.groupby("q"):
        a, b = gq[gq.nxt_now], gq[~gq.nxt_now]
        print("   %s  있음 %3d건 %+5.2f  · 없음 %3d건 %+5.2f" % (k, len(a), a.ret.mean() if len(a) else np.nan, len(b), b.ret.mean() if len(b) else np.nan))
    print("\n==== E NXT 장후 그림자 — 어제 장후(15:30 뒤) 움직임 ah = 토스 통합 종가 / KRX 종가 (개장 뒤만)")
    pv = (("20250304", "20251231"), ("20260101", "20991231"))
    print("(앞: 2025-03~12 / 뒤: 2026)")
    row("T1 & 어제 NXT 거래", BASEM & (U.nx_y == True), pv)
    for lo, hi in ((-99, -2), (-2, -0.5), (-0.5, 0.5), (0.5, 2), (2, 99)):
        row("T1 & 어제 장후 %+.1f < ah ≤ %+.1f" % (lo, hi), BASEM & (U.nx_y == True) & (U.ah_y > lo) & (U.ah_y <= hi), pv)
    print("\n-- 실전 T1 은 어제 종가를 토스 통합 종가로 쓴다(day_alert prep) → 그 갭으로 다시 고르면")
    # NXT 에서 거래 안 된 날은 토스 종가 = KRX 종가(차이는 kr_scan 이음새·조정 기준 차이뿐이라 지운다) · 장후 10% 넘는 차이도 이음새로 본다
    U.loc[(U.nx_y != True) | (U.ah_y.abs() > 10), "tc_y"] = U.px
    U["gap_l"] = (U.gap / 100 + 1) * U.px / U.tc_y * 100 - 100
    U.loc[U.tc_y.isna() | (U.date < "20250304"), "gap_l"] = np.nan
    w = OK & U.gap_l.notna()
    U["q_gap_l"] = U.gap_l.where(w).groupby(U.date).rank(pct=True)
    U["rgap_l"] = U.gap_l - U.date.map(U[w].groupby("date").gap_l.median())
    t1l = w & (U.q_gap_l <= 0.10) & (U.q_vm <= 0.30) & (U.liq <= 1 / 3) & (U.rgap_l <= -2.0)
    row("연구 T1(KRX 종가 갭)", BASEM & (U.date >= "20250304"), pv)
    row("실전식 T1(토스 통합 종가 갭)", t1l, pv)
    row("둘 다", BASEM & t1l, pv)
    row("연구에만(실전에선 놓침)", BASEM & ~t1l & (U.date >= "20250304"), pv)
    row("실전에만(연구엔 없음)", t1l & ~BASEM, pv)
    print("\n-- NXT 장전(08:00~) 첫 체결 대비 KRX 시가: pm = 토스 통합 시가 / KRX 시가 (T1 중 NXT 거래)")
    for lo, hi in ((-99, -1), (-1, -0.2), (-0.2, 0.2), (0.2, 1), (1, 99)):
        row("T1 & %+.1f < pm ≤ %+.1f" % (lo, hi), BASEM & (U.nx_y == True) & (U.pm > lo) & (U.pm <= hi), pv)


if __name__ == "__main__":
    if "A" in ARGS: part_A()
    if "C" in ARGS: part_C()
    if "F" in ARGS: part_F()
    if "B" in ARGS or "E" in ARGS: part_BE()
