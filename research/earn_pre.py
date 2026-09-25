# -*- coding: utf-8 -*-
"""**미장 실적발표 직전 매수** — 발표 프리미엄(Barber 외 2013, 46개국)·발표 직전 반전(So·Wang 2014) (2026-09-26, 외국 기법 후속 ②).

우리 [실적 서프라이즈](N6)는 발표 **뒤**(서프라이즈 상위·갭 +3%)를 산다. 여기는 발표 **앞**이라 구간이 안 겹친다.

반응일 R: 발표 시각이 장 전(ET 12시 전)이면 발표일, 장 마감 후면 다음 거래일. 시각이 0시(모름)면 뺀다.
발표일은 대개 2~4주 전에 공지된다 — 5~10거래일 전에 안다고 가정한다(yfinance 과거 발표일 = 실제 발표일).
패널: us_scan(현재 상장 종목 · 수정주가 close · 다음날 시가 buy). 유니버스: 진입 전날 거래대금 상위 40% · $3↑.

  A  R-5 시가 매수 → R-1 종가 매도   (발표 전 기대 상승만, 발표 위험 없음)
  B  R-5 시가 매수 → R 종가 매도     (발표 프리미엄 — 발표 반응까지)
  C  R-10 시가 매수 → R-1 종가 매도
  D  So·Wang 반전: R-4~R-2 누적 수익이 같은 주 발표 종목 중 하위 10% → R-1 종가 매수 → R 종가 매도
  E  B 중 직전 발표 반응일 거래량이 20일 평균 대비 상위 30%(예상 거래량 큼, Frazzini·Lamont 2007)
비교: 같은 날 같은 구간을 유니버스에서 아무거나 산 중앙(드리프트 착시 점검) · 비용 = 패널 왕복 비용.

    python research/earn_pre.py
"""
import glob, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials, boot_ci

