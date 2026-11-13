# -*- coding: utf-8 -*-
"""2026-11-14 사용자 "1주 테스트 중이니 더 봐 보자. 다른 이유가 있는 건지 상세하게 한 번 더" — [장전 되돌림] 10-09 뒤 부진의 원인 찾기.
비교: 안정기 OLD = 2025-07-01~2026-10-08 · 새 날 NEW = 2026-10-09~11-12(실전 기간 포함, 표본 늘리려고)
두 묶음: 규칙(지금 판: -3%p·얇음·순위 4·10개↑ 쉼) / 넓은 판(rpre ≤ -3 전부 — 같은 현상, 표본 큼)
가설: ① 수익 분해(08:40 뒤 더 빠짐? 시가에 덜 되돌아옴?) ② 어제 통합 종가에 섞인 장후 움직임 ③ 신호 종목 성격 변화
      ④ NXT 새 편입 종목 ⑤ 갭 구간 공시 ⑥ 시장 전체 되돌림 세기(달별 기울기) ⑦ 장전 참여 변화
    python research/t5_why_1114.py   (패널 C:/temp/kp/t5_full_panel_1114.pkl ← t5_full_1114.py)"""
import sys, glob, json, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent; C = ROOT / "cache"
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
CUM_MAX = 1_019_060_000
S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")

# ── 재료: KRX 어제 종가·20일 거래대금 ──
K = pd.read_parquet(C / "m1_daysum.parquet", columns=["t", "d", "o", "c", "val"]); K["t"] = K.t.astype(str); K["d"] = K.d.astype(str)
K = K[K.d >= "20250101"]; ks = []
for f in sorted(glob.glob(str(BASE / "data/m1/KR/day/*.parquet"))):
    d = Path(f).stem
    if d <= K.d.max(): continue
    x = pd.read_parquet(f, columns=["t", "ts", "o", "c", "v"]); x = x[x.v > 0].sort_values("ts"); x["val"] = x.c * x.v
    g = x.groupby("t").agg(o=("o", "first"), c=("c", "last"), val=("val", "sum")).reset_index(); g["d"] = d; ks.append(g)
K = pd.concat([K] + ks, ignore_index=True).sort_values(["t", "d"])
K["kpc"] = K.groupby("t").c.shift(1)
K["val20"] = K.groupby("t").val.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
S = S.merge(K[["t", "d", "kpc", "val20"]], on=["t", "d"], how="left")
# 장전 체결 봉 수(08:01~08:40)
KP = Path("C:/temp/kp")
PB = [str(KP / "pm_m1_1103.parquet")] + glob.glob(str(KP / "pm_parts" / "bars_*.parquet")) + glob.glob(str(KP / "pm_parts2" / "bars_*.parquet")) + glob.glob(str(C / "bf_nxt_pre" / "bars_*.parquet"))
B = pd.concat([pd.read_parquet(f, columns=["t", "d", "hm", "v"]) for f in PB], ignore_index=True)
B["t"] = B.t.astype(str); B["d"] = B.d.astype(str); B = B.drop_duplicates(["t", "d", "hm"])
nb = B[(B.hm <= 840) & (B.v > 0)].groupby(["t", "d"]).size().rename("nbar"); del B
S = S.merge(nb.reset_index(), on=["t", "d"], how="left")
first = S.groupby("t").d.min()
S["tenure"] = (pd.to_datetime(S.d) - pd.to_datetime(S.t.map(first))).dt.days      # NXT 장전 처음 보인 날부터
MK = {k: v.get("market") for k, v in json.load(open(C / "toss_nxt_kr.json", encoding="utf-8")).items()}
S["kosdaq"] = S.t.map(MK).eq("KOSDAQ")
# 갭 구간 공시(어제 15:30 뒤 ~ 오늘 08:40)
db = sqlite3.connect(str(BASE / "data/dart/kind_time.db"))
KD = pd.read_sql("select day, hm, kcode, title from kind where day >= '20250301'", db)
DAYS = sorted(S.d.unique()); PREV = {DAYS[i]: DAYS[i - 1] for i in range(1, len(DAYS))}
kd = {}
for r in KD.itertuples(): kd.setdefault(r.kcode, []).append((r.day, r.hm, r.title))
def kind_hit(t, d):
    p = PREV.get(d)
    if not p: return None
    for day, hm, ti in kd.get(t[:5], ()):
        if (day == p and hm > "1530") or (p < day < d) or (day == d and hm < "0840"): return ti
    return None
