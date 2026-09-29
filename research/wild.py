# -*- coding: utf-8 -*-
"""평소라면 안 할 방법 다섯 (2026-09-30, 사용자 "평소의 너라면 안 했을 방법으로 규칙 찾아봐 · 말도 안 되는 방법").

전부 국내 패널(run_spec.load_market) · 거래대금 상위 40% 유니버스 · 성적 = 같은 날 유니버스 중앙 대비 %p(n20·n40·n60 = 다음날 시가 매수·비용 차감).
구간: 옛날 2005~15 / 학습 2016~22 / 검증 2023~. 각 칸 = 날짜별 중앙의 평균이 아니라 **행 중앙**, 해별 부호도 본다.

  ① 달 — 신월 ±4일 vs 보름 ±4일(Yuan·Zheng·Zhu 2006: 48개국 보름 무렵 수익이 낮다)
  ② 서울 날씨 — 그날 일조시간(달별 평년 대비) 상·하위 1/3 (Hirshleifer·Shumway 2003 햇빛 효과) · open-meteo 기록
  ③ 동그란 가격 — 1천·2천·5천·1만·2만·5만·10만·20만·50만 원을 60일 만에 처음 종가로 넘은 날
  ④ 차트 모양 군집 — 20일 경로(정규화)를 학습 구간에서 k-평균 100묶음 → 학습 성적 상위 묶음이 검증에서도 좋은가
  ⑤ 무작위 규칙 3천 개 난사 — 재료 30여 개의 그날 백분위로 2~3개 조건을 아무렇게나 엮고, 학습 1등들이 검증에서 사나.
     **위약(가짜 재료)** 을 섞는다: 종목코드 끝자리·자릿수 합 홀짝·난수. 위약 규칙이 학습 상위에 오를 정도면 이 방법은 쓰레기다.

    python research/wild.py            # 전부
    python research/wild.py 3 4        # 골라서
"""
import json, math, sys, time, urllib.request, warnings, pickle
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials

CACHE = ROOT / "cache"; OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
PER = [("옛날 05~15", "20050101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231")]


def period(d):
    return np.where(d <= "20151231", 0, np.where(d <= "20221231", 1, 2))


def table(U, mask, title, cols=("ex20", "ex60")):
    """mask 가 참인 행의 같은 날 대비 초과(중앙) — 구간별 + 해별 음수 비율"""
    z = U[mask]
    row = [title, f"{len(z):,}"]
    for c in cols:
        for i, (lab, a, b) in enumerate(PER):
            w = z[z.per == i][c].dropna()
            row.append("%+.2f" % w.median() if len(w) >= 100 else "-")
    ys = z.dropna(subset=[cols[-1]]).groupby(z.date.str[:4])[cols[-1]].median()
    row.append("%d/%d" % ((ys > 0).sum(), len(ys)))
    P("| " + " | ".join(row) + " |")


def head(title, cols=("ex20", "ex60")):
    P(""); P("### " + title); P("")
    hs = ["조건", "행"] + ["%s %s" % (c[2:] + "일", lab.split()[0]) for c in cols for lab, _, _ in PER] + ["%s 양수 해" % (cols[-1][2:] + "일")]
    P("| " + " | ".join(hs) + " |"); P("|" + "---|" * len(hs))


def load():
    A, uni, since = R.load_market("KR")
    A["uni"] = uni.values
    U = A[A.uni].copy()
    for h in (20, 40, 60):
        U["ex%d" % h] = U["n%d" % h] - U.groupby("date")["n%d" % h].transform("median")
    U["per"] = period(U.date.values)
    return A, U


# ① 달 ------------------------------------------------------------------------------------------
def moon(U):
    ref = pd.Timestamp("2000-01-06 18:14", tz="UTC")
    ds = pd.to_datetime(U.date.unique(), format="%Y%m%d").tz_localize("Asia/Seoul") + pd.Timedelta(hours=15, minutes=30)
    age = ((ds.tz_convert("UTC") - ref).total_seconds() / 86400.0) % 29.530588853
    m = dict(zip(U.date.unique(), age))
    U["mage"] = U.date.map(m)
    head("① 달 — 매수 신호일의 달 나이(신월 0 · 보름 14.8)")
    table(U, (U.mage <= 4) | (U.mage >= 25.5), "신월 ±4일")
    table(U, (U.mage >= 10.8) & (U.mage <= 18.8), "보름 ±4일")
    # 시장 전체 타이밍: 유니버스 중앙 n20 (날짜 단위)
    D = U.groupby("date").agg(n20=("n20", "median"), mage=("mage", "first")).reset_index()
    D["per"] = period(D.date.values)
    P(""); P("시장 타이밍(유니버스 중앙 20일 수익, 날짜 단위 · 신월 − 보름 %p):")
    for i, (lab, a, b) in enumerate(PER):
        z = D[D.per == i]
        nm = z[(z.mage <= 4) | (z.mage >= 25.5)].n20.median(); fm = z[(z.mage >= 10.8) & (z.mage <= 18.8)].n20.median()
        P("- %s: 신월 %+.2f · 보름 %+.2f · 차 %+.2f" % (lab, nm, fm, nm - fm))


