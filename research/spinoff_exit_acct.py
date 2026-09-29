# -*- coding: utf-8 -*-
"""미국 분사주(N8) 청산 방식별 **계좌** 비교 (2026-09-29, spinoff_exit.py 후속).

거래 단위로는 트레일링·좁은 손절이 전부 나쁘고, 고정 180·250일 · 익절 +50·+100% · '250일 뒤 트레일링 -15%' 가
보유일당 효율에서 비슷했다. 일찍 풀린 돈은 다른 규칙이 쓰므로 **계좌**가 가른다.
us_capture 와 같은 매일 평가 계좌(폐지 포함 · N1~N6 사이트 비중) + N8(5%·5자리) · 세 구간 · 100시드 짝비교.
청산 판정 종가 → 다음날 시가 체결(spinoff_exit.simulate 그대로).

    python research/spinoff_exit_acct.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
src = src.replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20090101"]')
src = src.replace('x = fdr.DataReader(sym, "2015-06-01")', 'x = fdr.DataReader(sym, "2008-06-01")')
src = src.replace('x = x[x.index >= "20160101"]', 'x = x[x.index >= "20090101"]')
exec(compile(src, "us_capture.py", "exec"))
# 분사 사건 — spinoff_acct.py 와 같은 코드
import json, re, zipfile
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

# 청산 시뮬 — spinoff_exit.simulate 와 같은 코드
def simulate(pxp, buyp, rule):
    """pxp: 보유 1일째~ 종가 배열(매수가 기준 비율 아님, 원가), buyp: 다음날 시가 배열(같은 길이). 반환 (수익비, 보유일, 끝남여부)"""
    b0 = rule.get("_b0")
    h = rule["hold"]; n = len(pxp)
    peak = b0
    for d in range(min(h, n)):
        c = pxp[d]
        if not (c == c and c > 0):
            continue
        peak = max(peak, c)
        k = d + 1                                                # 보유 k일째 종가
        trig = False
        if "trail" in rule and k >= rule.get("trail_after", 0) and c <= peak * (1 - rule["trail"] / 100):
            trig = True
        if "stop" in rule and c <= b0 * (1 - rule["stop"] / 100):
            trig = True
        if "take" in rule and c >= b0 * (1 + rule["take"] / 100):
            trig = True
        if trig:
            ex = buyp[d] if d < len(buyp) and buyp[d] == buyp[d] and buyp[d] > 0 else c   # 다음날 시가(없으면 그날 종가)
            return ex / b0, k + 1, True
    if n >= h:
        return pxp[h - 1] / b0, h, True
    return pxp[-1] / b0, n, False                                # 자료 끝 또는 폐지(아래서 가름)



NS = 100
PER = [("A 2009~15", "20090101", "20151231"), ("B 2016~20", "20160101", "20201231"), ("C 2021~", "20210101", "20991231")]
EXITS = [("고정 250일", dict(hold=250)), ("고정 180일", dict(hold=180)), ("익절 +50% (최대 250일)", dict(hold=250, take=50)),
         ("익절 +100% (최대 250일)", dict(hold=250, take=100)), ("250일 뒤 트레일링 -15% (최대 500일)", dict(hold=500, trail=15, trail_after=250)),
         ("손절 -30% (최대 250일)", dict(hold=250, stop=30))]
pxv, buyv, div = K.px.values, K.buy.values, K.di.values


def n8_paths(rule):
    P, keep = [], []
    for n, (t, b0) in enumerate(zip(N8.ticker, N8.buy)):
        ix = kidx[t][21:21 + 520]
        if not len(ix):
            continue
        r = dict(rule); r["_b0"] = b0
        ratio, days, fin = simulate(pxv[ix], buyv[ix], r)
        m = min(days, len(ix))
        rat = pxv[ix][:m] / b0
        if fin:
            rat = rat.copy(); rat[-1] = ratio                      # 청산가(다음날 시가)로 마지막 칸을 바꾼다
        P.append((div[ix][:m], rat)); keep.append(n)
    Z = N8.iloc[keep].reset_index(drop=True).copy()
    Z["hold"] = 10 ** 6                                            # 경로 끝(청산·폐지)에서 실현 — 자료 끝 보유는 평가만
    Z["ok"] = True
    return Z, P


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


PC, MXX = {**PCT, "N8": 5}, {**MX, "N8": 5}
RES = {"지금 (분사주 없음)": run(S, PATH, PCT, MX)}
for nm, rule in EXITS:
    log(nm)
    Z, P8 = n8_paths(rule)
    RES["+ 분사주 · " + nm] = run(pd.concat([S, Z], ignore_index=True), PATH + P8, PC, MXX)
B0 = RES["지금 (분사주 없음)"]; B1 = RES["+ 분사주 · 고정 250일"]
O = ["# 미국 분사주 청산 방식별 계좌 · %s" % time.strftime("%Y-%m-%d"), "",
     "N8 %d건 · 5%%·5자리 · 각 칸: 연수익 / 최대낙폭 / 하락 포착. 괄호 = **분사주 고정 250일 대비** 낙폭 얕은 시드 %% · 수익 높은 시드 %%." % len(N8), "",
     "| 구성 | " + " | ".join(p[0] for p in PER) + " |", "|---|" + "---|" * len(PER)]
for lbl, R in RES.items():
    cells = []
    for k in range(len(PER)):
        med = np.median(R[:, k], axis=0)
        if R is B0 or R is B1:
            cells.append("%+.1f%% / %.1f%% / %.2f" % tuple(med))
        else:
            cells.append("%+.1f%% / %.1f%% / %.2f (%.0f · %.0f)" % (*med, (R[:, k, 1] > B1[:, k, 1]).mean() * 100, (R[:, k, 0] > B1[:, k, 0]).mean() * 100))
    O.append("| %s | %s |" % (lbl, " | ".join(cells)))
rp = ROOT / "reports" / ("spinoff_exit_acct_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(O) + "\n", encoding="utf-8")
print("\n".join(O))
