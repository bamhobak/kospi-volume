# -*- coding: utf-8 -*-
"""[갭 하락 조용주] 기본 금액 30·35·40만 나란히(2026-11-10 후속, 연구만) — day_acct_2e8_3e8_1110 모형 그대로(그물 -1.0 · 지정가 -2.0 ·
날 오차 부트스트랩 · 종목 오차 0.7) · 세 금액 모두 같은 씨앗 0~29.
  (a) 1억 · T5 100만 · T6 3천만·500만·k0.10   (b) 2억 안전안 · T5 100만 · T6 5천만·700만·k0.15
    python research/day_acct_t1base35_1110.py
"""
import io, contextlib, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "factory"))
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import day_acct_1e8_1110 as A, day_acct_1e8_net_1110 as N, day_acct_2e8_3e8_1110 as M

OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def main():
    import t1_size_liq_1021 as SL
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    E, _ = N.live_e()
    T6, T5, _ = A.load(); T1 = N.t1_wide()
    days = sorted(set(T1.date) | set(T5.d) | set(T6.d1)); days = [d for d in days if A.D0 <= d <= A.D1]
    ctx = ({d: g for d, g in T6.groupby("d1")}, {d: g for d, g in T5.groupby("d")}, T1, days, E, imp, fill)
    P("# [갭 하락 조용주] 기본 30·35·40만 · 같은 씨앗 %d개 · 그물 %.1f · 지정가 %.1f" % (M.SEEDS, M.NET, M.LIM))
    P("\n| 계좌 · 조합 | T1 기본 | 달 중앙 | 달 평균(씨앗 ±) | 최악의 달 | 최대 낙폭 | 2025 / 2026 중앙 | T1 몫(달) | 꽉 찬 날 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for lab, EQ, rest in (("1억 · T5 100만 · T6 3천만·500만", 1e8, (100e4, 3000e4, 500e4, 0.10)),
                          ("2억 · T5 100만 · T6 5천만·700만·k0.15", 2e8, (100e4, 5000e4, 700e4, 0.15))):
        for b1 in (30e4, 35e4, 40e4):
            m = M.evalc(ctx, EQ, (b1,) + rest)
            P("| %s | %d만 | %+.0f | %+.0f(±%.0f) | %+.0f | %.0f | %+.0f / %+.0f | %+.0f | %.0f%% |" % (
                lab, b1 / 1e4, m["med"], m["mean"], m["sd"], m["worst"], m["dd"], m["h25"], m["h26"], m["k1"], m["full"]))
    (ROOT / "day_acct_t1base35_1110.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
