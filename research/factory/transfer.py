# -*- coding: utf-8 -*-
"""미장 밤사이 → 국장 아침 전이표 (2026-10-08 사용자 아이디어 ⑧).

밤사이 미장 ETF·대형주 움직임이 국장 종목 시가 갭에 얼마나 옮겨 오나를 종목마다 잰다.
  짝 찾기: 종목마다 지난 2년(그해 1월 1일 전까지만 — 미래 안 봄) 시가 갭과 '그 전날 밤 미장 수익' 상관이 가장 큰 미장 종목 하나 + 기울기(베타)
  예상 갭 tr_pred = 베타 × 짝의 밤사이 수익 · 덜 반영 tr_res = 실제(또는 장전 예상) 갭 - 예상 갭
  밤사이 = 국장 거래일 t 바로 전에 끝난 미장 정규장(뉴욕 날짜 < t 중 가장 최근)
재료로 공장에 들어간다(us_ewy · tr_us · tr_pred · tr_res) — 진화기·정답지가 알아서 쓴다.
아침(07:50): 미장 일봉 갱신 → 오늘 예상 갭 → data/factory/transfer/YYYYMMDD.json · 텔레그램 짧게.
"""
import json, time
import numpy as np, pandas as pd

import common as C

US = ["SPY", "QQQ", "IWM", "DIA", "SOXX", "SMH", "XLK", "XLE", "XLF", "XLI", "XLB", "XLV", "XLY", "XLP", "XLU", "XBI", "IBB", "ITA", "XAR",
      "URA", "TAN", "ICLN", "LIT", "REMX", "KWEB", "FXI", "EWY", "EWJ", "EWT", "BOTZ", "ARKK", "ARKG", "XME", "COPX", "GDX", "JETS", "IYT",
      "TLT", "UUP", "USO", "PAVE", "IGV", "CIBR", "KRE", "XHB", "NVDA", "MU", "TSLA", "AAPL", "AMD", "AVGO", "LLY", "MSFT", "GOOGL", "META", "AMZN"]
UD = C.DATA / "us_daily.parquet"
FIT = C.DATA / "transfer_fit.json"
TD = C.DATA / "transfer"; TD.mkdir(exist_ok=True)


def fetch_us(full=False, since="20131201"):
    """토스 미장 일봉(정규장) — 처음엔 2013-12~ 전부, 그 뒤엔 최근 10개만 덧붙인다."""
    M = C.toss(rate=8)
    old = pd.read_parquet(UD) if UD.exists() else pd.DataFrame(columns=["sym", "date", "close"])
    rows = []
    for s in US:
        have = old[old.sym == s]
        if len(have) and not full:
            c = (M.get("/api/v1/candles", symbol=s, interval="1d", count=10) or {}).get("candles") or []
            rows += [(s, x["timestamp"][:10].replace("-", ""), float(x["closePrice"])) for x in c]
            continue
        before = None
        for _ in range(30):
            q = dict(symbol=s, interval="1d", count=200)
            if before: q["before"] = before
            r = M.get("/api/v1/candles", **q) or {}
            c = r.get("candles") or []
            if not c: break
            rows += [(s, x["timestamp"][:10].replace("-", ""), float(x["closePrice"])) for x in c]
            if min(x["timestamp"][:10].replace("-", "") for x in c) < since or not r.get("nextBefore"): break
            before = r["nextBefore"]
    N = pd.DataFrame(rows, columns=["sym", "date", "close"])
    A = pd.concat([old, N]).drop_duplicates(["sym", "date"], keep="last").sort_values(["sym", "date"])
    A.to_parquet(UD, index=False)
    C.log("미장 일봉 %d종목 · %s~%s" % (A.sym.nunique(), A.date.min(), A.date.max()))
    return A


def night_returns(kr_dates, upto=None):
    """국장 날짜마다 그 전날 밤 미장 수익(%) 표 — 줄 = 국장 날짜, 칸 = 미장 종목.
    upto: 이 국장 날짜 아침에 쓰는 경우, 아직 안 끝난 미장 봉(뉴욕 날짜 ≥ 국장 날짜)은 버린다."""
    A = pd.read_parquet(UD)
    P = A.pivot(index="date", columns="sym", values="close").sort_index()
    R = (P / P.shift(1) - 1) * 100                      # 뉴욕 날짜별 하루 수익(빈 날은 NaN)
    ud = R.index.to_numpy()
    kd = np.asarray(sorted(set(kr_dates)))
    pos = np.searchsorted(ud, kd, side="left") - 1          # 뉴욕 날짜 < 국장 날짜 중 가장 최근
    out = pd.DataFrame(np.where(pos[:, None] >= 0, R.to_numpy()[np.clip(pos, 0, None)], np.nan), index=kd, columns=R.columns)
    out["_night"] = np.where(pos >= 0, ud[np.clip(pos, 0, None)], None)
    return out


