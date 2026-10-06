# -*- coding: utf-8 -*-
"""데이 [갭 하락 조용주](T1) — 시가에 산 뒤 **언제 파나** (2026-10-06, 사용자 "돌려봐" · 국장 1분봉 완료 직후).
T1 = 지금 사이트·day_alert 정의 그대로: day2_T1(중소형 · 갭 하위10% · 어제 거래량 하위30%) & 유니버스 거래대금 아래 1/3 &
     시장 대비 갭 ≤ -2%p(전날 코스피가 60일선 위) / ≤ -1.5%p(아래).
매수 = 시가 단일가(일봉 시가). 나오기 후보:
  ① 종가 단일가(지금) ② 정해진 시각 시장가(09:30 ~ 15:19) ③ 익절 지정가 +1~+5%(닿으면 그 값, 안 닿으면 종가)
  ④ 손절 -2~-5%(닿으면 그 값 − 미끄러짐 0.1%, 안 닿으면 종가) ⑤ 익절+손절 ⑥ 고점 대비 -N% 되밀리면(트레일링) — 같은 1분 안에 둘 다 닿으면 **손절 먼저**(보수적)
비용: 시가·종가 단일가 0.23%(사이트·day_alert 와 같음) · 장중 시장가로 나오면 +0.05% · 손절은 +0.10%.
기간: 1분봉이 있는 2022-12 ~ 2026-08(day2_T1 캐시 끝) · 해마다 따로.
⚠ 1분봉은 **지금** 거래대금 상위 1,000종목만 있다 — 그 사이 작아지거나 폐지된 종목은 빠진다(얼마나 빠졌는지 같이 적는다).
    python research/t1_exit.py
"""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
from verdict import log_trials
KST = ZoneInfo("Asia/Seoul")
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST, MKT, SLIP = 0.23, 0.05, 0.10
TIMES = ["0930", "1000", "1030", "1100", "1200", "1300", "1400", "1500", "1519"]


def t1():
    B = pd.read_pickle(ROOT / "cache" / "day2_T1.pkl")
    import index_cal
    K = pd.Series(index_cal.naver_closes("KOSPI", back=1700)).sort_index()
    up = (K > K.rolling(60).mean()).shift(1)                 # 전날 종가가 전날 60일선 위
    B = B[(B.date >= "20221201")].copy()
    B["up"] = B.date.map(up)
    B = B[B.up.notna()]
    B["rel"] = B.gap - B.mgap
    thr = np.where(B.up.astype(bool), -2.0, -1.5)
    return B[(B.liq <= 1 / 3) & (B.rel <= thr)].copy()


def paths(C):
    """후보 종목-일마다 09:01~15:31 1분봉(시각·고·저·종)."""
    want = C.groupby("ticker").date.apply(set).to_dict()
    res = {}
    for t, ds in want.items():
        f = BASE / "data" / "m1" / "KR" / "bf" / (t + ".parquet")
        if not f.exists(): continue
        D = pd.read_parquet(f, columns=["ts", "o", "h", "l", "c"])
        tt = pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert(KST)
        D["date"] = tt.dt.strftime("%Y%m%d"); D["hm"] = tt.dt.strftime("%H%M")
        D = D[D.date.isin(ds)].sort_values("ts")
        for d, g in D.groupby("date"):
            if len(g) >= 200: res[(t, d)] = g[["hm", "h", "l", "c", "o"]].to_numpy()
    return res


