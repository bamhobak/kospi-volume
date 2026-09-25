# -*- coding: utf-8 -*-
"""규칙 안 스캔 통과 재료가 **낙폭의 대리지표**인지 가른다 (2026-09-25).

avoid_scan 에서 우리 규칙 안을 가른 외국 기법 지표(VR·시노하라·DV2·주봉 RSI·피셔·효율비·손실구간 IVOL)는
대부분 '더 과매도' 를 잰다. 예전 교훈: 규칙 안 최강 축은 '더 깊이 빠질수록 좋다' 였고 그건 새 정보가 아니었다.
그래서 같은 규칙·같은 달 묶음을 **20일 수익(ret20) 위/아래 절반**으로 한 번 더 쪼개고(=낙폭 통제) 다시 잰다.
두 번째 통제로 60일 고점 대비 낙폭(dd)도 본다. 통제 뒤에도 같은 방향·구간이 0 을 안 걸치면 '새 정보'.

    python research/mat_ctrl.py KR
    python research/mat_ctrl.py US
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import rule_scan as RS
import avoid_scan as AV
from verdict import log_trials

PICK = {"KR": ["m_er10", "ivol_l", "m_vr", "m_shinob", "m_dvb", "m_rsiw", "m_fisher", "m_psy"],
        "US": ["m_rsiw", "m_fisher", "m_shinob", "m_lrsi", "m_vr"]}


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    A = AV.features(mk)
    A["c_ret20"] = (A.close / A.groupby("ticker", sort=False).close.shift(20) - 1) * 100
    A["c_dd60"] = (A.close / A.groupby("ticker", sort=False).high.transform(lambda s: s.rolling(60, min_periods=20).max()) - 1) * 100
    cols = PICK[mk] + ["c_ret20", "c_dd60"]
    S = RS.kr_signals() if mk == "KR" else RS.us_signals()
    S = S[["date", "ticker", "rid", "r"]].merge(A[["date", "ticker"] + cols], on=["date", "ticker"], how="left")
    S["ym"] = S.date.str[:6]
    out = ["# 재료 낙폭 통제 · %s · %s" % (mk, time.strftime("%Y-%m-%d")), "",
           "D = 같은 규칙·같은 달(통제판은 + 같은 낙폭 절반) 안에서 재료 위 절반 − 아래 절반 거래 수익 중앙 차(%p).", "",
           "| 재료 | 낙폭과의 순위상관(규칙·달 안) | 통제 없음 D | 95% | ret20 통제 D | 95% | 학습/검증 | dd60 통제 D | 95% | 학습/검증 | 판정 |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    rng = np.random.default_rng(0)
    for m in PICK[mk]:
        z = S.dropna(subset=[m, "c_ret20"])
        rho = z.groupby(["rid", "ym"]).apply(lambda g: g[m].rank().corr(g.c_ret20.rank()) if len(g) >= 5 else np.nan).median()
        base = RS.scan(S, m, rng)
        res = [base]
        for ctl in ("c_ret20", "c_dd60"):
            T = S.dropna(subset=[ctl]).copy()
            half = T.groupby(["rid", "ym"])[ctl].rank(pct=True) > 0.5
            T["rid"] = T.rid + np.where(half, "_hi", "_lo")
            res.append(RS.scan(T, m, rng))
        f = lambda x: ("%+.2f" % x["D"], "%+.2f~%+.2f" % (x["lo"], x["hi"]), "%+.1f/%+.1f" % (x["dtr"], x["dva"])) if x else ("—", "—", "—")
        b, c1, c2 = f(res[0]), f(res[1]), f(res[2])
        keep = all(x and (x["lo"] > 0 or x["hi"] < 0) and np.sign(x["D"]) == np.sign(res[0]["D"])
                   and np.sign(x["dtr"]) == np.sign(x["D"]) and np.sign(x["dva"]) == np.sign(x["D"]) for x in res[1:]) if res[0] else False
        out.append("| %s | %+.2f | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            m, rho, b[0], b[1], c1[0], c1[1], c1[2], c2[0], c2[1], c2[2], "✅ 새 정보" if keep else "낙폭 대리/약함"))
    log_trials("mat_ctrl_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), 2 * len(PICK[mk]))
    out += ["", "총 %.0f초" % (time.time() - t0)]
    rp = ROOT / "reports" / ("mat_ctrl_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