def fit_year(U, Y, NR):
    """Y 해에 쓸 짝 — Y-2, Y-1 두 해의 (갭, 전날 밤 미장) 로. 반환 {티커: (짝, 베타, 상관)}."""
    a, b = "%d0101" % (Y - 2), "%d1231" % (Y - 1)
    Z = U[(U.date >= a) & (U.date <= b)][["ticker", "date", "gap"]]
    if Z.empty: return {}
    G = Z.pivot(index="date", columns="ticker", values="gap")
    X = NR.reindex(G.index)[US].astype(float)
    ok = X.notna().sum() >= 200
    X = X.loc[:, ok[ok].index]
    if X.shape[1] == 0: return {}
    out = {}
    Xm = X - X.mean()
    for t in G.columns:
        y = G[t]
        m = y.notna()
        if m.sum() < 120: continue
        yy = y[m] - y[m].mean(); XX = Xm[m].fillna(0)
        cov = (XX.mul(yy, axis=0)).sum() / (m.sum() - 1)
        var = (XX ** 2).sum() / (m.sum() - 1)
        corr = cov / np.sqrt(var * yy.var())
        j = corr.idxmax()
        if not np.isfinite(corr[j]) or corr[j] <= 0.05: continue
        out[t] = (j, float(cov[j] / var[j]), float(corr[j]))
    return out


def apply_fit(U, fits_by_year, NR):
    """U 에 us_ewy · tr_us · tr_pred · tr_res 를 붙인다(fits_by_year: {해: {티커: (짝, 베타, 상관)}})."""
    U["us_ewy"] = U.date.map(NR["EWY"]).astype("float32") if "EWY" in NR.columns else np.nan
    yr = U.date.str[:4].astype(int)
    tr_us = np.full(len(U), np.nan, dtype="float64"); beta = np.full(len(U), np.nan)
    stack = NR[[c for c in NR.columns if c != "_night"]].stack()
    for Y, fit in fits_by_year.items():
        idx = np.flatnonzero((yr == Y).to_numpy())
        if not len(idx) or not fit: continue
        tk = U.ticker.to_numpy()[idx]
        sym = np.array([fit.get(t, (None,))[0] for t in tk], dtype=object)
        b = np.array([fit[t][1] if t in fit else np.nan for t in tk])
        has = np.array([s is not None for s in sym])
        keys = pd.MultiIndex.from_arrays([U.date.to_numpy()[idx][has], sym[has]])
        vals = stack.reindex(keys).to_numpy()
        tr_us[idx[has]] = vals; beta[idx[has]] = b[has]
    U["tr_us"] = tr_us.astype("float32")
    U["tr_pred"] = (tr_us * beta).astype("float32")
    U["tr_res"] = (U.gap.astype(float) - U.tr_pred).astype("float32")


def attach_hist(U):
    """과거 자료에 전이표 재료를 붙인다(해마다 지난 2년으로 짝을 다시 찾는다 — 앞을 안 본다)."""
    if not UD.exists(): fetch_us(full=True)
    NR = night_returns(U.date.unique())
    fits = {}
    for Y in range(2016, int(U.date.max()[:4]) + 2):
        fits[Y] = fit_year(U, Y, NR)
        C.log("전이표 %d년 짝 %d종목" % (Y, len(fits[Y])))
    apply_fit(U, {Y: f for Y, f in fits.items() if Y <= int(U.date.max()[:4])}, NR)
    last = max(fits)                                        # 패널이 끝난 다음 해까지 만들어 둔다 — 매일 쓰는 건 가장 최근 것
    use = fits.get(last) or fits.get(last - 1)
    C.jsave(FIT, {"year": last, "made": time.strftime("%Y-%m-%d"), "fit": {t: list(v) for t, v in (use or {}).items()},
                  "fit_cur": {t: list(v) for t, v in (fits.get(last - 1) or {}).items()}})


def live_fit(day):
    j = C.jload(FIT, {})
    f = j.get("fit_cur") if day[:4] == str(int(j.get("year", 0)) - 1) else j.get("fit")
    return {t: tuple(v) for t, v in (f or {}).items()}


def morning(day):
    """오늘 아침 — 밤사이 미장으로 본 예상 갭(전 종목)을 저장하고 짧게 알린다."""
    fetch_us()
    NR = night_returns([day])
    row = NR.iloc[-1]
    fit = live_fit(day)
    pred = {t: [s, round(b, 4), (None if pd.isna(row.get(s)) else round(float(row[s]), 3)),
                (None if pd.isna(row.get(s)) else round(float(row[s]) * b, 3))] for t, (s, b, cr) in fit.items()}
    out = {"date": day, "night": row["_night"], "inst": {k: round(float(v), 3) for k, v in row.items() if k != "_night" and pd.notna(v)}, "pred": pred}
    C.jsave(TD / ("%s.json" % day), out)
    names = C.jload(C.DATA / "names.json", {})
    inst = sorted(out["inst"].items(), key=lambda kv: -abs(kv[1]))[:6]
    pp = sorted([(t, v[3]) for t, v in pred.items() if v[3] is not None], key=lambda kv: kv[1])
    lines = ["🌙→🌅 <b>밤사이 미장 → 오늘 국장</b> %s/%s (뉴욕 %s/%s 장)" % (day[4:6], day[6:], str(out["night"])[4:6], str(out["night"])[6:]),
             "EWY(한국) %+.2f%% · " % out["inst"].get("EWY", float("nan")) + " · ".join("%s %+.1f%%" % kv for kv in inst if kv[0] != "EWY")]
    if pp:
        lines.append("미장 따라 높게 열릴 쪽: " + ", ".join("%s(%s %+.1f)" % (names.get(t, t), pred[t][0], v) for t, v in pp[::-1][:5]))
        lines.append("낮게 열릴 쪽: " + ", ".join("%s(%s %+.1f)" % (names.get(t, t), pred[t][0], v) for t, v in pp[:5]))
    lines.append("(장전 08:59 예상가와 비교해 '덜 반영된 종목'은 녹화기가 저녁 정답지에 넣는다)")
    C.tg("\n".join(lines))
    C.log("전이표 오늘 %d종목" % len(pred))
    return out
