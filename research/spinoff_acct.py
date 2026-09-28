# -*- coding: utf-8 -*-
"""미국 분사주를 미장 계좌의 새 규칙(N8)으로 넣으면 (2026-09-29, spinoff·spinoff2 후속).

N8: 분사 상장 21일째 다음날 시가 매수 · 250거래일 보유(손절·익절 없음). 연 9건 안팎이라 자리 3이면 충분하다.
us_capture 와 같은 매일 평가 계좌(폐지 포함 · N1~N6 사이트 비중) + N8 · 세 구간 · 100시드 짝비교.
판정(미리 정함): 세 구간 중 두 곳 이상 수익 높은 시드 60%↑ · 낙폭이 두 곳 이상 나빠지지 않음(얕은 시드 40%↑).

    python research/spinoff_acct.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
src = src.replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20090101"]')
src = src.replace('x = fdr.DataReader(sym, "2015-06-01")', 'x = fdr.DataReader(sym, "2008-06-01")')
src = src.replace('x = x[x.index >= "20160101"]', 'x = x[x.index >= "20090101"]')
exec(compile(src, "us_capture.py", "exec"))

import json, re, zipfile
NS = 100
PER = [("A 2009~15", "20090101", "20151231"), ("B 2016~20", "20160101", "20201231"), ("C 2021~", "20210101", "20991231")]
log("분사 사건(10-12B)")
z = zipfile.ZipFile(BASE / "data/us/submissions.zip")
ev = {}
for n in z.namelist():
    b = z.read(n)
    if b'"10-12B' not in b:
        continue
    j = json.loads(b)
    cik = int(j.get("cik") or re.search(r"CIK(\d+)", n).group(1))
    rec = j["filings"]["recent"] if "filings" in j else j
    ds = [d for f, d in zip(rec.get("form", []), rec.get("filingDate", [])) if str(f).startswith("10-12B")]
    if ds:
        d0, tk = min(ds), set(j.get("tickers") or [])
        if cik in ev:
            d0 = min(d0, ev[cik][0]); tk |= ev[cik][1]
        ev[cik] = (d0, tk)
m = pd.read_pickle(BASE / "data/us/sec_cik.pkl")
for c, t in zip(m.cik, m.tickers):
    if c in ev and isinstance(t, (list, tuple)):
        ev[c] = (ev[c][0], ev[c][1] | set(t))
first = K.groupby("ticker").date.first()
kidx = K.groupby("ticker", sort=False).indices
rows = []
for c, (d0, tks) in ev.items():
    for t in tks:
        t = str(t).upper()
        if t not in first.index or first[t] <= "20070701":
            continue
        if not (0 <= (pd.Timestamp(first[t]) - pd.Timestamp(d0.replace("-", ""))).days <= 365):
            continue
        ix = kidx[t]
        if len(ix) <= 21:
            continue
        s = ix[20]
        rows.append(dict(date=K.date.values[s], ticker=t, di=int(K.di.values[s]), buy=K.buy.values[s], cost=K.cost.values[s],
                         amt20=K.amt20.values[s], rid="N8", hold=250))
N8 = pd.DataFrame(rows).drop_duplicates("ticker")
N8 = N8[(N8.date >= "20090101") & (N8.buy > 0)].reset_index(drop=True)
P8 = [path(t, s, h, b) for t, s, h, b in zip(N8.ticker, N8.di, N8.hold, N8.buy)]
N8["ok"] = [len(p[0]) > 0 for p in P8]
S2 = pd.concat([S, N8], ignore_index=True); PATH2 = PATH + P8
log("  N8 %d건" % len(N8))


def seg(nav, lo, hi):
    s = nav[(nav.index >= lo) & (nav.index <= hi)]
    b = SPX.reindex(s.index).ffill()
    mo = s.groupby(s.index.str[:6]).last().pct_change().dropna() * 100
    mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(mo.index) * 100
    return (((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1) * 100, (s / s.cummax() - 1).min() * 100,
            mo[mb < 0].mean() / mb[mb < 0].mean())


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
for p, mm in ((5, 3), (5, 5), (10, 3)):
    VAR.append(("+ 분사주 %d%%·%d자리" % (p, mm), S2, PATH2, {**PCT, "N8": p}, {**MX, "N8": mm}))
RES = {}
for lbl, Sx, pa, pc, mx in VAR:
    log(lbl); RES[lbl] = run(Sx, pa, pc, mx)
B = RES[VAR[0][0]]
O = ["# 미국 분사주(N8) 계좌 얹기 · %s" % time.strftime("%Y-%m-%d"), "",
     "N8 %d건(2009~) · 각 칸: 연수익 / 최대낙폭 / 하락 포착. 괄호 = 지금 대비 낙폭 얕은 시드 %% · 수익 높은 시드 %%." % len(N8), "",
     "| 구성 | " + " | ".join(p[0] for p in PER) + " |", "|---|" + "---|" * len(PER)]
for lbl, *_ in VAR:
    R = RES[lbl]; cells = []
    for k in range(len(PER)):
        med = np.median(R[:, k], axis=0)
        cells.append(("%+.1f%% / %.1f%% / %.2f" % tuple(med)) if R is B else
                     ("%+.1f%% / %.1f%% / %.2f (%.0f · %.0f)" % (*med, (R[:, k, 1] > B[:, k, 1]).mean() * 100, (R[:, k, 0] > B[:, k, 0]).mean() * 100)))
    O.append("| %s | %s |" % (lbl, " | ".join(cells)))
O += ["", "※ 판정(미리 정함): 두 구간 이상 수익 높은 시드 60%↑ · 낙폭이 두 구간 이상에서 나빠지지 않음(얕은 시드 40%↑)."]
rp = ROOT / "reports" / ("spinoff_acct_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(O) + "\n", encoding="utf-8")
print("\n".join(O))
