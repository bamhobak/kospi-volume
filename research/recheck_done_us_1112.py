# -*- coding: utf-8 -*-
"""미장 보유 재판정 — 산 뒤에 좁혀진 조건으로 다시 (2026-11-12 사용자).
N6 [실적 서프라이즈] 09-30 좁힘(H0260): 신호일 기준 60거래일 전보다 -20%↓ 빠졌다가 하락분 1/4↑ 회복 · 아직 60일 전 아래
N1 [상승장 신고가] 09-30 좁힘(H0261): 그날 거래 주식 수 상위 20%(유동 40% 안) · 10-02 2차(H0275): 5일 평균 거래량 ≤ 60일 평균 0.8배
신호일 = 매수일의 전 미장 거래일. 일봉 = 토스(/api/v1/candles 1d). 'N1 거래 주식 수 상위 20%' 는 연구 패널(09-22 까지)로만.
"""
import json, sys
sys.path.insert(0, r"C:\vscode\kospi-volume")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import autotrade as AT
P = json.load(open(r"C:\temp\done_pos.json", encoding="utf-8"))
P = [p for p in P if (p.get("filters") or ["?"])[0] in ("N1", "N6") and str(p["date"]) <= "20261002" and p.get("sell")]
U = None
try:
    U = pd.read_pickle(r"C:\vscode\kospi-volume\data\us_full_2007.pkl")
    U = U[U.date >= "20260801"][["ticker", "date", "volume", "amt20"]]
    U["liq"] = U.amt20.groupby(U.date).rank(pct=True) >= 0.60
    U["volq"] = U.volume.where(U.liq).groupby(U.date).rank(pct=True)
except Exception as ex:
    print("연구 패널 못 읽음", repr(ex)[:80])
rows = []
for p in P:
    rid, t, b = p["filters"][0], p["code"], str(p["date"])
    c = (AT.tget("/api/v1/candles", symbol=t, interval="1d", count=200) or {}).get("candles") or []
    D = pd.DataFrame([dict(d=x["timestamp"][:10].replace("-", ""), c=float(x["closePrice"]), v=float(x.get("volume") or 0)) for x in c]).drop_duplicates("d").sort_values("d").reset_index(drop=True)
    j = int(np.searchsorted(D.d.values, b)) - 1
    if j < 65:
        rows.append(dict(rid=rid, t=t, name=p.get("name"), buy=b, verdict="일봉 부족")); continue
    s = D.d[j]; cl = D.c.values; v = D.v.values
    r = dict(rid=rid, t=t, name=p.get("name"), buy=b, signal=s)
    if rid == "N6":
        c60 = cl[j - 60]; lo = cl[j - 59:j + 1].min(); now = cl[j]
        dd = (lo / c60 - 1) * 100; rcv = (now - lo) / (c60 - lo) * 100 if c60 > lo else np.nan
        ok = (lo <= c60 * 0.8) and (now >= lo + 0.25 * (c60 - lo)) and (now < c60)
        r.update(info="60일 전 대비 저점 %+.0f%% · 하락분 회복 %.0f%% · 지금 60일 전 대비 %+.0f%%" % (dd, rcv, (now / c60 - 1) * 100), verdict="그대로" if ok else "안 샀을 것")
    else:
        v5, v60 = v[j - 4:j + 1].mean(), v[j - 59:j + 1].mean()
        okv = v5 <= 0.8 * v60
        vq = None
        if U is not None:
            z = U[(U.ticker == t) & (U.date == s)]
            if len(z): vq = float(z.volq.iloc[0]) if z.volq.notna().iloc[0] else None
        okq = None if vq is None else (vq >= 0.8)
        info = "5일÷60일 거래량 %.2f(≤0.8 이어야)" % (v5 / v60) + (" · 거래 주식 수 유동 안 상위 %.0f%%(≥80 이어야)" % (vq * 100) if vq is not None else " · 거래 주식 수 순위 확인 못 함(연구 패널 09-22 까지)")
        verdict = "안 샀을 것" if (not okv or okq is False) else ("그대로" if okq else "거래량 조건은 통과 · 순위는 확인 못 함")
        r.update(info=info, verdict=verdict)
    rows.append(r)
R = pd.DataFrame(rows)
for r in R.itertuples():
    print("| %s | %s(%s) | %s | %s | %s | %s |" % (r.rid, r.name, r.t, r.buy, getattr(r, "signal", ""), getattr(r, "info", ""), r.verdict))
R.to_csv(r"C:\vscode\kospi-volume\research\reports\recheck_done_us_1112.csv", index=False, encoding="utf-8-sig")
