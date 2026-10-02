# -*- coding: utf-8 -*-
"""약한 규칙 셋 조이기 — 기각된 기법을 전부 거르개로 (2026-10-02 사용자: "셋 다 조일 수 있는지 다시 해봐, 실패한 매매법들 다 조합해서").

대상: [조용한 신고가] P1(국장·실제 청산) · [상승장 신고가] N1(미장 · 지금 규칙 = 거래 주식 수 상위 20% 포함 · 40일) · [잔잔한 급등주] N5(미장 · 60일)
재료(신호일 종가까지 아는 값, 기각 기법 총동원):
  · 되밀림·되오름(retrace_grid): L=20·40·60·120 상승폭·반납 비율 / 하락폭·회복 비율
  · us_filter 9종: 벨레즈 음봉 연속(고가 낮아짐) · 기간조정(저점 상승·하락일 거래량<상승일) · 다진 자리(40일 최저/120일 최고)
    · 팔리 밀집(5·10일선 간격·몸통·거래량) · 와조스키 눌림(5일선 아래·120일선 위·거래량 감소) · 바닥 확인 캔들(종가>전일고가·아래꼬리)
    · 조용함(20일 변동성)
  · 보조지표: RSI14 · RSI2 · 볼린저 %B · 윌리엄스 %R · 20·60일선 이격 · 5·10일 수익
  · 국장만: 네이버 관심도(att·att7) · 서울 일조(위약) · 최근 60일 공시 수(IR·공급계약·자사주 취득·유상증자·CB)
  · 위약: 달(신월 ±7일) · 동전
판정: tighten2.scan 과 같다 — 학습(16~22)·검증(23~) 둘 다 중앙·승률↑ & 무작위 대비 z≥1.5, 재료마다 가장 센 칸 하나, 상위끼리 두 개 조합.
    python research/tighten3.py P1 N1 N5
"""
import io, sqlite3, sys, time, warnings, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import tighten2 as T2

P = T2.P


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def ohlc_feats(D):
    """D: ticker·date·o·h·l·c·v (종목·날짜 정렬) → 기각 기법 재료 열 붙인 D"""
    g = D.groupby("ticker", sort=False)
    c, o, h, l, v = D.c, D.o, D.h, D.l, D.v
    pc = g.c.shift(1); ph = g.h.shift(1)
    R = lambda s, n, f: g[s].transform(lambda z: getattr(z.rolling(n, min_periods=max(2, int(n * 0.8))), f)())
    # 되밀림·되오름
    for L in (20, 40, 60, 120):
        b = g.c.shift(L); hi = R("c", L + 1, "max"); lo = R("c", L + 1, "min")
        with np.errstate(all="ignore"):
            D["up%d" % L] = (hi / b - 1) * 100; D["ru%d" % L] = ((hi - c) / (hi - b)).where(hi > b)
            D["dn%d" % L] = (1 - lo / b) * 100; D["rd%d" % L] = ((c - lo) / (b - lo)).where(b > lo)
    # 벨레즈: 고가 낮아지는 음봉 연속 길이
    x = ((c < o) & (D.h < ph)).astype(int); x[D.ticker != D.ticker.shift()] = 0
    D["velez_run"] = x.groupby((x != x.shift()).cumsum()).cumsum() * x
    # 기간조정
    lo20 = R("l", 20, "min"); lo40 = g.l.transform(lambda z: z.shift(20).rolling(20, min_periods=16).min())
    D["higher_low"] = (lo20 > lo40).astype(float)
    D["_vu"] = v.where(c > pc); D["_vd"] = v.where(c < pc)
    g2 = D.groupby("ticker", sort=False)
    D["vd_vu"] = g2._vd.transform(lambda z: z.rolling(20, min_periods=5).mean()) / g2._vu.transform(lambda z: z.rolling(20, min_periods=5).mean())
    # 다진 자리
    D["base_tight"] = R("c", 40, "min") / R("h", 120, "max")
    # 팔리 밀집
    ma5 = R("c", 5, "mean"); ma10 = R("c", 10, "mean"); ma20 = R("c", 20, "mean"); ma60 = R("c", 60, "mean"); ma120 = R("c", 120, "mean")
    D["ma5_10"] = (ma5 / ma10 - 1).abs() * 100
    D["body"] = (c - o).abs() / c * 100
    v20 = g.v.transform(lambda z: z.shift(1).rolling(20, min_periods=16).mean())
    D["v_v20"] = v / v20
    # 와조스키
    D["c_ma5"] = (c / ma5 - 1) * 100; D["c_ma120"] = (c / ma120 - 1) * 100
    D["v5_v60"] = R("v", 5, "mean") / R("v", 60, "mean")
    # 바닥 확인 캔들
    lw = np.minimum(o, c) - l; bd = (c - o).abs()
    D["c_gt_ph"] = (c > ph).astype(float)
    D["lwick"] = (lw / bd.replace(0, np.nan)).clip(upper=20)
    # 조용함·보조지표
    D["_r"] = g.c.pct_change()
    g3 = D.groupby("ticker", sort=False)
    D["vol20x"] = g3._r.transform(lambda z: z.rolling(20, min_periods=16).std()) * 100
    def rsi(n):
        up = D._r.clip(lower=0); dn = (-D._r).clip(lower=0)
        au = up.groupby(D.ticker, sort=False).transform(lambda z: z.ewm(alpha=1 / n, adjust=False).mean())
        ad = dn.groupby(D.ticker, sort=False).transform(lambda z: z.ewm(alpha=1 / n, adjust=False).mean())
        return 100 - 100 / (1 + au / ad.replace(0, np.nan))
    D["rsi14"] = rsi(14); D["rsi2"] = rsi(2)
    sd20 = R("c", 20, "std")
    D["bb_pctb"] = (c - (ma20 - 2 * sd20)) / (4 * sd20)
    D["willr"] = (R("h", 14, "max") - c) / (R("h", 14, "max") - R("l", 14, "min")) * -100
    D["dma20x"] = (c / ma20 - 1) * 100; D["dma60x"] = (c / ma60 - 1) * 100
    D["ret5x"] = (c / g.c.shift(5) - 1) * 100; D["ret10x"] = (c / g.c.shift(10) - 1) * 100
    return D.drop(columns=["_vu", "_vd", "_r"])


