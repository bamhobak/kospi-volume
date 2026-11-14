# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "지금 규칙들을 방식은 비슷하게, 자료는 다른 걸 쓰면서 겹침은 줄이면서" — ② [반대매매] 형제 [지수 편출 매도 되돌림].
원리 같음: 정보 없는 기계적 매도(반대매매 = 담보 부족 강제 매도 / 편출 = 인덱스 펀드가 정기변경 날 종가에 판다) → 되돌림.
자료: data/index_members.db (코스피200 1028 · 코스닥150 2203, 2018-02~ 달마다 구성) — 6·12월 정기변경: 6월 1일 구성에 있고 7월 1일 구성에 없으면 편출
      효력일 D = 6·12월 둘째 목요일(선물 만기) 다음 거래일 → 인덱스 펀드는 D-1 종가에 판다. 편입도 같이(참고 — 회피 재료로 알려짐).
손익(비용 0.23 뒤, KRX 일봉 factory_px): ① D-1 종가 매수 → D 시가 ② D-1 종가 → D+4 종가(5일) ③ D-1 종가 → D+9(10일) ④ D 시가 → D+4 종가 ⑤ D-5 종가 → D-1 종가(편출 앞 하락, 참고)
시장 대비 = 같은 날 유니버스(factory_px 전 종목) 같은 구간 평균을 뺀 값. 학습 2018~2022 / 검증 2023~.
겹침: 같은 종목이 [반대매매](P9, mix_p9 거래표) 신호와 D±5 안에 겹친 비율.
    python research/memguard.py research/sib_idxout_1115.py → research/reports/sib_idxout_1115.md"""
import sqlite3, sys, pickle
from pathlib import Path
import numpy as np, pandas as pd
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
CK = 0.23
c = sqlite3.connect("file:" + str(BASE / "data" / "index_members.db") + "?mode=ro", uri=True)
M = pd.read_sql("select idx, name, date, ticker from members where idx in (1028, 2203)", c)
PX = pd.read_pickle(ROOT / "cache" / "factory_px.pkl")[["ticker", "date", "open", "close"]]
PX = PX[PX.date >= "20171201"].copy(); PX["ticker"] = PX.ticker.astype(str)
cal = sorted(PX.date.unique()); ci = {d: i for i, d in enumerate(cal)}
O = PX.pivot(index="date", columns="ticker", values="open"); Cl = PX.pivot(index="date", columns="ticker", values="close")
O = O.reindex(cal); Cl = Cl.reindex(cal)
Clf = Cl.ffill()


def second_thu(y, m):
    d = pd.Timestamp(y, m, 1); d += pd.Timedelta(days=(3 - d.weekday()) % 7); return d + pd.Timedelta(days=7)


ev = []
for idx, g in M.groupby("idx"):
    snaps = {d: set(x.ticker) for d, x in g.groupby("date")}
    ds = sorted(snaps)
    for a, b in zip(ds, ds[1:]):
        if a[4:6] not in ("06", "12"): continue
        st = second_thu(int(a[:4]), int(a[4:6])).strftime("%Y%m%d")
        dm1 = max(d for d in cal if d <= st)                         # 선물 만기일(인덱스 펀드가 종가에 사고판다)
        if dm1 not in ci or ci[dm1] + 1 >= len(cal): continue
        D = cal[ci[dm1] + 1]
        for side, tk in (("편출", snaps[a] - snaps[b]), ("편입", snaps[b] - snaps[a])):
            for t in tk: ev.append(dict(idx=g["name"].iloc[0], side=side, t=t, dm1=dm1, D=D))
E = pd.DataFrame(ev)
P("# [지수 편출 매도 되돌림] — [반대매매] 형제 (2026-11-15)\n")
P("- 정기변경 %d번(%s~%s) · 편출 %d건 · 편입 %d건 · 비용 0.23 뒤 · 시장 대비 = 같은 구간 전 종목 평균 뺌\n" % (
    E.dm1.nunique(), E.dm1.min(), E.dm1.max(), (E.side == "편출").sum(), (E.side == "편입").sum()))
mk_on = (O.div(Cl.shift(1)) - 1).mean(axis=1) * 100


def win(i0, j0, i1, j1, t):
    """(날 i0, 가격 j0) → (날 i1, 가격 j1) 등락 %. j: 'o' 시가 / 'c' 종가"""
    if i0 < 0 or i1 >= len(cal) or t not in Cl.columns: return np.nan
    a = (O if j0 == "o" else Clf).iat[i0, Cl.columns.get_loc(t)]; b = (O if j1 == "o" else Clf).iat[i1, Cl.columns.get_loc(t)]
    return (b / a - 1) * 100 if a and b and a == a and b == b else np.nan


def mkt(i0, j0, i1, j1):
    if i0 < 0 or i1 >= len(cal): return np.nan
    a = (O if j0 == "o" else Clf).iloc[i0]; b = (O if j1 == "o" else Clf).iloc[i1]
    r = (b / a - 1) * 100; r = r[np.isfinite(r) & (r.abs() < 60)]
    return r.mean()


WINS = {"① D-1 종가 → D 시가": (-1, "c", 0, "o"), "② D-1 종가 → D+4 종가(5일)": (-1, "c", 4, "c"), "③ D-1 종가 → D+9 종가(10일)": (-1, "c", 9, "c"),
        "④ D 시가 → D+4 종가": (0, "o", 4, "c"), "⑤ (참고) D-5 종가 → D-1 종가 · 편출 앞": (-5, "c", -1, "c")}
rows = []
for r in E.itertuples():
    iD = ci[r.D]; x = dict(r._asdict())
    for k, (a, ja, b, jb) in WINS.items():
        x[k] = win(iD + a, ja, iD + b, jb, r.t); x["x" + k] = x[k] - mkt(iD + a, ja, iD + b, jb)
    rows.append(x)
R = pd.DataFrame(rows); R["yr"] = R.D.str[:4]
for side in ("편출", "편입"):
    P("\n## %s\n" % side)
    P("| 구간 | 기간 | 건수 | 평균(비용 뒤) | 중앙 | 승률 | 시장 대비 평균 | 시장 대비 플러스 |"); P("|---|---|---|---|---|---|---|---|")
    for k in WINS:
        for lab, q in (("학습 2018~22", R[(R.side == side) & (R.D < "20230101")]), ("검증 2023~", R[(R.side == side) & (R.D >= "20230101")])):
            v = q[k].dropna() - (0 if k.startswith("⑤") else CK); xv = q["x" + k].dropna()
            if not len(v): continue
            P("| %s | %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %+.2f%%p | %.0f%% |" % (k, lab, len(v), v.mean(), v.median(), (v > 0).mean() * 100, xv.mean(), (xv > 0).mean() * 100))
P("\n## 편출 — 지수별·해마다 (② 5일, 비용 뒤)\n")
q = R[R.side == "편출"]
P("| 지수 | " + " | ".join(sorted(q.yr.unique())) + " |"); P("|---" * (q.yr.nunique() + 1) + "|")
for nm, g in q.groupby("idx"):
    P("| %s | %s |" % (nm, " | ".join("%+.1f(%d)" % ((g[g.yr == y]["② D-1 종가 → D+4 종가(5일)"] - CK).mean(), (g.yr == y).sum()) if (g.yr == y).any() else "-" for y in sorted(q.yr.unique()))))
try:
    Z = pickle.load(open(r"C:\temp\kp\mix_p9.pkl", "rb"))[(2000000.0, 50000000.0)]
    Z["t"] = Z.t.astype(str); hit = 0
    for r in q.itertuples():
        z = Z[Z.t == r.t]
        if len(z) and any(abs(ci.get(d, -99) - ci[r.D]) <= 5 for d in z.date): hit += 1
    P("\n- 겹침: 편출 %d건 중 [반대매매] 신호와 D±5 안에 같은 종목 %d건(%.1f%%)" % (len(q), hit, hit / max(1, len(q)) * 100))
except Exception as ex:
    P("\n- 겹침 계산 실패: %r" % ex)
(ROOT / "reports" / "sib_idxout_1115.md").write_text("\n".join(OUT), encoding="utf-8")
