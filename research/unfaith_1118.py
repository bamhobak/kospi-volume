# -*- coding: utf-8 -*-
"""코덱스 제안 6번(2026-11-18 사용자 "테스트는 너가 해줘. 2 6 해줘") — 불성실공시법인 지정예고 뒤 과잉 하락 되돌림.
가설: 악재(계약 해지 등)가 이미 알려진 뒤 같은 일로 '지정예고'가 한 번 더 나오면, 두 번째 제목 때문에 빠진 몫 일부가 돌아온다.
사건 = KIND '불성실공시법인지정예고…'(data/dart/kind_time.db, 분 단위 시각, 2016~). 반응일 R = 공시가 15:20 전이면 그날, 뒤면 다음 거래일.
말한 판 = 반응일에 시장보다 더 빠졌으면 R+1 시가 매수 → R+3 종가. 변형 = 낙폭 문턱·보유 기간·사유(번복·불이행·변경)·'이미 알려진 악재' 대리(직전 60일 안 같은 회사 해지·철회·취소 공시).
    python research/memguard.py research/unfaith_1118.py → research/reports/unfaith_1118.md"""
import sqlite3
from evlib_1118 import *

c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "kind_time.db"), uri=True)
K = pd.read_sql("select day, hm, kcode, market, title from kind where title like '불성실공시법인지정예고%'", c)
codes = tuple(sorted(set(K.kcode)))
Q = pd.read_sql("select day, kcode, title from kind where (title like '%해지%' or title like '%철회%' or title like '%취소%') and title not like '불성실공시%'", c)
Q = Q[Q.kcode.isin(codes)]
c.close()
K["t"] = K.kcode + "0"; K = K[K.t.isin(ti)].copy()
K["late"] = (K.hm >= "1520") | ~K.day.isin(ci)
K["i"] = [after(d) if l else ci[d] for d, l in zip(K.day, K.late)]
K = K[(K.i >= 21) & (K.i < nd - 1)].copy(); K["j"] = K.t.map(ti)
K["day0"] = K.day; K["day"] = calA[K.i.values]                       # day = 반응일(날 바구니 기준)
K = K.sort_values(["j", "i"]).drop_duplicates(["j", "i"])
K["pc"] = CL[K.i.values - 1, K.j.values]; K = K[K.pc >= 1000]
RR = (CL / sh(CL, -1) - 1) * 100; MR = mkt(RR)
K["rr"] = RR[K.i.values, K.j.values]; K["rel"] = K.rr - MR[K.i.values]
K["p20"] = (K.pc / CL[K.i.values - 21, K.j.values] - 1) * 100
K["kind"] = np.where(K.title.str.contains("번복"), "공시번복 포함", np.where(K.title.str.contains("불이행"), "공시불이행", np.where(K.title.str.contains("변경"), "공시변경", "사유 안 적힘")))
Q["d"] = pd.to_datetime(Q.day); qd = {k: np.sort(g.d.values) for k, g in Q.groupby("kcode")}
d0 = pd.to_datetime(K.day0).values
def known(k, d):
    a = qd.get(k)
    if a is None: return False
    lo = np.searchsorted(a, d - np.timedelta64(60, "D")); hi = np.searchsorted(a, d - np.timedelta64(1, "D"), side="right")
    return hi > lo
K["known"] = [known(k, d) for k, d in zip(K.kcode, d0)]

RET = {"R+1 시가→R+3 종가(말한 판)": fwd(sh(OP, 1), sh(CL, 3)), "R+1 시가→당일 종가": fwd(sh(OP, 1), sh(CL, 1)), "R+1 시가→R+5 종가": fwd(sh(OP, 1), sh(CL, 5)),
       "R+1 시가→R+10 종가": fwd(sh(OP, 1), sh(CL, 10)), "R+1 시가→R+20 종가": fwd(sh(OP, 1), sh(CL, 20)), "R 종가→R+3 종가": fwd(CL, sh(CL, 3))}
HOLD = {"R+1 시가→R+3 종가(말한 판)": 3, "R+1 시가→당일 종가": 1, "R+1 시가→R+5 종가": 5, "R+1 시가→R+10 종가": 10, "R+1 시가→R+20 종가": 20, "R 종가→R+3 종가": 3}
MK = {k: mkt(v) for k, v in RET.items()}
k0 = "R+1 시가→R+3 종가(말한 판)"

P_("# 코덱스 6번 — 불성실공시법인 지정예고 뒤 되돌림 (2026-11-18)\n")
P_("사건(2016~, 보통주·전날 종가 1,000원↑): %d건 · 장 끝난 뒤 공시 %.0f%% · 사유 %s" % (len(K), K.late.mean() * 100, K.kind.value_counts().to_dict()))
P_("반응일 등락: 평균 %+.2f%% · 중앙 %+.2f%% · 시장 대비 중앙 %+.2f%%p · 시장보다 더 빠진 비율 %.0f%% · -5%%p↓ %.0f%% · 직전 20일 등락 중앙 %+.1f%% · '이미 알려진 악재' 대리 %.0f%%" % (
    K.rr.mean(), K.rr.median(), K.rel.median(), (K.rel < 0).mean() * 100, (K.rel <= -5).mean() * 100, K.p20.median(), K.known.mean() * 100))
