# -*- coding: utf-8 -*-
"""미장 규칙 다시 실측 — 규칙 자체 성적 + 같은 보유기간 S&P 500 과 견줌 (2026-10-07 사용자).
"미장 규칙들 한번 더 실측해봐, 규칙 자체 수익률·승률 체크하고 각 규칙별로 걸린 것들 매수기간 동안의 미장 지수랑도 비교"

패널: 폐지 포함 us_full_2007.pkl(us_surv_measure 와 같은 재료 · 주가 $3↑) · 신호가 나면 다 산다(돈 무한) · 같은 종목은 보유 중 다시 안 산다.
매수 = 신호 다음날 시가 · 매도 = 신호일 + 보유일 종가 · 비용 = 패널 cost(미장 0.10~0.60%) — n{h} 와 같은 정의.
지수 = 같은 매수일 시가 → 같은 매도일 종가의 S&P 500(FDR US500, 배당 빼고) 등락 → 초과 = 규칙 − 지수(비용은 규칙만).
규칙 정의는 사이트 지금 정의(2026-10-07):
  [상승장 신고가] S&P 60일선 위 · 52주 고점 -5% 안에 처음 · 3일 평균 거래량 ≤ 한 달 평균 · 거래대금 상위 40% · 그날 거래 주식 수 그중 상위 20% ·
                  5일 평균 거래량 ≤ 60일 평균 0.8배 · 가격 죽은 종목 제외 → 40일
  [낙폭과대]      S&P 60일선 아래 · 20일 -30%↓ · 거래량 20일 평균 2배↑ · 업종 60일 -10%↓ · 부채비율 ≤ 200% · 거래대금 ≥ $2M → 20일
  [저PBR 낙폭]    S&P 60일선 아래 · PBR ≤ 0.8 · 20일 -10%↓ · 거래량 2배↑ · 업종 60일 -10%↓ · 거래대금 ≥ $2M → 60일
  [자사주 낙폭]   52주 고점 -30%↓ + 20일 -20%↓ + 자사주 집행중(88일 안 SEC 보고)에 처음 · 거래대금 상위 40% → 60일
  [잔잔한 급등주] 1년 +120%↑ · 3·6·12개월 플러스 · 60일 평균 일간등락 ≤ 1.5% 에 처음 진입 후 3일 안 · 거래대금 상위 40% → 60일
  [실적 서프라이즈] 그날 발표분 서프라이즈 상위 30% · 다음 거래일 +3%↑ · 60거래일 전보다 -20%↓ 빠졌다가 하락분 1/4↑ 회복(아직 그 아래) · 거래대금 상위 40% → 60일
                  ⚠ 실적 자료(yfinance)는 지금 상장 종목뿐 — 이 규칙만 생존편향이 남는다
  [분사주]        10-12B 제출 1년 안에 새로 상장(패널 2007-06 이후 첫 등장) · 상장 25거래일째 신호 → 250일
  [S&P 편출]      편출 효력일 뒤 21거래일째 · 편출일 종가보다 안 오름 · 편출 뒤 30거래일↑ 시세 있음 → 40일
기간: 옛날 2009~15 · 학습 2016~22 · 검증 2023~.
    python research/us_rules_recheck.py
"""
import contextlib, glob, io, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
sys.argv = [sys.argv[0], "--panel", "us_full_2007.pkl", "--since", "20090101"]
_real = sys.stdout
with contextlib.redirect_stdout(io.StringIO()):
    import us_surv_measure as M
