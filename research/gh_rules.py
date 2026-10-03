# -*- coding: utf-8 -*-
"""공개 GitHub 매매 규칙 실측 (2026-10-04, 사용자 요청) — 규칙 출처는 저장소 실제 코드(조사 2026-10-04).
gh_engine 의 같은 잣대(유니버스 거래대금 상위 40% · 우리 비용 · 학습/검증/참고). 공매도 전용·1분봉·재무제표·ML 규칙은 제외.
  python research/gh_rules.py [KR|US]
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import gh_engine as G
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
RES = []


def extra(A):
    g = A.groupby("ticker", sort=False)
    sh = lambda c, n=1: g[c].shift(n)
    roll = lambda c, n, f, lag=1: g[c].transform(lambda s: getattr(s.shift(lag).rolling(n, min_periods=n), f)())
    A["ma5p"], A["ma10p"] = sh("ma5"), sh("ma10")
    A["ma15p"] = roll("close", 15, "mean")
    A["rng_p"] = A.ph - A.pl
    rr = (A.high - A.low).replace(0, np.nan)
    A["noise"] = 1 - (A.close - A.open).abs() / rr
    A["k_noise"] = roll("noise", 20, "mean")
    # Dual Thrust: 직전 5일
    A["dt_rng"] = np.maximum(roll("high", 5, "max") - roll("close", 5, "min"), roll("close", 5, "max") - roll("low", 5, "min"))
    A["ibs"] = (A.close - A.low) / rr
    A["pctb"] = (A.close - A.bbl) / (A.bbu - A.bbl).replace(0, np.nan)
    tp = (A.high + A.low + A.close) / 3; mf = tp * A.volume
    tpd = tp.groupby(A.ticker).diff()
    pmf = (mf.where(tpd > 0, 0)).groupby(A.ticker).transform(lambda s: s.rolling(10).sum())
    nmf = (mf.where(tpd < 0, 0)).groupby(A.ticker).transform(lambda s: s.rolling(10).sum())
    A["mfi10"] = 100 - 100 / (1 + pmf / nmf.replace(0, np.nan))
    ii = (2 * A.close - A.high - A.low) / rr * A.volume
    A["ii21"] = ii.groupby(A.ticker).transform(lambda s: s.rolling(21).sum()) / g.volume.transform(lambda s: s.rolling(21).sum()) * 100
    A["ema130"] = g.close.transform(lambda s: s.ewm(span=130, adjust=False).mean())
    hh14 = g.high.transform(lambda s: s.rolling(14).max()); ll14 = g.low.transform(lambda s: s.rolling(14).min())
    fk = (A.close - ll14) / (hh14 - ll14).replace(0, np.nan) * 100
    A["slowk"] = fk.groupby(A.ticker).transform(lambda s: s.rolling(3).mean())
    d = g.close.diff()
    up = d.clip(lower=0).groupby(A.ticker).transform(lambda s: s.rolling(21).mean())
    dn = (-d.clip(upper=0)).groupby(A.ticker).transform(lambda s: s.rolling(21).mean())
    A["rsi21"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    upd = (d > 0).astype(int); dnd = (d < 0).astype(int)
    A["up5"] = upd.groupby(A.ticker).transform(lambda s: s.rolling(5).sum()) == 5
    A["dn5"] = dnd.groupby(A.ticker).transform(lambda s: s.rolling(5).sum()) == 5
    A["max252p"] = roll("close", 252, "max"); A["max20p"] = roll("close", 20, "max"); A["hmax20p"] = roll("high", 20, "max")
    tr = np.maximum(A.high - A.low, np.maximum((A.high - A.pc).abs(), (A.low - A.pc).abs()))
    A["atr10"] = tr.groupby(A.ticker).transform(lambda s: s.rolling(10).mean())
    A["atr10ma"] = A.atr10.groupby(A.ticker).transform(lambda s: s.rolling(20).mean())
    A["ma150"] = g.close.transform(lambda s: s.rolling(150, min_periods=150).mean())
    A["ma150_63"] = A.ma150.groupby(A.ticker).shift(63); A["ma200_20"] = A.ma200.groupby(A.ticker).shift(20)
    A["lo260"] = g.close.transform(lambda s: s.rolling(260, min_periods=200).min()); A["hi260"] = g.close.transform(lambda s: s.rolling(260, min_periods=200).max())
    A["vma50"] = g.volume.transform(lambda s: s.rolling(50).mean())
    A["below150_20"] = (A.close < A.ma150).astype(float).groupby(A.ticker).transform(lambda s: s.rolling(20).max()) > 0
    A["sig_ret1"] = A.ret1
    # 하이킨아시
    hac = (A.open + A.high + A.low + A.close) / 4
    hao = np.empty(len(A)); o, c, tk = A.open.to_numpy(), hac.to_numpy(), A.ticker.to_numpy()
    for i in range(len(A)):
        hao[i] = (o[i] + c[i]) / 2 if i == 0 or tk[i] != tk[i - 1] else (hao[i - 1] + c[i - 1]) / 2
    A["hao"], A["hac"] = hao, hac
    A["hah"] = np.maximum(A.high, np.maximum(A.hao, A.hac)); A["hal"] = np.minimum(A.low, np.minimum(A.hao, A.hac))
    # 12개월 수익(모멘텀 RS)
    A["r252"] = (A.close / g.close.shift(252) - 1) * 100
    A["rs"] = A.groupby("date").r252.rank(pct=True) * 100
    return A


def run_rules(mk):
    t0 = time.time()
    A = extra(G.load(mk))
    P("## %s — 패널 %s행 · 준비 %.0f초" % ("국장" if mk == "KR" else "미장", f"{len(A):,}", time.time() - t0)); P("")
    g = A.groupby("ticker", sort=False)
    S = lambda c, n=1: g[c].shift(n)
    cross_up = lambda a, b: (A[a] > A[b]) & (S(a) <= S(b))
    rules = []
    # ── 데이 (장중 진입) ───────────────────────────────
    t = A.open + 0.5 * A.rng_p
    rules.append(("D1 변동성 돌파+MA5·10 · 같은 날 종가 (INVESTAR)", dict(sig=(A.high >= t) & (t > A.ma5p) & (t > A.ma10p) & (A.rng_p > 0),
                  entry="intraday", entry_px=np.maximum(t, A.open), exit="sameclose", day=True)))
    t2 = A.pc + 0.5 * A.rng_p
    rules.append(("D2 변동성 돌파(전일 종가 기준)+MA15 · 다음날 시가 (조코딩)", dict(sig=(A.high >= t2) & (t2 > A.ma15p) & (A.rng_p > 0),
                  entry="intraday", entry_px=np.maximum(t2, A.open), exit="nextopen", day=True)))
    t3 = A.open + A.rng_p * A.k_noise
    rules.append(("D3 노이즈 k 변동성 돌파 · 손절 3% · 같은 날 종가", dict(sig=(A.high >= t3) & (A.rng_p > 0), entry="intraday",
                  entry_px=np.maximum(t3, A.open), exit="hold", H=1, stop=3, day=True)))
    up = A.open + 0.5 * A.dt_rng
    rules.append(("D4 Dual Thrust 롱 · 같은 날 종가 (je-suis-tm)", dict(sig=(A.high >= up) & (A.dt_rng > 0), entry="intraday",
                  entry_px=np.maximum(up, A.open), exit="sameclose", day=True)))
    sig5 = g.close.transform(lambda s: s.ewm(alpha=0.01).std())
    rules.append(("D5 갭 하락(전일 저가−σ 아래 & 20일선 아래) 시가 매수 · 종가 (sell-gap 반대)", dict(sig=(A.open < A.pl - sig5) & (A.open < A.ma20.groupby(A.ticker).shift(1)) & (A.pc > S("ma20")),
                  entry="intraday", entry_px=A.open, exit="sameclose", day=True)))
    rules.append(("D6 -10% 급락 다음날 시가→종가 롱 (dead-cat 반대 확인용)", dict(sig=S("ret1") <= -10, entry="intraday", entry_px=A.open, exit="sameclose", day=True)))
    # ── 스윙 (신호일 종가 → 다음날 시가) ────────────────
    rules += [
        ("S7 강한 종가 IBS≥0.8 → IBS<0.2·손절5% (KIS)", dict(sig=A.ibs >= 0.8, exit="cond", exit_mask=A.ibs < 0.2, stop=5, maxh=60)),
        ("S8 IBS<0.2 → IBS>0.8 (roboquant)", dict(sig=A.ibs < 0.2, exit="cond", exit_mask=A.ibs > 0.8, maxh=60)),
        ("S10 Connors RSI2<10 & 200일선 위 → 5일선 위", dict(sig=(A.close > A.ma200) & (A.rsi2 < 10), exit="cond", exit_mask=A.close > A.ma5, maxh=30)),
        ("S11 볼린저 %b>0.8 & MFI10>80 → %b<0.2&MFI<20 (INVESTAR)", dict(sig=(A.pctb > 0.8) & (A.mfi10 > 80), exit="cond", exit_mask=(A.pctb < 0.2) & (A.mfi10 < 20), maxh=120)),
        ("S12 볼린저 %b<0.05 & II%21>0 → %b>0.95&II<0 (INVESTAR)", dict(sig=(A.pctb < 0.05) & (A.ii21 > 0), exit="cond", exit_mask=(A.pctb > 0.95) & (A.ii21 < 0), maxh=120)),
        ("S13 삼중창 EMA130↑ & 스토캐 20 하향돌파 (INVESTAR)", dict(sig=(A.ema130 > S("ema130")) & (A.slowk < 20) & (S("slowk") >= 20), exit="cond",
                                                             exit_mask=(A.ema130 < S("ema130")) & (A.slowk > 80) & (S("slowk") <= 80), maxh=120)),
        ("S14 RSI21<30 → RSI>70 (INVESTAR)", dict(sig=A.rsi21 < 30, exit="cond", exit_mask=A.rsi21 > 70, maxh=120)),
        ("S15a 이격도 20일선 0.9 아래 → 1.1 위·손절5·익절10 (KIS)", dict(sig=A.close / A.ma20 < 0.90, exit="cond", exit_mask=A.close / A.ma20 > 1.10, stop=5, target=10, maxh=60)),
        ("S15b 5일선 -3% 아래 → +3% 위·손절3·익절3 (KIS)", dict(sig=A.close < A.ma5 * 0.97, exit="cond", exit_mask=A.close > A.ma5 * 1.03, stop=3, target=3, maxh=30)),
        ("S16 5일 연속 상승 → 5일 연속 하락·손절5 (KIS)", dict(sig=A.up5, exit="cond", exit_mask=A.dn5, stop=5, maxh=60)),
        ("S17 52주 신고가 돌파 → 손절5·익절15 (KIS)", dict(sig=(A.close > A.max252p) & (A.pc <= S("max252p")), exit="hold", H=250, stop=5, target=15)),
        # 원본은 '3일 안 돌파선 아래면 매도' + 손절 3% 뿐(익절 없음) — 3일 이탈은 손절 3% 가 거의 같이 잡는다고 보고 손절만 · 최대 60일
        ("S18 20일 종가 돌파 → 손절3·최대 60일 (KIS)", dict(sig=(A.close > A.max20p) & (A.pc <= S("max20p")), exit="hold", H=60, stop=3)),
        ("S19 변동성 축소 후 +3% → -3%·손절5 (KIS)", dict(sig=(A.atr10 < A.atr10ma) & (A.ret1 > 3), exit="cond", exit_mask=A.ret1 < -3, stop=5, maxh=60)),
        ("S20 골든크로스 5/20 → 데드크로스·손절5·익절10 (KIS)", dict(sig=cross_up("ma5", "ma20"), exit="cond", exit_mask=(A.ma5 < A.ma20), stop=5, target=10, maxh=120)),
        ("S21 정배열 첫날 → 정배열 깨지면 (wikibook)", dict(sig=((A.ma5 >= A.ma20) & (A.ma20 >= A.ma60) & (A.ma60 >= A.ma120)) & ~((S("ma5") >= S("ma20")) & (S("ma20") >= S("ma60")) & (S("ma60") >= S("ma120"))),
                                                     exit="cond", exit_mask=~((A.ma5 >= A.ma20) & (A.ma20 >= A.ma60) & (A.ma60 >= A.ma120)), maxh=250)),
    ]
    for n1, n2, m1, m2 in ((20, 20, 5, 5), (60, 120, 20, 10), (240, 240, 30, 30)):
        mx = g.close.transform(lambda s: s.rolling(n1, min_periods=n1).max())
        rules.append(("S22 낙폭 %d일 고점 -%d%% → +%d%% 또는 %d일 (wikibook)" % (n1, m1, m2, n2), dict(sig=(mx - A.close) / mx * 100 >= m1, exit="hold", H=n2, target=m2)))
    eng = (S("close") < S("open")) & (A.close > A.open) & (A.open < A.pl) & (A.close > A.ph)
    for h in (5, 20, 60):
        rules.append(("S23 상승장악형(갭) %d일 보유 (wikibook)" % h, dict(sig=eng, exit="hold", H=h)))
    tws = (A.close > A.open) & (S("close") > S("open")) & (S("close", 2) > S("open", 2)) & (A.close > A.pc) & (A.pc > S("close", 2))
    rules.append(("S23 적삼병 20일 보유 (wikibook)", dict(sig=tws, exit="hold", H=20)))
    rules.append(("S24 터틀 20일 돌파 → 10일 저가·20일 고가 중간 이탈 (Harvey-Sun)", dict(sig=S("close") > S("hmax20p"), exit="cond",
                  exit_mask=A.close < (A.ll10 + A.hh20) / 2, maxh=250)))
    ha_bear = A.hac < A.hao
    rules.append(("S26 하이킨아시 역추세(음봉·윗꼬리 없음·몸통 커짐) (je-suis-tm)", dict(sig=ha_bear & ((A.hah - A.hao).abs() < 1e-9 * A.close + 0) & ((A.hao - A.hac) > (S("hao") - S("hac"))) & (S("hac") < S("hao")),
                  exit="cond", exit_mask=(A.hac > A.hao) & ((A.hao - A.hal).abs() < 1e-9 * A.close + 0) & (S("hac") > S("hao")), maxh=60)))
    mtt = (A.close > A.ma150) & (A.close > A.ma200) & (A.ma150 > A.ma200) & (A.ma200 > A.ma200_20) & (A.ma50 > A.ma150) & (A.close > A.ma50) \
          & (A.close >= 1.3 * A.lo260) & (A.close >= 0.75 * A.hi260) & (A.rs >= 70)
    fresh = mtt & ~mtt.groupby(A.ticker).shift(1).fillna(False).astype(bool)
    for h in (20, 60):
        rules.append(("S28 미너비니 추세 템플릿 처음 통과 · %d일 (minervini screener)" % h, dict(sig=fresh, exit="hold", H=h)))
    wst = (A.close > A.ma150) & (A.ma150 > A.ma200) & (A.ma150 > A.ma150_63) & (A.close > A.ma50) & A.below150_20 & (A.volume > 1.5 * A.vma50)
    rules.append(("S29 와인스타인 2단계 돌파 · 60일", dict(sig=wst & ~wst.groupby(A.ticker).shift(1).fillna(False).astype(bool), exit="hold", H=60)))
    rules.append(("S29 다바스 상자 돌파(직전 20일 고가·거래량 1.4배) · 손절10·익절20", dict(sig=(A.close > A.hmax20p) & (A.volume > 1.4 * A.vma50), exit="hold", H=60, stop=10, target=20)))
    bm = {h: G.bench(A, h) for h in (5, 10, 20, 40, 60)}
    for lab, kw in rules:
        sig = kw.pop("sig")
        try:
            Y = G.simulate(A, sig, mk, **kw)
        except Exception as ex:
            P("| %s | 실패 %r |" % (lab, ex)); continue
        H = kw.get("H")
        r = G.report(Y, lab, bm.get(H) if kw.get("exit") == "hold" and not kw.get("day") else None)
        # 비용 전도 같이 — 어디서 무너지나
        r["gross"] = (Y.r + (G.DAYCOST[mk] if kw.get("day") else 0)).mean() if kw.get("day") else None
        RES.append((mk, r)); N.append(1)
        tr, va, old = r["rows"]
        P("| %s | %s | %s | %s | %s |" % (lab, G.fmt(tr), G.fmt(va), G.fmt(old), "✅" if r["ok"] else ""))
    return A


def factors(A, mk):
    P(""); P("### 팩터 (분기·월 리밸런싱 · 같은 기간 유니버스 동일가중 대비)"); P("")
    P("| 규칙 | 학습 16~22 연평균 · 초과 · 플러스 해 | 검증 23~ | 참고 05~15 | 통과 |"); P("|---|---|---|---|---|")
    U = A[A.uni].copy()
    U["ym"] = U.date.str[:6]
    days = sorted(A.date.unique())
    first_of = U.groupby("ym").date.min().sort_values()
    def rebal(freq):
        d = first_of.copy()
        if freq == "Q": d = d[d.index.str[4:6].isin(["01", "04", "07", "10"])]
        if freq == "Y": d = d[d.index.str[4:6] == "04"]
        return list(d.values)
    px = A.pivot_table(index="date", columns="ticker", values="open")
    cst = A.groupby("ticker").cost.median()
    def run(name, freq, score, n, asc):
        R = rebal(freq); rows = []
        for a, b in zip(R[:-1], R[1:]):
            i = days.index(a)
            prev = days[i - 1]
            X = U[U.date == prev].copy()
            X["s"] = score(X)
            X = X.dropna(subset=["s"])
            if len(X) < n * 3: continue
            pick = X.sort_values("s", ascending=asc).head(n).ticker
            pa, pb = px.loc[a], px.loc[b]
            rr = (pb[pick] / pa[pick] - 1).dropna() * 100 - cst.reindex(pick).fillna(0.5).mean()
            ra = (pb[X.ticker] / pa[X.ticker] - 1).dropna() * 100
            rows.append((a, rr.clip(-95, 500).mean(), ra.clip(-95, 500).mean()))
        Z = pd.DataFrame(rows, columns=["date", "p", "u"])
        out = []
        for nm, lo, hi in G.PER:
            z = Z[(Z.date >= lo) & (Z.date <= hi)]
            if len(z) < 4: out.append("-"); continue
            per_y = {"M": 12, "Q": 4, "Y": 1, "W": 52}[freq]
            yr = z.groupby(z.date.str[:4]).apply(lambda q: (1 + q.p / 100).prod() - 1)
            ex = (z.p - z.u).mean() * per_y
            out.append("%+.1f%% · 초과 %+.1f%%p · %d/%d해" % (((1 + z.p / 100).prod() ** (per_y / len(z)) - 1) * 100, ex, (yr > 0).sum(), len(yr)))
        ok = all(o != "-" for o in out[:2]) and all("초과 +" in o for o in out[:2])
        P("| %s | %s | %s | %s | %s |" % (name, out[0], out[1], out[2], "✅" if ok else "")); N.append(1)
    has = lambda c: c in U.columns and U[c].notna().mean() > 0.3
    P("(재무 칸 채움: PBR %.0f%% · PER %.0f%% · 시총 %.0f%%)" % (U.PBR.notna().mean() * 100 if "PBR" in U else 0, U.PER.notna().mean() * 100 if "PER" in U else 0,
                                                       U.marcap.notna().mean() * 100 if "marcap" in U else 0)); P("")
    if has("PBR") and has("PER"):
        run("F31a 저PBR(PER 2.5~10) 30종목 · 분기", "Q", lambda X: X.PBR.where(X.PER.between(2.5, 10) & (X.PBR > 0)), 30, True)
        run("F31b 저PER+저PBR 순위합 20종목 · 분기", "Q", lambda X: (X.PER.where(X.PER > 0).rank() + X.PBR.where(X.PBR > 0).rank()), 20, True)
        if has("marcap"):
            run("F32 소형(시총 하위 20%) 가치 20종목 · 분기 (강환국)", "Q",
                lambda X: (X.PER.where(X.PER >= 0.5).rank() + X.PBR.where(X.PBR >= 0.2).rank()).where(X.marcap <= X.marcap.quantile(0.2)), 20, True)
    run("F33 12개월 모멘텀 20종목 · 분기", "Q", lambda X: X.r252, 20, False)
    run("F35 주간 반전(5일 최악 10종목) · 월", "M", lambda X: X.ret5, 10, True)
    run("F37 저변동성(20일 변동성 낮은 25%) 30종목 · 월", "M", lambda X: X.vol20, 30, True)


N = []


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    mks = [a for a in sys.argv[1:] if a in ("KR", "US")] or ["KR", "US"]
    t0 = time.time()
    P("# 공개 GitHub 규칙 실측 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("잣대: 유니버스 거래대금 상위 40% · 스윙 비용 = 우리 규칙과 같은 보수적 왕복(국장 0.35~1.15% · 미장 0.10~0.60%) · 데이 = 국장 0.30% · 미장 0.25% · "
      "통과 = 학습·검증 둘 다 건당 평균 플러스 & 학습 중앙 플러스 & 학습 해 60%↑ & (고정 보유는) 아무 종목 대비 초과 플러스"); P("")
    for mk in mks:
        P("| 규칙 | 학습 16~22 | 검증 23~ | 참고 05~15 | 통과 |"); P("|---|---|---|---|---|")
        A = run_rules(mk)
        factors(A, mk)
        P("")
        del A
    log_trials("gh_rules_%s" % time.strftime("%Y%m%d"), len(N))
    pd.to_pickle(RES, ROOT / "cache" / ("gh_rules_%s.pkl" % "_".join(mks)))
    P("(칸 %d · %.0f분)" % (len(N), (time.time() - t0) / 60))
    (ROOT / "reports" / ("gh_rules_%s_%s.md" % ("_".join(mks), time.strftime("%Y%m%d")))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
