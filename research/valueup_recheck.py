# -*- coding: utf-8 -*-
"""밸류업(기업가치 제고 계획) 공시 다시 재기 (2026-10-25, 사용자 "그림자 테스트 중인 거 가치 있는지 다시 체크") — H0245 / 그림자 S3.

처음 실측(disc_scan 09-29)은 2년치를 한 덩어리로 봤다. 지금은 2024-05~2026-10 이라 나눠 볼 수 있다.
  · 첫 공시(그 회사 처음) / 다시 낸 공시(해마다 갱신·이행) / 예고 공시
  · 제목 꼬리표 'PBR 개선 계획 제출 기업' — 2026-10-22 하루 46건 몰림(의무 성격 일괄 제출로 보임)
  · 해마다(2024·2025·2026) · 20일 -10% 낙폭 · 유니버스(거래대금 상위 40%)
수익 = 공시일 다음 거래일 시가 매수 → h 거래일 뒤 종가 · 비용 0.43 · 초과 = 같은 날 유니버스 같은 보유 평균 대비.
보유가 다 안 찬 신호는 뺀다(NaN).
    python research/valueup_recheck.py
"""
import re, sqlite3, sys
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "research"))
import run_spec as RS
from verdict import log_trials

OUT = []
def P(s=""): OUT.append(s); print(s)

K, uni, _ = RS.load_market("KR")
K["uni"] = uni.values
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
g = K.groupby("ticker", sort=False)
H = (5, 10, 20, 60)
for h in H:
    f = ((g.close.shift(-h) / g.open.shift(-1) - 1) * 100).clip(-95, 300)
    K["a%d" % h] = f - 0.43
    K["x%d" % h] = f - f.where(K.uni).groupby(K.date).transform("mean") - 0.43
P("가격 마지막 날 %s" % K.date.max())

con = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS date, report_nm FROM disclosure WHERE length(stock_code)=6 AND "
                "replace(report_nm,' ','') LIKE '%기업가치제고계획%'", con)
D = D[~D.report_nm.str.contains("정정")]
w = BASE / "data" / "disc_watch.csv"
if w.exists():   # DART 캐시가 늦으면 감시 파일로 채운다
    W = pd.read_csv(w, dtype=str)
    W = W[W.kind == "밸류업"].rename(columns={"rcept_dt": "date"})[["ticker", "date", "report_nm"]]
    D = pd.concat([D, W]).drop_duplicates(["ticker", "date"])
D = D.sort_values(["ticker", "date"])
nm = D.report_nm.str.replace(" ", "")
D["pre"] = nm.str.contains("예고")
D["pbr"] = nm.str.contains("PBR개선")
D["nth"] = D[~D.pre].groupby("ticker").cumcount()
D.loc[D.pre, "nth"] = -1
P("공시 %d건 (%s~%s) · 예고 %d · PBR 꼬리표 %d · 첫 공시 %d · 다시 낸 것 %d" % (
    len(D), D.date.min(), D.date.max(), D.pre.sum(), D.pbr.sum(), (D.nth == 0).sum(), (D.nth > 0).sum()))
P("달마다 건수: " + " ".join("%s:%d" % (k[2:], v) for k, v in D.groupby(D.date.str[:6]).size().items()))

TI = K.groupby("ticker").indices; DT = K.date.to_numpy()
recs = []
for r in D.itertuples():
    ii = TI.get(r.ticker)
    if ii is None: continue
    j = np.searchsorted(DT[ii], r.date)
    if j >= len(ii): continue
    i = ii[j]
    d = dict(date=DT[i], ticker=r.ticker, pre=r.pre, pbr=r.pbr, nth=r.nth, uni=bool(K.uni.iat[i]), ret20=K.ret20.iat[i])
    for h in H: d["a%d" % h] = K["a%d" % h].iat[i]; d["x%d" % h] = K["x%d" % h].iat[i]
    recs.append(d)
E = pd.DataFrame(recs); E["y"] = E.date.str[:4]


def row(name, Z):
    c = []
    for h in H:
        a, x = Z["a%d" % h].dropna(), Z["x%d" % h].dropna()
        if len(a) < 8: c.append("- (%d)" % len(a)); continue
        t = x.mean() / (x.std() / np.sqrt(len(x))) if x.std() > 0 else 0
        c.append("%+.1f / %+.1f · %.0f%% · t%.1f (%d)" % (a.median(), x.mean(), (a > 0).mean() * 100, t, len(a)))
    P("| %s | %s |" % (name, " | ".join(c)))


P("\n칸 = 절대 중앙 / 초과 평균 · 승률 · 초과 t (건수)\n")
P("| 무리 | 5일 | 10일 | 20일 | 60일 |"); P("|---|---|---|---|---|")
dd = E.ret20 <= -10
for name, m in (("전체", E.index == E.index), ("예고 공시", E.pre), ("첫 공시", E.nth == 0), ("다시 낸 공시", E.nth > 0),
                ("PBR 꼬리표", E.pbr), ("꼬리표 없음(예고 빼고)", ~E.pbr & ~E.pre),
                ("첫 공시 · 유니버스", (E.nth == 0) & E.uni), ("첫 공시 · 20일 -10%", (E.nth == 0) & dd),
                ("다시 낸 공시 · 20일 -10%", (E.nth > 0) & dd), ("전체 · 20일 -10%", dd), ("전체 · 20일 -10% · 유니버스", dd & E.uni)):
    row(name, E[m])
P("\n해마다")
P("| 무리 | 5일 | 10일 | 20일 | 60일 |"); P("|---|---|---|---|---|")
for y, Z in E.groupby("y"):
    row("%s 전체" % y, Z); row("%s 첫 공시" % y, Z[Z.nth == 0]); row("%s 20일 -10%%" % y, Z[Z.ret20 <= -10])
P("\n분기마다 20일(전체): " + " ".join("%s:%+.1f/%+.1f(%d)" % (q, z.a20.median(), z.x20.mean(), z.a20.notna().sum())
                                      for q, z in E.groupby(E.date.str[:4] + "Q" + ((E.date.str[4:6].astype(int) - 1) // 3 + 1).astype(str))))
log_trials("valueup_recheck_20261025", 11 * 4 + 9 * 4)
(BASE / "research" / "reports").mkdir(exist_ok=True)
(BASE / "research" / "reports" / "valueup_recheck_20261025.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
