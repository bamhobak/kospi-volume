# -*- coding: utf-8 -*-
"""그림자 — 깔때기 G2 를 통과한 명세(또는 실시간 재료 명세)를 **실제로 사지 않고** 앞으로 오는 날 성적만 매일 적는다.

앞으로 오는 날은 아무도 미리 못 본 데이터라 다중검정이 없는 유일한 정직한 시험이다.
  기록: data/factory/shadow_trades.csv (id, mode, date, ticker, ret)
        data/factory/shadow_mkt.csv (mode, date, mkt) — 같은 날 유니버스 아무 종목 평균(대조)
  판정: 그림자 시작 뒤 20거래일↑ · 15건↑ → 건당 평균 > 0 & 승률 50%↑ & **같은 날 시장 대비 초과 > 0 · t ≥ 2**
        & **뒤집은 짝보다 초과가 클 것** → 상태 propose + 텔레그램 "1주 실전 올릴까?"(한 번)
        & **100만씩 샀다고 치고 체결 손해(손해 = 0.143 + 1.321×√p %, 체결률 1/(1+3p), p = 100만 ÷ 20일 평균 거래대금 %) 뺀 하루 손익 > 0**
        40거래일↑ 인데 건당 평균 < 0 또는 초과 ≤ 0 또는 100만 하루 손익 < 0 → retired(그만 봄)
  11-12 체결 손해 추가: 하루 97종목처럼 얇게 많이 사는 판은 건당이 +여도 실금액이면 손해였다([예상 하회]) — research/t1_size_liq_1021.py 실측 맞춤.
  2026-11-12 사용자: F1659 를 오른 장 3일만 보고 채택했다가 녹화 23일로 다시 재니 실금액이면 손해 → 날 수·시장 대비·뒤집은 짝을
        늘 같이 보이고, 20거래일 전엔 성적을 '판정 전'으로만 보인다(fwd.ready · 사이트 후보 페이지).
  실제 주문은 하지 않는다 — 1주 실전은 사용자가 정한다.
"""
import time
import numpy as np, pandas as pd

import common as C
import feats as FT
import lab

TRF = C.DATA / "shadow_trades.csv"
MKF = C.DATA / "shadow_mkt.csv"
MIN_DAYS, MIN_N, MIN_EX_T = 20, 15, 2.0
AMT = 100e4                                       # 체결 손해 볼 때 한 건 금액(원)
IMP_A, IMP_B, FILL_C = 0.143, 1.321, 3.0          # t1_size_liq_1021 실측 맞춤(11-12) — 사고·파는 손해 합 %, 체결률
LAG = {"oc": 0, "on": 1, "m10c": 0, "m14c": 0, "sw5": 4, "sw10": 9, "sw20": 19, "sw40": 39, "sw60": 59}   # 오늘 저녁에 성적이 확정되는 매수일 = 오늘에서 몇 거래일 전


def _mkt(Ud, mode):
    """그날 유니버스 아무 종목 평균 — lab.trades 와 같은 비용 규칙."""
    tgt = FT.TARGET[mode]
    if tgt not in Ud.columns: return None
    r = Ud[tgt].astype(float).clip(-60, 60).dropna()
    if not len(r): return None
    cost = FT.COST if mode in ("oc", "on") else (FT.COST + FT.INTRA_SLIP) if mode.startswith("m") else 0.0
    return float(r.mean() - cost)


def liq_fill(T, A):
    """amt20(그날 기준 20일 평균 거래대금, 억원)이 빈 줄을 live 일봉으로 메운다(11-12 전 기록)."""
    if "amt20" not in T.columns: T = T.assign(amt20=np.nan)
    m = T.amt20.isna()
    if not m.any(): return T
    D = A[A.ticker.isin(set(T.ticker[m]))].sort_values(["ticker", "date"])[["ticker", "date", "close", "volume"]].copy()
    D["a"] = D.close * D.volume
    D["amt20"] = D.groupby("ticker").a.transform(lambda z: z.rolling(20, min_periods=3).mean().shift(1)) / 1e8
    k = T[m][["ticker", "date"]].astype(str).merge(D[["ticker", "date", "amt20"]].astype({"date": str}), on=["ticker", "date"], how="left")
    T = T.copy(); T.loc[m, "amt20"] = k.amt20.values
    return T