sys.stdout = _real; sys.stdout.reconfigure(encoding="utf-8")
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
t0 = time.time()
K = M.K; UP, DN = M.UP, M.DN
G = K.groupby("ticker", sort=False)
ud = np.array(sorted(K.date.unique()))
mask = pd.Series(True, index=K.index)
C = M.rules(mask, "u_all")
amtq = K.amt20.groupby(K.date).rank(pct=True); usliq = (amtq >= 0.60).fillna(False)
# [상승장 신고가] 9-30 좁힘: 거래 주식 수 상위 20%(유동 40% 안) · 5일 평균 거래량 ≤ 60일 평균 0.8배
volq = K.volume.where(usliq).groupby(K.date).rank(pct=True)
v5 = G.volume.transform(lambda s: s.rolling(5).mean()); v60 = G.volume.transform(lambda s: s.rolling(60).mean())
C["N1"] = (C["N1"] & (volq >= 0.8) & (v5 <= 0.8 * v60)).fillna(False)
# [실적 서프라이즈]
E = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(str(BASE / "data/us/analyst/*.pkl")))], ignore_index=True)
E["dt"] = pd.to_datetime(E["Earnings Date"], utc=True, errors="coerce")
E = E.dropna(subset=["dt", "Surprise(%)"]).copy()
E["edate"] = E.dt.dt.tz_convert("US/Eastern").dt.strftime("%Y%m%d")
E = E.drop_duplicates(["ticker", "edate"], keep="last")
E["bdate"] = [ud[i] if i < len(ud) else None for i in np.searchsorted(ud, E.edate.values, "right")]
E = E.dropna(subset=["bdate"]); E["sur"] = E["Surprise(%)"].astype(float)
E = E[E.groupby("bdate").sur.transform("size") >= 5]; E["q"] = E.groupby("bdate").sur.rank(pct=True)
peadq = (K.ticker + K.date).map(dict(zip(E.ticker + E.bdate, E.q)))
ret1 = (K.close / G.close.shift(1) - 1) * 100
c60 = G.close.shift(60); lo60 = G.close.transform(lambda s: s.rolling(60).min())
rec = (lo60 <= c60 * 0.8) & (K.close >= lo60 + 0.25 * (c60 - lo60)) & (K.close < c60)
C["N6"] = (usliq & (peadq >= 0.7) & (ret1 >= 3) & rec).fillna(False)
# [분사주] — research/spinoff.py 와 같은 사건 찾기(SEC 제출 목록의 Form 10-12B → 그 회사 티커가 패널에 처음 나온 날)
import json, re, zipfile
ev = {}
z = zipfile.ZipFile(BASE / "data/us/submissions.zip")
for nm in z.namelist():
    b = z.read(nm)
    if b'"10-12B' not in b: continue
    j = json.loads(b)
    cik = int(j.get("cik") or re.search(r"CIK(\d+)", nm).group(1))
    rec = j["filings"]["recent"] if "filings" in j else j
    dates = [d for f, d in zip(rec.get("form", []), rec.get("filingDate", [])) if str(f).startswith("10-12B")]
    if not dates: continue
    d0, tks = min(dates), set(j.get("tickers") or [])
    if cik in ev: d0 = min(d0, ev[cik][0]); tks |= ev[cik][1]
    ev[cik] = (d0, tks)
mm = pd.read_pickle(BASE / "data/us/sec_cik.pkl")
for c_, t_ in zip(mm.cik, mm.tickers):
    if c_ in ev and isinstance(t_, (list, tuple)): ev[c_] = (ev[c_][0], ev[c_][1] | set(t_))
try:
    tc = pd.read_pickle(BASE / "data/us/tiingo_cik.pkl")
    cc = [c for c in tc.columns if "cik" in c.lower()][0]; tcol = [c for c in tc.columns if "ticker" in c.lower()][0]
    for t_, c_ in zip(tc[tcol], tc[cc]):
        try: c_ = int(c_)
        except Exception: continue
        if c_ in ev: ev[c_] = (ev[c_][0], ev[c_][1] | {str(t_).upper()})
except Exception: pass
first = G.date.first(); n_ = G.cumcount()
okt = set()
for d0, tks in ev.values():
    d0 = d0.replace("-", "")
    for t_ in tks:
        f = first.get(str(t_).upper())
        if f is None or f <= "20070701" or f < d0: continue
        if (pd.Timestamp(f) - pd.Timestamp(d0)).days > 365: continue
        okt.add(str(t_).upper())
print("분사 상장 %d종목" % len(okt), flush=True)
C["N8"] = (K.ticker.isin(okt) & (n_ == 24)).values
# [S&P 편출]
SE = pd.read_csv(BASE / "data/us/sp500/ticker_start_end.csv", dtype=str)
endc = [c for c in SE.columns if "end" in c.lower()][0]; tkc = [c for c in SE.columns if "ticker" in c.lower() or c.lower() == "symbol"][0]
SE = SE.dropna(subset=[endc])
SE["end"] = pd.to_datetime(SE[endc], errors="coerce").dt.strftime("%Y%m%d")
n9 = np.zeros(len(K), bool)
kidx = pd.DataFrame({"index": np.arange(len(K)), "ticker": K.ticker.values, "date": K.date.values, "close": K.close.values})   # index = K 안 위치
byt = {t: g for t, g in kidx.groupby("ticker")}
for r in SE.dropna(subset=["end"]).itertuples():
    g = byt.get(getattr(r, tkc))
    if g is None: continue
    j = np.searchsorted(g.date.values, r.end, "left")
    if j >= len(g) or len(g) - j < 31: continue
    base = g.close.values[j - 1] if j > 0 and g.date.values[j - 1] <= r.end else g.close.values[j]
    k = j + 21
    if k < len(g) and g.close.values[k] <= base: n9[g["index"].values[k]] = True
C["N9"] = n9
NAME = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭", "N4": "자사주 낙폭", "N5": "잔잔한 급등주",
        "N6": "실적 서프라이즈", "N8": "분사주", "N9": "S&P 편출"}
