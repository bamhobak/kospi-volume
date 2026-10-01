# -*- coding: utf-8 -*-
"""후보 3개 정밀 검증·조정 (2026-10-02 사용자: "테스트 데이터 정확한 건지 상세하게 보고 조정할 부분 있는지도 같이 다시 돌려봐").

A 자사주 신탁계약 + 20일 낙폭 (H0271)
  ① 데이터: 표본 거래 원가격 대조 · 회사코드→종목코드 · 정정 중복 · 가격 점프(감자 등)로 부푼 수익
  ② 쏠림: 상위 5% 비중 · 2020 빼고 · 해별
  ③ 조정 격자: 낙폭 문턱(-5/-10/-15/-20) × 계약 규모(전부/1%↑) × 보유(10/20/40/60) × 진입(다음날 시가/2일 뒤)
B S&P 500 편출 (H0263)
  ① 데이터: 이름만 바뀐 경우(같은 날 다른 티커로 다시 편입) 제외 · 알려진 편출 표본 대조 · 수익 극단값
  ② 조정 격자: 진입 +15/+21/+30 × 보유 20/40/60/120 · 편출 전 60일 낙폭으로 나누기
C 신호 몰린 날 120일 보유 (H0268)
  ① 데이터: 120일 수익 극단값(가격 점프) · 기간 맞추기(하루당 수익)
  ② '몰린 날만' 인가: 몰림 문턱(3/4/6/8개) × 보유(원래/60/120/250) × 평범한 날과의 차이 · 2008·2020 빼고

    python research/verify3.py A B C
"""
import sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
f2 = lambda v: "%+.2f" % v if v == v else "-"


def stats(r):
    r = pd.Series(r).dropna()
    if len(r) == 0:
        return dict(n=0, mean=np.nan, med=np.nan, win=np.nan, trim=np.nan, top5=np.nan)
    s = r.sort_values(ascending=False)
    k = max(1, int(len(s) * 0.05))
    return dict(n=len(r), mean=r.mean(), med=r.median(), win=(r > 0).mean() * 100,
                trim=r[r <= r.quantile(0.95)].mean(), top5=s.head(k).sum() / s.sum() * 100 if s.sum() > 0 else np.nan)


