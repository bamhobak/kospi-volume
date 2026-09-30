# -*- coding: utf-8 -*-
"""오른 종목의 되밀림 / 내린 종목의 되오름 격자 실측 (2026-09-30 사용자 요청).

  오른 쪽: L거래일 전 종가(기준) 대비 그 뒤 최고 종가가 +X% 이상 → 오늘 종가가 상승분의 f 이상을 **처음** 반납(기준가 아래로는 안 감)
  내린 쪽: L거래일 전 종가 대비 그 뒤 최저 종가가 -X% 이하 → 오늘 종가가 하락분의 f 이상을 **처음** 회복(기준가 위로는 안 감)
  L = 20·40·60·120거래일(1·2·3·6개월) · X = 10·20·30% · f = 1/4·1/3·1/2·2/3 · 보유 H = 5·10·20·30거래일
  매수 = 신호 다음날 시가 · 매도 = H거래일째 종가 · 비용 차감 · 같은 칸 같은 종목은 20거래일 안 재신호 제외
  국장: 거래대금 상위 40% · 2005~ (폐지 포함) / 미장: 거래대금 상위 40% · $3↑ · 2008~ (폐지 포함 us_full_2007)
  잣대: 거래 평균·중앙·승률 + **같은 날 유니버스 대비 초과(중앙)** · 옛날 / 학습 16~22 / 검증 23~ · 해별 부호

    python research/retrace_grid.py            # 국장·미장 둘 다
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials

LS = [20, 40, 60, 120]; LN = {20: "1달", 40: "2달", 60: "3달", 120: "6달"}
XS = [10, 20, 30]
FS = [(1 / 4, "1/4"), (1 / 3, "1/3"), (1 / 2, "1/2"), (2 / 3, "2/3")]
HS = [5, 10, 20, 30]
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def load(mk):
    if mk == "KR":
        A, uni, _ = R.load_market("KR")
        D = pd.DataFrame({"ticker": A.ticker.values, "date": A.date.values, "c": A.close.values.astype(float),
                          "buy": A.buy.values.astype(float), "cost": A.cost.values.astype(float), "uni": uni.values})
        start = "20050101"
    else:
        K = pd.read_pickle(BASE / "data" / "us_full_2007.pkl")[["ticker", "date", "px", "buy", "cost", "rawclose", "amt20"]]
        K = K[K.date >= "20070601"]
        q = K.groupby("date").amt20.rank(pct=True)
        D = pd.DataFrame({"ticker": K.ticker.values, "date": K.date.values, "c": K.px.values.astype(float),
                          "buy": K.buy.values.astype(float), "cost": K.cost.values.astype(float),
                          "uni": ((q >= 0.6) & (K.rawclose >= 3)).values})
        del K
        start = "20080101"
    D = D.sort_values(["ticker", "date"]).reset_index(drop=True)
    return D, start


def roll(c, starts, L, fn):
    """종목별로 끊어서 [t-L, t] 창의 최대/최소(오늘 포함) — 창이 다 안 차면 NaN"""
    out = np.full(len(c), np.nan)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    for a, b in zip(starts[:-1], starts[1:]):
        if b - a > L:
            W = sw(c[a:b], L + 1)
            out[a + L:b] = W.max(1) if fn == "max" else W.min(1)
    return out


def run(mk):
    D, start = load(mk)
    log("%s 패널 %s행" % (mk, f"{len(D):,}"))
    tk = D.ticker.values
    starts = np.r_[0, np.where(tk[1:] != tk[:-1])[0] + 1, len(D)]
    same = lambda k: np.r_[tk[k:] == tk[:-k], np.zeros(k, bool)]      # t 와 t+k 가 같은 종목인가
    c = D.c.values; buy = D.buy.values; cost = D.cost.values
    FR, EX = {}, {}
    dates = D.date.values
    for H in HS:
        f = np.full(len(D), np.nan)
        ok = same(H)
        f[:-H][ok[:-H]] = (c[H:][ok[:-H]] / buy[:-H][ok[:-H]] - 1) * 100 - cost[:-H][ok[:-H]]
        f[~np.isfinite(buy) | (buy <= 0)] = np.nan
        FR[H] = f
        med = pd.Series(f[D.uni.values]).groupby(dates[D.uni.values]).median()
        EX[H] = f - pd.Series(dates).map(med).values
    per = np.where(dates <= "20151231", 0, np.where(dates <= "20221231", 1, 2))
    yr = pd.Series(dates).str[:4].values
    valid = D.uni.values & (dates >= start)
    prev_ok = np.r_[False, tk[1:] == tk[:-1]]
    rows = []
    for L in LS:
        log("%s L=%d" % (mk, L))
        okL = np.r_[np.zeros(L, bool), tk[L:] == tk[:-L]]
        base = np.r_[np.full(L, np.nan), c[:-L]]
        base[~okL] = np.nan
        hi = roll(c, starts, L, "max"); lo = roll(c, starts, L, "min")
        for dirn in ("up", "dn"):
            if dirn == "up":
                move = (hi / base - 1) * 100
                r = (hi - c) / (hi - base)
            else:
                move = (1 - lo / base) * 100
                r = (c - lo) / (base - lo)
            rprev = np.r_[np.nan, r[:-1]]; rprev[~prev_ok] = np.nan
            for fv, fl in FS:
                cross = (r >= fv) & (r < 1) & (rprev < fv) & valid
                for X in XS:
                    idx = np.where(cross & (move >= X))[0]
                    keep, last = [], {}
                    for i in idx:
                        t = tk[i]
                        if i - last.get(t, -10 ** 9) < 20:
                            continue
                        last[t] = i; keep.append(i)
                    keep = np.array(keep, int)
                    for H in HS:
                        rr = FR[H][keep]; ee = EX[H][keep]; pp = per[keep]; yy = yr[keep]
                        m = np.isfinite(rr)
                        rr, ee, pp, yy = rr[m], ee[m], pp[m], yy[m]
                        rec = dict(mk=mk, dir=dirn, L=L, X=X, f=fl, H=H, n=len(rr))
                        for p_ in (0, 1, 2):
                            w = pp == p_
                            rec["n%d" % p_] = int(w.sum())
                            rec["mean%d" % p_] = rr[w].mean() if w.sum() >= 30 else np.nan
                            rec["med%d" % p_] = np.median(rr[w]) if w.sum() >= 30 else np.nan
                            rec["win%d" % p_] = (rr[w] > 0).mean() * 100 if w.sum() >= 30 else np.nan
                            rec["ex%d" % p_] = np.median(ee[w]) if w.sum() >= 30 else np.nan
                        ys = pd.Series(rr).groupby(yy).mean()
                        rec["ypos"] = int((ys > 0).sum()); rec["ny"] = len(ys)
                        rows.append(rec)
    return pd.DataFrame(rows)


def fmt(x, s="%+.2f"):
    return s % x if x == x else "-"


def report(G, mk):
    nm = "국장" if mk == "KR" else "미장"
    P(""); P("# %s" % nm)
    for dirn, dl in (("up", "오른 종목이 상승분을 반납했을 때 매수"), ("dn", "내린 종목이 하락분을 회복했을 때 매수")):
        g = G[(G.mk == mk) & (G.dir == dirn)]
        P(""); P("## %s — %s" % (nm, dl)); P("")
        # 요약 ①: 칸 통과 — 학습·검증·옛날 모두 평균 > 0 & 초과(중앙) > 0 & 양수 해 60%↑ & 검증 표본 30↑
        ok = g[(g.mean0 > 0) & (g.mean1 > 0) & (g.mean2 > 0) & (g.ex0 > 0) & (g.ex1 > 0) & (g.ex2 > 0) & (g.ypos >= 0.6 * g.ny)]
        P("세 구간 모두 평균 수익 > 0 이고 같은 날 유니버스보다 나음(중앙 초과 > 0) · 양수 해 60%%↑ : **%d칸 / %d칸**" % (len(ok), len(g))); P("")
        # 요약 ②: 보유기간 × 반납 비율 — L·X 평균(검증)
        P("### 한눈에 — 검증(2023~) 거래 평균(%) · [기준기간·폭 12칸 평균]"); P("")
        P("| 반납 비율 \\ 보유 | " + " | ".join("%d일" % h for h in HS) + " |"); P("|---|" + "---|" * len(HS))
        for fv, fl in FS:
            P("| %s | " % fl + " | ".join(fmt(g[(g.f == fl) & (g.H == h)].mean2.mean()) for h in HS) + " |")
        P(""); P("같은 칸의 **같은 날 유니버스 대비 초과(중앙, %p)** — 학습 / 검증:"); P("")
        P("| 반납 비율 \\ 보유 | " + " | ".join("%d일" % h for h in HS) + " |"); P("|---|" + "---|" * len(HS))
        for fv, fl in FS:
            P("| %s | " % fl + " | ".join("%s / %s" % (fmt(g[(g.f == fl) & (g.H == h)].ex1.mean()), fmt(g[(g.f == fl) & (g.H == h)].ex2.mean())) for h in HS) + " |")
        P(""); P("### 상위 10칸 (학습 평균 기준, 세 구간 표본 30↑)"); P("")
        P("| 기준기간 | 폭 | 반납 | 보유 | 건수(옛·학·검) | 옛날 평균·승률 | 학습 평균·승률 | 검증 평균·승률 | 초과 옛·학·검 | 양수 해 |"); P("|---|---|---|---|---|---|---|---|---|---|")
        top = g.dropna(subset=["mean0", "mean1", "mean2"]).sort_values("mean1", ascending=False).head(10)
        for _, x in top.iterrows():
            P("| %s | %d%% | %s | %d일 | %d·%d·%d | %s · %.0f%% | %s · %.0f%% | %s · %.0f%% | %s · %s · %s | %d/%d |" % (
                LN[x.L], x.X, x.f, x.H, x.n0, x.n1, x.n2, fmt(x.mean0), x.win0, fmt(x.mean1), x.win1, fmt(x.mean2), x.win2,
                fmt(x.ex0), fmt(x.ex1), fmt(x.ex2), x.ypos, x.ny))
        if len(ok):
            P(""); P("### 세 구간 통과 칸 전부"); P("")
            P("| 기준기간 | 폭 | 반납 | 보유 | 건수(옛·학·검) | 옛날 | 학습 | 검증 | 초과 옛·학·검 | 양수 해 |"); P("|---|---|---|---|---|---|---|---|---|---|")
            for _, x in ok.sort_values("mean2", ascending=False).iterrows():
                P("| %s | %d%% | %s | %d일 | %d·%d·%d | %s · %.0f%% | %s · %.0f%% | %s · %.0f%% | %s · %s · %s | %d/%d |" % (
                    LN[x.L], x.X, x.f, x.H, x.n0, x.n1, x.n2, fmt(x.mean0), x.win0, fmt(x.mean1), x.win1, fmt(x.mean2), x.win2,
                    fmt(x.ex0), fmt(x.ex1), fmt(x.ex2), x.ypos, x.ny))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    mks = [m for m in ("KR", "US") if not [a for a in argv if a in ("KR", "US")] or m in argv]
    t0 = time.time()
    if "--report" in argv:
        G = pd.read_pickle(ROOT / "cache" / "retrace_grid.pkl")
    else:
        G = pd.concat([run(m) for m in mks], ignore_index=True)
        G.to_pickle(ROOT / "cache" / "retrace_grid.pkl")
    P("# 되밀림·되오름 격자 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("기준기간 1·2·3·6달 × 폭 10·20·30%% × 반납 1/4·1/3·1/2·2/3 × 보유 5·10·20·30일 × 오름/내림 = 시장당 384칸. "
      "다음날 시가 매수 · 비용 차감 · 같은 칸 같은 종목 20일 안 재신호 제외. 옛날 = 국장 2005~15 · 미장 2008~15.")
    for m in mks:
        report(G, m)
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    if "--report" not in argv:
        log_trials("retrace_grid_%s" % time.strftime("%Y%m%d"), len(G))
    (ROOT / "reports" / ("retrace_grid_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