st = np.isnan(OP[np.clip(K.i.values + 1, 0, nd - 1), K.j.values]).mean() * 100
P_("R+1 에 시가가 없는 건(거래정지 등): %.0f%% — 이런 건은 못 사는 걸로 뺐다." % st)

def rows(title, sets, rets):
    P_("\n## %s\n\n| 조건 | 판 %s\n|---|---|---|---|---|---|---|---|---|---|" % (title, HEAD))
    for nm, m in sets.items():
        for k in rets:
            Z = nodup(K[m], HOLD[k]).copy(); Z["r"] = RET[k][Z.i.values, Z.j.values]; Z["m"] = MK[k][Z.i.values]
            P_("| %s | %s | %s |" % (nm, k, both(Z)))

ALL = pd.Series(True, index=K.index)
rows("말한 판(반응일에 시장보다 더 빠짐)과 보유 기간 변형", {"시장보다 더 빠짐": K.rel < 0}, list(RET))
rows("반응일 낙폭 문턱 변형", {"전부(조건 없음)": ALL, "시장 대비 -3%p↓": K.rel <= -3, "시장 대비 -5%p↓": K.rel <= -5, "시장 대비 -10%p↓": K.rel <= -10, "시장보다 덜 빠짐·오름": K.rel >= 0}, [k0, "R+1 시가→R+10 종가"])
rows("사유별(시장보다 더 빠진 것만)", {s: (K.kind == s) & (K.rel < 0) for s in ("공시번복 포함", "공시불이행", "공시변경", "사유 안 적힘")}, [k0, "R+1 시가→R+10 종가"])
rows("'이미 알려진 악재' 대리 — 직전 60일 안 같은 회사 해지·철회·취소 공시", {"있음 · 더 빠짐": K.known & (K.rel < 0), "없음 · 더 빠짐": ~K.known & (K.rel < 0),
     "있음 · -5%p↓": K.known & (K.rel <= -5), "없음 · -5%p↓": ~K.known & (K.rel <= -5)}, [k0, "R+1 시가→R+10 종가"])
rows("그 밖 변형(시장보다 더 빠진 것만)", {"직전 20일 -20%↓(이미 많이 빠짐)": (K.p20 <= -20) & (K.rel < 0), "직전 20일 > -20%": (K.p20 > -20) & (K.rel < 0),
     "유가증권": (K.market == "유가증권") & (K.rel < 0), "코스닥": (K.market == "코스닥") & (K.rel < 0), "장중 공시": ~K.late & (K.rel < 0)}, [k0])
P_("\n## 시장보다 더 빠짐 · 말한 판 해마다\n\n| 해 | 건 | 건당 | 중앙 | 승률 | 시장 대비 |\n|---|---|---|---|---|---|")
Z = nodup(K[K.rel < 0], 3).copy(); Z["r"] = RET[k0][Z.i.values, Z.j.values]; Z["m"] = MK[k0][Z.i.values]; Z = Z.dropna(subset=["r"])
for y, z in Z.groupby(Z.day.str[:4]):
    P_("| %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %+.2f |" % (y, len(z), z.r.mean(), z.r.median(), (z.r > 0).mean() * 100, (z.r - z.m).mean()))
P_("\n## 회피 재료로 보면 — 반응일 종가에서 들고 있었다면(비용 없음)\n\n| 조건 | 기간 | 학습 건 | 평균(중앙) | 시장 대비(t) | 검증 건 | 평균(중앙) | 시장 대비(t) |\n|---|---|---|---|---|---|---|---|")
for n in (5, 20, 60):
    A = fwd(CL, sh(CL, n), cost=0); M = mkt(A)
    for nm, m in (("전부", ALL), ("더 빠짐", K.rel < 0)):
        Z = nodup(K[m], n).copy(); Z["r"] = A[Z.i.values, Z.j.values]; Z["m"] = M[Z.i.values]; out = []
        for _, a, b in SPLIT:
            z = Z[(Z.day >= a) & (Z.day <= b)].dropna(subset=["r"]); e = (z.r - z.m).groupby(z.day).mean()
            out.append("%d | %+.2f%% (%+.2f) | %+.2f (t%.1f)" % (len(z), z.r.mean(), z.r.median(), e.mean(), t_(e)))
        P_("| %s | %d일 | %s | %s |" % (nm, n, out[0], out[1]))
P_("\n- 비용 0.23% 뺀 값(회피 표만 비용 없음). 날 바구니 = 같은 반응일 사건을 하루 한 표본으로. 시장 대비 = 같은 날 종가 1,000원↑ 전 종목 평균을 뺀 값.")
P_("- '이미 알려진 악재'는 제목 대리 지표다 — 지정예고문 본문의 원공시일·추가 손실은 읽지 않았다.")
save("unfaith_1118.md")