# ② 날씨 -----------------------------------------------------------------------------------------
def weather(U):
    cp = CACHE / "seoul_weather.pkl"
    if not cp.exists():
        url = ("https://archive-api.open-meteo.com/v1/archive?latitude=37.57&longitude=126.98&start_date=2005-01-01"
               "&end_date=2026-09-28&daily=sunshine_duration,precipitation_sum,cloud_cover_mean&timezone=Asia%2FSeoul")
        j = json.loads(urllib.request.urlopen(url, timeout=120).read().decode())["daily"]
        W = pd.DataFrame({"date": [t.replace("-", "") for t in j["time"]], "sun": j["sunshine_duration"],
                          "rain": j["precipitation_sum"], "cloud": j["cloud_cover_mean"]})
        W.to_pickle(cp)
    W = pd.read_pickle(cp).dropna(subset=["sun"])
    W["m"] = W.date.str[4:6]
    W["sunz"] = W.sun - W.groupby("m").sun.transform("median")          # 달별 평년 대비
    W["q"] = W.groupby("m").sunz.rank(pct=True)
    U["sunq"] = U.date.map(dict(zip(W.date, W.q))); U["rain"] = U.date.map(dict(zip(W.date, W.rain)))
    head("② 서울 날씨 — 신호일의 일조(달별 평년 대비 백분위)")
    table(U, U.sunq >= 2 / 3, "맑은 날(상위 1/3)")
    table(U, U.sunq <= 1 / 3, "흐린 날(하위 1/3)")
    table(U, U.rain >= 10, "비 10mm 이상")
    D = U.groupby("date").agg(n20=("n20", "median"), sunq=("sunq", "first")).reset_index(); D["per"] = period(D.date.values)
    P(""); P("시장 타이밍(유니버스 중앙 20일, 맑음 − 흐림 %p):")
    for i, (lab, a, b) in enumerate(PER):
        z = D[D.per == i]
        P("- %s: %+.2f" % (lab, z[z.sunq >= 2 / 3].n20.median() - z[z.sunq <= 1 / 3].n20.median()))


# ③ 동그란 가격 -----------------------------------------------------------------------------------
def roundnum(A, U):
    LV = np.array([1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000])
    A = A.sort_values(["ticker", "date"])
    pm = A.groupby("ticker").close.transform(lambda s: s.shift(1).rolling(60, min_periods=40).max())
    c = A.close.values; p = pm.values
    hit = np.zeros(len(A), bool); lvl = np.zeros(len(A))
    for L in LV:
        h = (c >= L) & (p < L) & (c < L * 1.1)
        hit |= h; lvl[h] = L
    K = pd.DataFrame({"ticker": A.ticker.values, "date": A.date.values, "rhit": hit, "rlvl": lvl})
    U2 = U.merge(K, on=["ticker", "date"], how="left")
    head("③ 동그란 가격 — 60일 만에 처음 종가로 넘은 날(넘은 폭 10% 이내)")
    table(U2, U2.rhit == True, "아무 동그란 선")
    for grp, lv in (("1천~5천", (1000, 2000, 5000)), ("1만~5만", (10000, 20000, 50000)), ("10만 이상", (100000, 200000, 500000))):
        table(U2, U2.rlvl.isin(lv) & (U2.rhit == True), grp)
    table(U2, (U2.rlvl == 10000) & (U2.rhit == True), "딱 1만 원")