def net_money(T, nd):
    """100만씩 샀다고 치고 체결 손해 뺀 → (건당 순 %, 하루 손익 원 — 거래 없는 날 0 포함)."""
    if T is None or not len(T) or "amt20" not in T.columns: return None, None
    a = T.amt20.astype(float) * 1e8
    if a.isna().all(): return None, None
    a = a.fillna(a.median())
    pp = AMT / a * 100
    loss = np.maximum(0, IMP_A + IMP_B * np.sqrt(pp)); fill = 1 / (1 + FILL_C * pp)
    net = T.ret.astype(float) - loss
    return float((net * fill).sum() / fill.sum()), float((AMT * fill * net / 100).sum() / max(nd, 1))


def twin_of(x, L):
    """뒤집은 짝 — 뒤집기면 원본, 원본이면 그 뒤집기."""
    if x.get("origin") == "invert": return next((y for y in L if y.get("id") == x.get("source")), None)
    return next((y for y in L if y.get("origin") == "invert" and y.get("source") == x.get("id")), None)


def excess(T, M, mode):
    """날 바구니 − 같은 날 시장 → 평균·t·플러스 날·날 수. 시장 값 없는 날은 뺀다."""
    if T is None or not len(T) or not len(M): return None
    b = T.groupby(T.date.astype(str)).ret.mean()
    m = M[M["mode"] == mode].set_index("date").mkt
    e = (b - m.reindex(b.index)).dropna()
    if not len(e): return None
    sd = e.std(ddof=1) if len(e) > 1 else np.nan
    return dict(ex=float(e.mean()), ex_t=float(e.mean() / sd * np.sqrt(len(e))) if sd and sd > 0 else 0.0,
                ex_pos=int((e > 0).sum()), ex_days=int(len(e)))


def fill_mkt(allT, need, dates, U, A):
    """같은 날 시장 값 — 오늘 확정된 날은 U 로, 예전 그림자 날 중 빠진 날은 한 번만 메운다."""
    import live
    M = pd.read_csv(MKF, dtype={"date": str}) if MKF.exists() else pd.DataFrame(columns=["mode", "date", "mkt"])
    have = set(zip(M["mode"], M["date"]))
    ds = set(dates)
    want = {(mo, d) for mo, d in set(zip(allT["mode"], allT["date"].astype(str))) if (mo, d) not in have and d in ds}
    want |= {(mo, d) for mo, d in need.items() if (mo, d) not in have}
    if not want: return M
    days = sorted({d for _, d in want})
    Uw = U if set(days) <= set(U.date.unique()) else live.frame(days=days, A=A)
    add = [(mo, d, round(v, 4)) for mo, d in sorted(want) for v in [_mkt(Uw[Uw.date == d], mo)] if v is not None]
    if add:
        M = pd.concat([M, pd.DataFrame(add, columns=["mode", "date", "mkt"])]).drop_duplicates(["mode", "date"], keep="last")
        M.to_csv(MKF, index=False, encoding="utf-8-sig")
    return M


def judge(x, L, allT, M, dates):
    """fwd(앞으로 성적) 채우고, 통과·그만이면 상태를 바꾼다. 통과면 텔레그램 문구를 돌려준다."""
    T = allT[allT.id == x["id"]]
    nd = len([d for d in dates if d >= x.get("shadow_from", "0")])
    if len(T) == 0:
        x["fwd"] = dict(n=0, days=nd, ready=False); return None
    e = excess(T, M, x["mode"]) or {}
    tw = twin_of(x, L)
    te = excess(allT[allT.id == tw["id"]], M, tw["mode"]) if tw is not None else None
    nr, pnl = net_money(T, nd)
    f = x["fwd"] = dict(n=int(len(T)), days=nd, mean=float(T.ret.mean()), win=float((T.ret > 0).mean() * 100), ready=nd >= MIN_DAYS, **e,
                        twin=tw["id"] if tw is not None else None, twin_ex=(te or {}).get("ex"), net=nr, pnl=pnl)
    beat_twin = f["twin_ex"] is None or (f.get("ex") is not None and f["ex"] > f["twin_ex"])
    if (x["status"] == "shadow" and nd >= MIN_DAYS and len(T) >= MIN_N and f["mean"] > 0 and f["win"] >= 50
            and (f.get("ex") or 0) > 0 and (f.get("ex_t") or 0) >= MIN_EX_T and beat_twin and (f.get("pnl") or 0) > 0):
        x["status"] = "propose"
        return "🧪 <b>공장 그림자 통과</b> %s %s\n%s\n%d거래일 %d건 건당 %+.2f%% · 승률 %.0f%% · 시장 대비 %+.2f%%p(t %.1f · 플러스 날 %d/%d)%s\n100만씩·체결 손해 뒤 건당 %+.2f%% · 하루 %+.1f만\n과거 학습 %s / 검증 %s\n→ 1주 실전으로 올릴지 정해줘(자동 주문 안 함)" % (
            x["id"], x.get("name", ""), x.get("desc", ""), nd, len(T), f["mean"], f["win"], f["ex"], f["ex_t"], f["ex_pos"], f["ex_days"],
            (" · 뒤집은 짝 %s %+.2f%%p" % (f["twin"], f["twin_ex"])) if f["twin_ex"] is not None else "", f["net"], f["pnl"] / 1e4,
            lab.fmt_s((x.get("res") or {}).get("tr")), lab.fmt_s((x.get("res") or {}).get("va")))
    if x["status"] == "shadow" and nd >= 2 * MIN_DAYS and (f["mean"] < 0 or (f.get("ex") is not None and f["ex"] <= 0) or (f.get("pnl") is not None and f["pnl"] < 0)):   # 검토·채택은 사람이 정한다 — 자동으로 내리지 않음
        x["status"] = "retired"; x["why"] = (x.get("why") or "") + " · 그림자 %d거래일 건당 %+.2f%% · 시장 대비 %s → 그만" % (
            nd, f["mean"], ("%+.2f%%p" % f["ex"]) if f.get("ex") is not None else "-")
    return None