# ────────────────────────────────────────────── A
def part_a():
    import event_lab as E
    L = E.Lab()
    A = L.A
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    cm = pd.read_sql("select corp_code, stock_code, count(*) n from disclosure where stock_code!='' group by corp_code, stock_code", c)
    multi = cm.groupby("corp_code").stock_code.nunique()
    cmap = cm.sort_values("n").groupby("corp_code").stock_code.last().to_dict()
    B = pd.read_pickle(ROOT / "cache" / "buyback_kr.pkl").dropna(subset=["rcept_no"])
    B = B[B._api == "tsstkAqTrctrCnsDecsn"].copy()
    B["date"] = B.rcept_no.str[:8]; B["ticker"] = B.corp_code.map(cmap)
    num = lambda s: pd.to_numeric(str(s).replace(",", ""), errors="coerce")
    B["amt"] = B.ctr_prc.map(num)
    P("## A 자사주 신탁계약 + 낙폭"); P("")
    P("### ① 데이터 점검"); P("")
    P("- 신탁계약 체결 결정 %s건 · 회사코드가 종목코드 둘 이상에 걸린 회사 %d곳(가장 많이 쓰인 코드로 맞춤) · 종목코드 못 찾음 %d건" % (
        f"{len(B):,}", int((multi.reindex(B.corp_code.unique()) > 1).sum()), int(B.ticker.isna().sum())))
    dup = B.duplicated(["ticker", "date"]).sum()
    P("- 같은 종목·같은 날 중복 %d건(정정 등) → 보유 중 재신호 무시로 한 번만 센다" % dup)
    B = B.dropna(subset=["ticker"]).drop_duplicates(["ticker", "date"])
    mc = dict(zip(A.ticker + "|" + A.date, A.marcap)); r20 = dict(zip(A.ticker + "|" + A.date, A.ret20))
    B["sd"] = [L.shift(d, 0) for d in B.date]
    B["r20"] = [r20.get("%s|%s" % (t, d)) for t, d in zip(B.ticker, B.sd)]
    B["size"] = B.amt / pd.Series([mc.get("%s|%s" % (t, d)) for t, d in zip(B.ticker, B.sd)], index=B.index) * 100
    # 기준 칸 거래 표 + 가격 점프 점검
    z = B[B.r20 <= -10]
    L.cell("A", "기준", list(zip(z.ticker, z.date)), 0, 20)
    Y = L.cells[-1]["Y"].copy()
    g = A.groupby("ticker", sort=False).close
    A["_jump"] = (A.close / g.shift(1) - 1).abs()
    jmax = A.groupby("ticker")._jump.rolling(25).max().reset_index(level=0, drop=True)
    A["_jfwd"] = jmax.groupby(A.ticker).shift(-21)
    jf = dict(zip(A.ticker + "|" + A.date, A._jfwd))
    Y["jump"] = [jf.get("%s|%s" % (t, d)) for t, d in zip(Y.ticker, Y.date)]
    bad = Y[Y.jump > 0.31]
    P("- 기준 칸(20일 -10%%·다음날 시가·20일) 거래 %d건 · 보유 중 하루 ±31%% 넘는 가격 점프(상한가 30%% 초과 = 감자·병합 의심) %d건 → 빼도 중앙 %s → %s" % (
        len(Y), len(bad), f2(Y.r.median()), f2(Y[~Y.index.isin(bad.index)].r.median())))
    smp = Y.sample(5, random_state=3)
    P(""); P("표본 5건 원가격 대조(신호일 다음날 시가 → 20거래일 뒤 종가, 비용 차감):"); P("")
    P("| 신호일 | 종목 | 다음날 시가 | 20일 뒤 종가 | 계산 수익 | 표의 수익 |"); P("|---|---|---|---|---|---|")
    for _, x in smp.iterrows():
        ix = L.pos[x.ticker + "|" + x.date]
        rows = A.iloc[ix:ix + 21]
        if rows.ticker.nunique() != 1 or len(rows) < 21:
            continue
        o = A.buy.values[ix]; cl = A.close.values[ix + 20]; cost = A.cost.values[ix]
        P("| %s | %s | %s | %s | %+.2f%% | %+.2f%% |" % (x.date, x.ticker, f"{o:,.0f}", f"{cl:,.0f}", (cl / o - 1) * 100 - cost, x.r))
    P(""); P("### ② 쏠림"); P("")
    s = stats(Y.r); s0 = stats(Y[~Y.date.str.startswith("2020")].r)
    P("- 전체 중앙 %s · 평균 %s · 상위5%% 뺀 평균 %s · 상위 5%%가 수익의 %.0f%% · **2020 빼면** 중앙 %s · 평균 %s · 승률 %.0f%% (%d건)" % (
        f2(s["med"]), f2(s["mean"]), f2(s["trim"]), s["top5"], f2(s0["med"]), f2(s0["mean"]), s0["win"], s0["n"]))
    P(""); P("### ③ 조정 격자 (2016~ · 학습 / 검증 중앙 · 승률 · 2020 뺀 중앙)"); P("")
    P("| 낙폭 | 규모 | 진입 | 보유 | 건수 학·검 | 학습 중앙·승률 | 검증 중앙·승률 | 2020 뺀 중앙 | 같은 날 대비 초과(검증) |"); P("|---|---|---|---|---|---|---|---|---|")
    for th in (-5, -10, -15, -20):
        for sz, szl in ((0, "전부"), (1, "1%↑")):
            zz = B[(B.r20 <= th) & ((B["size"] >= sz) if sz else True)]
            for k in (0, 2):
                for h in (10, 20, 40, 60):
                    L.cell("A", "x", list(zip(zz.ticker, zz.date)), k, h)
                    Yx = L.cells[-1]["Y"]
                    tr = Yx[(Yx.date >= "20160101") & (Yx.date <= "20221231")]; va = Yx[Yx.date >= "20230101"]
                    no20 = Yx[(Yx.date >= "20160101") & ~Yx.date.str.startswith("2020")]
                    P("| %d%% | %s | %s | %d일 | %d·%d | %s · %.0f%% | %s · %.0f%% | %s | %s |" % (
                        th, szl, "다음날" if k == 0 else "2일 뒤", h, len(tr), len(va), f2(tr.r.median()), (tr.r > 0).mean() * 100 if len(tr) else 0,
                        f2(va.r.median()), (va.r > 0).mean() * 100 if len(va) else 0, f2(no20.r.median()), f2(va.ex.median())))


