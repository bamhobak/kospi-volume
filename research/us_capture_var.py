# -*- coding: utf-8 -*-
"""us_capture.py 후속 — 약한 고리를 빼거나 투입 상한을 낮추면 '내릴 때 덜 깨지나' (2026-09-29).

us_capture: 2021~ 미장 계좌 연 +3.7% · 상승 포착 0.59 · 하락 포착 0.89 · 최대낙폭 -31.6%.
[자사주 낙폭]이 단독 연 -4.2% · 하락 포착 1.64 · 최대낙폭 -58% 로 약한 고리였다.
최근 구간에만 맞추지 않게 **2016~2020 과 2021~ 을 따로** 본다(각 구간 첫날 1.0 에서 다시 시작하는 게 아니라
같은 경로를 잘라 구간 수익·낙폭을 잰다). 50시드 중앙.

    python research/us_capture_var.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
exec(compile(src, "us_capture.py", "exec"))


def seg_metrics(navs, lo, hi):
    out = []
    for c in navs.columns:
        s = navs[c][(navs.index >= lo) & (navs.index <= hi)]
        b = SPX.reindex(s.index).ffill()
        m = s.groupby(s.index.str[:6]).last().pct_change().dropna() * 100
        mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(m.index) * 100
        up, dn = mb > 0, mb < 0
        yrs = len(s) / 252
        out.append(dict(cagr=((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) * 100, mdd=(s / s.cummax() - 1).min() * 100,
                        upc=m[up].mean() / mb[up].mean(), dnc=m[dn].mean() / mb[dn].mean(),
                        e22=(s[s.index <= "20221012"].iloc[-1] / s[s.index >= "20220103"].iloc[0] - 1) * 100 if lo <= "20220103" <= hi else np.nan,
                        e25=(s[s.index <= "20250408"].iloc[-1] / s[s.index >= "20250219"].iloc[0] - 1) * 100 if lo <= "20250219" <= hi else np.nan,
                        e20=(s[s.index <= "20200323"].iloc[-1] / s[s.index >= "20200219"].iloc[0] - 1) * 100 if lo <= "20200219" <= hi else np.nan))
    return {k: np.nanmedian([o[k] for o in out]) for k in out[0]}


VAR = [("지금 (6규칙 · 투입 상한 100%)", S, 1.0),
       ("[자사주 낙폭] 빼기", S[S.rid != "N4"], 1.0),
       ("[자사주 낙폭]·[실적 서프라이즈] 빼기", S[~S.rid.isin(["N4", "N6"])], 1.0),
       ("6규칙 · 투입 상한 70%", S, 0.7),
       ("[자사주 낙폭] 빼기 · 투입 상한 70%", S[S.rid != "N4"], 0.7)]
OUT2 = ["# 미장 계좌 변형 — 약한 고리 빼기·투입 상한 · %s" % time.strftime("%Y-%m-%d"), "",
        "50시드 중앙 · 매일 평가 · 폐지 포함. 포착률은 S&P500 월수익 기준(1 미만 = 덜 움직임).", ""]
for lo, hi, nm in (("20160101", "20201231", "2016~2020"), ("20210101", "20991231", "2021~")):
    OUT2 += ["## %s" % nm, "",
             "| 구성 | 연수익 | 최대낙폭 | 상승 포착 | 하락 포착 | %s |" % ("2020 코로나 폭락" if nm.startswith("2016") else "2022 약세장 | 2025 관세 폭락"),
             "|---|---|---|---|---|---|" + ("" if nm.startswith("2016") else "---|")]
    for lbl, Sx, cap in VAR:
        PATH_X = [PATH[i] for i in Sx.index]
        Sx = Sx.reset_index(drop=True)
        navs = pd.concat([sim(Sx, PCT, MX, s, cap)[0] for s in range(50)], axis=1)
        m = seg_metrics(navs, lo, hi)
        tail = ("%+.1f%%" % m["e20"]) if nm.startswith("2016") else ("%+.1f%% | %+.1f%%" % (m["e22"], m["e25"]))
        OUT2.append("| %s | %+.1f%% | %.1f%% | %.2f | %.2f | %s |" % (lbl, m["cagr"], m["mdd"], m["upc"], m["dnc"], tail))
        log("%s %s %.1f%%" % (nm, lbl, m["cagr"]))
    b = BN["S&P500"]; s = b[(b.index >= lo) & (b.index <= hi)]
    OUT2.append("| (참고) S&P500 | %+.1f%% | %.1f%% | 1.00 | 1.00 | |" % (((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1) * 100,
                                                                       (s / s.cummax() - 1).min() * 100))
    OUT2.append("")
rp = ROOT / "reports" / ("us_capture_var_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(OUT2) + "\n", encoding="utf-8")
print("\n".join(OUT2))