def daily(A, today):
    """A = live 일봉(전체). 오늘 확정되는 매수일들의 재료를 만들어 그림자 명세마다 거래를 적는다."""
    import live
    L = lab.load()
    S = [x for x in L if x.get("status") in ("shadow", "propose", "review", "adopted")]
    dates = sorted(A.date.unique())
    if today not in dates:
        C.log("그림자: 오늘 일봉 없음"); return []
    i = dates.index(today)
    need = {m: dates[i - k] for m, k in LAG.items() if i - k >= 0}
    if not S: return []
    U = live.frame(days=sorted(set(need.values())), A=A)
    old = pd.read_csv(TRF, dtype={"date": str, "ticker": str}) if TRF.exists() else pd.DataFrame(columns=["id", "mode", "date", "ticker", "ret"])
    rows = []
    honest = {}                                   # 종가 매수(on)는 15:19 까지 모습으로 고른다(종가 단일가 착시 방지, 2026-10-10)
    for x in S:
        d = need.get(x["mode"])
        if not d or d < x.get("shadow_from", "0"): continue
        Ud = U[U.date == d]
        if lab.needs_1519(x):
            if d not in honest:
                sn = live.snap1519(d)
                honest[d] = None if sn is None else lab.apply_1519(Ud.merge(sn, on="ticker", how="inner").assign(
                    pc_m=lambda z: z.px.astype(float), o_m=lambda z: z.px.astype(float) * (1 + z.gap.astype(float) / 100)))
            if honest[d] is None:
                C.log("그림자: %s 1분봉 없어 %s 건너뜀" % (d, x["id"])); continue
            Ud = honest[d]
        T = lab.trades(Ud, x, PXD=(lab.px_dict(A, key='live' + today) if x.get('exit') else None))
        liq = Ud.set_index("ticker").amt20.to_dict() if "amt20" in Ud.columns else {}
        rows += [(x["id"], x["mode"], d, t, round(float(r), 4), liq.get(t)) for t, r in zip(T.ticker, T.ret)]
    N = pd.DataFrame(rows, columns=["id", "mode", "date", "ticker", "ret", "amt20"])
    allT = pd.concat([old, N]).drop_duplicates(["id", "date", "ticker"], keep="last")
    try: allT = liq_fill(allT, A)
    except Exception as ex: C.log("그림자: 거래대금 메우기 실패", repr(ex)[:300])
    allT.to_csv(TRF, index=False, encoding="utf-8-sig")
    allS = [x for x in L if x.get("status") in ("shadow", "propose", "review", "adopted", "retired")]
    try:
        M = fill_mkt(allT[allT.id.isin({x["id"] for x in allS})], need, dates, U, A)
    except Exception as ex:                       # 대조를 못 만들면 판정은 미룬다(초과 없음 → 통과 안 함)
        C.log("그림자: 시장 대조 실패", repr(ex)[:300]); M = pd.DataFrame(columns=["mode", "date", "mkt"])
    msgs = [m for m in (judge(x, L, allT, M, dates) for x in S) if m]
    lab.save(L)
    for m in msgs: C.tg(m)
    C.log("그림자 %d명세 · 오늘 거래 %d" % (len(S), len(N)))
    return N