def placebo(Z):
    ref = pd.Timestamp("2000-01-06 18:14", tz="UTC")
    dd = pd.to_datetime(Z.date, format="%Y%m%d").dt.tz_localize("UTC")
    age = ((dd - ref).dt.total_seconds() / 86400.0) % 29.530588853
    Z["moon_new"] = ((age <= 7.4) | (age >= 22.1)).astype(float)
    Z["coin"] = (np.random.default_rng(5).random(len(Z)) < 0.5).astype(float)
    return Z


FEATS_BASE = ["up20", "ru20", "dn20", "rd20", "up40", "ru40", "dn40", "rd40", "up60", "ru60", "dn60", "rd60", "up120", "ru120", "dn120", "rd120",
              "velez_run", "higher_low", "vd_vu", "base_tight", "ma5_10", "body", "v_v20", "c_ma5", "c_ma120", "v5_v60", "c_gt_ph", "lwick",
              "vol20x", "rsi14", "rsi2", "bb_pctb", "willr", "dma20x", "dma60x", "ret5x", "ret10x", "moon_new", "coin"]


# ─────────────────────────── 국장 P1
def kr_p1():
    import rule_scan as RS
    S = RS.kr_signals()[["date", "ticker", "rid", "r"]]
    sys.stdout = sys.__stdout__; sys.stdout.reconfigure(encoding="utf-8")
    S = S[S.rid == "P1"].drop_duplicates(["ticker", "date"])
    K = pd.read_pickle(BASE / "data" / "kr_scan.pkl")[["ticker", "date", "open", "high", "low", "close", "volume"]]
    K = K[K.ticker.isin(S.ticker.unique())].sort_values(["ticker", "date"]).reset_index(drop=True)
    K.columns = ["ticker", "date", "o", "h", "l", "c", "v"]
    log("P1 재료 계산 %s행" % f"{len(K):,}")
    K = ohlc_feats(K)
    Z = S.merge(K, on=["ticker", "date"], how="left")
    # 네이버 관심도
    N = pd.read_pickle(ROOT / "cache" / "naver_att.pkl")
    Z = Z.merge(N, on=["ticker", "date"], how="left")
    # 서울 일조(위약)
    W = pd.read_pickle(ROOT / "cache" / "seoul_weather.pkl")
    W["q"] = W.groupby(W.date.str[4:6]).sun.rank(pct=True)
    Z["sunq"] = Z.date.map(dict(zip(W.date, W.q)))
    # 최근 60일 공시 수
    c = sqlite3.connect("file:" + str(BASE / "data" / "dart" / "disclosures.db") + "?mode=ro", uri=True)
    Dd = pd.read_sql("select stock_code ticker, rcept_dt, report_nm from disclosure where stock_code in (%s)" %
                     ",".join("'%s'" % t for t in Z.ticker.unique()), c)
    Dd["t"] = Dd.report_nm.str.replace(" ", "")
    kinds = {"disc_ir": r"기업설명회", "disc_supply": r"단일판매ㆍ공급계약체결", "disc_bb": r"자기주식취득", "disc_rights": r"유상증자결정",
             "disc_cb": r"전환사채권발행결정|신주인수권부사채권발행결정"}
    for nm, rx in kinds.items():
        x = Dd[Dd.t.str.contains(rx, regex=True)]
        by = x.groupby("ticker").rcept_dt.apply(lambda s: np.sort(s.values))
        def cnt(t, d):
            a = by.get(t)
            if a is None: return 0.0
            d0 = (pd.Timestamp(d) - pd.Timedelta(days=90)).strftime("%Y%m%d")
            return float(np.searchsorted(a, d, "right") - np.searchsorted(a, d0, "left"))
        Z[nm] = [cnt(t, d) for t, d in zip(Z.ticker, Z.date)]
    Z = placebo(Z)
    feats = FEATS_BASE + ["att", "att7", "zfrac", "sunq"] + list(kinds)
    P("## [조용한 신고가] P1 — 국장 · 실제 청산(40일) · 신호 %d건" % len(Z)); P("")
    return T2.scan(Z.reset_index(drop=True), feats, "P1")


