# -*- coding: utf-8 -*-
"""미장 방어형(H0239)을 **계좌에 넣으면 내릴 때 덜 깨지나** (2026-09-29).

H0239: S&P 60일선 아래일 때 저변동(하위 20%)·대형(거래대금 상위 10%)·20일 -5%↑ → 40일 보유.
규칙 단위로는 4단계 탈락(같은 날 아무거나보다 못함 · 2026 음수). 하지만 목적이 수익이 아니라 **방어**라서 계좌로 한 번 더 본다.
us_capture 와 같은 매일 평가 계좌(폐지 포함 · N1~N6 사이트 비중) + N7(방어형) · 세 구간 · 100시드 짝비교.
채택 기준(미리 정함): 세 구간 모두 낙폭 얕은 시드 60%↑ · 하락 포착이 낮아짐 · 수익이 두 구간 이상에서 50%↑.

    python research/us_defense_acct.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
src = src.replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20090101"]')
src = src.replace('x = fdr.DataReader(sym, "2015-06-01")', 'x = fdr.DataReader(sym, "2008-06-01")')
src = src.replace('x = x[x.index >= "20160101"]', 'x = x[x.index >= "20090101"]')
exec(compile(src, "us_capture.py", "exec"))

NS = 100
PER = [("A 2009~15", "20090101", "20151231"), ("B 2016~20", "20160101", "20201231"), ("C 2021~", "20210101", "20991231")]
log("N7 방어형 신호")
ix = fdr.DataReader("US500", "2004-06-01"); ix = ix[ix.Close > 0]
dn = dict(zip(ix.index.strftime("%Y%m%d"), (ix.Close < ix.Close.rolling(60).mean()).values))
r1 = K.px.groupby(K.ticker, sort=False).pct_change() * 100
K["v20"] = r1.groupby(K.ticker, sort=False).transform(lambda s: s.rolling(20, min_periods=15).std())
K["dn60"] = K.date.map(dn).fillna(False).astype(bool)
vq = K.v20.groupby(K.date).rank(pct=True); aq = K.amt20.groupby(K.date).rank(pct=True)
cond = K.dn60 & (vq <= 0.2) & (aq >= 0.9) & (K.ret20 >= -5)
N7 = dedup_all(cond.fillna(False), 40, "N7")
N7 = N7[(N7.date >= "20090101") & N7.ticker.isin(PX)].reset_index(drop=True)
P7 = [path(t, s, h, b) for t, s, h, b in zip(N7.ticker, N7.di, N7.hold, N7.buy)]
N7["ok"] = [len(p[0]) > 0 for p in P7]
S2 = pd.concat([S, N7], ignore_index=True)
PATH2 = PATH + P7
log("  N7 %s건" % f"{len(N7):,}")


def seg(nav, lo, hi):
    s = nav[(nav.index >= lo) & (nav.index <= hi)]
    b = SPX.reindex(s.index).ffill()
    m = s.groupby(s.index.str[:6]).last().pct_change().dropna() * 100
    mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(m.index) * 100
    return (((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1) * 100, (s / s.cummax() - 1).min() * 100,
            m[mb < 0].mean() / mb[mb < 0].mean())


def run(Sx, paths, pct, mx):
    global PATH_X
    PATH_X = paths
    R = np.zeros((NS, len(PER), 3))
    for s in range(NS):
        nav = sim(Sx, pct, mx, s)[0]
        for k, (_, lo, hi) in enumerate(PER):
            R[s, k] = seg(nav, lo, hi)
    return R


VAR = [("지금 (6규칙)", S, PATH, PCT, MX)]
for p, m in ((5, 3), (5, 6), (10, 4)):
    VAR.append(("+ 방어형 %d%%·%d자리" % (p, m), S2, PATH2, {**PCT, "N7": p}, {**MX, "N7": m}))
RES = {}
for lbl, Sx, pa, pc, mx in VAR:
    log(lbl); RES[lbl] = run(Sx, pa, pc, mx)
B = RES[VAR[0][0]]
O = ["# 미장 방어형(N7) 계좌 얹기 · %s" % time.strftime("%Y-%m-%d"), "",
     "N7 신호 %s건(2009~) · 각 칸: 연수익 / 최대낙폭 / 하락 포착. 괄호 = 지금 대비 낙폭 얕은 시드 %% · 수익 높은 시드 %%." % f"{len(N7):,}", "",
     "| 구성 | " + " | ".join(p[0] for p in PER) + " |", "|---|" + "---|" * len(PER)]
for lbl, *_ in VAR:
    R = RES[lbl]; cells = []
    for k in range(len(PER)):
        med = np.median(R[:, k], axis=0)
        if R is B:
            cells.append("%+.1f%% / %.1f%% / %.2f" % tuple(med))
        else:
            cells.append("%+.1f%% / %.1f%% / %.2f (%.0f · %.0f)" % (*med, (R[:, k, 1] > B[:, k, 1]).mean() * 100, (R[:, k, 0] > B[:, k, 0]).mean() * 100))
    O.append("| %s | %s |" % (lbl, " | ".join(cells)))
O += ["", "※ 기준(미리 정함): 세 구간 모두 낙폭 얕은 시드 60%↑ · 하락 포착 낮아짐 · 두 구간 이상 수익 50%↑."]
rp = ROOT / "reports" / ("us_defense_acct_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(O) + "\n", encoding="utf-8")
print("\n".join(O))
