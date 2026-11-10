# -*- coding: utf-8 -*-
"""H0410 전날 막판 급등·급락주 빼기 거르개 — 지금 규칙에 붙이면 나아지나 (2026-11-11 사용자 "이거 과거 데이터로 실측해봐").

출발점(lhgap_1111 참고 표): 국장 전 종목에서 전날 막판 1시간(14:30→종가) 시장 대비 +3%p↑ 는 다음 날 시가→종가 -1.14/-1.33,
-3%p↓ 는 -0.58/-1.27 (보통 -0.34/-0.39). → 규칙 거래에서도 이런 종목이 나쁜가, 빼면 계좌가 나아지나.
 ① 말한 그대로 판: 막판 1시간 시장 대비 +3%p↑ 또는 -3%p↓ 이면 뺀다
 ② 변형 판: 위쪽만(+1·+2·+3) · 아래쪽만(-2·-3) · 양쪽 ±2 · 막판 창 30분·2시간 · 시장 대비 대신 절대 등락 · 빼기 대신 0.5배(계좌)
 규칙: 데이 T1 [갭 하락 조용주]·T2 [갭 하락 조용주 +]·T3 [갭 하락 조용주 ++]·T4 [미장 폭락 과잉 갭] = 매수 날의 '전 거래일' 막판
       T6 [NXT 장후 빠진 종목] = 장후 매수 날 정규장 막판 · 스윙 국장 규칙 = 신호 날 막판(매수가 그날 종가·다음 날 시가라 그때 알 수 있다)
 ⚠ T2 는 원래 '어제 14:00→종가 -1%↓' 를 한 번 더 사는 규칙 — 아래쪽 빼기와 정면으로 부딪힌다(따로 본다).
 1분봉 2022-12~2026-10 만 → 학습 22.12~24 / 검증 25~. 시장 = 그날 1분봉 전 종목 중앙.
    python research/dayfilt_1111.py build    # 날마다 막판 표 → C:/temp/kp/dayfilt/lh.pkl
    python research/dayfilt_1111.py rep      # → research/reports/dayfilt_1111.md
"""
import io, os, sys, glob, pickle, warnings, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
CMD = sys.argv[1] if len(sys.argv) > 1 else "rep"
OUTD = Path("C:/temp/kp/dayfilt"); OUTD.mkdir(parents=True, exist_ok=True)
KD = Path("C:/temp/kp/kind")
START, NMIN = 9 * 60 + 1, 391
IX = {"30": 359, "60": 329, "90": 299, "120": 269}          # 장 끝 30·60·90·120분 전 봉(15:00·14:30·14:00·13:30)
PER = (("학습 22.12~24", "20221201", "20241231"), ("검증 25~", "20250101", "20991231"))


def load(f):
    B = pd.read_parquet(f, columns=["ts", "c", "v"])
    k = pd.to_datetime(B.ts.values + 9 * 3600, unit="s")
    mi = (k.hour * 60 + k.minute).values - START
    ok = (mi >= 0) & (mi < NMIN)
    B = B[ok]; day = k.strftime("%Y%m%d")[ok]; mi = mi[ok]
    days, di = np.unique(day, return_inverse=True)
    C = np.full((len(days), NMIN), np.nan); V = np.zeros((len(days), NMIN))
    C[di, mi] = B.c.values; V[di, mi] = B.v.values
    Cf = pd.DataFrame(np.where(V > 0, C, np.nan)).ffill(axis=1).values
    return days, Cf, V