S["oK"] = (S.o / S.pT - 1) * 100                           # 08:40 → KRX 시가
S["drift"] = (S.vw5 / S.pT - 1) * 100                      # 08:40 → 매수 VWAP
S["ah"] = (S.tc_y / S.kpc - 1) * 100                       # 어제 KRX 종가 → 통합 종가(장후 움직임)
S["preK"] = (S.pT / S.kpc - 1) * 100                       # KRX 종가 기준 장전 움직임
S["rev"] = (S.o - S.pT) / (S.tc_y - S.pT)                   # 빠진 만큼 중 시가까지 되돌린 몫
S["px"] = S.pT

W = S[(S.rpre <= -3) & S.r_vwhs.notna()].copy()
W["kind"] = [kind_hit(t, d) for t, d in zip(W.t, W.d)]; W["hasK"] = W.kind.notna()
R = W[(W.cum <= CUM_MAX) & (W.rk <= 4) & (W.nsig < 10)]
per = lambda Z, a, b: Z[(Z.d >= a) & (Z.d <= b)]
OLD, NEW = ("20250701", "20261008"), ("20261009", "20261112")
Ro, Rn, Wo, Wn = per(R, *OLD), per(R, *NEW), per(W, *OLD), per(W, *NEW)
f = lambda z: "%+.2f%% · 승 %.0f%% · %d건" % (z.r_vwhs.mean(), (z.r_vwhs > 0).mean() * 100, len(z)) if len(z) else "-"
P("# [장전 되돌림] 10-09 뒤 부진 원인 찾기 (11-14)\n")
P("안정기 2025-07~10-08 · 새 날 10-09~11-12 · 규칙 = 지금 판 · 넓은 판 = 시장 대비 -3%p↓ 전부(얇음·순위·쉼 없음)\n")
P("| 묶음 | 안정기 | 새 날 |"); P("|---|---|---|")
P("| 규칙 | %s | %s |" % (f(Ro), f(Rn))); P("| 넓은 판 | %s | %s |" % (f(Wo), f(Wn)))
P("| 넓은 판 · 얇음만 | %s | %s |" % (f(Wo[Wo.cum <= CUM_MAX]), f(Wn[Wn.cum <= CUM_MAX])))
P("| 넓은 판 · 두꺼움 | %s | %s |" % (f(Wo[Wo.cum > CUM_MAX]), f(Wn[Wn.cum > CUM_MAX])))

P("\n## ⑥ 시장 전체 되돌림 세기 — 달별 (넓은 판 · 대조 = 시장 대비 -1~+1)\n")
P("| 달 | 넓은 판 건당 | 승률 | 건수 | 되돌린 몫 중앙 | 08:40→시가 | 대조(평범한 종목) 건당 | 기울기(전 종목 rpre<0: 시가 반등 ÷ 깊이) |"); P("|---|---|---|---|---|---|---|---|")
for m, g in S[S.d >= "20250501"].groupby(S.d.str[:6]):
    w = g[(g.rpre <= -3) & g.r_vwhs.notna()]; c0 = g[(g.rpre > -1) & (g.rpre < 1)].r_vwhs
    z = g[(g.rpre < 0) & g.oK.notna() & (g.rpre > -15)]
    sl = np.polyfit(z.rpre, z.oK, 1)[0] if len(z) > 30 else np.nan
    P("| %s | %+.2f%% | %.0f%% | %d | %.2f | %+.2f%% | %+.2f%% | %+.3f |" % (m, w.r_vwhs.mean(), (w.r_vwhs > 0).mean() * 100, len(w), w.rev.median(), w.oK.mean(), c0.mean(), sl))
P("\n(기울기 = 시장 대비 1%p 더 빠질 때 08:40→시가 반등이 몇 %p 더 커지나. 음수일수록 되돌림 강함)")

