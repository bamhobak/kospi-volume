# -*- coding: utf-8 -*-
"""2026-11-18 사용자 "원화 5천만 넣어놨거든 … 데이 규칙만 실제 플레이" — 5천만 계좌에서 데이 규칙 금액 설정별 비교.
acct_mix_1114.run 그대로(T6 → T5 → T1 순서로 그날 돈을 씀 · T1 예상 오차 · 체결 손해), 스윙·[반대매매]는 1주라 0 으로 둠.
창 2025-04-01~2026-10-08(강세장) · 값 만원.   python research/acct_day_5k_1118.py → research/reports/acct_day_5k_1118.md"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import acct_mix_1114 as MX
import day_acct_1e8_1110 as A
import day_acct_1e8_net_1110 as N
import t1_size_liq_1021 as SL

C = 5000e4
with contextlib.redirect_stdout(io.StringIO()):
    ab, cf = SL.fit(SL.liq_of_exec())
imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
E, ne = N.live_e()
T6, T5, _ = A.load(); T1 = N.t1_wide()
days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
T6g, T5g = {d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}
nd = len(days); yrs = nd / 250
OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
#        이름: (T1 기준, T5 기준, T6 하룻밤 한도, T6 종목당, k)
CFG = [("지금 설정값 그대로 (T1 30만·T5 100만·T6 5천만/500만)", (30e4, 100e4, 5000e4, 500e4, 0.10)),
       ("T5 는 1주 유지 (T1 30만·T6 5천만/500만)", (30e4, 0, 5000e4, 500e4, 0.10)),
       ("T5 1주 · T6 한도 4천만", (30e4, 0, 4000e4, 500e4, 0.10)),
       ("T5 1주 · T6 한도 3천만", (30e4, 0, 3000e4, 500e4, 0.10)),
       ("T5 1주 · T6 한도 2천만", (30e4, 0, 2000e4, 500e4, 0.10)),
       ("T5 1주 · T6 3천만/종목당 300만", (30e4, 0, 3000e4, 300e4, 0.10)),
       ("T5 1주 · T6 5천만/종목당 300만", (30e4, 0, 5000e4, 300e4, 0.10)),
       ("T5 1주 · T1 20만 · T6 5천만", (20e4, 0, 5000e4, 500e4, 0.10)),
       ("T5 1주 · T1 50만 · T6 5천만", (50e4, 0, 5000e4, 500e4, 0.10)),
       ("[갭하락]만 30만 (T6 도 1주)", (30e4, 0, 0, 500e4, 0.10)),
       ("[장후 낙폭]만 5천만/500만", (0, 0, 5000e4, 500e4, 0.10)),
       ("[장후 낙폭]만 3천만/500만", (0, 0, 3000e4, 500e4, 0.10))]
P("# 5천만 계좌 — 데이 규칙 금액 설정 비교 (%s~%s · %d거래일 · 값 만원 · 강세장 창)" % (days[0], days[-1], nd)); P("")
P("| 설정 | 합계 | 1년 % | T6·T5·T1 몫 | 달 중앙 | 최악의 달 | 플러스 달 | 최악의 날 | 손해 날 | 최대 낙폭 | 쓴 돈 평균·최대 | 2025(4~12) · 2026(1~10) |")
P("|---|---|---|---|---|---|---|---|---|---|---|---|")
cash = np.full(nd, C)
for lab, cfg in CFG:
    dd = np.mean([MX.run(T6g, T5g, T1, days, cash, *cfg, E, np.random.default_rng(s), imp, fill) for s in range(MX.SEEDS)], axis=0)
    dp = dd[:, :3].sum(1); tot = np.cumsum(dp); nav = C + tot
    mdd = (nav / np.maximum.accumulate(nav) - 1).min() * 100
    mon = pd.Series(dp, index=[d[:6] for d in days]).groupby(level=0).sum() / 1e4
    P("| %s | **%+.0f** | %+.0f%% | %+.0f·%+.0f·%+.0f | %+.0f | %+.0f | %.0f%% | %+.0f | %.0f%% | %.1f%% | %.0f·%.0f | %+.0f · %+.0f |" % (
        lab, tot[-1] / 1e4, tot[-1] / C / yrs * 100, dd[:, 0].sum() / 1e4, dd[:, 1].sum() / 1e4, dd[:, 2].sum() / 1e4, mon.median(), mon.min(), (mon > 0).mean() * 100,
        dp.min() / 1e4, (dp < 0).mean() * 100, mdd, dd[:, 3].mean() / 1e4, dd[:, 3].max() / 1e4,
        mon[mon.index.str[:4] == "2025"].sum(), mon[mon.index.str[:4] == "2026"].sum()))
P(""); P("- 스윙·[반대매매]·[단기과열]은 1주 시험이라 0 으로 둠. 돈 쓰는 순서: [장후 낙폭](전날 밤) → [장전 되돌림] → [갭하락](남은 돈).")
P("- 최악의 날·낙폭은 씨앗 %d개 평균이라 실제 하루는 더 나쁠 수 있음. 창이 강세장(2026 몰림)이라 낙관 숫자." % MX.SEEDS)
(ROOT / "reports" / "acct_day_5k_1118.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