# ────────────────────────────────────────────── B
def part_b():
    K = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")[["ticker", "date", "px", "buy", "cost", "amt20", "rawclose"]]
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    g = K.groupby("ticker", sort=False).px
    for h in (20, 40, 60, 120):
        K["n%d" % h] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
    K["dd60"] = (K.px / g.transform(lambda s: s.rolling(60, min_periods=40).max()) - 1) * 100
    cal = np.array(sorted(K.date.unique()))
    q = K.groupby("date").amt20.rank(pct=True); uni = (q >= 0.6) & (K.rawclose >= 3)
    bench = {h: K[uni].dropna(subset=["n%d" % h]).groupby("date")["n%d" % h].median() for h in (20, 40, 60, 120)}
    pos = {k: i for i, k in enumerate(K.ticker + "|" + K.date)}
    dates_of = K.groupby("ticker").date.apply(np.array)
    T = pd.read_csv(BASE / "data" / "us" / "sp500" / "ticker_start_end.csv", dtype=str)
    T["s"] = T.start_date.str.replace("-", ""); T["e"] = T.end_date.fillna("").str.replace("-", "")
    starts = T.groupby("s").ticker.apply(set).to_dict()
    D = T[(T.e >= "20080101") & (T.e != "")]
    P("## B S&P 500 편출"); P("")
    ev, rename, gone = [], 0, 0
    for t, e in zip(D.ticker, D.e):
        tt = t if t in dates_of.index else t.replace(".", "-")
        if tt not in dates_of.index:
            gone += 1; continue
        ds = dates_of[tt]
        if (ds > e).sum() < 30:
            gone += 1; continue
        # 이름만 바뀐 경우: 같은 날(±3일) 편입된 티커의 가격이 이 티커와 같다
        same = False
        for dd in pd.date_range(pd.Timestamp(e) - pd.Timedelta(days=3), pd.Timestamp(e) + pd.Timedelta(days=3)).strftime("%Y%m%d"):
            for nt in starts.get(dd, ()):
                i1, i2 = pos.get(tt + "|" + e), None
                for d2 in cal[np.searchsorted(cal, e):np.searchsorted(cal, e) + 3]:
                    i2 = pos.get(nt + "|" + d2) or i2
                if i1 is not None and i2 is not None and abs(K.px.values[i1] / K.px.values[i2] - 1) < 0.02:
                    same = True
        if same:
            rename += 1; continue
        ev.append((tt, e))
    P("### ① 데이터 점검"); P("")
    P("- 2008~ 편출 %d건 → 편출 뒤 30거래일 못 채움(인수·합병·폐지) %d건 · **이름·티커만 바뀌어 사실상 남은 것 %d건 제외** → %d건" % (len(D), gone, rename, len(ev)))
    kn = [("AAL", "20240923"), ("ETSY", "20230918"), ("LNC", "20230918"), ("MRO", "20241122")]
    P("- 알려진 편출과 대조: " + " · ".join("%s %s %s" % (t, d, "✓" if (t, d) in set(ev) else "✗(목록: %s)" % ",".join(x[1] for x in ev if x[0] == t)) for t, d in kn))
    rows = []
    for k in (15, 21, 30):
        for h in (20, 40, 60, 120):
            for t, e in ev:
                i = np.searchsorted(cal, e, "left") + k
                if i >= len(cal):
                    continue
                ix = pos.get(t + "|" + cal[i])
                if ix is None:
                    continue
                r = K["n%d" % h].values[ix]
                if r == r:
                    rows.append((k, h, cal[i], t, r, r - bench[h].get(cal[i], np.nan), K.dd60.values[pos.get(t + "|" + e, ix)]))
    R = pd.DataFrame(rows, columns=["k", "h", "date", "ticker", "r", "ex", "dd"])
    base = R[(R.k == 21) & (R.h == 40)]
    P("- 기준(+21일·40일) 수익 극단값: 최대 %s · 최소 %s · 상위 5%%가 수익의 %.0f%%" % (f2(base.r.max()), f2(base.r.min()), stats(base.r)["top5"]))
    P(""); P("### ② 조정 격자 (옛날 08~15 / 학습 16~22 / 검증 23~ — 중앙 · 승률)"); P("")
    P("| 진입 | 보유 | 건수 | 옛날 | 학습 | 검증 | 같은 날 대비 초과 중앙(전체) | 양수 해 |"); P("|---|---|---|---|---|---|---|---|")
    for (k, h), z in R.groupby(["k", "h"]):
        cell = []
        for a, b in (("20080101", "20151231"), ("20160101", "20221231"), ("20230101", "20991231")):
            w = z[(z.date >= a) & (z.date <= b)]
            cell.append("%s · %.0f%%" % (f2(w.r.median()), (w.r > 0).mean() * 100) if len(w) >= 8 else "-")
        ys = z.groupby(z.date.str[:4]).r.mean()
        P("| +%d일 | %d일 | %d | %s | %s | %s | %s | %d/%d |" % (k, h, len(z), cell[0], cell[1], cell[2], f2(z.ex.median()), (ys > 0).sum(), len(ys)))
    P(""); P("편출 전 60일 고점 대비 낙폭으로 나누기 (+21일·40일):"); P("")
    z = base.copy(); z["grp"] = pd.cut(z.dd, [-100, -30, -15, 0.1], labels=["-30% 이하", "-15~-30%", "-15% 위"])
    P("| 편출 전 낙폭 | 건수 | 중앙 | 승률 | 평균 |"); P("|---|---|---|---|---|")
    for gname, w in z.groupby("grp"):
        P("| %s | %d | %s | %.0f%% | %s |" % (gname, len(w), f2(w.r.median()), (w.r > 0).mean() * 100 if len(w) else 0, f2(w.r.mean())))


