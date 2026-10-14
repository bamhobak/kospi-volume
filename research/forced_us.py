# -*- coding: utf-8 -*-
"""'남들이 어쩔 수 없이 파는 자리' 미장 2종 (2026-10-15) — H0345·H0346. 폐지 포함 패널 us_scan_full(2007~).

U1 연말 손실 확정 매도(tax-loss) → 1월 반등: 올해 -30%↓(·-50%↓) 소형주(그날 시총 중앙값 아래)를
   12월 중순(15일 뒤 첫 거래일) 또는 마지막 거래일 종가 매수 → 20·40일 보유. 대조: 6월 같은 조건(세금 동기 없음).
U2 러셀 정기변경 편출: 순위일(5월 마지막 거래일 · 2024~ 4월 마지막 거래일) 시총 순위로 러셀 근사(상위 3000 · 2000 = 1001~3000) —
   작년 1001~3000 → 올해 3200위 밖(러셀2000에서 빠짐) / 작년 1001~3000 → 올해 900위 안(러셀1000으로 졸업 · 2000 펀드가 팜)
   변경일(6월 마지막 금요일) 종가 매수 → 5·20·60일. 대조: 2년 연속 2500~3000위(계속 남음).
잣대: 같은 날 유니버스(주가 $3↑) 같은 보유 평균 대비 초과 · 비용 0.25 · 폐지는 마지막 가격. 구간 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/forced_us.py
"""
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
COST = 0.25


def per(d):
    return np.where(d <= "20151231", "옛날", np.where(d <= "20221231", "학습", "검증"))


def cell(x):
    x = x.dropna()
    if len(x) < 8: return "%d건" % len(x)
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else 0
    return "%d · %+.2f · 중앙 %+.2f · %.0f%% · t%.1f" % (len(x), x.clip(-100, 300).mean(), x.median(), (x > 0).mean() * 100, t)


def table(title, rows, cols, head):
    P("\n### " + title)
    P("| 판 | " + " | ".join("%s 옛날 | 학습 | 검증" % h for h in head) + " |"); P("|---" * (1 + 3 * len(head)) + "|")
    for nm, Z in rows:
        Z = Z.assign(p=per(Z.date.values)); cs = []
        for c in cols:
            for p in ("옛날", "학습", "검증"): cs.append(cell(Z.loc[Z.p == p, c]))
        P("| %s | %s |" % (nm, " | ".join(cs)))
    # 해마다(첫 칸)
    allz = pd.concat([Z.assign(nm=nm) for nm, Z in rows])
    allz["y"] = allz.date.str[:4]
    t = allz.groupby(["nm", "y"])[cols[0]].mean().unstack()
    P("\n해마다 %s 평균 초과: " % head[0] + " / ".join("%s: %s" % (nm, " ".join("%s%+.1f" % (y[2:], v) for y, v in t.loc[nm].dropna().items())) for nm, _ in rows))


def main():
    A = pd.read_pickle(BASE / "data" / "us_scan_full.pkl")[["date", "ticker", "close", "rawclose", "marcap", "pref"]]
    A = A[~A.pref.fillna(False) & (A.rawclose >= 1)].sort_values(["ticker", "date"]).reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    last = g.close.transform("last")
    for h in (5, 20, 40, 60):
        A["c%d" % h] = ((g.close.shift(-h).fillna(last) / A.close - 1) * 100).clip(-100, 300)
        bench = A["c%d" % h].where(A.rawclose >= 3).groupby(A.date).transform("mean")
        A["x%d" % h] = A["c%d" % h] - bench - COST
    dates = np.array(sorted(A.date.unique()))
    P("# 미장 강제 매도 2종 — %d줄 · %d종목 · %s~%s" % (len(A), A.ticker.nunique(), dates[0], dates[-1]))

    # ── U1 tax-loss ──
    yr_last = pd.Series(dates).groupby(pd.Series(dates).str[:4]).max()
    def first_on_after(d):
        k = np.searchsorted(dates, d); return dates[k] if k < len(dates) else None
    rows = []
    for nm, mmdd_sig, base_mmdd, thr in (("12월 중순 · 올해 -30%↓ · 소형", "1215", "0101", -30), ("12월 중순 · 올해 -50%↓ · 소형", "1215", "0101", -50),
                                          ("12월 마지막 날 · 올해 -30%↓ · 소형", "last", "0101", -30), ("대조: 6월 중순 · 연초 대비 -30%↓ · 소형", "0615", "0101", -30)):
        recs = []
        for y in range(2008, 2026):
            sd = yr_last.get(str(y)) if mmdd_sig == "last" else first_on_after("%d%s" % (y, mmdd_sig))
            b0 = yr_last.get(str(y - 1))
            if sd is None or b0 is None: continue
            S = A[A.date == sd].set_index("ticker"); B = A[A.date == b0].set_index("ticker").close
            S = S.join(B.rename("c0"), how="inner")
            S["ytd"] = (S.close / S.c0 - 1) * 100
            med = S.marcap.median()
            Z = S[(S.ytd <= thr) & (S.marcap < med) & (S.rawclose >= 1)]
            recs.append(Z.reset_index()[["date", "ticker", "x20", "x40", "c20"]])
        rows.append((nm, pd.concat(recs)))
    table("U1 연말 손실 확정 매도 → 1월 (종목 단위 · 비용 뒤 초과: 20일 / 40일 · 20일 절대)", rows, ["x20", "x40", "c20"], ["20일 초과", "40일 초과", "20일 절대"])

    # ── U2 러셀 ──
    recs = {k: [] for k in ("del", "grad", "stay")}
    prev_rank = None
    for y in range(2007, 2026):
        rd = pd.Series(dates[(dates >= "%d0401" % y) & (dates <= ("%d0430" if y >= 2024 else "%d0531") % y)]).max()
        jun = pd.to_datetime(pd.Series(dates[(dates >= "%d0601" % y) & (dates <= "%d0630" % y)]))
        fri = jun[jun.dt.weekday == 4]
        if pd.isna(rd) or not len(fri): continue
        recon = fri.max().strftime("%Y%m%d")
        S = A[(A.date == rd) & A.marcap.notna()].copy()
        S["rk"] = S.marcap.rank(ascending=False)
        rk = S.set_index("ticker").rk
        if prev_rank is not None:
            both = pd.concat([prev_rank.rename("r0"), rk.rename("r1")], axis=1, join="inner")
            Rc = A[A.date == recon].set_index("ticker")[["date", "x5", "x20", "x60"]]
            for k, m in (("del", both.r0.between(1001, 3000) & (both.r1 > 3200)), ("grad", both.r0.between(1001, 3000) & (both.r1 <= 900)),
                         ("stay", both.r0.between(2500, 3000) & both.r1.between(2500, 3000))):
                recs[k].append(Rc.join(both[m], how="inner").reset_index()[["date", "ticker", "x5", "x20", "x60"]])
        prev_rank = rk
    rows = [("러셀2000 편출(작년 1001~3000 → 3200위 밖)", pd.concat(recs["del"])), ("러셀1000 졸업(→ 900위 안)", pd.concat(recs["grad"])),
            ("대조: 2년 연속 2500~3000위", pd.concat(recs["stay"]))]
    table("U2 러셀 변경일 종가 매수 (종목 단위 · 비용 뒤 초과: 5 / 20 / 60일)", rows, ["x20", "x5", "x60"], ["20일", "5일", "60일"])
    (BASE / "research" / "cache" / "forced_us.out").write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