HOLD = {"N1": 40, "N2": 20, "N3": 60, "N4": 60, "N5": 60, "N6": 60, "N8": 250, "N9": 40}
print("규칙 재료 %.1f분" % ((time.time() - t0) / 60), flush=True)
# ── 지수 ──
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2007-01-01"); IX["date"] = IX.index.strftime("%Y%m%d")
io_ = dict(zip(IX.date, IX.Open)); ic_ = dict(zip(IX.date, IX.Close))
cl = K.px.values; bu = K.buy.values; cost = K.cost.values if "cost" in K else np.full(len(K), 0.2)
di = K.di.values; tk = K.ticker.values


HAS = {h: (f"n{h}" in K.columns) for h in (20, 40, 60, 250)}
NV = {h: K[f"n{h}"].values for h in HAS if HAS[h]}
kpos = np.arange(len(K))


def trades(cond, h):
    """cond: K 와 같은 순서의 불 배열. 매도일 = 거래일 달력으로 신호일 + h. 수익 = 패널 n{h}(있으면) / 없으면 같은 종목 h 행 뒤 종가."""
    m = np.asarray(cond, bool) & (bu > 0)
    idx = kpos[m]; idx = idx[np.argsort(di[idx], kind="stable")]
    rows, last = [], {}
    for p in idx:
        t = tk[p]
        if last.get(t, -10 ** 9) >= di[p]: continue
        last[t] = di[p] + h
        if HAS.get(h):
            ret = NV[h][p]
            if ret != ret: continue
        else:
            q = p + h
            if q >= len(K) or tk[q] != t:                      # 보유 중 폐지 → 마지막 종가 / 아직 안 끝난 최근 신호는 뺀다
                q = p
                while q + 1 < len(K) and tk[q + 1] == t: q += 1
                if di[p] + h < len(ud) - 1 and K.grp.values[p] != "폐지": continue
            ret = (cl[q] / bu[p] - 1) * 100 - cost[p]
        if di[p] + h >= len(ud): continue
        d_in, d_out = ud[di[p] + 1], ud[di[p] + h]
        ixr = (ic_[d_out] / io_[d_in] - 1) * 100 if d_in in io_ and d_out in ic_ else np.nan
        rows.append((K.date.values[p], t, ret, ixr))
    return pd.DataFrame(rows, columns=["date", "ticker", "ret", "idx"])


PER = (("옛날 2009~15", "20090101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
P("# 미장 규칙 다시 실측 — 규칙 성적 + 같은 보유기간 S&P 500 · %s" % time.strftime("%Y-%m-%d")); P("")
P("- 폐지 포함 패널 us_full_2007 · 신호 나면 다 산다 · 같은 종목 보유 중 재매수 없음 · 비용 뒤(규칙만) · 지수 = 같은 매수일 시가→매도일 종가 S&P 500"); P("")
P("| 규칙 | 보유 | 기간 | 건수 | 평균 | 중앙 | 승률 | PF | 같은 기간 S&P 평균 | 초과 평균 | 지수 이긴 비율 |"); P("|---|---|---|---|---|---|---|---|---|---|---|")
ALL = {}
for rid in NAME:
    h = HOLD[rid]; Tr = trades(np.asarray(pd.Series(C[rid]).fillna(False).values, bool), h); ALL[rid] = Tr
    for lab, a, b in PER:
        z = Tr[(Tr.date >= a) & (Tr.date <= b)].dropna(subset=["ret"])
        if not len(z): P("| [%s] | %d일 | %s | 0 | | | | | | | |" % (NAME[rid], h, lab)); continue
        up, dn = z.ret[z.ret > 0].sum(), -z.ret[z.ret < 0].sum()
        zi = z.dropna(subset=["idx"])
        P("| [%s] | %d일 | %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %.2f | %+.2f%% | **%+.2f%%p** | %.0f%% |" % (
            NAME[rid], h, lab, len(z), z.ret.mean(), z.ret.median(), (z.ret > 0).mean() * 100, up / dn if dn else np.nan,
            zi.idx.mean(), (zi.ret - zi.idx).mean(), (zi.ret > zi.idx).mean() * 100))
P("")
P("## 해마다(2016~) — 규칙 평균 / 같은 기간 S&P / 초과"); P("")
yrs = [str(y) for y in range(2016, 2027)]
P("| 규칙 | " + " | ".join(yrs) + " |"); P("|---|" + "---|" * len(yrs))
for rid in NAME:
    z = ALL[rid].dropna(subset=["ret", "idx"]); z = z[z.date >= "20160101"]; g = z.groupby(z.date.str[:4])
    cells = []
    for y in yrs:
        if y in g.groups:
            x = g.get_group(y); cells.append("%+.1f / %+.1f (%d)" % (x.ret.mean(), x.idx.mean(), len(x)))
        else: cells.append("-")
    P("| [%s] | %s |" % (NAME[rid], " | ".join(cells)))
P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
pd.to_pickle(ALL, ROOT / "cache" / "us_rules_recheck.pkl")
log_trials("us_rules_recheck_%s" % time.strftime("%Y%m%d"), len(NAME))
(ROOT / "reports" / ("us_rules_recheck_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