# ────────────────────────────────────────────── C
def part_c():
    import rule_scan as RS
    S = RS.kr_signals()[["date", "ticker", "rid", "r"]]
    sys.stdout = sys.__stdout__; sys.stdout.reconfigure(encoding="utf-8")
    K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "close", "buy", "cost"]].sort_values(["ticker", "date"])
    g = K.groupby("ticker", sort=False).close
    for h in (60, 120, 250):
        K["n%d" % h] = (g.shift(-h) / K.buy - 1) * 100 - K.cost
    K["_j"] = (K.close / g.shift(1) - 1).abs()
    K["jf"] = K.groupby("ticker", sort=False)._j.transform(lambda s: s[::-1].rolling(121, min_periods=1).max()[::-1].shift(-1))
    S = S.merge(K[["ticker", "date", "n60", "n120", "n250", "jf"]], on=["ticker", "date"], how="left")
    S["crowd"] = S.groupby("date").ticker.transform("size")
    P("## C 신호 몰린 날 120일 보유"); P("")
    P("### ① 데이터 점검"); P("")
    j = S[S.jf > 0.31]
    P("- 120일 보유 중 하루 ±31%%↑ 가격 점프(감자·병합 의심) 신호 %d건 / %d — 빼고 다시 잰다" % (len(j), len(S)))
    S = S[~(S.jf > 0.31)]
    P("- 120일 수익 상위 5개: " + " · ".join("%s %s %+.0f%%" % (r.date, r.ticker, r.n120) for r in S.nlargest(5, "n120").itertuples()))
    P(""); P("### ② 몰림 문턱별 — 원래 청산 vs 고정 보유 (평균 / 중앙, 끝난 거래만) · 하루당 = 수익 ÷ 보유일"); P("")
    P("| 묶음 | 신호 | 원래 청산 | 60일 | 120일 | 250일 | 120일 − 원래(중앙 차) | 120일이 나은 해 |"); P("|---|---|---|---|---|---|---|---|")
    for th in (3, 4, 6, 8):
        for lab, m in (("몰린 날(%d개↑)" % th, S.crowd >= th), ("평범한 날(%d개 미만)" % th, S.crowd < th)):
            z = S[m].dropna(subset=["n120"])
            if len(z) < 30:
                continue
            ys = z.groupby(z.date.str[:4]).apply(lambda w: w.n120.median() > w.r.median())
            P("| %s | %d | %s / %s | %s / %s | %s / %s | %s / %s | %s | %d/%d |" % (
                lab, len(z), f2(z.r.mean()), f2(z.r.median()), f2(z.n60.mean()), f2(z.n60.median()), f2(z.n120.mean()), f2(z.n120.median()),
                f2(z.n250.mean()), f2(z.n250.median()), f2(z.n120.median() - z.r.median()), ys.sum(), len(ys)))
    P(""); P("2008·2020 빼고(몰림 4개↑):"); P("")
    z = S[(S.crowd >= 4) & ~S.date.str[:4].isin(["2008", "2020"])].dropna(subset=["n120"])
    w = S[(S.crowd < 4) & ~S.date.str[:4].isin(["2008", "2020"])].dropna(subset=["n120"])
    for lab, x in (("몰린 날", z), ("평범한 날", w)):
        P("- %s %d건: 원래 청산 중앙 %s · 120일 중앙 %s · 차 %s · 승률 %.0f%% → %.0f%%" % (
            lab, len(x), f2(x.r.median()), f2(x.n120.median()), f2(x.n120.median() - x.r.median()), (x.r > 0).mean() * 100, (x.n120 > 0).mean() * 100))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(argv) or {"A", "B", "C"}
    P("# 후보 3개 정밀 검증·조정 · %s" % time.strftime("%Y-%m-%d")); P("")
    if "A" in pick: part_a()
    if "B" in pick: P(""); part_b()
    if "C" in pick: P(""); part_c()
    (ROOT / "reports" / ("verify3_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
