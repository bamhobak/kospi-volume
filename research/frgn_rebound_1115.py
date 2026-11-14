# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "외국인 보유량이 저점 대비 혹은 고점 대비 10% 혹은 20% 반동됐을 때 매수 테스트" — H0422.
자료: 월별 CSV(data/YYYY-MM.csv) foreign_ratio(외국인 지분율, 일별 2009~) — 발행주식 수가 그대로면 보유 수량 변화율 = 지분율 변화율.
사건(그날 장 끝 기준 → 다음 날 시가 매수, 공장 패널 sw5·sw20·sw60 비용 뒤):
  저점 반등: 지분율 ÷ 지난 L일 최저 - 1 이 처음 +X% 를 넘은 날   (외국인이 다시 사 모으기 시작)
  고점 하락: 지분율 ÷ 지난 L일 최고 - 1 이 처음 -X% 아래로 간 날 (외국인이 많이 판 뒤 — 역발상 매수)
  L = 60·120·250일 · X = 10·20% · 지분율 바닥 = 전부 / 2%↑ / 10%↑(지분율 아주 작은 종목은 몇 주만 사도 +20% 라)
말한 그대로 판 = L 250(1년)·X 10/20·전부·20일 보유. 나머지는 변형.
유니버스 = 공장 패널(거래대금 상위 40%) · 초과 = 같은 날 유니버스 같은 보유 평균 뺌 · 옛날 2010~15 / 학습 2016~22 / 검증 2023~.
겹침 = [외인 매집] P7 신호(같은 종목 ±5거래일).
    python research/memguard.py research/frgn_rebound_1115.py → research/reports/frgn_rebound_1115.md"""
import sys, glob, pickle
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, common as C
from verdict import log_trials
BASE = C.BASE
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
F = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "foreign_ratio"], dtype={"ticker": str, "date": str}) for f in fs if Path(f).stem >= "2008-06"], ignore_index=True)
F = F[F.foreign_ratio.notna()].sort_values(["ticker", "date"]).drop_duplicates(["ticker", "date"]).reset_index(drop=True)
F.loc[(F.foreign_ratio < 0) | (F.foreign_ratio > 100), "foreign_ratio"] = np.nan
g = F.groupby("ticker", sort=False).foreign_ratio
fr = F.foreign_ratio
bad = (fr / g.shift(1) - 1).abs() > 0.5                                  # 하루 ±50% 넘는 급변 = 자료 오류·분할 → 그날 사건 안 씀
EV = {}
for L in (60, 120, 250):
    lo = g.transform(lambda s: s.rolling(L, min_periods=int(L * 0.8)).min()); hi = g.transform(lambda s: s.rolling(L, min_periods=int(L * 0.8)).max())
    rl = fr / lo.where(lo > 0) - 1; rh = fr / hi.where(hi > 0) - 1
    prl = rl.groupby(F.ticker).shift(1); prh = rh.groupby(F.ticker).shift(1)
    for X in (0.10, 0.20):
        EV[("저점 반등", L, X)] = (rl >= X) & (prl < X) & ~bad
        EV[("고점 하락", L, X)] = (rh <= -X) & (prh > -X) & ~bad
print("사건 만듦", {k: int(v.sum()) for k, v in list(EV.items())[:4]}, flush=True)
U = lab.hist()
U = U[U.date >= "20100101"][["ticker", "date", "sw5", "sw20", "sw60"]].copy(); U["ticker"] = U.ticker.astype(str)
cal = sorted(U.date.unique()); nx = dict(zip(cal[:-1], cal[1:]))
MK = {h: U.groupby("date")[h].mean() for h in ("sw5", "sw20", "sw60")}
Ui = U.set_index(["ticker", "date"])
Z = pickle.load(open(r"C:\temp\kp\port_sig.pkl", "rb")); S = Z["S"]; dates = Z["dates"]; DI = {d: i for i, d in enumerate(dates)}
p7 = S[S.rid == "P7"].groupby("ticker").di.apply(np.array).to_dict()
SEG = (("옛날 10~15", "20100101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
rows = []
for (side, L, X), m in EV.items():
    for fl, fmin in (("전부", 0), ("지분율 2%↑", 2), ("지분율 10%↑", 10)):
        e = F[m & (fr >= fmin)][["ticker", "date"]].copy()
        e["date"] = e.date.map(nx); e = e.dropna()
        ix = pd.MultiIndex.from_arrays([e.ticker.values, e.date.values]); e = e[ix.isin(Ui.index)]
        if not len(e): continue
        R = Ui.loc[pd.MultiIndex.from_arrays([e.ticker.values, e.date.values])].reset_index()
        for h in ("sw5", "sw20", "sw60"):
            R["x" + h] = R[h] - R.date.map(MK[h])
        ov = np.mean([any(abs(DI.get(d, -99) - y) <= 5 for y in p7.get(t, [])) for t, d in zip(R.ticker, R.date)]) * 100 if len(R) < 20000 else np.nan
        for h in ("sw5", "sw20", "sw60"):
            r = dict(side=side, L=L, X=X, fl=fl, h=h, n=len(R), ov=ov)
            for lab_, a, b in SEG:
                q = R[(R.date >= a) & (R.date <= b)].dropna(subset=[h])
                yr = q.groupby(q.date.str[:4])["x" + h].mean()
                r[lab_] = (len(q), q[h].mean(), q[h].median(), (q[h] > 0).mean() * 100, q["x" + h].mean(),
                           q["x" + h].mean() / (q["x" + h].std() / np.sqrt(len(q))) if len(q) > 2 else np.nan, int((yr > 0).sum()), len(yr))
            rows.append(r)
log_trials("frgn_rebound_1115", len(rows))
fmt = lambda t: "%d · %+.2f / %+.2f · %.0f%% · 초과 %+.2f (t%.1f) · %d/%d해" % t if t[0] else "-"
P("# 외국인 보유량(지분율) 저점 반등 / 고점 하락 매수 — H0422 (2026-11-15)\n")
P("- 사건 = 지분율이 지난 L일 최저 대비 처음 +X% 넘은 날(저점 반등) / 최고 대비 처음 -X% 아래(고점 하락) · 다음 날 시가 매수 · 비용 뒤 · 유니버스 거래대금 상위 40%")
P("- 칸 = 건수 · 평균 / 중앙 · 승률 · 시장 대비 초과(t) · 초과 플러스 해 · 시행 %d칸(다중검정 누적에 더함)\n" % len(rows))
R0 = pd.DataFrame(rows)
P("## 말한 그대로 판 — 1년(250일) 저점·고점 · 지분율 전부 · 20일 보유\n")
P("| 사건 | X | 옛날 2010~15 | 학습 2016~22 | 검증 2023~ | [외인 매집] 겹침 |"); P("|---|---|---|---|---|---|")
for side in ("저점 반등", "고점 하락"):
    for X in (0.10, 0.20):
        r = R0[(R0.side == side) & (R0.L == 250) & (R0.X == X) & (R0.fl == "전부") & (R0.h == "sw20")].iloc[0]
        P("| %s | %d%% | %s | %s | %s | %.0f%% |" % (side, X * 100, fmt(r["옛날 10~15"]), fmt(r["학습 16~22"]), fmt(r["검증 23~"]), r.ov))
P("\n## 변형 전체 — 학습·검증 둘 다 초과 플러스인 칸만(초과 t 순)\n")
P("| 사건 | L | X | 지분율 | 보유 | 학습 2016~22 | 검증 2023~ | 옛날 2010~15 |"); P("|---|---|---|---|---|---|---|---|")
ok = R0[[(a[4] > 0 and b[4] > 0) if a[0] and b[0] else False for a, b in zip(R0["학습 16~22"], R0["검증 23~"])]].copy()
ok["tt"] = [min(a[5], b[5]) for a, b in zip(ok["학습 16~22"], ok["검증 23~"])]
for _, r in ok.sort_values("tt", ascending=False).head(25).iterrows():
    P("| %s | %d | %d%% | %s | %s | %s | %s | %s |" % (r["side"], r["L"], r["X"] * 100, r["fl"], r["h"], fmt(r["학습 16~22"]), fmt(r["검증 23~"]), fmt(r["옛날 10~15"])))
P("\n- 학습·검증 둘 다 초과 플러스 칸: %d / %d" % (len(ok), len(R0)))
(BASE / "research" / "reports" / "frgn_rebound_1115.md").write_text("\n".join(OUT), encoding="utf-8")
R0.to_pickle(r"C:\temp\kp\frgn_rebound_1115.pkl")