P("\n## ① 수익 분해 — 평균 (규칙 / 넓은 판)\n")
P("| 항목 | 규칙 안정기 | 규칙 새 날 | 넓은 판 안정기 | 넓은 판 새 날 |"); P("|---|---|---|---|---|")
for c, nm in (("pre", "어제 통합 종가 대비 장전(08:40)"), ("rpre", "시장 대비"), ("drift", "08:40 → 매수 VWAP(08:41~45)"), ("oK", "08:40 → KRX 시가"),
              ("r_vwhs", "수익(연구 기준)"), ("rev", "되돌린 몫(중앙)"), ("hs", "봉폭 절반(호가 근사)")):
    fn = (lambda s: s.median()) if c == "rev" else (lambda s: s.mean())
    P("| %s | %+.2f | %+.2f | %+.2f | %+.2f |" % (nm, fn(Ro[c]), fn(Rn[c]), fn(Wo[c]), fn(Wn[c])))

P("\n## ② 어제 종가에 섞인 장후 움직임(어제 KRX 종가 → 통합 종가)\n")
P("| 장후 움직임 | 넓은 판 안정기 | 넓은 판 새 날 | 규칙 안정기 | 규칙 새 날 |"); P("|---|---|---|---|---|")
for nm, lo, hi in (("장후 +1%↑ (장후에 오름)", 1, 99), ("-1 ~ +1%", -1, 1), ("장후 -1%↓", -99, -1)):
    sel = lambda Z: Z[(Z.ah > lo) & (Z.ah <= hi)]
    P("| %s | %s | %s | %s | %s |" % (nm, f(sel(Wo)), f(sel(Wn)), f(sel(Ro)), f(sel(Rn))))
P("\n장후 +1%%↑ 비중: 넓은 판 안정기 %.0f%% → 새 날 %.0f%% · 규칙 %.0f%% → %.0f%%" % (
  (Wo.ah > 1).mean() * 100, (Wn.ah > 1).mean() * 100, (Ro.ah > 1).mean() * 100, (Rn.ah > 1).mean() * 100))
P("KRX 종가 기준으로 다시 잰 깊이(장전÷어제 KRX 종가) 평균: 규칙 안정기 %+.2f → 새 날 %+.2f" % (Ro.preK.mean(), Rn.preK.mean()))

P("\n## ⑤ 갭 구간 공시(어제 15:30 ~ 오늘 08:40)\n")
P("| | 넓은 판 안정기 | 넓은 판 새 날 | 규칙 안정기 | 규칙 새 날 |"); P("|---|---|---|---|---|")
for nm, v in (("공시 있음", True), ("공시 없음", False)):
    P("| %s | %s | %s | %s | %s |" % (nm, f(Wo[Wo.hasK == v]), f(Wn[Wn.hasK == v]), f(Ro[Ro.hasK == v]), f(Rn[Rn.hasK == v])))
P("\n공시 있음 비중: 넓은 판 %.0f%% → %.0f%% · 규칙 %.0f%% → %.0f%%" % (Wo.hasK.mean() * 100, Wn.hasK.mean() * 100, Ro.hasK.mean() * 100, Rn.hasK.mean() * 100))

P("\n## ③④ 신호 종목 성격 — 중앙값 비교와 안정기 3분위 성적\n")
P("| 특성 | 규칙 안정기 중앙 | 규칙 새 날 중앙 | 안정기 넓은 판 3분위(낮음 / 중간 / 높음) | 새 날 넓은 판 3분위(같은 경계) |"); P("|---|---|---|---|---|")
FEAT = (("rpre", "시장 대비 깊이", 1), ("cum", "장전 누적 거래대금(억)", 1e8), ("val5", "매수 5분 거래대금(억)", 1e8), ("val20", "KRX 20일 거래대금(억)", 1e8),
        ("px", "가격(원)", 1), ("nbar", "장전 체결 봉 수", 1), ("hs", "봉폭 절반", 1), ("nsig", "그날 신호 수", 1), ("tenure", "NXT 장전 처음 본 뒤 날 수", 1),
        ("mpre", "시장 장전 중앙", 1), ("ah", "장후 움직임", 1))
for c, nm, sc in FEAT:
    q = Wo[c].quantile([1 / 3, 2 / 3]).to_numpy()
    def cells(Z):
        out = []
        for lo, hi in ((-1e18, q[0]), (q[0], q[1]), (q[1], 1e18)):
            z = Z[(Z[c] > lo) & (Z[c] <= hi)]; out.append("%+.2f(%d)" % (z.r_vwhs.mean(), len(z)) if len(z) else "-")
        return " / ".join(out)
    P("| %s | %.2f | %.2f | %s | %s |" % (nm, Ro[c].median() / sc, Rn[c].median() / sc, cells(Wo), cells(Wn)))