OUT = []
P = OUT.append


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    log("실적 발표일")
    E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))], ignore_index=True)
    E = E[E["Earnings Date"].notna() & E["EPS Estimate"].notna()].copy()
    E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce").dt.tz_convert("US/Eastern")
    E = E.dropna(subset=["dt"])
    E["hh"] = E.dt.dt.hour
    E = E[E.hh != 0]
    E["d"] = E.dt.dt.strftime("%Y%m%d"); E["amc"] = E.hh >= 12
    E = E.drop_duplicates(["ticker", "d"])
    log("  %s건 · 장전 %.0f%% · 장후 %.0f%%" % (f"{len(E):,}", (~E.amc).mean() * 100, E.amc.mean() * 100))

    log("패널")
    A = pd.read_pickle(BASE / "data/us_scan.pkl")
    A = A[((~A.pref.fillna(False)) & (A.rawclose >= 3)).fillna(False)][["ticker", "date", "close", "buy", "volume", "amt20", "cost"]]
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    cal = np.array(sorted(A.date.unique())); DI = {d: i for i, d in enumerate(cal)}
    A["di"] = A.date.map(DI).astype(int)
    A["uq"] = A.amt20.groupby(A.date).rank(pct=True)
    A["v20"] = A.volume / A.groupby("ticker", sort=False).volume.transform(lambda s: s.shift(1).rolling(20).mean())
    # 종목별 배열
    idx = A.groupby("ticker", sort=False).indices
    C, B, DIa, U, CO, V = A.close.values, A.buy.values, A.di.values, A.uq.values, A.cost.values, A.v20.values

    # 반응일 R (거래일 달력)
    pos = np.searchsorted(cal, E.d.values, "left")                  # 발표일 이상인 첫 거래일
    same = (pos < len(cal)) & (cal[np.minimum(pos, len(cal) - 1)] == E.d.values)
    rpos = np.where(E.amc.values, np.where(same, pos + 1, pos), pos)
    E["R"] = rpos
    E = E[(E.R < len(cal) - 1)]

    rows = []
    prev_v = {}
    for t, r, dd in sorted(zip(E.ticker.values, E.R.values, E.d.values), key=lambda x: (x[0], x[1])):
        ix = idx.get(t)
        if ix is None:
            continue
        di = DIa[ix]
        k = np.searchsorted(di, r)
        if k >= len(ix) or di[k] != r or k < 12:
            continue
        # 연속 거래일 확인(공백이 있으면 뺀다)
        if di[k] - di[k - 11] != 11:
            continue
        g = lambda j: ix[k + j]
        e5, e10 = g(-6), g(-11)                                      # 신호일(다음날 시가 매수)
        vol_prev = prev_v.get(t)
        prev_v[t] = V[g(0)]
        rec = dict(ticker=t, R=r, date=cal[di[k - 6]], uq5=U[e5], uq10=U[e10], cost=CO[e5], vprev=vol_prev,
                   A=(C[g(-1)] / B[e5] - 1) * 100, Bv=(C[g(0)] / B[e5] - 1) * 100, Cv=(C[g(-1)] / B[e10] - 1) * 100,
                   pre3=(C[g(-2)] / C[g(-5)] - 1) * 100, Dv=(C[g(0)] / C[g(-1)] - 1) * 100, dateD=cal[di[k - 1]],
                   dateC=cal[di[k - 11]])
        rows.append(rec)
    X = pd.DataFrame(rows)
    X = X[X.date >= "20130101"]
    log("  사건 %s건" % f"{len(X):,}")

    # 같은 구간 무작위 기준(유니버스 상위 40%, 같은 신호일)
    log("기준(같은 날 아무거나)")
    A["nx5c"] = A.groupby("ticker", sort=False).close.shift(-5)      # 신호일 R-6 → +5 = R-1 종가(A)
    A["nx6c"] = A.groupby("ticker", sort=False).close.shift(-6)      # +6 = R 종가(B)
    A["nx10c"] = A.groupby("ticker", sort=False).close.shift(-10)    # 신호일 R-11 → +10 = R-1 종가(C)
    A["pc1"] = A.groupby("ticker", sort=False).close.shift(-1)
    u = A[A.uq >= 0.6]
    ben = pd.DataFrame({"date": u.date.values, "A": (u.nx5c.values / u.buy.values - 1) * 100,
                        "B": (u.nx6c.values / u.buy.values - 1) * 100,
                        "C": (u.nx10c.values / u.buy.values - 1) * 100, "D": (u.pc1.values / u.close.values - 1) * 100})
    BEN = ben.groupby("date").median()

    X["benA"] = X.date.map(BEN.A); X["benB"] = X.date.map(BEN.B)
    X["benC"] = X.dateC.map(BEN.C)
    X["benD"] = X.dateD.map(BEN.D)
    X["Dq"] = X.groupby(X.dateD.str[:6] + X.dateD.str[6:8].astype(int).floordiv(7).astype(str)).pre3.rank(pct=True)
    vq = X.vprev.rank(pct=True)

    CFG = [("A · R-5 시가→R-1 종가(발표 전만)", X.uq5 >= 0.6, "A", "benA"),
           ("B · R-5 시가→R 종가(발표 반응 포함)", X.uq5 >= 0.6, "Bv", "benB"),
           ("C · R-10 시가→R-1 종가", X.uq10 >= 0.6, "Cv", "benC"),
           ("D · R-4~R-2 하위10% → R-1 종가→R 종가(So·Wang)", (X.uq5 >= 0.6) & (X.Dq <= 0.1), "Dv", "benD"),
           ("D 대조 · 상위10%", (X.uq5 >= 0.6) & (X.Dq >= 0.9), "Dv", "benD"),
           ("E · B 중 직전 반응 거래량 상위30%", (X.uq5 >= 0.6) & (vq >= 0.7), "Bv", "benB")]
    SEG = [("13~15", "20130101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"),
           ("전체 13~", "20130101", "20991231")]
    P("# 미장 실적발표 직전 매수 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("사건 %s건(2013~) · 수익 %%, **순 = 패널 왕복 비용 차감** · 기준 = 같은 날 같은 구간 유니버스 아무거나 중앙(비용 전)" % f"{len(X):,}"); P("")
    P("| 전략 · 구간 | n | 평균(순) | 중앙(순) | 승률(순) | 기준 중앙 | **중앙−기준(비용 전)** | 양수해(순 평균) | 월CI 하한(순) |")
    P("|---|---|---|---|---|---|---|---|---|")
    for nm, m, col, bc in CFG:
        z0 = X[m.fillna(False)].dropna(subset=[col])
        for lbl, lo, hi in SEG:
            z = z0[(z0.date >= lo) & (z0.date <= hi)]
            if len(z) < 30:
                P("| %s · %s | %d | 표본 부족 | | | | | | |" % (nm, lbl, len(z))); continue
            net = z[col] - z.cost
            yr = net.groupby(z.date.str[:4]).mean(); ym = net.groupby(z.date.str[:6]).mean()
            P("| %s · %s | %s | %+.2f | %+.2f | %.0f%% | %+.2f | **%+.2f** | %d/%d | %s |" % (
                nm, lbl, f"{len(z):,}", net.mean(), net.median(), (net > 0).mean() * 100, z[bc].median(),
                z[col].median() - z[bc].median(), (yr > 0).sum(), len(yr),
                ("%+.2f" % boot_ci(ym)) if len(ym) >= 12 else "-"))
    P(""); P("총 %.0f초" % (time.time() - t0))
    log_trials("earn_pre_%s" % time.strftime("%Y%m%d"), len(CFG))
    rp = ROOT / "reports" / ("earn_pre_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
