# -*- coding: utf-8 -*-
"""C — 미장 공매도 잔고 (2026-10-03, 사용자: a b c 다 해줘).
FINRA consolidatedShortInterest(2주마다 · 2017-12~) → research/cache/finra_si.pkl (fetch_finra_si.py).
⚠ 미래 금지: 결제일 잔고는 약 7영업일 뒤 공개 → 결제일 + 8거래일부터 '아는 값'. 그 뒤 다음 공개까지 그 값을 쓴다.
재료: dtc(잔고 ÷ 하루 평균 거래량 = 다 갚는 데 며칠), sip(잔고 ÷ 발행주식 %), chg(직전 대비 잔고 변화 %)
1) 독립 신호 — 공개일(새 값이 생긴 날)에만 판정 · 보유 20·60일 · 거래대금 상위 40%
2) 지금 미장 규칙(N1~N5) 안 거르개 — 공매도 많은/줄어든 것만 남기면 나아지나 (z = 남긴 평균 − 전체 평균 ÷ 무작위 같은 건수 SE)
학습 2018~22 · 검증 2023~
    python research/short_int.py
"""
import pickle, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import run_spec as R
from verdict import log_trials
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
LAG = 8


def attach(A):
    F = pd.read_pickle(ROOT / "cache" / "finra_si.pkl")
    F = F[F.ticker.isin(set(A.ticker))].copy()
    cal = sorted(A.date.unique()); pos = {d: i for i, d in enumerate(cal)}
    ci = np.searchsorted(cal, F.sdate.values)            # 결제일 이후 첫 거래일(같은 날 포함)
    ki = ci + LAG
    F = F[ki < len(cal)].copy(); F["kd"] = [cal[i] for i in ki[ki < len(cal)]]
    F = F.sort_values(["ticker", "kd"]).drop_duplicates(["ticker", "kd"], keep="last")
    F.loc[F.dtc >= 900, "dtc"] = np.nan
    F["chg"] = F.chg.clip(-100, 1000)
    M = A[["ticker", "date", "marcap", "rawclose"]].merge(F[["ticker", "kd", "si", "dtc", "chg"]].rename(columns={"kd": "date"}),
                                                     on=["ticker", "date"], how="left")
    M["fresh"] = M.si.notna()
    M = M.sort_values(["ticker", "date"])
    for c in ("si", "dtc", "chg"):
        M[c] = M.groupby("ticker")[c].ffill(limit=15)
    M = M.sort_index()
    sh = M.marcap / M.rawclose
    A["sip"] = (M.si / sh * 100).where(sh > 0)
    A["dtc"] = M.dtc; A["sichg"] = M.chg; A["fresh"] = M.fresh.values
    # 1년 안 자기 잔고 대비 위치(공개일 값끼리)
    return A


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    A, uni, since = R.load_market("US")
    A = attach(A)
    print("sip 중앙 %.2f%% · dtc 중앙 %.2f" % (A.sip[A.fresh & uni].median(), A.dtc[A.fresh & uni].median()), flush=True)
    J = R.Judge(A, uni, "20180301")
    fr = A.fresh
    q = A[fr & uni].groupby("date").sip.rank(pct=True).reindex(A.index)
    cells = []
    def add(lab, cond):
        for h in (20, 60):
            Y = J.run(pd.Series(cond, index=A.index).fillna(False).astype(bool), h)
            Y["ex"] = Y.r - Y.date.map(J.bench(h))
            cells.append((lab, h, Y))
    add("잔고 상위 5%(%% 기준)", fr & (q >= 0.95))
    add("잔고 하위 20%", fr & (q <= 0.2))
    add("dtc ≥ 10일", fr & (A.dtc >= 10))
    add("잔고 급감(-40%↓) & 직전까지 많았던(sip≥5%)", fr & (A.sichg <= -40) & (A.sip >= 3))
    add("잔고 급증(+100%↑) & sip≥3%", fr & (A.sichg >= 100) & (A.sip >= 3))
    add("60일 -30%↓ & sip ≥ 10% (숏 스퀴즈 대기)", fr & (A.ret60 <= -30) & (A.sip >= 10))
    add("60일 -30%↓ & 잔고 급감 -30%↓ (숏 커버 시작)", fr & (A.ret60 <= -30) & (A.sichg <= -30))
    add("60일 -30%↓ & 잔고 하위 20% (숏도 안 붙은 낙폭)", fr & (A.ret60 <= -30) & (q <= 0.2))
    add("신고가권(fromhi ≥ -5%) & 잔고 하위 20%", fr & (A.fromhi >= -5) & (q <= 0.2))
    add("신고가권 & 잔고 상위 10%", fr & (A.fromhi >= -5) & (q >= 0.9))
    rows = []
    for lab, h, Y in cells:
        tr = Y[Y.date <= "20221231"]; va = Y[Y.date >= "20230101"]
        ys = tr.groupby(tr.date.str[:4]).ex.median()
        ok = len(tr) >= 30 and len(va) >= 15 and tr.r.median() > 0 and va.r.median() > 0 and tr.ex.median() > 0 and va.ex.median() > 0 and (ys > 0).mean() >= 0.6
        rows.append(dict(lab=lab, h=h, ntr=len(tr), nva=len(va), trm=tr.r.median(), trw=(tr.r > 0).mean() * 100, trx=tr.ex.median(),
                         vam=va.r.median(), vaw=(va.r > 0).mean() * 100, vax=va.ex.median(), ypos="%d/%d" % ((ys > 0).sum(), len(ys)), ok=ok))
    G = pd.DataFrame(rows)
    P("# C — 미장 공매도 잔고 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("FINRA 2주 잔고 · 결제일+%d거래일부터 앎 · 거래대금 상위 40%% · 비용 차감 · 학습 2018~22 / 검증 2023~" % LAG); P("")
    P("## 1) 독립 신호"); P("")
    P("| 조건 | 보유 | 학습 건수·중앙·승률·초과 | 검증 건수·중앙·승률·초과 | 학습 초과 플러스 해 | 판정 |"); P("|---|---|---|---|---|---|")
    for _, x in G.iterrows():
        P("| %s | %d일 | %d · %+.2f · %.0f%% · %+.2f | %d · %+.2f · %.0f%% · %+.2f | %s | %s |" % (
            x.lab, x.h, x.ntr, x.trm, x.trw, x.trx, x.nva, x.vam, x.vaw, x.vax, x.ypos, "✅" if x.ok else ""))
    # 2) 지금 규칙 안 거르개
    S = pickle.load(open(BASE / "data" / "sector_drop_us_sig.pkl", "rb"))["S"].copy()
    S["r"] = S.ret.astype(float)
    if S.r.abs().median() < 1:
        S["r"] = S.r * 100
    S = S[(S.date >= "20180301")][["date", "ticker", "rid", "r"]].merge(A[["date", "ticker", "sip", "dtc", "sichg"]], on=["date", "ticker"], how="left")
    P(""); P("## 2) 지금 미장 규칙 안 거르개 (신호 %d건 · 잔고 붙은 것 %.0f%%)" % (len(S), S.sip.notna().mean() * 100)); P("")
    P("| 규칙 | 거르개 | 학습 남김/전체 · 남김 평균 vs 전체 · z | 검증 남김/전체 · 남김 평균 vs 전체 · z |"); P("|---|---|---|---|")
    S = S.dropna(subset=["sip"])
    S["q"] = S.groupby("rid").sip.rank(pct=True)
    filt = [("잔고 하위 1/3", lambda z: z.q <= 1 / 3), ("잔고 상위 1/3 빼기", lambda z: z.q <= 2 / 3), ("잔고 상위 1/3만", lambda z: z.q > 2 / 3),
            ("잔고 줄어드는 중(chg<0)", lambda z: z.sichg < 0), ("dtc < 3", lambda z: z.dtc < 3)]
    fz = []
    for rid, g in S.groupby("rid"):
        for nm, fn in filt:
            cells2 = []
            for z in (g[g.date <= "20221231"], g[g.date >= "20230101"]):
                k = z[fn(z).fillna(False)]
                if len(z) < 20 or len(k) < 5:
                    cells2.append(None); continue
                se = z.r.std() / np.sqrt(len(k)) * np.sqrt(max(1 - len(k) / len(z), 1e-9))
                cells2.append((len(k), len(z), k.r.mean(), z.r.mean(), (k.r.mean() - z.r.mean()) / se))
            if None in cells2:
                continue
            fz.append((rid, nm, cells2))
            a, b = cells2
            P("| %s | %s | %d/%d · %+.2f vs %+.2f · %.1f | %d/%d · %+.2f vs %+.2f · %.1f |" % ((rid, nm) + a + b))
    log_trials("short_int_%s" % time.strftime("%Y%m%d"), len(G) + len(fz))
    G.to_pickle(ROOT / "cache" / "short_int.pkl")
    P(""); P("(%.0f분)" % ((time.time() - t0) / 60))
    (ROOT / "reports" / ("short_int_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
