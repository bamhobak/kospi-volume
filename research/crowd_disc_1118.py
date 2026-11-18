# -*- coding: utf-8 -*-
"""H? 공시가 몰린 시간대에 나온 호재는 묻혀서 늦게 반영되나 (2026-11-18 코덱스 제안 9번 · 사용자 "돌려봐").
호재(제목으로 분명한 것만): 단일판매ㆍ공급계약체결(본인·자율공시) · 무상증자결정 · 자기주식 취득 결정·신탁계약 체결 결정 · 주식 소각 결정.
몰림 = 그 공시 앞뒤 5분 안에 나온 전체 공시 수(유가·코스닥). 시간대(장전 ~08:49 / 장중 08:50~15:19 / 장후 15:20~)마다 그 해 안에서 3등분 → 시간대 효과와 안 섞이게.
       덧: 그날 하루 전체 공시 수 3등분(그 해 안).
살 수 있는 가장 빠른 때: 장전 = 그날 시가 · 장중 = 그날 종가 · 장후 = 다음 날 시가 → 1·3·5·10일째 종가. 첫 반응 = 그 직전 종가 → 사는 값.
가설이 맞다면: 몰린 때가 첫 반응은 작고 그 뒤 수익은 커야 한다(학습·검증 둘 다)."""
import sqlite3
import numpy as np, pandas as pd
from evlib_1118 import *
c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
A = pd.read_sql("select dt, day, hm, kcode, title from kind where market in ('유가증권','코스닥') and day >= '20160101'", c); c.close()
A["ts"] = pd.to_datetime(A.dt).values.astype("int64") // 60_000_000_000         # 분
allmin = np.sort(A.ts.values)
KIND = (("공급계약", A.title.isin(["단일판매ㆍ공급계약체결", "단일판매ㆍ공급계약체결(자율공시)"])), ("무상증자", A.title == "무상증자결정"),
        ("자사주 취득·신탁", A.title.str.match(r"^자기주식\s?취득\s?결정$|^자기주식취득 신탁계약 체결 결정$")), ("주식 소각", A.title.str.match(r"^주식\s?소각 결정$")))
E = pd.concat([A[m].assign(kind=k) for k, m in KIND], ignore_index=True)
E["crowd"] = np.searchsorted(allmin, E.ts.values + 5, side="right") - np.searchsorted(allmin, E.ts.values - 5, side="left")
E["daycnt"] = E.day.map(A.groupby("day").size())
E["t"] = E.kcode + "0"; E = E[E.t.isin(ti)].copy(); E["j"] = E.t.map(ti)
i0 = np.array([on_or_before(d) for d in E.day.values]); trade = calA[np.clip(i0, 0, nd - 1)] == E.day.values
E["seg"] = np.where(~trade | (E.hm >= "1520"), "장후", np.where(E.hm < "0850", "장전", "장중"))
E["i"] = i0; E = E[(E.i > 5) & (E.i < nd - 12)]
i, j = E.i.values, E.j.values; post, pre = (E.seg == "장후").values, (E.seg == "장전").values
ent = np.where(post, OP[np.minimum(i + 1, nd - 1), j], np.where(pre, OP[i, j], CL[i, j])); base = np.where(pre, CL[i - 1, j], CL[i, j]); base = np.where((E.seg == "장중").values, CL[i - 1, j], base)
E["react"] = (ent / base - 1) * 100; E["px"] = base
mo = mkt(OP); mc = mkt(CL)
for h in (1, 3, 5, 10):
    k = np.where(pre, i + h - 1, i + h); ex = CL[np.minimum(k, nd - 1), j]
    r = (ex / ent - 1) * 100 - COST; r[(np.abs(r) > 150) | ~np.isfinite(r)] = np.nan; E["r%d" % h] = r
    me = np.where(post, mo[np.minimum(i + 1, nd - 1)], np.where(pre, mo[i], mc[i])); E["m%d" % h] = (mc[np.minimum(k, nd - 1)] / me - 1) * 100
E = E[(E.px >= 1000) & E.react.notna() & (E.react < 29)]
E["day"] = calA[np.where((E.seg == "장후").values, np.minimum(E.i.values + 1, nd - 1), E.i.values)]      # 사는 날 기준 바구니
E = E.sort_values("ts").drop_duplicates(["t", "day"]); E = nodup(E.assign(i=E.i.values), 5)
E["yr"] = E.day.str[:4]
E["cq"] = E.groupby(["seg", "yr"]).crowd.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
E["dq"] = E.groupby("yr").daycnt.transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
P_("# 공시가 몰린 시간대 호재 — 묻혀서 늦게 반영되나 (2026-11-18, 코덱스 9번)\n")
P_("호재 공시 %d건(2016~) · 종류 %s · 시간대 %s · 앞뒤 5분 공시 수 중앙 %d (한산 3분의 1 %d↓ · 몰림 3분의 1 %d↑)\n" % (len(E), E.kind.value_counts().to_dict(), E.seg.value_counts().to_dict(), E.crowd.median(), E.crowd.quantile(1 / 3), E.crowd.quantile(2 / 3)))
LAB = {0: "한산", 1: "보통", 2: "몰림"}
def block(title, Z, qcol="cq"):
    P_("\n## %s\n\n| 몰림 | 건 | 첫 반응 평균(중앙) | 구간 | %s" % (title, HEAD[2:])); P_("|---|---|---|---|" + "---|" * 8)
    for q in (0, 1, 2):
        z = Z[Z[qcol] == q]
        for h in (1, 5, 10):
            P_("| %s | %d | %+.2f%% (%+.2f) | %d일 | %s |" % (LAB[q], len(z), z.react.mean(), z.react.median(), h, both(z, "r%d" % h, "m%d" % h)))
    for h in (1, 5, 10):                                   # 몰림 − 한산 (날 바구니 차이)
        cs = []
        for _, a, b in SPLIT:
            z = Z[(Z.day >= a) & (Z.day <= b)]; x = z.assign(e=z["r%d" % h] - z["m%d" % h])
            hi = x[x[qcol] == 2].groupby("day").e.mean(); lo = x[x[qcol] == 0].groupby("day").e.mean()
            se = math.sqrt(hi.var(ddof=1) / len(hi) + lo.var(ddof=1) / len(lo)) if len(hi) > 5 and len(lo) > 5 else float("nan")
            cs.append("%+.2f (t%.1f)" % (hi.mean() - lo.mean(), (hi.mean() - lo.mean()) / se))
        P_("| **몰림−한산** |  |  | %d일 | 학습 %s · 검증 %s |||||||" % (h, cs[0], cs[1]))
block("1. 전체 호재 — 앞뒤 5분 몰림(시간대·해 안 3등분)", E)
for sg in ("장전", "장중", "장후"): block("2. 시간대: %s" % sg, E[E.seg == sg])
for k, _ in KIND: block("3. 종류: %s" % k, E[E.kind == k])
block("4. 그날 하루 전체 공시 수(해 안 3등분)", E, "dq")
block("5. 작은 종목(1만원↓) — 눈길이 덜 가는 쪽", E[E.px < 10000])
P_("\n## 6. 첫 반응이 작았던 것만(−1~+2%) — '묻힌' 호재\n")
block("첫 반응 −1~+2%", E[(E.react > -1) & (E.react < 2)])
save("crowd_disc_1118.md")