P("\n코스닥 비중: 규칙 %.0f%% → %.0f%% · 넓은 판 코스닥 %s → %s · 코스피 %s → %s" % (Ro.kosdaq.mean() * 100, Rn.kosdaq.mean() * 100,
  f(Wo[Wo.kosdaq]), f(Wn[Wn.kosdaq]), f(Wo[~Wo.kosdaq]), f(Wn[~Wn.kosdaq])))
P("NXT 새 편입(처음 본 뒤 60일 안): 넓은 판 안정기 %s · 새 날 %s / 오래된 종목: %s · %s" % (f(Wo[Wo.tenure <= 60]), f(Wn[Wn.tenure <= 60]), f(Wo[Wo.tenure > 60]), f(Wn[Wn.tenure > 60])))

P("\n## ⑦ 장전 참여 — 달별\n")
P("| 달 | 장전 거래 종목(하루 중앙) | 장전 누적 거래대금 중앙(억) | -3%p↓ 신호 중 얇음 비율 | 하루 신호 수(얇음) 평균 | 규칙 건수 |"); P("|---|---|---|---|---|---|")
for m, g in S[S.d >= "20250501"].groupby(S.d.str[:6]):
    w = g[g.rpre <= -3]; r = R[R.d.str[:6] == m]
    P("| %s | %d | %.2f | %.0f%% | %.1f | %d |" % (m, g.groupby("d").size().median(), g.cum.median() / 1e8, (w.cum <= CUM_MAX).mean() * 100,
      g.groupby("d").nsig.first().mean(), len(r)))

P("\n## 특성 회귀 — 안정기 넓은 판으로 맞추고 새 날에 대보기\n")
X = ["rpre", "mpre", "ah", "hs", "drift"]
A = Wo.dropna(subset=X + ["r_vwhs"]).copy(); A["lc"] = np.log1p(A.cum / 1e8); A["lv"] = np.log1p(A.val20.fillna(A.val20.median()) / 1e8); A["k"] = A.hasK.astype(float)
Bn = Wn.dropna(subset=X + ["r_vwhs"]).copy(); Bn["lc"] = np.log1p(Bn.cum / 1e8); Bn["lv"] = np.log1p(Bn.val20.fillna(A.val20.median()) / 1e8); Bn["k"] = Bn.hasK.astype(float)
X2 = X + ["lc", "lv", "k"]
Xa = np.column_stack([np.ones(len(A))] + [A[c].clip(A[c].quantile(.01), A[c].quantile(.99)) for c in X2])
b = np.linalg.lstsq(Xa, A.r_vwhs.clip(-20, 30).to_numpy(), rcond=None)[0]
Xb = np.column_stack([np.ones(len(Bn))] + [Bn[c].clip(A[c].quantile(.01), A[c].quantile(.99)) for c in X2])
P("계수: " + " · ".join("%s %+.3f" % (n, v) for n, v in zip(["상수"] + X2, b)))
P("새 날 넓은 판 %d건: 특성으로 맞춘 기대 %+.2f%% · 실제 %+.2f%% · 설명 안 되는 몫 %+.2f%%p" % (len(Bn), (Xb @ b).mean(), Bn.r_vwhs.mean(), Bn.r_vwhs.mean() - (Xb @ b).mean()))
P("(drift 는 매수 시점 뒤 정보라 원인 분해용 — 규칙에 쓸 수 없음)")

P("\n## 새 날 규칙 거래 하나씩\n")
P("| 날 | 종목 | 깊이 | 장후 | 08:40→VWAP | 08:40→시가 | 수익 | 공시 |"); P("|---|---|---|---|---|---|---|---|")
for r in Rn.sort_values("d").itertuples():
    P("| %s | %s | %+.1f | %+.1f | %+.2f | %+.2f | %+.2f | %s |" % (r.d[4:], r.t, r.rpre, r.ah, r.drift, r.oK, r.r_vwhs, (r.kind or "")[:24]))
(ROOT / "reports" / "t5_why_1114.md").write_text("\n".join(OUT), encoding="utf-8")