def build():
    files = sorted(glob.glob(str(BASE / "data" / "m1" / "KR" / "bf" / "*.parquet")))
    rows = []
    for i, f in enumerate(files):
        t = Path(f).stem
        try: days, Cf, V = load(f)
        except Exception: continue
        if not len(days): continue
        cl = Cf[:, -1]
        d = {"t": t, "date": days, "val": np.nansum(np.where(V > 0, Cf * V, 0), axis=1)}
        for k_, ix in IX.items(): d["a" + k_] = (cl / Cf[:, ix] - 1) * 100
        rows.append(pd.DataFrame(d))
        if i % 300 == 0: print(i, len(files), flush=True)
    D = pd.concat(rows, ignore_index=True)
    for k_ in IX:
        D.loc[D["a" + k_].abs() > 30, "a" + k_] = np.nan
        D["r" + k_] = D["a" + k_] - D.groupby("date")["a" + k_].transform("median")
    D.to_pickle(OUTD / "lh.pkl"); print("끝", len(D), D.date.min(), D.date.max(), flush=True)


# ── 거르개 정의: (이름, 함수(표) → 뺄 것) ──
FILT = [
    ("① 말한 그대로: 막판 1시간 시장 대비 +3%p↑ 또는 -3%p↓", lambda z: (z.r60 >= 3) | (z.r60 <= -3)),
    ("위쪽만 +3%p↑", lambda z: z.r60 >= 3),
    ("위쪽만 +2%p↑", lambda z: z.r60 >= 2),
    ("위쪽만 +1%p↑", lambda z: z.r60 >= 1),
    ("아래쪽만 -3%p↓", lambda z: z.r60 <= -3),
    ("아래쪽만 -2%p↓", lambda z: z.r60 <= -2),
    ("양쪽 ±2%p", lambda z: z.r60.abs() >= 2),
    ("막판 30분 ±3%p", lambda z: z.r30.abs() >= 3),
    ("막판 2시간 ±3%p", lambda z: z.r120.abs() >= 3),
    ("절대 등락 1시간 ±3%", lambda z: z.a60.abs() >= 3),
]


def attach(T, LH, cal, prev):
    """T(ticker,date,r) 에 막판 값 붙이기. prev=True 면 매수 날의 전 거래일 값."""
    T = T.copy(); T["ticker"] = T.ticker.astype(str).str.zfill(6)
    if prev:
        ca = np.array(cal); ix = np.searchsorted(ca, T.date.values) - 1
        T["fd"] = np.where(ix >= 0, ca[np.maximum(ix, 0)], "")
    else: T["fd"] = T.date
    X = T.merge(LH.rename(columns={"t": "ticker", "date": "fd"}), on=["ticker", "fd"], how="left")
    return X


def cell(z, col="r"):
    z = z.dropna(subset=[col])
    if len(z) < 5: return "%d건" % len(z)
    d = z.groupby("date")[col].mean()
    t = d.mean() / d.std() * np.sqrt(len(d)) if len(d) > 3 and d.std() > 0 else float("nan")
    return "%d건 **%+.2f** (승 %.0f%%) t%.1f" % (len(z), z[col].mean(), (z[col] > 0).mean() * 100, t)


def per(z, a, b): return z[(z.date >= a) & (z.date <= b)]


def rule_table(P, nm, X, col="r"):
    X = X[X.date >= "20221201"]
    cov = X.r60.notna().mean() * 100
    X = X.dropna(subset=["r60"])
    P("### %s — 막판 값 있는 거래 %.0f%%" % (nm, cov)); P("")
    P("| 거르개 | 빠지는 비율 | 빠지는 거래 학습 | 빠지는 거래 검증 | 남는 거래 학습 | 남는 거래 검증 |"); P("|---|---|---|---|---|---|")
    P("| (지금 그대로) | 0%% | | | %s | %s |" % tuple(cell(per(X, a, b), col) for _, a, b in PER))
    for fn, f in FILT:
        m = f(X).fillna(False).values
        P("| %s | %.1f%% | %s | %s | %s | %s |" % (fn, m.mean() * 100, cell(per(X[m], *PER[0][1:]), col), cell(per(X[m], *PER[1][1:]), col),
                                              cell(per(X[~m], *PER[0][1:]), col), cell(per(X[~m], *PER[1][1:]), col)))
    P("")
    return len(FILT) * 4


