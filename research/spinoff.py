# -*- coding: utf-8 -*-
"""**미국 분사(스핀오프) 회사** (2026-09-29, 사용자 제안 목록 10번 — 알려진 이상현상: 상장 초기 기관의 기계적 매도 뒤 회복).

사건 찾기: SEC 제출 목록(data/us/submissions.zip, 99만 회사)에서 **Form 10-12B**(분사 등록 서류)를 낸 회사 →
  그 회사 티커가 폐지 포함 패널(us_full_2007)에 **처음 나타난 날** = 분사 상장일(10-12B 제출 후 1년 안이어야 인정).
  패널 시작(2007-06) 전부터 있던 티커는 뺀다. 티커 ↔ CIK: sec_cik.pkl · 제출 파일의 tickers · tiingo_cik.pkl.
수익: 상장 k일째(1·21일째) 다음날 시가 매수 → 60·120·250거래일 뒤 종가(비용 차감) · 비교 = 같은 날 유동성 상위 40% 아무거나 중앙.
미장 계좌 숙제(하락 포착 0.89)에 맞는지 — 시장 방향보다 사건으로 움직이나 — 도 본다(S&P 하락 구간 성적).

    python research/spinoff.py
"""
import io, json, re, sys, time, zipfile, contextlib, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials, boot_ci


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    log("SEC 제출 목록에서 10-12B 찾기")
    z = zipfile.ZipFile(BASE / "data/us/submissions.zip")
    ev = {}                                              # cik -> (첫 10-12B 날짜, tickers)
    for n in z.namelist():
        b = z.read(n)
        if b'"10-12B' not in b:
            continue
        j = json.loads(b)
        cik = int(j.get("cik") or re.search(r"CIK(\d+)", n).group(1))
        rec = j["filings"]["recent"] if "filings" in j else j
        dates = [d for f, d in zip(rec.get("form", []), rec.get("filingDate", [])) if str(f).startswith("10-12B")]
        if not dates:
            continue
        d0, tk = min(dates), set(j.get("tickers") or [])
        if cik in ev:
            d0 = min(d0, ev[cik][0]); tk |= ev[cik][1]
        ev[cik] = (d0, tk)
    log("  10-12B 낸 회사 %d곳" % len(ev))
    m = pd.read_pickle(BASE / "data/us/sec_cik.pkl")
    for c, t in zip(m.cik, m.tickers):
        if c in ev and isinstance(t, (list, tuple)):
            ev[c] = (ev[c][0], ev[c][1] | set(t))
    try:
        tc = pd.read_pickle(BASE / "data/us/tiingo_cik.pkl")
        cc = [c for c in tc.columns if "cik" in c.lower()][0]; tcol = [c for c in tc.columns if "ticker" in c.lower()][0]
        for t, c in zip(tc[tcol], tc[cc]):
            try:
                c = int(c)
            except Exception:
                continue
            if c in ev:
                ev[c] = (ev[c][0], ev[c][1] | {str(t).upper()})
    except Exception as e:
        log("  tiingo_cik 못 씀: %r" % e)

    log("패널")
    with contextlib.redirect_stdout(io.StringIO()):
        K = pd.read_pickle(BASE / "data/us_full_2007.pkl")[["ticker", "date", "px", "buy", "cost", "amt20", "rawclose"]]
    K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
    ud = np.array(sorted(K.date.unique())); DI = {d: i for i, d in enumerate(ud)}
    K["di"] = K.date.map(DI).astype(np.int32)
    first = K.groupby("ticker").date.first()
    idx = K.groupby("ticker", sort=False).indices
    rows = []
    for c, (d0, tks) in ev.items():
        d0 = d0.replace("-", "")
        for t in tks:
            t = str(t).upper()
            if t not in first.index:
                continue
            f = first[t]
            if f <= "20070701":
                continue
            dd = (pd.Timestamp(f) - pd.Timestamp(d0)).days
            if not (0 <= dd <= 365):
                continue
            rows.append((t, c, d0, f))
    E = pd.DataFrame(rows, columns=["ticker", "cik", "d10", "first"]).drop_duplicates("ticker")
    log("  분사 상장 사건 %d건" % len(E))

    uq = K.amt20.groupby(K.date).rank(pct=True)
    O = ["# 미국 분사(스핀오프) 회사 · %s" % time.strftime("%Y-%m-%d"), "",
         "10-12B 제출 회사 %d곳 → 패널에서 1년 안에 처음 거래된 분사주 **%d건**(폐지 포함). 수익 = 비용 차감 %%, 기준 = 같은 날 유동성 상위 40%% 아무거나 중앙." % (len(ev), len(E)), ""]
    px, buy, cost, di = K.px.values, K.buy.values, K.cost.values, K.di.values
    # 같은 날 기준(유동성 상위 40%)
    BEN = {}
    for h in (60, 120, 250):
        fut = K.groupby("ticker", sort=False).px.shift(-h)
        r = (fut / K.buy - 1) * 100
        BEN[h] = r[uq >= 0.6].groupby(K.date[uq >= 0.6]).median()
    cells = 0
    for k in (1, 21):
        for h in (60, 120, 250):
            R_ = []
            for t, f in zip(E.ticker, E["first"]):
                ix = idx[t]
                if len(ix) <= k + h:
                    # 폐지 — 마지막 가격까지(폐지 = 마지막 거래가)
                    if len(ix) <= k:
                        continue
                    s, e = ix[k - 1], ix[-1]
                else:
                    s, e = ix[k - 1], ix[k - 1 + h]
                b = buy[s]
                if not (b == b and b > 0):
                    continue
                R_.append((K.date.values[s], (px[e] / b - 1) * 100 - cost[s], len(ix) <= k + h))
            X = pd.DataFrame(R_, columns=["date", "r", "dead"])
            X["bm"] = X.date.map(BEN[h])
            cells += 1
            O += ["## 상장 %d일째 매수 · %d거래일 보유" % (k, h), "",
                  "| 구간 | n | 평균 | 중앙 | 상위5% 뺀 평균 | 승률 | 같은 날 아무거나 중앙 | **중앙 − 기준** | 중간 폐지 |", "|---|---|---|---|---|---|---|---|---|"]
            for lbl, lo, hi in (("2008~15", "20080101", "20151231"), ("2016~22", "20160101", "20221231"),
                                ("2023~", "20230101", "20991231"), ("전체", "20080101", "20991231")):
                x = X[(X.date >= lo) & (X.date <= hi)]
                if len(x) < 10:
                    O.append("| %s | %d | 표본 부족 | | | | | | |" % (lbl, len(x))); continue
                O.append("| %s | %d | %+.1f%% | %+.1f%% | %+.1f%% | %.0f%% | %+.1f%% | **%+.1f%%p** | %d |" % (
                    lbl, len(x), x.r.mean(), x.r.median(), x.r[x.r <= x.r.quantile(0.95)].mean(), (x.r > 0).mean() * 100,
                    x.bm.median(), x.r.median() - x.bm.median(), x.dead.sum()))
            O.append("")
    O.append("사건 목록 예(최근 15건): " + ", ".join("%s(%s)" % (t, f) for t, f in E.sort_values("first").tail(15)[["ticker", "first"]].values))
    log_trials("spinoff_%s" % time.strftime("%Y%m%d"), cells)
    rp = ROOT / "reports" / ("spinoff_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