# ④ 차트 모양 군집 ---------------------------------------------------------------------------------
def shapes(A, U):
    A = A.sort_values(["ticker", "date"])
    g = A.groupby("ticker").close
    X = np.column_stack([np.log(g.shift(k) / A.close).values for k in range(1, 20)])
    vr = np.log((A.volume / A.groupby("ticker").volume.transform(lambda s: s.rolling(60, min_periods=40).mean())).clip(lower=1e-3)).values
    F = pd.DataFrame(X, columns=["s%d" % k for k in range(1, 20)]); F["vr"] = vr
    F["ticker"] = A.ticker.values; F["date"] = A.date.values
    U2 = U[["ticker", "date", "ex20", "ex40", "ex60", "per"]].merge(F, on=["ticker", "date"], how="inner").dropna(subset=["s19", "vr"])
    cols = ["s%d" % k for k in range(1, 20)] + ["vr"]
    Z = U2[cols].values.astype(np.float32)
    Z = np.clip(Z, -1.5, 1.5)
    sd = Z[U2.per.values == 1].std(0); Z = Z / sd
    rng = np.random.default_rng(0)
    tr = np.where(U2.per.values == 1)[0]
    S = Z[rng.choice(tr, 200000, replace=False)]
    Kc = 100; C = S[rng.choice(len(S), Kc, replace=False)].copy()
    for it in range(25):
        d = (S ** 2).sum(1)[:, None] - 2 * S @ C.T + (C ** 2).sum(1)[None, :]
        lab = d.argmin(1)
        for k in range(Kc):
            w = S[lab == k]
            if len(w): C[k] = w.mean(0)
    lab = np.empty(len(Z), int)
    for i in range(0, len(Z), 200000):
        z = Z[i:i + 200000]
        lab[i:i + 200000] = ((z ** 2).sum(1)[:, None] - 2 * z @ C.T + (C ** 2).sum(1)[None, :]).argmin(1)
    U2["cl"] = lab
    G = U2.groupby(["cl", "per"]).ex40.agg(["median", "size"]).unstack("per")
    G.columns = ["%s_%d" % c for c in G.columns]
    G = G[G["size_1"] >= 2000].copy()
    rho_tv = G["median_1"].rank().corr(G["median_2"].rank())
    rho_to = G["median_1"].rank().corr(G["median_0"].rank())
    P(""); P("### ④ 차트 모양 군집 — 20일 경로+거래량 k-평균 100묶음(학습에서만 만듦) · 40일 초과(%p)"); P("")
    P("- 묶음 순위 상관(학습 vs 검증) **%.2f** · (학습 vs 옛날) **%.2f** — 0 근처면 모양은 아무것도 예측 못 한다" % (rho_tv, rho_to))
    P(""); P("| 학습 순위 | 묶음 | 옛날 | 학습 | 검증 | 검증 행 | 모양(20일 수익·거래량배) |"); P("|---|---|---|---|---|---|---|")
    G = G.sort_values("median_1", ascending=False)
    for r, (k, x) in enumerate(G.iterrows()):
        if r < 8 or r >= len(G) - 3:
            c = C[k] * sd
            P("| %d | %d | %+.2f | %+.2f | %+.2f | %s | %+.0f%% · %.1f배 |" % (r + 1, k, x.median_0, x.median_1, x.median_2,
                                                                     f"{int(x.size_2):,}", (math.exp(-c[18]) - 1) * 100, math.exp(c[19])))
    top = G.index[:5]; bot = G.index[-5:]
    for lab_, ks in (("학습 상위 5묶음", top), ("학습 하위 5묶음", bot)):
        z = U2[U2.cl.isin(ks)]
        P("- %s: 검증 40일 %+.2f (%s행) · 옛날 %+.2f" % (lab_, z[z.per == 2].ex40.median(), f"{(z.per == 2).sum():,}", z[z.per == 0].ex40.median()))
    pickle.dump({"C": C, "sd": sd, "G": G}, open(CACHE / "wild_shapes.pkl", "wb"))


