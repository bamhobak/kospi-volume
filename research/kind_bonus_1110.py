# -*- coding: utf-8 -*-
"""H0401 장중 무상증자 결정 공시 직후 매수 — H0400(공시 직후 반응 180칸)에서 나온 유일한 후보를 변형으로 다시 잰다 (2026-11-10).
진입 지연(공시 분 뒤 1·2·5·10·30분) × 매도(30·60·120분·종가·다음 날 시가·다음 날 종가) · 해마다 · 직후 반응 조건 · 정정 공시 구분 · 큰 거래 몫.
비용 0.23 뒤. 1분봉 2022-12~2026-10-01. 학습 22.12~24 / 검증 25~.
    python research/kind_bonus_1110.py
"""
import os, re, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
COST = 0.23
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
E = pd.read_sql("select day, hm, kcode, corp, title from kind where market in ('유가증권','코스닥') and title like '%무상증자결정%' and day >= '20221201'", c)
E["hmi"] = E.hm.astype(int); E["fix"] = E.title.str.contains("정정")
E["both"] = E.title.str.contains("유상|유무상")
E = E[(E.hmi >= 901) & (E.hmi <= 1500)].sort_values(["kcode", "day", "hmi"]).drop_duplicates(["kcode", "day"])
P("# H0401 장중 무상증자 결정 공시 직후 매수(실제 첫 체결 기준으로 고침) · 2026-11-10"); P("")
P("- 장중(09:01~15:00) 무상증자결정 공시 %d건(2022-12~) · 정정 %d · 유상 겸한 것 %d" % (len(E), E.fix.sum(), E.both.sum()))
LAGS = (1, 2, 5, 10, 30); EXITS = (30, 60, 120)
rows = []
for kc, g in E.groupby("kcode"):
    f = BASE / "data" / "m1" / "KR" / "bf" / (kc + "0.parquet")
    if not f.exists(): continue
    B = pd.read_parquet(f, columns=["ts", "o", "h", "c", "v"])
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s"); B["day"] = k.strftime("%Y%m%d"); B["mi"] = k.hour * 60 + k.minute
    days = {d: x for d, x in B.groupby("day", sort=True)}; dl = sorted(days); pos = {d: j for j, d in enumerate(dl)}
    for day, hmi, corp, title, fix, both in zip(g.day, g.hmi, g.corp, g.title, g.fix, g.both):
        if day not in pos or pos[day] == 0: continue
        X = days[day]; mi = X.mi.values; o = X.o.values; cc = X.c.values; v = X.v.values; h = X.h.values
        m = (hmi // 100) * 60 + hmi % 100
        pc = float(days[dl[pos[day] - 1]].c.values[-1])
        j0 = np.searchsorted(mi, m, side="right") - 1
        if j0 < 0: continue
        p0 = float(cc[j0]); a30 = float((cc[max(0, j0 - 29):j0 + 1] * v[max(0, j0 - 29):j0 + 1]).sum())
        nx = days[dl[pos[day] + 1]] if pos[day] + 1 < len(dl) else None
        r = dict(t=kc + "0", corp=corp, date=day, hm=hmi, fix=bool(fix), both=bool(both), pre=(p0 / pc - 1) * 100, a30=a30, dayhi=(float(h.max()) / pc - 1) * 100,
                 dayc=(float(cc[-1]) / pc - 1) * 100)
        for L in LAGS:
            je = np.searchsorted(mi, m + 1 + L, side="left")           # 끝 시각 m+1+L 봉의 시가 = 공시 분이 끝나고 L-1~L 분 뒤
            if je >= len(mi): continue
            je0 = je
            while je < len(mi) and v[je] <= 0: je += 1                 # ⚠ 거래량 0 인 채운 봉엔 못 산다(무상증자 결정 = 30분 매매정지) — 실제 첫 체결 봉에서 산다
            if je >= len(mi) - 1: continue
            r["wait_%d" % L] = int(mi[je] - mi[je0])
            pe = float(o[je])
            r["r0_%d" % L] = (pe / p0 - 1) * 100; r["lim_%d" % L] = (pe / pc - 1) * 100
            r["a5_%d" % L] = float((cc[je:je + 5] * v[je:je + 5]).sum())                     # 매수 뒤 5분 거래대금(살 수 있는 크기)
            for kx in EXITS:
                jx = np.searchsorted(mi, mi[je] + kx, side="right") - 1
                r["x%d_%d" % (kx, L)] = (float(cc[jx]) / pe - 1) * 100 - COST if jx > je else np.nan
            r["xc_%d" % L] = (float(cc[-1]) / pe - 1) * 100 - COST if mi[-1] >= 920 and je < len(mi) - 1 else np.nan
            if nx is not None:
                r["xno_%d" % L] = (float(nx.o.values[0]) / pe - 1) * 100 - COST; r["xnc_%d" % L] = (float(nx.c.values[-1]) / pe - 1) * 100 - COST
        rows.append(r)
Z = pd.DataFrame(rows); Z.to_pickle("C:/temp/kp/kind/bonus.pkl")
Z["y"] = Z.date.str[:4]
P("- 1분봉이 있는 사건 %d건 · 해마다 %s" % (len(Z), Z.y.value_counts().sort_index().to_dict())); P("")
PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))
def cell(z, col):
    z = z.dropna(subset=[col])
    if len(z) < 8: return "—"
    x = z[col]; top = x.nlargest(3).sum() / x.sum() * 100 if x.sum() > 0 else float("nan")
    return "%d건 **%+.2f** (중앙 %+.2f·승 %.0f%%·최악 %+.1f·위3건 몫 %.0f%%)" % (len(z), x.mean(), x.median(), (x > 0).mean() * 100, x.min(), top)