def rep():
    import lab, feats as FT
    import t1_size_liq_1021 as SL
    import FinanceDataReader as fdr
    from verdict import log_trials
    LH = pd.read_pickle(OUTD / "lh.pkl")[["t", "date", "a60", "r30", "r60", "r90", "r120", "a90"]]
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))
    ncell = 0
    H = lab.hist()[["ticker", "date", "oc", "gap", "rgap", "q_gap", "q_vm", "liq", "amt20", "tr_pred", "q_tr_res"]]
    H = H[H.date >= "20221101"].dropna(subset=["oc", "gap", "rgap", "liq", "amt20"]).copy()
    H["ticker"] = H.ticker.astype(str).str.zfill(6)
    cal = sorted(lab.hist().date.unique())
    H["r"] = H.oc - FT.COST; H["a20"] = H.amt20 * 1e8
    H["gq"] = H.groupby("date").gap.rank(pct=True)
    T1 = H[(H.q_vm.fillna(1) <= 0.30) & (H.liq <= 2 / 3) & (H.gq <= 0.40) & (H.rgap <= -1.5) & (H.gap > -27.5)].copy()
    T1 = attach(T1, LH, cal, True)
    T1["t2"] = (T1.liq <= 1 / 3) & (T1.a90 <= -1.0)
    T1["t3"] = (T1.liq <= 1 / 3) & (T1.tr_pred <= -0.5).fillna(False)
    X = fdr.DataReader("IXIC", "2022-01-01"); X = X[X.Close > 0]
    us = X.Close.pct_change() * 100; us.index = us.index.strftime("%Y%m%d"); ud = us.index.values
    H["us"] = H.date.map({d: (us.iloc[np.searchsorted(ud, d) - 1] if np.searchsorted(ud, d) > 0 else np.nan) for d in H.date.unique()})
    T4 = attach(H[(H.us <= -2.5) & (H.gap <= -2.0) & (H.q_tr_res <= 0.10) & (H.liq <= 0.5) & (H.gap > -27.5)], LH, cal, True)

    P("# 전날 막판 급등·급락주 빼기 거르개 — 지금 규칙에 붙여 보기 (H0410) · 2026-11-11"); P("")
    P("- 막판 = 장 끝 1시간(14:30→종가) 등락 − 그날 1분봉 전 종목 중앙(시장 대비). 1분봉 %s~%s → 학습 22.12~24 / 검증 25~" % (LH.date.min(), LH.date.max()))
    P("- 칸 = 건수 **건당 평균**(비용 0.23 뒤) · 승률 · 날 바구니 t. '빠지는 거래'가 남는 거래보다 확실히 나쁘고(둘 다 구간에서) 마이너스여야 거르개 값이 있다.")
    P("- 데이 규칙은 매수 날의 전 거래일 막판, T6·스윙은 그날(장후 매수 날·신호 날) 막판"); P("")
    P("## ① 데이 규칙"); P("")
    ncell += rule_table(P, "T1 [갭 하락 조용주] (실제 갭 기준 · 예상 갭 오차 없음)", T1)
    ncell += rule_table(P, "T2 [갭 하락 조용주 +] (T1 중 크기 1/3 안 · 어제 14:00→종가 -1%↓)", T1[T1.t2])
    ncell += rule_table(P, "T3 [갭 하락 조용주 ++] (T1 중 크기 1/3 안 · 짝 미장 예상 갭 -0.5%↓)", T1[T1.t3])
    ncell += rule_table(P, "T1 중 T2 아님", T1[~T1.t2])
    ncell += rule_table(P, "T4 [미장 폭락 과잉 갭]", T4)
    t6 = pickle.load(open(KD / "t6.pkl", "rb"))["T"]
    ncell += rule_table(P, "T6 [NXT 장후 빠진 종목] (그림자 조건 · 장후 매수 날 정규장 막판)", attach(t6, LH, cal, False))

    # ── 계좌: T1+T2+T3 꾸러미, 5천만 하루 한도, 실제 갭 기준 ──
    with contextlib.redirect_stdout(io.StringIO()):
        ab, cf = SL.fit(SL.liq_of_exec())
    imp = lambda p: np.maximum(0.0, ab[0] + ab[1] * np.sqrt(p)); fill = lambda p: 1 / (1 + cf * p)
    A0 = T1[T1.date >= "20221201"].dropna(subset=["r60"]).copy()

    def acct(drop, mode="drop", cap=5e7):
        S = A0.copy()
        S["unit"] = 50e4 * (-S.rgap).clip(1, 3) * (S.a20 / S.groupby("date").a20.transform("median")).clip(0.3, 3)
        S["k"] = 1 + S.t2.astype(int) + S.t3.astype(int)
        S["amt"] = S.unit * S.k
        if drop is not None:
            m = drop(S).fillna(False).values
            if mode == "drop": S = S[~m]
            elif mode == "half": S.loc[m, "amt"] *= 0.5
            elif mode == "noextra": S.loc[m, "amt"] = S.loc[m, "unit"]          # 덤만 안 붙임
        S = S.sort_values(["date", "rgap"]); S["cum"] = S.groupby("date").amt.cumsum(); S = S[S.cum <= cap]
        p = S.amt / S.a20 * 100
        S["inv"] = S.amt * fill(p); S["pnl"] = S.inv * (S.r - imp(p) + 0.05) / 100
        o = []
        for _, a, b in PER:
            z = per(S, a, b); yrs = per(A0, a, b).date.nunique() / 250
            o.append("%+.0f만 · %.0f건 · %.1f억 투입" % (z.pnl.sum() / 1e4 / yrs, len(z) / yrs, z.inv.sum() / 1e8 / yrs))
        dd = S.groupby("date").pnl.sum().cumsum() / 1e4
        o.append("%+.0f만" % (dd - dd.cummax()).min())
        return o

    P("## ② 계좌 — T1+T2+T3 꾸러미 (하루 5천만 한도 · 금액·체결 손해는 지금 모형 · 실제 갭 기준)"); P("")
    P("칸 = 1년 손익 · 연 주문 건수 · 연 투입 / 최대 낙폭"); P("")
    P("| 방법 | 학습 22.12~24 | 검증 25~ | 최대 낙폭 |"); P("|---|---|---|---|")
    P("| 지금 그대로 | %s | %s | %s |" % tuple(acct(None)))
    for fn, f in FILT:
        P("| 빼기 · %s | %s | %s | %s |" % ((fn,) + tuple(acct(f))))
    for fn, f in FILT[:2]:
        P("| 0.5배 · %s | %s | %s | %s |" % ((fn,) + tuple(acct(f, "half"))))
        P("| 덤(T2·T3)만 안 붙임 · %s | %s | %s | %s |" % ((fn,) + tuple(acct(f, "noextra"))))
    ncell += len(FILT) + 4
    P("")

    P("## ③ 변형 — 스윙 국장 규칙 (신호 날 막판 · 규칙 거래 그대로)"); P("")
    sw = pickle.load(open(KD / "swing.pkl", "rb"))
    for rid, o in sw.items():
        X = attach(o["T"], LH, cal, False)
        if X[X.date >= "20221201"].r60.notna().sum() < 30: continue
        ncell += rule_table(P, "%s [%s] (보유 %s일 · 매수=종가 %.0f%%)" % (o["disp"], o["name"], o["hold"], o["buy_close"] * 100), X)
    P("(칸 %d)" % ncell)
    (ROOT / "reports" / "dayfilt_1111.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    log_trials("dayfilt_1111", ncell)


if __name__ == "__main__":
    build() if CMD == "build" else rep()
