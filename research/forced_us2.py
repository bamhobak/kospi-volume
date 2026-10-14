# -*- coding: utf-8 -*-
"""U1 연말 손실 확정 매도 → 1월 반등 다지기 (H0345 후속).
살 수 있는 종목만(주가 $3↑·시총 하한) · 매수일(12/1·12/15·12/22·마지막 날) · 보유(1월 말까지·20·40일) · 해마다 바구니(그해 신호 평균 = 표본 1개) ·
비용 0.25 + 소형 미끄러짐 가정 더(0.5·1.0) · 손실 폭(-30·-50·-70) · 시총 띠($50M~300M · 300M~2B · 2B↑).
    python research/forced_us2.py
"""
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def main():
    A = pd.read_pickle(BASE / "data" / "us_scan_full.pkl")[["date", "ticker", "close", "rawclose", "marcap", "pref", "amt20"]]
    A = A[~A.pref.fillna(False) & (A.rawclose >= 1)].sort_values(["ticker", "date"]).reset_index(drop=True)
    dates = np.array(sorted(A.date.unique()))
    yr_last = pd.Series(dates).groupby(pd.Series(dates).str[:4]).max()
    g = A.groupby("ticker", sort=False); last = g.close.transform("last")
    T = A[["date", "ticker"]].copy()
    TI = A.groupby("ticker").indices; DT = A.date.to_numpy(); CL = A.close.to_numpy()

    def fwd(sd, ed):
        """sd 종가 → ed(그날 또는 그 전 마지막 거래일) 종가, 폐지는 마지막 가격. 종목별 Series."""
        S = A[A.date == sd].set_index("ticker")
        out = {}
        for tk in S.index:
            ii = TI[tk]; j0 = np.searchsorted(DT[ii], sd); j1 = np.searchsorted(DT[ii], ed, side="right") - 1
            out[tk] = (CL[ii[max(j1, j0)]] / CL[ii[j0]] - 1) * 100
        return pd.Series(out)

    def first_on_after(d):
        k = np.searchsorted(dates, d); return dates[k] if k < len(dates) else None

    def nth_after(d, n):
        k = np.searchsorted(dates, d); return dates[min(k + n, len(dates) - 1)]

    rows = []
    for y in range(2008, 2026):
        b0 = yr_last.get(str(y - 1))
        if b0 is None: continue
        B = A[A.date == b0].set_index("ticker").close
        jan_end = pd.Series(dates[(dates >= "%d0101" % (y + 1)) & (dates <= "%d0131" % (y + 1))]).max()
        for sig_nm, sd in (("12/1", first_on_after("%d1201" % y)), ("12/15", first_on_after("%d1215" % y)), ("12/22", first_on_after("%d1222" % y)), ("마지막 날", yr_last.get(str(y)))):
            if sd is None or pd.isna(jan_end): continue
            S = A[A.date == sd].set_index("ticker").join(B.rename("c0"), how="inner")
            S["ytd"] = (S.close / S.c0 - 1) * 100
            S = S[(S.ytd <= -30) & (S.rawclose >= 3) & (S.marcap >= 50e6)]
            if not len(S): continue
            uni = A[(A.date == sd) & (A.rawclose >= 3) & (A.marcap >= 50e6)].ticker
            for hnm, ed in (("1월 말까지", jan_end), ("20일", nth_after(sd, 20)), ("40일", nth_after(sd, 40))):
                f = fwd(sd, ed).clip(-100, 300)
                bench = f.reindex(uni).mean()
                Z = S.join(f.rename("r"), how="inner")
                Z["x"] = Z.r - bench
                Z["y"] = y; Z["sig"] = sig_nm; Z["hold"] = hnm
                rows.append(Z.rename_axis("ticker").reset_index()[["ticker", "y", "sig", "hold", "ytd", "marcap", "r", "x"]])
        print("..", y, flush=True)
    E = pd.concat(rows)
    E.to_pickle(BASE / "research" / "cache" / "forced_us2.pkl")
    E["per"] = np.where(E.y <= 2015, "옛날", np.where(E.y <= 2022, "학습", "검증"))
    E["band"] = pd.cut(E.marcap, [50e6, 300e6, 2e9, 1e15], labels=["$50M~300M", "$300M~2B", "$2B↑"])
    P("## U1 연말 손실 확정 매도 → 1월 — 살 수 있는 종목(주가 $3↑·시총 $50M↑) · 해마다 바구니(그해 신호 평균) 초과(비용 전)")
    P("| 매수일 | 보유 | 해 수 | 바구니 평균 | 플러스 해 | 옛날 | 학습 | 검증 | 해마다 신호 수 |"); P("|---|---|---|---|---|---|---|---|---|")
    for (s, h), Z in E.groupby(["sig", "hold"], sort=False):
        Bk = Z.groupby("y").agg(x=("x", "mean"), n=("x", "size"), per=("per", "first"))
        pp = Bk.groupby("per").x.mean()
        P("| %s | %s | %d | %+.2f | %d/%d | %+.2f | %+.2f | %+.2f | %.0f |" % (s, h, len(Bk), Bk.x.mean(), (Bk.x > 0).sum(), len(Bk), pp.get("옛날", np.nan), pp.get("학습", np.nan), pp.get("검증", np.nan), Bk.n.mean()))
    P("\n### 12/15 매수 · 1월 말까지 — 시총 띠·손실 폭별 (해마다 바구니 평균 · 플러스 해 · 종목 중앙)")
    P("| 판 | 바구니 평균 | 플러스 해 | 종목 중앙 | 종목 승률 | 해마다 신호 수 |"); P("|---|---|---|---|---|---|")
    Z0 = E[(E.sig == "12/15") & (E.hold == "1월 말까지")]
    for nm, m in [("전체 -30%↓", Z0.ytd <= -30), ("-50%↓", Z0.ytd <= -50), ("-70%↓", Z0.ytd <= -70)] + [("시총 " + b, Z0.band == b) for b in ["$50M~300M", "$300M~2B", "$2B↑"]]:
        Z = Z0[m]; Bk = Z.groupby("y").x.mean()
        P("| %s | %+.2f | %d/%d | %+.2f | %.0f%% | %.0f |" % (nm, Bk.mean(), (Bk > 0).sum(), len(Bk), Z.x.median(), (Z.x > 0).mean() * 100, Z.groupby("y").size().mean()))
    P("\n비용: 왕복 0.25 + 소형주 미끄러짐 가정 0.5~1.0 → 바구니 평균에서 0.75~1.25 빼고 볼 것")
    Bk = Z0.groupby("y").x.mean()
    P("12/15 · 1월 말까지 해마다: " + " ".join("%d%+.1f" % (y % 100, v) for y, v in Bk.items()))
    (BASE / "research" / "cache" / "forced_us2.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
