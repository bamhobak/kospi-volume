# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 지정가 문턱 비교를 과거 전체로(2026-11-10 사용자 "비교 기간을 과거 모든 날짜 다 적용해서").
과거엔 장전 예상 시장 갭 기록이 없어 두 판으로 본다:
  A 시장 갭을 정확히 알 때 — 실제 시장 대비 ≤ 문턱이면 시가에 사서 종가에 판다
  B 실전 예상 오차 반영 — 실전(10-13~) 날마다 '장전 예상 시장 갭 − 실제 시장 갭'(e) 을 재서, 과거 날마다 e 를 무작위로 뽑아
    '실제 시장 대비 ≤ 문턱 + e' 로 산다(지정가가 예상 시장 갭에 걸리므로). 시드 200번 평균. 어제 종가 오류(10월 토스 통합값)는 고쳐졌으니 안 넣는다.
그물 = 지금 설정(거래대금 상위 40% 중 아래 2/3 · 갭 하위 40% · 어제 거래량 하위 30%) · 비용 0.23 · 금액 판 = 30만 × 깊이(1~3) × 거래대금 배율(0.3~3), 돈 제한 없음
자료 = data/y1_hist.pkl(2016~2026-11-04, KRX 일봉 재료) · 9-14 뒤 종가는 네이버 통합값이 섞여 있음(작음)
    python research/t1_thr_hist_1110.py
"""
import sys, json, glob
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

THRS = (-1.5, -1.75, -2.0, -2.25, -2.5, -3.0)
COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def live_err():
    """실전 날마다 장전 예상 시장 갭(snap mgap) − 실제 시장 갭(1분봉 첫 봉 시가 ÷ 어제 KRX 종가, 유니버스 중앙)."""
    out = {}
    allm = sorted(p[-16:-8] for p in glob.glob(str(BASE / "data" / "m1" / "KR" / "day" / "*.parquet")))
    def m1(d):
        X = pd.read_parquet(BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % d), columns=["t", "ts", "o", "c", "v"])
        X = X[X.v > 0].sort_values(["t", "ts"]); g = X.groupby("t"); return g.o.first(), g.c.last()
    for f in sorted(glob.glob(str(BASE / "data" / "day" / "snap_*.json"))):
        d = f[-13:-5]
        if d < "20261013" or d not in allm: continue
        s = json.loads(Path(f).read_text(encoding="utf-8"))
        pv = max([x for x in allm if x < d], default=None)
        if pv is None or s.get("mgap") is None: continue
        o, _ = m1(d); _, cp = m1(pv)
        uni = [t for t in (s.get("all") or {}) if t in o.index and t in cp.index]
        if len(uni) < 300: continue
        out[d] = float(s["mgap"]) - float(np.median([(o[t] / cp[t] - 1) * 100 for t in uni]))
    return pd.Series(out)


def main():
    E = live_err()
    P("실전 예상 시장 갭 오차(예상 − 실제) %d일: 평균 %+.2f%%p · 중앙 %+.2f · 표준편차 %.2f · 범위 %+.2f~%+.2f\n" % (len(E), E.mean(), E.median(), E.std(), E.min(), E.max()))
    U = pd.read_pickle(BASE / "data" / "y1_hist.pkl")
    W = U[(U.date >= "20160101") & (U.liq <= 2 / 3) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.rgap <= 0.5)].dropna(subset=["oc", "rgap", "amt20"]).copy()
    W["ret"] = W.oc - COST
    W["amt"] = 30e4 * (-W.rgap).clip(1, 3) * (W.amt20 / W.groupby("date").amt20.transform("median")).clip(0.3, 3)
    days = np.array(sorted(U[U.date >= "20160101"].date.unique())); nd = len(days)
    yrs = W.date.str[:4]
    P("기간 %s~%s · %d거래일 · 그물 안 줄 %d\n" % (days[0], days[-1], nd, len(W)))

    def stat(Z, wt=None):
        wt = np.ones(len(Z)) if wt is None else wt
        n = wt.sum()
        if n <= 0: return None
        r = Z.ret.to_numpy()
        return dict(n=n, avg=(r * wt).sum() / n, win=((r > 0) * wt).sum() / n * 100, pnl=(Z.amt.to_numpy() * r / 100 * wt).sum())
    # A
    P("## A. 시장 갭을 정확히 알 때(실제 시장 대비 ≤ 문턱)\n")
    P("| 문턱 | 건수(하루) | 건당 | 승률 | 30만 기준 1년 손익 | 2016~22 건당 | 2023~ 건당 |"); P("|---|---|---|---|---|---|---|")
    for th in THRS:
        Z = W[W.rgap <= th]; s = stat(Z); a = Z[Z.date <= "20221231"]; b = Z[Z.date >= "20230101"]
        P("| %s%.2f | %d (%.1f) | %+.2f%% | %.0f%% | %+.0f만 | %+.2f%% | %+.2f%% |" % ("**지금** " if th == -1.5 else "", th, s["n"], s["n"] / nd, s["avg"], s["win"],
          s["pnl"] / 1e4 / (nd / 250), a.ret.mean(), b.ret.mean()))
    # B
    P("\n## B. 실전 예상 오차를 날마다 무작위로 입혔을 때(시드 200번 평균)\n")
    rng = np.random.default_rng(7)
    di = pd.Series(np.arange(nd), index=days); wi = di[W.date].to_numpy()
    res = {th: [] for th in THRS}; per = {th: [] for th in THRS}
    for _ in range(200):
        e = rng.choice(E.to_numpy(), nd); ew = e[wi]
        for th in THRS:
            m = (W.rgap.to_numpy() <= th + ew)
            Z = W[m]; s = stat(Z)
            res[th].append(s); per[th].append(Z.groupby(Z.date.str[:4]).ret.mean())
    P("| 문턱 | 건수(하루) | 건당 | 승률 | 30만 기준 1년 손익 | 연구 조건(실제 ≤ -1.5) 맞는 비율 |"); P("|---|---|---|---|---|---|")
    for th in THRS:
        R = res[th]; n = np.mean([r["n"] for r in R])
        # 연구 조건 비율(같은 시드 평균) — 다시 한 번 계산
        rr = []
        for k in range(20):
            e = np.random.default_rng(100 + k).choice(E.to_numpy(), nd)[wi]; m = W.rgap.to_numpy() <= th + e
            rr.append((W.rgap.to_numpy()[m] <= -1.5).mean() * 100)
        P("| %s%.2f | %.0f (%.1f) | %+.2f%% | %.0f%% | %+.0f만 | %.0f%% |" % ("**지금** " if th == -1.5 else "", th, n, n / nd, np.mean([r["avg"] for r in R]),
          np.mean([r["win"] for r in R]), np.mean([r["pnl"] for r in R]) / 1e4 / (nd / 250), np.mean(rr)))
    P("\n### B 해마다 건당(%%) — 시드 평균\n")
    ys = sorted(W.date.str[:4].unique())
    P("| 해 | " + " | ".join("%.2f" % th for th in THRS) + " |"); P("|---" * (len(THRS) + 1) + "|")
    for y in ys:
        P("| %s | %s |" % (y, " | ".join("%+.2f" % np.nanmean([s.get(y, np.nan) for s in per[th]]) for th in THRS)))
    (ROOT / "t1_thr_hist_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