def exits(o, A, close):
    """o = 시가, A = [hm,h,l,c] 1분봉 → {이름: 비용 뒤 수익률%}."""
    hm = A[:, 0]; h = A[:, 1].astype(float); l = A[:, 2].astype(float); c = A[:, 3].astype(float)
    cl = close
    R = {"종가 단일가(지금)": (cl / o - 1) * 100 - COST}
    for t_ in TIMES:
        k = np.where(hm <= t_)[0]
        if len(k): R["%s:%s 시장가" % (t_[:2], t_[2:])] = (c[k[-1]] / o - 1) * 100 - COST - MKT
    for tp in (1, 2, 3, 5):
        hit = np.where(h >= o * (1 + tp / 100))[0]
        R["익절 +%d%%" % tp] = (tp - COST) if len(hit) else R["종가 단일가(지금)"]
    for sl in (2, 3, 5):
        hit = np.where(l <= o * (1 - sl / 100))[0]
        R["손절 -%d%%" % sl] = (-sl - COST - SLIP) if len(hit) else R["종가 단일가(지금)"]
    for tp, sl in ((2, 3), (3, 3), (3, 5), (5, 5)):
        th = np.where(h >= o * (1 + tp / 100))[0]; ts = np.where(l <= o * (1 - sl / 100))[0]
        a = th[0] if len(th) else 10 ** 9; b = ts[0] if len(ts) else 10 ** 9
        if b <= a and len(ts): R["익절 +%d%% · 손절 -%d%%" % (tp, sl)] = -sl - COST - SLIP
        elif len(th): R["익절 +%d%% · 손절 -%d%%" % (tp, sl)] = tp - COST
        else: R["익절 +%d%% · 손절 -%d%%" % (tp, sl)] = R["종가 단일가(지금)"]
    for tr, arm in ((2, 1), (3, 2), (3, 0)):
        # 고점이 시가 +arm% 를 넘은 뒤 그 고점에서 tr% 밀리면 시장가 — 안 그러면 종가
        peak = np.maximum.accumulate(h); armed = peak >= o * (1 + arm / 100)
        trig = np.where(armed & (l <= peak * (1 - tr / 100)))[0]
        nm = "트레일링 고점 -%d%%" % tr + (" (+%d%% 넘은 뒤)" % arm if arm else " (처음부터)")
        R[nm] = ((peak[trig[0]] * (1 - tr / 100)) / o - 1) * 100 - COST - SLIP if len(trig) else R["종가 단일가(지금)"]
    # 참고: 그날 고점이 언제였나 · 최고·최저
    R["_hi_t"] = hm[int(np.argmax(h))]; R["_mfe"] = (h.max() / o - 1) * 100; R["_mae"] = (l.min() / o - 1) * 100
    return R


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    C = t1()
    PT = paths(C)
    rows = []
    for r in C.itertuples():
        A = PT.get((r.ticker, r.date))
        if A is None: continue
        # ⚠ 일봉(수정주가)과 1분봉(원주가)을 섞으면 안 된다 — 첫 판에서 분할·증자 종목이 +30% 로 튀었다.
        #   시가 = 09:01 봉 시가(장전 단일가 체결), 종가 = 마지막 봉 종가(종가 단일가) — 둘 다 1분봉에서.
        o1, c1 = float(A[0, 4]), float(A[-1, 3])
        if A[0, 0] > "0905" or A[-1, 0] < "1530" or o1 <= 0: continue
        x = exits(o1, A, c1); x.update(date=r.date, ticker=r.ticker, adj=abs(o1 / float(r.open) - 1) > 0.01); rows.append(x)
    R = pd.DataFrame(rows)
    R["yr"] = R.date.str[:4]
    nadj = int(R.adj.sum())
    P("# 데이 [갭 하락 조용주] 언제 파나 — 1분봉 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- T1 후보 %d건(%s~%s) 중 1분봉 있는 것 **%d건(%.0f%%)** · %d일 · 매수 = 시가 단일가" % (
        len(C), C.date.min(), C.date.max(), len(R), len(R) / len(C) * 100, R.date.nunique()))
    P("- 1분봉 시가가 일봉 시가와 1%%↑ 다른(분할·증자 등 수정주가) %d건 — 1분봉 가격끼리만 계산해 영향 없음" % nadj)
    P("- 비용: 단일가 %.2f%% · 장중 시장가 +%.2f%% · 손절·트레일링 +%.2f%% (같은 1분에 익절·손절 둘 다 닿으면 손절로 셈)" % (COST, MKT, SLIP)); P("")
    names = [k for k in R.columns if not k.startswith("_") and k not in ("date", "ticker", "yr", "adj")]
    base = R["종가 단일가(지금)"]
    yrs = sorted(R.yr.unique())
    P("| 파는 법 | 건당 평균 | 승률 | 평균 수익/손실 | 종가 대비 | " + " | ".join(yrs) + " | 종가보다 나은 해 |")
    P("|---|---|---|---|---|" + "---|" * len(yrs) + "---|")
    out = []
    for k in names:
        v = R[k]
        win = v[v > 0].mean(); loss = v[v <= 0].mean()
        by = v.groupby(R.yr).mean(); bb = base.groupby(R.yr).mean()
        d = (v - base).groupby(R.date).mean()
        tstat = d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else np.nan
        out.append((k, v.mean(), (v > 0).mean() * 100, win, loss, v.mean() - base.mean(), tstat, by, (by > bb).sum()))
    for k, m, w, wn, ls, dv, ts, by, nb in out:
        P("| %s | %+.2f%% | %.0f%% | %+.1f / %+.1f | %s | %s | %s |" % (
            k, m, w, wn, ls, "—" if k.startswith("종가") else "%+.2f%%p (t %.1f)" % (dv, ts),
            " | ".join("%+.2f" % by.get(y, np.nan) for y in yrs), "—" if k.startswith("종가") else "%d/%d" % (nb, len(yrs))))
    P("")
    P("**그날 움직임(시가 기준)** · 고점 평균 %+.2f%% · 저점 평균 %+.2f%% · 시가보다 +2%% 넘게 오른 날 %.0f%% · -3%% 넘게 빠진 날 %.0f%%" % (
        R._mfe.mean(), R._mae.mean(), (R._mfe >= 2).mean() * 100, (R._mae <= -3).mean() * 100)); P("")
    hb = pd.cut(R._hi_t.astype(int), [0, 930, 1000, 1100, 1300, 1500, 1600], labels=["~09:30", "~10:00", "~11:00", "~13:00", "~15:00", "~마감"])
    P("| 그날 고점 시각 | 비율 |"); P("|---|---|")
    for lab, n in hb.value_counts(sort=False).items(): P("| %s | %.0f%% |" % (lab, n / len(R) * 100))
    P(""); P("(칸 %d · %.1f분)" % (len(names), (time.time() - t0) / 60))
    log_trials("t1_exit_%s" % time.strftime("%Y%m%d"), len(names))
    R.to_pickle(ROOT / "cache" / "t1_exit.pkl")
    (ROOT / "reports" / ("t1_exit_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