base = Z[~Z.fix]
for nm, cond in (("① 전부(정정 뺌 · 상한가 근처 매수 뺌)", lambda L: base["lim_%d" % L] < 27),
                 ("② 직후 반응 ±0.3% 안(H0400 과 같은 조건)", lambda L: (base["lim_%d" % L] < 27) & (base["r0_%d" % L].abs() <= 0.3)),
                 ("③ 직후 반응 +3% 안쪽(아직 덜 오른 것)", lambda L: (base["lim_%d" % L] < 27) & (base["r0_%d" % L] <= 3)),
                 ("④ 직후 반응 +3% 넘음(이미 뜀)", lambda L: (base["lim_%d" % L] < 27) & (base["r0_%d" % L] > 3))):
    P("## " + nm); P("")
    P("| 진입(공시 뒤) | 매도 | 학습 22.12~24 | 검증 25~ |"); P("|---|---|---|---|")
    for L in LAGS:
        m = cond(L).fillna(False)
        for ex, en in (("x30", "30분"), ("x60", "60분"), ("x120", "120분"), ("xc", "종가"), ("xno", "다음 날 시가"), ("xnc", "다음 날 종가")):
            col = "%s_%d" % (ex, L)
            P("| %d분 | %s | %s |" % (L, en, " | ".join(cell(base[m & (base.date >= a) & (base.date <= b)], col) for _, a, b in PER)))
    P("")
P("- 매수까지 기다린 시간(진입 2분 기준): 중앙 %d분 · 10분 넘게 %d건/%d · 그동안 뜬 폭(직후 반응) 중앙 %+.1f%% 평균 %+.1f%%" % (base.wait_2.median(), int((base.wait_2 > 10).sum()), int(base.wait_2.notna().sum()), base.r0_2.median(), base.r0_2.mean())); P("")
P("## 해마다 — ③(직후 +3% 안쪽) · 진입 2분 · 종가 매도 / 60분 매도"); P("")
m = ((base.lim_2 < 27) & (base.r0_2 <= 3)).fillna(False)
for y, g in base[m].groupby("y"):
    P("- %s: 종가 %s · 60분 %s" % (y, cell(g, "xc_2"), cell(g, "x60_2")))
P(""); P("## 정정 공시만(대조 — 새 소식이 아님) · 진입 2분"); P("")
fx = Z[Z.fix & (Z.lim_2 < 27)]
P("- 종가 %s · 60분 %s" % (cell(fx, "xc_2"), cell(fx, "x60_2")))
P(""); P("## 살 수 있는 크기 — ③ · 진입 2분: 매수 뒤 5분 거래대금"); P("")
g = base[m]
P("- 중앙 %s원 · 하위 25%% %s원 · 1천만 미만 %d건/%d" % (f"{g.a5_2.median():,.0f}", f"{g.a5_2.quantile(.25):,.0f}", int((g.a5_2 < 1e7).sum()), len(g)))
for lo, hi, nm2 in ((0, 3e7, "5분 거래대금 3천만 미만"), (3e7, 3e8, "3천만~3억"), (3e8, 1e15, "3억↑")):
    P("- %s: %s" % (nm2, cell(g[(g.a5_2 >= lo) & (g.a5_2 < hi)], "xc_2")))
P(""); P("## 낱개(③ · 진입 2분) — 최근 25건"); P("")
P("| 날짜 | 시각 | 종목 | 공시 전 등락 | 직후 반응 | 60분 | 종가 | 다음 날 시가 | 그날 고가 | 5분 거래대금(억) |"); P("|---|---|---|---|---|---|---|---|---|---|")
for _, r in g.sort_values("date").tail(25).iterrows():
    P("| %s | %04d | %s | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f | %+.1f | %.1f |" % (r.date, r.hm, r.corp, r.pre, r.r0_2, r.x60_2, r.xc_2, r.get("xno_2", np.nan), r.dayhi, r.a5_2 / 1e8))
(ROOT / "reports" / "kind_bonus_1110.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
from verdict import log_trials
log_trials("kind_bonus_1110", 4 * len(LAGS) * 6)
