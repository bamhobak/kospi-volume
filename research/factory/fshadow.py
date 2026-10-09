# -*- coding: utf-8 -*-
"""그림자 — 깔때기 G2 를 통과한 명세(또는 실시간 재료 명세)를 **실제로 사지 않고** 앞으로 오는 날 성적만 매일 적는다.

앞으로 오는 날은 아무도 미리 못 본 데이터라 다중검정이 없는 유일한 정직한 시험이다.
  기록: data/factory/shadow_trades.csv (id, mode, date, ticker, ret)
  판정: 그림자 시작 뒤 20거래일↑ · 15건↑ → 건당 평균 > 0 & 승률 50%↑ → 상태 propose + 텔레그램 "1주 실전 올릴까?"(한 번)
        40거래일↑ 인데 건당 평균 < 0 → retired(그만 봄)
  실제 주문은 하지 않는다 — 1주 실전은 사용자가 정한다.
"""
import time
import numpy as np, pandas as pd

import common as C
import lab

TRF = C.DATA / "shadow_trades.csv"
LAG = {"oc": 0, "on": 1, "sw5": 4, "sw10": 9, "sw20": 19, "sw40": 39, "sw60": 59}   # 오늘 저녁에 성적이 확정되는 매수일 = 오늘에서 몇 거래일 전


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
        rows += [(x["id"], x["mode"], d, t, round(float(r), 4)) for t, r in zip(T.ticker, T.ret)]
    N = pd.DataFrame(rows, columns=["id", "mode", "date", "ticker", "ret"])
    allT = pd.concat([old, N]).drop_duplicates(["id", "date", "ticker"], keep="last")
    allT.to_csv(TRF, index=False, encoding="utf-8-sig")
    msgs = []
    for x in S:
        T = allT[allT.id == x["id"]]
        nd = len([d for d in dates if d >= x.get("shadow_from", "0")])
        if len(T) == 0:
            x["fwd"] = dict(n=0, days=nd); continue
        x["fwd"] = dict(n=int(len(T)), days=nd, mean=float(T.ret.mean()), win=float((T.ret > 0).mean() * 100))
        if x["status"] == "shadow" and nd >= 20 and len(T) >= 15 and T.ret.mean() > 0 and (T.ret > 0).mean() >= 0.5:
            x["status"] = "propose"
            msgs.append("🧪 <b>공장 그림자 통과</b> %s %s\n%s\n앞으로 %d거래일 %d건 건당 %+.2f%% · 승률 %.0f%% (과거 학습 %s / 검증 %s)\n→ 1주 실전으로 올릴지 정해줘(자동 주문 안 함)" % (
                x["id"], x.get("name", ""), x.get("desc", ""), nd, len(T), T.ret.mean(), (T.ret > 0).mean() * 100,
                lab.fmt_s((x.get("res") or {}).get("tr")), lab.fmt_s((x.get("res") or {}).get("va"))))
        elif x["status"] == "shadow" and nd >= 40 and T.ret.mean() < 0:      # 검토·채택은 사람이 정한다 — 자동으로 내리지 않음
            x["status"] = "retired"; x["why"] = (x.get("why") or "") + " · 그림자 %d거래일 건당 %+.2f%% → 그만" % (nd, T.ret.mean())
    lab.save(L)
    for m in msgs: C.tg(m)
    C.log("그림자 %d명세 · 오늘 거래 %d" % (len(S), len(N)))
    return N
