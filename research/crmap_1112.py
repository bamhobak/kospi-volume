# -*- coding: utf-8 -*-
"""H0411 반대매매 발동 가격 지도 (2026-11-12 사용자 "기억 rulefind-1112 1번 실측").

가설: 신용으로 산 물량의 담보비율이 깨지면 이틀 뒤 아침 단일가에 반대매매가 시장가로 나온다 → 그 시가가 과하게 밀리고 되돌린다.
선 = 담보비율 k × (1 − 증거금률 m) × 신용 평균 단가 (예: 1.4 × 0.6 = 평균 단가의 84%). 종가가 선을 처음 깬 날 D → D+2(또는 D+1) 시가 매수.
 ① 말한 그대로 판: 평균 단가 = 최근 40일 신규 신용(loan_new)을 그날 종가로 가중 평균(=날짜·주가로 추정) · k 1.4 · m 0.4 · D+2 시가 → 당일 종가·3·5·10일
 ② 변형 판: k 1.3/1.5 · 창 20/60일 · 장부 평균(잔고 금액 ÷ 잔고 주수 — KIS 가 주는 값) · D+1 · 자료 지연 1/3/5일
          · 묶음 지도 모델(신규 신용을 그날 가격 칸에 쌓고 상환은 비례로 빼며, 선을 깬 칸만 '강제 물량'으로 셈 → 강제 물량 ÷ 20일 거래대금 5분위)
          · 대상: 강제 물량 비율 문턱 · 신용잔고율
 대조: 같은 날 · 20일 수익 ±3%p · 신용잔고율 0.3% 이하 종목의 같은 날 같은 보유 평균(낙폭 효과 떼기) · H0315 대리 판(잔고율 3%↑ & 20일 고점 -20% 처음)
 자료 지연: 신용 자료는 L(기본 3) 거래일 묵은 것만 쓴다 · 가격은 그날 종가까지. 비용 0.23. 옛날 2009~15 / 학습 2016~22 / 검증 2023~. 날 바구니 t.
    python research/crmap_1112.py build   → C:/temp/kp/crmap/ev.pkl
    python research/crmap_1112.py rep     → research/reports/crmap_1112.md
"""
import os, sys, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8")
CMD = sys.argv[1] if len(sys.argv) > 1 else "rep"
OUTD = Path("C:/temp/kp/crmap"); OUTD.mkdir(parents=True, exist_ok=True)
COST = 0.23
HS = (1, 3, 5, 10)
PER = (("옛날 09~15", "20090101", "20151231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"))
NB, LG = 820, np.log(1.02)


def wide(df, col, cal, tk):
    return df.pivot(index="date", columns="ticker", values=col).reindex(index=cal, columns=tk).values.astype(np.float32)


