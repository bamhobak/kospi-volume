# -*- coding: utf-8 -*-
"""외국 논문·사이트의 **회피 신호**를 두 층으로 잰다 (2026-09-25, 외국 기법 실측의 짝).

매수 기법은 run_spec(명세 실행기)으로 잰다. 여기는 "이런 건 사지 마라" 쪽이다 — 판정 질문이 다르다.

  ① 시장 전체 — 유동성 상위 40% 안에서 그날 재료 상위 10% 와 나머지의 20일 수익 중앙값 차(날마다 → 평균),
     학습(2016~22)·검증(2023~) 방향. 우리 시장에도 그 이상현상이 있나.
  ② 우리 규칙 안 — rule_scan.scan 그대로(같은 규칙·같은 달 위/아래 절반 짝비교). 우리가 실제로 산 종목을
     이 재료로 걸러낼 수 있나. 폭락을 사는 우리 규칙에선 시장 전체 경향이 안 통할 수 있다([[research-pipeline]] 교훈).

재료 (전부 과거만 — 신호일 종가까지)
  max21   직전 21일 최대 일간수익(로또주 · Bali 외 2011 · 한국 Nartea 외 2014)
  big60   60일 안 +10% 이상 날 수(로또주 빈도판)
  ivol21  21일 (일간수익 − 그날 시장 평균) 표준편차(고유 변동성 · Ang 외 2006 · 한국 Kang 2014)
  ivol_l  ivol21, 단 미실현 손실(종가 < 250일 거래량가중 평균가)일 때만 · 이익이면 0 (준거점 의존 · Cogent 2020)
  imin21  −(21일 중 최저 고유 수익)(고유 급락 · KJFS 2023)
  abturn  5일 평균 거래량 ÷ 그 전 250일 평균(이상 회전율 · 한국은 저거래량 프리미엄 Chae·Kang 2019)
  sal21   돌출성 ST(Cosemans·Frehen 2021) — 21일 중 시장과 가장 달랐던 날들에 가중한 수익 공분산
  nhk     250일 신고가 연속 갱신 일수(일본 systemtrade-kabu: 3일째+거래량 3배 = 소진)
  nhk_v   nhk ≥ 3 이면 당일 거래량/20일 평균, 아니면 0
  upv10   상승일 거래량/20일 평균(상승일만, 일본: 10배 이상 = 재료 소진)
  red3    적삼병(3연속 양봉·종가 상승·시가가 전일 몸통 안·윗꼬리 1% 이하) 3일째 = 1 (중화권 반증: 이후 상승확률 33%)

    python research/avoid_scan.py KR
    python research/avoid_scan.py US
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import rule_scan as RS
from verdict import log_trials

AX = ["max21", "big60", "ivol21", "ivol_l", "imin21", "abturn", "sal21", "nhk", "nhk_v", "upv10", "red3"]
# 외국 매수 기법 지표(재료) — 방향은 D 부호로 읽는다(양수 = 클수록 좋다)
MAT = ["m_rsi2", "m_rsiw", "m_dvb", "m_vr", "m_psy", "m_lrsi", "m_fisher", "m_adx", "m_bbz", "m_ibs", "m_er10", "m_shinob"]
OUT = []


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def salience(r, m, n=21, delta=0.7):
    """한 종목의 일간수익 r·시장수익 m(배열) → ST(창 n). 순위 1이 가장 돌출된 날."""
    out = np.full(len(r), np.nan)
    if len(r) < n:
        return out
    from numpy.lib.stride_tricks import sliding_window_view as W
    R, M = W(r, n), W(m, n)
    s = np.abs(R - M) / (np.abs(R) + np.abs(M) + 0.1)
    rk = (-s).argsort(axis=1).argsort(axis=1) + 1                   # 1 = 가장 돌출
    w = delta ** rk
    w = w / w.mean(axis=1, keepdims=True)
    st = ((w - w.mean(axis=1, keepdims=True)) * (R - R.mean(axis=1, keepdims=True))).mean(axis=1)
    ok = np.isfinite(R).all(axis=1) & np.isfinite(M).all(axis=1)
    out[n - 1:] = np.where(ok, st, np.nan)
    return out


def features(mk):
    if mk == "KR":
        A = pd.read_pickle(BASE / "data/kr_scan.pkl")
        A = A[((A.close >= 1000) & (~A.pref.fillna(False))).fillna(False)]
    else:
        A = pd.read_pickle(BASE / "data/us_scan.pkl")
        A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)]
    keep = ["date", "ticker", "close", "volume", "amt20", "su1", "n20"] + (["open", "high", "low"] if "open" in A.columns else [])
    A = A[keep + (["rng", "clv"] if mk == "US" else [])].sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    r1 = (A.close / g.close.shift(1) - 1) * 100
    A["r1"] = r1
    mret = r1.groupby(A.date).transform("mean")
    ir = r1 - mret
    gi = ir.groupby(A.ticker, sort=False)
    A["max21"] = r1.groupby(A.ticker, sort=False).transform(lambda s: s.rolling(21, min_periods=21).max())
    A["big60"] = (r1 >= 10).astype(float).groupby(A.ticker, sort=False).transform(lambda s: s.rolling(60, min_periods=60).sum())
    A["ivol21"] = gi.transform(lambda s: s.rolling(21, min_periods=21).std())
    pv = (A.close * A.volume).groupby(A.ticker, sort=False).transform(lambda s: s.rolling(250, min_periods=120).sum())
    vv = A.volume.groupby(A.ticker, sort=False).transform(lambda s: s.rolling(250, min_periods=120).sum())
    cgo = A.close / (pv / vv.replace(0, np.nan)) - 1
    A["ivol_l"] = np.where(cgo < 0, A.ivol21, 0.0)
    A.loc[cgo.isna() | A.ivol21.isna(), "ivol_l"] = np.nan
    A["imin21"] = -gi.transform(lambda s: s.rolling(21, min_periods=21).min())
    v5 = g.volume.transform(lambda s: s.rolling(5, min_periods=5).mean())
    v250 = g.volume.transform(lambda s: s.shift(5).rolling(250, min_periods=120).mean())
    A["abturn"] = v5 / v250.replace(0, np.nan)
    log("  돌출성 계산")
    sal = np.full(len(A), np.nan)
    rv, mv = r1.values / 100, mret.values / 100
    for idx in A.groupby("ticker", sort=False).indices.values():
        sal[idx] = salience(rv[idx], mv[idx])
    A["sal21"] = sal
    hi250 = g.close.transform(lambda s: s.shift(1).rolling(250, min_periods=200).max())
    nh = (A.close > hi250)
    A["nhk"] = nh.astype(int).groupby([A.ticker, (~nh).groupby(A.ticker).cumsum()]).cumsum().astype(float)
    A["nhk_v"] = np.where(A.nhk >= 3, A.su1, 0.0)
    A["upv10"] = np.where(r1 > 0, A.su1, 0.0)
    # ── 외국 매수 기법의 지표를 재료로 (2026-09-25: 단독으로는 141개 전부 2단계 탈락 → 우리 규칙 안에서 가르나) ──
    log("  기법 지표 재료 계산")
    if "high" not in A.columns:             # 미장: 고저를 폭·종가위치로 되살린다(run_spec.load_market 과 같다)
        Rg = A.rng * A.close / 100
        A["low"] = A.close - (A.clv + 1) / 2 * Rg
        A["high"] = A["low"] + Rg
    ew = lambda x, a: x.groupby(A.ticker, sort=False).transform(lambda s: s.ewm(alpha=a, adjust=False).mean())
    rl = lambda x, n, f: getattr(x.groupby(A.ticker, sort=False).rolling(n, min_periods=n), f)().reset_index(level=0, drop=True)
    pc = g.close.shift(1)
    upd, dnd = (A.close - pc).clip(lower=0), (pc - A.close).clip(lower=0)
    A["m_rsi2"] = 100 * ew(upd, 0.5) / (ew(upd, 0.5) + ew(dnd, 0.5) + 1e-12)
    c5 = g.close.shift(5)
    u5, d5 = (A.close - c5).clip(lower=0), (c5 - A.close).clip(lower=0)
    A["m_rsiw"] = 100 * ew(u5, 1 / 70) / (ew(u5, 1 / 70) + ew(d5, 1 / 70) + 1e-12)
    dv = rl(A.close / ((A.high + A.low) / 2) - 1, 2, "mean")
    A["m_dvb"] = (dv - rl(dv, 252, "min")) / (rl(dv, 252, "max") - rl(dv, 252, "min") + 1e-9)
    vu, vd = A.volume * (A.close > pc), A.volume * (A.close < pc)
    vf = A.volume * (A.close == pc)
    A["m_vr"] = 100 * (rl(vu, 25, "sum") + 0.5 * rl(vf, 25, "sum")) / (rl(vd, 25, "sum") + 0.5 * rl(vf, 25, "sum") + 1)
    A["m_psy"] = rl((A.close > pc).astype(float), 10, "sum")
    l0 = ew(A.close, 0.5)
    l1 = ew((l0.groupby(A.ticker).shift(1) - 0.5 * l0) / 0.5, 0.5)
    l2 = ew((l1.groupby(A.ticker).shift(1) - 0.5 * l1) / 0.5, 0.5)
    l3 = ew((l2.groupby(A.ticker).shift(1) - 0.5 * l2) / 0.5, 0.5)
    cu = (l0 - l1).clip(lower=0) + (l1 - l2).clip(lower=0) + (l2 - l3).clip(lower=0)
    cd = (l1 - l0).clip(lower=0) + (l2 - l1).clip(lower=0) + (l3 - l2).clip(lower=0)
    A["m_lrsi"] = cu / (cu + cd + 1e-12)
    mid = (A.high + A.low) / 2
    sn = (mid - rl(mid, 10, "min")) / (rl(mid, 10, "max") - rl(mid, 10, "min") + 1e-9)
    v = ew(2 * (sn - 0.5), 0.33).clip(-0.999, 0.999)
    A["m_fisher"] = ew(np.log((1 + v) / (1 - v)), 0.5)
    tr = np.maximum(A.high - A.low, np.maximum((A.high - pc).abs(), (A.low - pc).abs()))
    upm = A.high - A.high.groupby(A.ticker).shift(1); dnm = A.low.groupby(A.ticker).shift(1) - A.low
    pdm = upm * ((upm > dnm) & (upm > 0)); mdm = dnm * ((dnm > upm) & (dnm > 0))
    atr = ew(tr, 1 / 14)
    pdi, mdi = 100 * ew(pdm, 1 / 14) / (atr + 1e-9), 100 * ew(mdm, 1 / 14) / (atr + 1e-9)
    A["m_adx"] = ew(100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9), 1 / 14)
    mb, sb = rl(A.close, 20, "mean"), rl(A.close, 20, "std")
    A["m_bbz"] = (A.close - mb) / (sb + 1e-9)
    A["m_ibs"] = (A.close - A.low) / (A.high - A.low + 1e-9)
    A["m_er10"] = (A.close - g.close.shift(10)).abs() / (rl((A.close - pc).abs(), 10, "sum") + 1e-9)
    A["m_shinob"] = 100 * rl((A.high - pc).clip(lower=0), 26, "sum") / (rl((pc - A.low).clip(lower=0), 26, "sum") + 1e-9)

    if "open" in A.columns:                 # 적삼병은 시가가 있어야 한다 — 미장 us_scan 엔 시가가 없어 뺀다
        o, c, h = A.open, A.close, A.high
        po, pcl = g.open.shift(1), g.close.shift(1)
        bull = (c > o) & (c > pcl) & ((h - c) / c <= 0.01)
        inb = (o > np.minimum(po, pcl)) & (o < np.maximum(po, pcl))
        b3 = bull & inb
        A["red3"] = (b3 & b3.groupby(A.ticker).shift(1).fillna(False).astype(bool)
                     & b3.groupby(A.ticker).shift(2).fillna(False).astype(bool)).astype(float)
    else:
        A["red3"] = np.nan
    return A


def market_level(A, col, uni_q=0.6, top=0.9):
    """유동성 상위 40% 안: 그날 재료 상위 10% 의 20일 수익 중앙 − 나머지 중앙 (날마다) → 평균."""
    z = A[["date", col, "n20", "amt20"]].dropna()
    z = z[z.amt20.groupby(z.date).rank(pct=True) >= uni_q]
    if z[col].nunique() <= 2:                                   # 0/1 표시형은 '표시된 쪽' vs 나머지
        z["hi"] = z[col] > 0
    else:
        z["hi"] = z[col].groupby(z.date).rank(pct=True) >= top
    d = z.groupby(["date", "hi"]).n20.median().unstack()
    if True not in d.columns or False not in d.columns:
        return None
    dd = (d[True] - d[False]).dropna()
    dd = dd[dd.index >= "20160101"]
    if len(dd) < 100:
        return None
    ym = dd.groupby(dd.index.str[:6]).mean()
    tr, va = ym[ym.index <= "202212"], ym[ym.index >= "202301"]
    rng = np.random.default_rng(1)
    bs = [rng.choice(ym.values, len(ym)).mean() for _ in range(1000)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return dict(D=ym.mean(), lo=lo, hi=hi, tr=tr.mean(), va=va.mean(), n=int(z.hi.sum()),
                pos=int((ym.groupby(ym.index.str[:4]).mean() < 0).sum()), ny=ym.index.str[:4].nunique())


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    log("%s 재료 계산" % mk)
    A = features(mk)
    P("# 회피 신호 실측 · %s · %s" % (mk, time.strftime("%Y-%m-%d"))); P("")
    P("## ① 시장 전체 — 유동성 상위 40% 안, 그날 재료 상위 10%(표시형은 표시된 쪽) − 나머지의 20일 수익 중앙 차(%p)"); P("")
    P("음수면 '사지 마라' 가 맞다. 2016~ 월평균 · 월 부트스트랩 95% 구간 · 음수 해 수."); P("")
    P("| 재료 | 표시 건수 | 차이 | 95% 구간 | 학습 16~22 | 검증 23~ | 음수 해 |")
    P("|---|---|---|---|---|---|---|")
    ML = {}
    for c in AX:
        if A[c].notna().sum() == 0:
            P("| %s | 자료 없음 | | | | | |" % c); continue
        x = market_level(A, c); ML[c] = x
        if x:
            P("| %s | %s | %+.2f | %+.2f ~ %+.2f | %+.2f | %+.2f | %d/%d |" % (
                c, f"{x['n']:,}", x["D"], x["lo"], x["hi"], x["tr"], x["va"], x["pos"], x["ny"]))
    log("규칙 신호 붙이기")
    S = RS.kr_signals() if mk == "KR" else RS.us_signals()
    S = S[["date", "ticker", "rid", "r"]].merge(A[["date", "ticker"] + AX + MAT], on=["date", "ticker"], how="left")
    P(""); P("## ② 우리 규칙 안 — 같은 규칙·같은 달 재료 위 절반 − 아래 절반 거래 수익 중앙 차(%p)"); P("")
    P("음수 & 통과면 이 재료로 우리 규칙 신호를 걸러낼 후보(→ 계좌 얹기로 넘긴다)."); P("")
    P("| 재료 | 신호 | 묶음 | D | 95% 구간 | 학습 | 검증 | 규칙 같은방향 | 규칙별 D | 통과 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    rng = np.random.default_rng(0); n = 0
    for c in AX + MAT:
        x = RS.scan(S, c, rng)
        if not x:
            P("| %s | 표본 부족 | | | | | | | | |" % c); continue
        n += 1
        P("| %s | %s | %d | %+.2f | %+.2f ~ %+.2f | %+.2f | %+.2f | %d/%d | %s | %s |" % (
            c, f"{x['n']:,}", x["groups"], x["D"], x["lo"], x["hi"], x["dtr"], x["dva"], x["same"], x["nr"],
            " ".join("%s%+.1f" % (k, v) for k, v in sorted(x["per"].items())), "✅" if x["ok"] else ""))
    log_trials("avoid_scan_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), len(AX) + n)
    P(""); P("※ 재료 %d개를 5%% 유의수준으로 봤으니 운으로도 %.1f개쯤은 95%% 구간을 통과한다 — 학습·검증·규칙 방향 조건이 그걸 거른다." % (n, n * 0.05))
    P(""); P("총 %.0f초" % (time.time() - t0))
    rp = ROOT / "reports" / ("avoid_scan_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