# ⑤ 무작위 규칙 난사 + 위약 -------------------------------------------------------------------------
def randrules(U, col="ex40", nrule=3000, tag=""):
    FEAT = ["ret3", "ret5", "ret10", "ret20", "ret60", "ret120", "ret250", "fromhi", "fromlo", "dd", "mdd60", "above20",
            "dev25", "vol20", "rng", "clv", "vm1", "vm3", "a40", "a240", "r16", "rw1", "su1", "PBR", "PER", "marcap",
            "sr20", "srd", "dma5", "dma20", "dma60", "dma120"]
    FEAT = [f for f in FEAT if f in U.columns]
    t = U.ticker.astype(str)
    U["pz_last"] = t.str[-2].map(lambda x: int(x) if x.isdigit() else 0).astype(float)     # 끝에서 둘째 자리(끝은 대부분 0)
    U["pz_sum"] = t.map(lambda s: sum(int(ch) for ch in s if ch.isdigit()) % 7).astype(float)
    U["pz_rand"] = np.random.default_rng(1).random(len(U))
    PZ = ["pz_last", "pz_sum", "pz_rand"]
    Q = {}
    for f in FEAT + PZ:
        Q[f] = U.groupby("date")[f].rank(pct=True).values.astype(np.float32)
    ex = U[col].values; per = U.per.values; yr = U.date.str[:4].values
    rng = np.random.default_rng(7)
    allf = FEAT + PZ
    res = []
    for i in range(nrule):
        k = rng.choice([2, 3])
        fs = list(rng.choice(allf, k, replace=False))
        conds = [(f, rng.choice(["<=", ">="]), float(rng.choice([0.1, 0.2, 0.3]))) for f in fs]
        m = np.ones(len(U), bool)
        for f, op, q in conds:
            m &= (Q[f] <= q) if op == "<=" else (Q[f] >= 1 - q)
        out = {"conds": conds, "placebo": any(f in PZ for f, _, _ in conds), "allplacebo": all(f in PZ for f, _, _ in conds)}
        for p_ in (0, 1, 2):
            w = ex[m & (per == p_)]; w = w[~np.isnan(w)]
            out["n%d" % p_] = len(w); out["m%d" % p_] = float(np.median(w)) if len(w) >= 300 else np.nan
        w = m & (per == 1) & ~np.isnan(ex)
        ys = pd.Series(ex[w]).groupby(yr[w]).median() if w.sum() else pd.Series(dtype=float)
        out["ypos"] = int((ys > 0).sum()) if len(ys) else 0
        res.append(out)
    Rz = pd.DataFrame(res)
    Rz.to_pickle(CACHE / ("wild_rand%s.pkl" % tag))
    ok = Rz.dropna(subset=["m1"])
    ok = ok.assign(score=ok.m1)
    P(""); P("### ⑤%s 무작위 규칙 %d개 난사(2~3조건 · 그날 백분위 10/20/30%%) + 위약 재료 · 잣대 %s" % (tag, nrule, "40일 초과(%p)" if col == "ex40" else "40일 **절대** 수익(%)")); P("")
    P("- 학습 표본 300↑ 규칙 %s개 · 그중 위약 섞인 것 %s개(가짜만 %s개)" % (len(ok), ok.placebo.sum(), ok.allplacebo.sum()))
    rho = ok.m1.rank().corr(ok.m2.rank()); rho0 = ok.m1.rank().corr(ok.m0.rank())
    P("- 규칙 순위 상관 학습→검증 **%.2f** · 학습→옛날 **%.2f**" % (rho, rho0))
    for lab_, z in (("진짜 재료만", ok[~ok.placebo]), ("가짜만", ok[ok.allplacebo])):
        if len(z):
            P("- %s %d개: 학습 상위 10%% 가 검증 %+.2f · 하위 10%% 가 검증 %+.2f · 전체 검증 %+.2f" % (
                lab_, len(z), z[z.m1 >= z.m1.quantile(0.9)].m2.median(), z[z.m1 <= z.m1.quantile(0.1)].m2.median(), z.m2.median()))
    pz = ok[ok.allplacebo]
    if len(pz):
        P("- 가짜만 규칙의 학습 성적 범위 %+.2f ~ %+.2f (진짜 규칙 상위 20위 문턱 %+.2f)" % (pz.m1.min(), pz.m1.max(), ok[~ok.placebo].m1.nlargest(20).min()))
    P(""); P("학습 1~20위 (학습 7해 중 양수 해 5↑만):"); P("")
    P("| 순위 | 조건 | 위약 | 옛날 | 학습 | 검증 | 검증 행 | 양수 해 |"); P("|---|---|---|---|---|---|---|---|")
    top = ok[ok.ypos >= 5].sort_values("m1", ascending=False).head(20)
    for r, (_, x) in enumerate(top.iterrows()):
        cs = " & ".join("%s %s%s" % (f, "하위" if op == "<=" else "상위", int(q * 100)) for f, op, q in x.conds)
        P("| %d | %s | %s | %s | %+.2f | %s | %s | %d/7 |" % (r + 1, cs, "●" if x.placebo else "",
                                                          "%+.2f" % x.m0 if x.m0 == x.m0 else "-", x.m1,
                                                          "%+.2f" % x.m2 if x.m2 == x.m2 else "-", f"{int(x.n2):,}", x.ypos))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(argv) or {"1", "2", "3", "4", "5"}
    t0 = time.time()
    A, U = load()
    P("# 말도 안 되는 방법 다섯 · %s" % time.strftime("%Y-%m-%d"))
    P("유니버스 %s행 · 같은 날 유니버스 중앙 대비 초과(%%p, 중앙)" % f"{len(U):,}")
    if "1" in pick: moon(U)
    if "2" in pick: weather(U)
    if "3" in pick: roundnum(A, U)
    if "4" in pick: shapes(A, U)
    if "5" in pick: randrules(U)
    if "6" in pick: randrules(U, col="n40", nrule=5000, tag="b")
    log_trials("wild_%s_%s" % (time.strftime("%Y%m%d"), "".join(sorted(pick))), (3000 if "5" in pick else 0) + (5000 if "6" in pick else 0) + (120 if pick & {"1", "2", "3", "4"} else 0))
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("wild_%s_%s.md" % (time.strftime("%Y%m%d"), "".join(sorted(pick))))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