def build():
    import common as C
    c = sqlite3.connect(f"file:{BASE / 'data' / 'kis' / 'market.db'}?mode=ro", uri=True)
    K = pd.read_sql("select date, ticker, close, volume, loan_new, loan_rdmp, loan_rmnd, loan_rmnd_amt, loan_rmnd_rate from credit", c); c.close()
    P = pd.read_pickle(C.CACHE / "factory_px.pkl")
    P = P[P.date >= "20090101"]
    cal = sorted(P.date.unique()); tk = sorted(set(K.ticker) & set(P.ticker))
    print("날", len(cal), "종목", len(tk), flush=True)
    OP, CL = wide(P, "open", cal, tk), wide(P, "close", cal, tk); del P
    K = K[K.ticker.isin(tk)]
    NW, RD, RM, AM, RT, CC, VO = (wide(K, x, cal, tk) for x in ("loan_new", "loan_rdmp", "loan_rmnd", "loan_rmnd_amt", "loan_rmnd_rate", "close", "volume"))
    del K
    nd, nt = CL.shape
    # 액면 분할·병합 등 가격 불연속: 하루 ±40% 넘는 변화 → 그 뒤 60일 사건 막음
    rr = CL[1:] / CL[:-1]
    sp = np.zeros_like(CL, dtype=bool); sp[1:] = (rr > 1.42) | (rr < 0.58)
    blk = pd.DataFrame(sp).rolling(60, min_periods=1).max().values.astype(bool)
    amt20 = pd.DataFrame(np.nan_to_num(CC) * np.nan_to_num(VO)).replace(0, np.nan).rolling(20, min_periods=10).mean().values.astype(np.float32)
    r20 = (CL / pd.DataFrame(CL).shift(20).values - 1) * 100
    hi20 = pd.DataFrame(CL).rolling(20, min_periods=15).max().values
    # 앞으로 수익: 진입 i 의 시가 → i+h-1 종가 (비용 뒤)
    FR = {}
    for h in HS:
        x = (pd.DataFrame(CL).shift(-(h - 1)).values / OP - 1) * 100 - COST
        x[(np.abs(x) > 60) | ~np.isfinite(x)] = np.nan
        FR[h] = x.astype(np.float32)
    base_ok = (CL >= 1000) & (amt20 >= 3e8) & ~blk
    np.savez_compressed(OUTD / "fr.npz", **{"h%d" % h: FR[h] for h in HS}, r20=r20.astype(np.float32), rt=RT, ok=base_ok)
    pd.Series(cal).to_pickle(OUTD / "cal.pkl"); pd.Series(tk).to_pickle(OUTD / "tk.pkl")

    EV = []

    def add(name, mask, F=None, off=2, L=3):
        d, t = np.nonzero(mask)
        e = d + off
        keep = e < nd
        d, t, e = d[keep], t[keep], e[keep]
        df = pd.DataFrame({"var": name, "d": d, "t": t, "e": e, "off": off, "L": L,
                           "rate": RT[np.maximum(d - L, 0), t], "r20": r20[d, t], "amt20": amt20[d, t], "cl": CL[d, t]})
        if F is not None: df["F"] = F[d, t]
        for h in HS: df["r%d" % h] = FR[h][e, t]
        EV.append(df); print(name, len(df), flush=True)

    def lagged(X, L):
        Y = np.full_like(X, np.nan); Y[L:] = X[:-L]; return Y

    # ── 평균 단가 선 판 ──
    nwc = np.nan_to_num(NW) * np.nan_to_num(CC)
    for L in (1, 3, 5):
        RTL = lagged(RT, L)
        for W in (20, 40, 60):
            if L != 3 and W != 40: continue
            avg = pd.DataFrame(nwc).rolling(W, min_periods=W // 2).sum().values / pd.DataFrame(np.nan_to_num(NW)).rolling(W, min_periods=W // 2).sum().replace(0, np.nan).values
            avg = lagged(avg.astype(np.float32), L)
            for k in (1.3, 1.4, 1.5):
                if (L != 3 or W != 40) and k != 1.4: continue
                line = k * 0.6 * avg
                cross = (CL < line) & (np.vstack([np.full((1, nt), np.nan), CL[:-1]]) >= np.vstack([np.full((1, nt), np.nan), line[:-1]]))
                m = cross & base_ok & (RTL >= 0.5)
                for off in ((1, 2) if (L == 3 and W == 40 and k == 1.4) else (2,)):
                    add("추정 평균 W%d k%.1f L%d" % (W, k, L), m, off=off, L=L)
    # 장부 평균(잔고 금액 ÷ 주수)
    book = (np.nan_to_num(AM) * 1e4 / np.where(RM > 0, RM, np.nan)).astype(np.float32)
    book[(book / CC > 5) | (book / CC < 0.2)] = np.nan
    book = lagged(book, 3); RTL = lagged(RT, 3)
    for k in (1.3, 1.4, 1.5):
        line = k * 0.6 * book
        cross = (CL < line) & (np.vstack([np.full((1, nt), np.nan), CL[:-1]]) >= np.vstack([np.full((1, nt), np.nan), line[:-1]]))
        add("장부 평균 k%.1f L3" % k, cross & base_ok & (RTL >= 0.5))
    # H0315 대리 판
    first = (CL <= 0.8 * hi20) & (np.vstack([np.full((1, nt), np.nan), CL[:-1]]) > 0.8 * np.vstack([np.full((1, nt), np.nan), hi20[:-1]]))
    add("H0315 대리(잔고율 3%↑·20일 고점 -20%)", first & base_ok & (RTL >= 3))

    # ── 묶음 지도 모델: 강제 물량 ──
    ar = np.arange(NB, dtype=np.int32)
    bidx = lambda p: np.clip(np.round(np.log(np.maximum(p, 1)) / LG), 0, NB - 1).astype(np.int32)
    for (k, m_, L) in ((1.4, 0.4, 3), (1.3, 0.4, 3), (1.5, 0.4, 3), (1.4, 0.5, 3), (1.4, 0.4, 1), (1.4, 0.4, 5)):
        S = np.zeros((nt, NB), np.float32); init = np.zeros(nt, bool); FS = np.zeros((nd, nt), np.float32)
        for i in range(nd):
            j = i - L
            if j >= 0:
                rm, nw, rd, cc = RM[j], NW[j], RD[j], CC[j]
                ok = np.isfinite(rm) & np.isfinite(cc) & (cc > 0)
                ni = ok & ~init
                if ni.any():
                    r_ = np.nonzero(ni)[0]; S[r_, bidx(cc[r_])] += rm[r_]; init |= ni
                up = np.nonzero(ok & init & ~ni)[0]
                if len(up) and j >= 1:
                    pv = RM[j - 1][up]
                    ratio = np.where(np.isfinite(pv) & (pv > 0), 1 - np.nan_to_num(rd[up]) / np.where(pv > 0, pv, 1), 1.0)
                    S[up] *= np.clip(ratio, 0, 1)[:, None]
                    S[up, bidx(cc[up])] += np.nan_to_num(nw[up])
                rs = np.nonzero(sp[j] & ok)[0]
                if len(rs): S[rs] = 0; S[rs, bidx(cc[rs])] = rm[rs]
            c_ = CL[i]; v = np.isfinite(c_) & (c_ > 0) & init
            if not v.any(): continue
            tb = np.floor(np.log(np.where(v, c_, 1) / (k * (1 - m_))) / LG).astype(np.int32)
            mk = (ar[None, :] > tb[:, None]) & v[:, None]
            FS[i] = (S * mk).sum(1); S[mk] = 0
            if i % 500 == 0: print("  지도", k, m_, L, i, nd, flush=True)
        F = FS * CL / np.where(amt20 > 0, amt20, np.nan)
        val = FS * CL
        add("지도 k%.1f m%.1f L%d" % (k, m_, L), (val >= 1e8) & base_ok & (np.arange(nd)[:, None] >= 250), F=F.astype(np.float32), L=L)
    E = pd.concat(EV, ignore_index=True)
    E["date"] = np.array(cal)[E.d.values]; E["ticker"] = np.array(tk)[E.t.values]
    E.to_pickle(OUTD / "ev.pkl"); print("끝", len(E), flush=True)


def rep():
    from verdict import log_trials
    E = pd.read_pickle(OUTD / "ev.pkl")
    Z = np.load(OUTD / "fr.npz"); FR = {h: Z["h%d" % h] for h in HS}; r20 = Z["r20"]; rt = Z["rt"]; ok = Z["ok"]
    # 대조: 같은 날(d) · 20일 수익 ±3%p · 잔고율 ≤0.3 · 같은 진입(e)
    keys = E[["d", "e", "t", "r20"]].drop_duplicates(["d", "e", "t"])
    ctrl = {h: {} for h in HS}
    for (d, e), g in keys.groupby(["d", "e"]):
        pool = ok[d] & (np.nan_to_num(rt[max(d - 3, 0)], nan=9) <= 0.3) & np.isfinite(r20[d])
        if not pool.any(): continue
        pr = r20[d][pool]
        for h in HS:
            fr = FR[h][e][pool]
            for t, x in zip(g.t.values, g.r20.values):
                sel = np.abs(pr - x) <= 3
                if sel.sum() >= 3: ctrl[h][(d, e, t)] = float(np.nanmean(fr[sel]))
    for h in HS:
        E["c%d" % h] = [ctrl[h].get(k) for k in zip(E.d, E.e, E.t)]
        E["x%d" % h] = E["r%d" % h] - E["c%d" % h]
    OUT = []; P = lambda s="": (OUT.append(s), print(s, flush=True))

    def cell(z, col):
        z = z.dropna(subset=[col])
        if len(z) < 10: return "%d건" % len(z)
        dd = z.groupby("date")[col].mean()
        t = dd.mean() / dd.std() * np.sqrt(len(dd)) if len(dd) > 3 and dd.std() > 0 else float("nan")
        return "%d건 %+.2f · 날 %d개 **%+.2f** t%.1f" % (len(z), z[col].mean(), len(dd), dd.mean(), t)

    def per(z, a, b): return z[(z.date >= a) & (z.date <= b)]
    P("# 반대매매 발동 가격 지도 (H0411) · 2026-11-12"); P("")
    P("- 선 = 담보비율 k × (1 − 증거금 0.4) × 신용 평균 단가. 종가가 선을 처음 깬 날 D → D+2 시가 매수(비용 0.23 뒤). 신용 자료는 L 거래일 묵은 것만 사용.")
    P("- 칸 = 건수 건당 · 날 바구니 **평균** t. '대조 대비' = 같은 날·20일 수익 ±3%p·신용잔고율 0.3%↓ 종목 같은 보유 평균을 뺀 값(낙폭 효과 떼기)")
    P("- 공통: 주가 1,000원↑ · 20일 거래대금 3억↑ · 가격 불연속(±40%) 뒤 60일 제외 · 평균 단가 판은 신용잔고율 0.5%↑"); P("")
    ncell = 0
    VARS = list(dict.fromkeys(E["var"]))
    first = "추정 평균 W40 k1.4 L3"
    for sec, vs in (("① 말한 그대로 판", [first]), ("② 변형 판", [v for v in VARS if v != first])):
        P("## " + sec); P("")
        for v in vs:
            for off in sorted(E[E["var"] == v].off.unique()):
                z = E[(E["var"] == v) & (E.off == off)]
                P("### %s · D+%d 시가 매수" % (v, off)); P("")
                P("| 보유 | " + " | ".join(n for n, _, _ in PER) + " |"); P("|---|---|---|---|")
                for h in HS:
                    P("| %s | %s |" % ("당일(시가→종가)" if h == 1 else "%d일" % h, " | ".join(cell(per(z, a, b), "r%d" % h) for _, a, b in PER)))
                    P("| ↳ 대조 대비 | %s |" % " | ".join(cell(per(z, a, b), "x%d" % h) for _, a, b in PER))
                    ncell += 2
                P("")
    P("## ③ 지도 모델 — 강제 물량 ÷ 20일 거래대금(F) 크기별 · 당일 / 5일 · 학습 16~22 · 검증 23~"); P("")
    P("| 판 | F | 당일 학습 | 당일 검증 | 5일 학습 | 5일 검증 | 5일 대조 대비 검증 |"); P("|---|---|---|---|---|---|---|")
    for v in [x for x in VARS if x.startswith("지도")]:
        z = E[E["var"] == v].dropna(subset=["F"])
        for lo, hi in ((0, 0.05), (0.05, 0.2), (0.2, 0.5), (0.5, 1.0), (1.0, 99)):
            w = z[(z.F >= lo) & (z.F < hi)]
            P("| %s | %.2f~%s | %s | %s | %s | %s | %s |" % (v, lo, ("%.2f" % hi) if hi < 99 else "", cell(per(w, *PER[1][1:]), "r1"), cell(per(w, *PER[2][1:]), "r1"),
                                                      cell(per(w, *PER[1][1:]), "r5"), cell(per(w, *PER[2][1:]), "r5"), cell(per(w, *PER[2][1:]), "x5")))
            ncell += 5
    P("")
    P("## ④ 말한 판 — 해마다 · 날 몰림"); P("")
    z = E[(E["var"] == first) & (E.off == 2)]
    y = z.groupby(z.date.str[:4]).agg(n=("r1", "size"), days=("date", "nunique"), r1=("r1", "mean"), r5=("r5", "mean"), x5=("x5", "mean")).round(2)
    P("| 해 | 건수 | 날 | 당일 | 5일 | 5일 대조 대비 |"); P("|---|---|---|---|---|---|")
    for yr, r in y.iterrows(): P("| %s | %d | %d | %+.2f | %+.2f | %+.2f |" % (yr, r.n, r.days, r.r1, r.r5, r.x5))
    top = z.groupby("date").size().sort_values(ascending=False).head(8)
    P(""); P("가장 몰린 날: " + " · ".join("%s %d건" % (d, n) for d, n in top.items()))
    P(""); P("(칸 %d)" % ncell)
    (ROOT / "reports" / "crmap_1112.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    log_trials("crmap_1112", ncell)


if __name__ == "__main__":
    build() if CMD == "build" else rep()
