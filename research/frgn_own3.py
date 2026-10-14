# -*- coding: utf-8 -*-
"""frgn_own 3 — 외인 비중 '수준'이 시총 효과인지 + 기존 국장 규칙(portfolio.py 9개) 신호를 외인 비중으로 거르면 (H0334).
판정 = 돈 무한·다 산다(신호마다 portfolio.py 의 청산 그대로 · 비용 포함 ret).
    python research/frgn_own3.py
"""
import sys, glob, io, os
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research" / "factory"))
import numpy as np, pandas as pd

OUT = []
def P(s=""):
    OUT.append(s); sys.__stdout__.write(s + "\n"); sys.__stdout__.flush()

U = pd.read_pickle(BASE / "research" / "cache" / "frgn_own.pkl")
U["yr"] = U.date.str[:4]
PER = [("옛날", "20100101", "20151231"), ("학습", "20160101", "20221231"), ("검증", "20230101", "20991231")]

P("## 1. 거래대금 같은 무리 안에서도 외인 비중 수준이 갈리나 — 20일 초과(%) 옛날/학습/검증")
U["mc3"] = pd.cut(U.groupby("date").liq.rank(pct=True), [0, 1 / 3, 2 / 3, 1], labels=["작은", "중간", "큰"])
P("| 거래대금 | 외인 비중 하위20% | 20~80% | 상위20% |"); P("|---|---|---|---|")
U["q_fr_in"] = U.groupby(["date", "mc3"], observed=True).fr.rank(pct=True)
for mc in ["작은", "중간", "큰"]:
    row = []
    for lo, hi in ((0, 0.2), (0.2, 0.8), (0.8, 1.01)):
        m = (U.mc3 == mc) & (U.q_fr_in > lo) & (U.q_fr_in <= hi)
        cs = []
        for _, a, b in PER:
            x = U.loc[m & (U.date >= a) & (U.date <= b), "x_sw20"].dropna()
            cs.append("%+.2f" % x.mean())
        row.append("/".join(cs))
    P("| %s | %s |" % (mc, " | ".join(row)))

# 기존 규칙 신호 — portfolio.py 를 @@ANALYSIS 앞까지만
src = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS")[0].replace('sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")', "")
_cwd = os.getcwd(); os.chdir(BASE)
ns = {"__file__": str(BASE / "portfolio.py"), "__name__": "pf"}
_o = sys.stdout
exec(compile(src, "portfolio.py", "exec"), ns)
sys.stdout = _o; os.chdir(_cwd)
S = ns["S"].copy()
S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost

fs = sorted(glob.glob(str(BASE / "data" / "20[0-2][0-9]-[01][0-9].csv")))
F = pd.concat([pd.read_csv(f, usecols=["date", "ticker", "foreign_ratio"], dtype={"ticker": str, "date": str}) for f in fs if Path(f).stem >= "2004-01"], ignore_index=True)
F = F.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"])
g = F.groupby("ticker", sort=False).foreign_ratio
F["fd20"] = F.foreign_ratio - g.shift(20)
F["fd60"] = F.foreign_ratio - g.shift(60)
F["qfr"] = F.groupby("date").foreign_ratio.rank(pct=True)          # 그날 상장 전 종목 안 순위
S = S.merge(F[["ticker", "date", "foreign_ratio", "qfr", "fd20", "fd60"]], on=["ticker", "date"], how="left")
S = S[S.date >= "20050101"]
S["per"] = np.where(S.date <= "20151231", "옛날", np.where(S.date <= "20221231", "학습", "검증"))
P("\n외인 비중 붙은 신호 %d / %d" % (S.foreign_ratio.notna().sum(), len(S)))

def cell(x):
    return "%d건 %+.2f%% · %.0f%%" % (len(x), x.mean(), (x > 0).mean() * 100) if len(x) >= 5 else "%d건" % len(x)

P("\n## 2. 기존 규칙 × 외인 비중 수준(그날 전 종목 순위) — 평균 수익(비용 뒤)·승률, 옛날/학습/검증")
P("| 규칙 | 구간 | 옛날 | 학습 | 검증 |"); P("|---|---|---|---|---|")
for rid in sorted(S.rid.unique()):
    Z = S[S.rid == rid]
    for nm, m in (("전체", Z.qfr.notna()), ("비중 하위30%", Z.qfr <= 0.3), ("비중 30%↑", Z.qfr > 0.3)):
        P("| %s | %s | %s |" % (rid, nm, " | ".join(cell(Z.loc[m & (Z.per == p), "ret"]) for p in ("옛날", "학습", "검증"))))

P("\n## 3. 기존 규칙 × 외인 비중 60일 변화 — 평균 수익(비용 뒤), 옛날/학습/검증")
P("| 규칙 | 구간 | 옛날 | 학습 | 검증 |"); P("|---|---|---|---|---|")
for rid in sorted(S.rid.unique()):
    Z = S[S.rid == rid]
    for nm, m in (("60일 감소(<-0.5%p)", Z.fd60 < -0.5), ("보합", Z.fd60.between(-0.5, 0.5)), ("60일 증가(>+0.5%p)", Z.fd60 > 0.5)):
        P("| %s | %s | %s |" % (rid, nm, " | ".join(cell(Z.loc[m & (Z.per == p), "ret"]) for p in ("옛날", "학습", "검증"))))
(BASE / "research" / "cache" / "frgn_own3.out").write_text("\n".join(OUT), encoding="utf-8")
S.to_pickle(BASE / "research" / "cache" / "frgn_own3_sig.pkl")