# ─────────────────────────── 미장 N1·N5
def us_prep():
    src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌")[0]
    src = src.replace('"--since", "20160101"', '"--since", "20080101"').replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20080101"]')
    src = src.split("# ── 기준 지수")[0]
    ns = {"__file__": str(ROOT / "us_capture.py"), "__name__": "us_capture_prep"}
    exec(compile(src, "us_capture.py", "exec"), ns)
    sys.stdout.reconfigure(encoding="utf-8")
    S, PATH, K = ns["S"], ns["PATH"], ns["K"]
    r = []
    for i in range(len(S)):
        ddi, ratio = PATH[i]
        done = len(ddi) and ddi[-1] >= S.di[i] + S.hold[i] - 3
        r.append((ratio[-1] - 1) * 100 - S.cost[i] if done else np.nan)
    return S.assign(r=r).dropna(subset=["r"]), K


def us_rule(S, K, rid):
    Z0 = S[S.rid == rid][["date", "ticker", "r"]].copy()
    tick = Z0.ticker.unique()
    Kx = K[K.ticker.isin(tick)][["ticker", "date", "buy", "high", "low", "rawclose", "volume"]].sort_values(["ticker", "date"]).reset_index(drop=True)
    Kx["o"] = Kx.groupby("ticker").buy.shift(1).fillna(Kx.rawclose)
    D = pd.DataFrame({"ticker": Kx.ticker, "date": Kx.date, "o": Kx.o, "h": Kx.high, "l": Kx.low, "c": Kx.rawclose, "v": Kx.volume})
    log("%s 재료 계산 %s행" % (rid, f"{len(D):,}"))
    D = ohlc_feats(D)
    Z = Z0.merge(D, on=["ticker", "date"], how="left")
    if rid == "N1":                                   # 지금 규칙: 거래대금 상위 40% 안 거래 주식 수 상위 20%
        q = K.groupby("date").amt20.rank(pct=True)
        U = K[(q >= 0.6) & (K.rawclose >= 3)][["ticker", "date", "volume"]].copy()
        U["vq"] = U.groupby("date").volume.rank(pct=True)
        Z = Z.merge(U[["ticker", "date", "vq"]], on=["ticker", "date"], how="left")
        n0 = len(Z); Z = Z[Z.vq >= 0.8]
        P("(N1 은 지금 규칙대로 거래 주식 수 상위 20%%만 남겨 시작 — %d → %d건)" % (n0, len(Z)))
    Z = placebo(Z.reset_index(drop=True))
    P("## %s — 미장 · 신호 %d건" % ("[상승장 신고가] N1(40일)" if rid == "N1" else "[잔잔한 급등주] N5(60일)", len(Z))); P("")
    return T2.scan(Z, FEATS_BASE, rid)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    pick = set(argv) or {"P1", "N1", "N5"}
    T2.OUT.clear()
    P("# 약한 규칙 셋 조이기 — 기각 기법 총동원 · %s" % time.strftime("%Y-%m-%d")); P("")
    if "P1" in pick:
        kr_p1()
    if pick & {"N1", "N5"}:
        S, K = us_prep()
        for rid in ("N1", "N5"):
            if rid in pick:
                us_rule(S, K, rid)
    (ROOT / "reports" / ("tighten3_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(T2.OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
