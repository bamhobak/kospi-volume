# -*- coding: utf-8 -*-
"""코덱스 제안 3번(2026-11-18 사용자가 붙여 준 명세) — A사 돌발 생산중단 공시 다음 거래일 시가에 대체 공급업체 B 매수 → 5거래일째 종가.
명세: B = 사건 전에 같은 제품을 같은 고객에게 납품한 기록이 있는 상장사(당시 공개 자료로만) · 대조 = A가 재고·다른 공장으로 정상 공급 가능하다고 밝힌 사건
      · 첫 판정 = B의 비용 뒤 날 바구니 절대수익(대조보다 덜 빠져도 절대수익이 음수면 기각).
이 스크립트가 한 것과 못 한 것:
  · 사건 = DART '생산중단' 공시 2016~(정정 제외) 원문을 Claude 가 본문만 읽고 사유·돌발·제품·'정상 공급 언급'으로 분류(research/halt_label_1118.py).
  · B(제품 일치 판) = KIND 상장법인목록 '주요제품' 글자에 A의 멈춘 제품 낱말이 든 상장사. ⚠ 이 목록은 **지금 시점·지금 상장사만**이다(당시 자료 아님·폐지 종목 없음).
  · B(업종 판, 변형) = KSIC 업종 코드가 같은 상장사(data/ksic.csv, 폐지 포함).
  · '같은 고객에게 납품' 은 공개 자료로 확인할 길이 없어 못 넣었다.
    python research/memguard.py research/halt_test_1118.py → research/reports/halt_test_1118.md"""
import re
from evlib_1118 import *

X = pd.read_pickle(BASE / "research" / "cache" / "halt_kr_1118.pkl")[["rcept_no", "ticker", "corp", "date", "report_nm"]]
L = pd.read_pickle(BASE / "research" / "cache" / "halt_lab_1118.pkl")
E = X.merge(L, on="rcept_no")
E = E[~E.report_nm.str.contains("정정")].copy()
E["sub"] = E.report_nm.str.contains("자회사")
E["i"] = E.date.map(on_or_before); E = E[(E.i >= 21) & (E.i < nd - 1)].sort_values(["ticker", "i"])
E["day"] = calA[E.i.values]
keep = []; last = {}
for t, i in zip(E.ticker, E.i):                                   # 같은 회사가 10거래일 안에 또 내면 뒤엣것은 버린다
    ok = t not in last or i - last[t] >= 10
    keep.append(ok)
    if ok: last[t] = i
E = E[np.array(keep)].reset_index(drop=True)
SUD = ["사고·재해", "당국 명령", "설비 고장"]
E["grp"] = np.where(E.kind.isin(SUD) & E.sudden, np.where(E.supply_ok, "돌발 · 정상 공급 가능(대조)", "돌발 · 공급 차질"),
           np.where(E.kind.isin(["파업·노사", "원재료·협력사"]), "파업·협력사", "계획된 중단(정기보수·감산·이전·철수)"))

C = pd.read_pickle(BASE / "research" / "cache" / "kind_corplist_1118.pkl")
C = C[C.ticker.isin(ti)].copy(); C["p"] = C["prod"].fillna("").str.replace(r"\s+", "", regex=True).str.lower()
C["listed"] = C.listed.astype(str).str.replace("-", "")
KS = pd.read_csv(BASE / "data" / "ksic.csv", dtype=str, encoding="utf-8-sig"); KS = KS[KS.ticker.isin(ti)]
kmap = dict(zip(KS.ticker, KS.ksic)); kgrp = KS.groupby("ksic").ticker.apply(list).to_dict()
GEN = 25                                                           # 낱말 하나에 25곳 넘게 걸리면 너무 넓은 말(의약품·철강)이라 안 쓴다

def b_prod(r):
    out = set()
    for p in r.products or []:
        p = re.sub(r"\s+", "", str(p)).lower()
        if len(p) < 2: continue
        m = C[C.p.str.contains(re.escape(p), regex=True) & (C.listed <= r.day)]
        if 0 < len(m) <= GEN + 1: out |= set(m.ticker)
    out.discard(r.ticker); return sorted(out)
def b_ksic(r):
    k = kmap.get(r.ticker)
    if not k or len(k) < 4: return []                               # 3자리 코드는 너무 넓다
    g = [t for t in kgrp.get(k, []) if t != r.ticker]
    return g if len(g) <= 40 else []
E["Bp"] = [b_prod(r) for r in E.itertuples()]; E["Bk"] = [b_ksic(r) for r in E.itertuples()]

RET = {"D+1 시가→D+5 종가(말한 판)": fwd(sh(OP, 1), sh(CL, 5)), "D+1 시가→당일 종가": fwd(sh(OP, 1), sh(CL, 1)), "D+1 시가→D+3 종가": fwd(sh(OP, 1), sh(CL, 3)),
       "D+1 시가→D+10 종가": fwd(sh(OP, 1), sh(CL, 10)), "D+1 시가→D+20 종가": fwd(sh(OP, 1), sh(CL, 20))}
MK = {k: mkt(v) for k, v in RET.items()}
k0 = "D+1 시가→D+5 종가(말한 판)"
R0 = (CL / sh(CL, -1) - 1) * 100                                    # 공시일 등락(비용 없음)
G1 = (sh(OP, 1) / CL - 1) * 100                                     # 다음 날 시가 갭

def pairs(Z, col):
    rows = [(r.Index, r.day, r.i, ti[b]) for r in Z.itertuples() for b in getattr(r, col) if b in ti]
    P2 = pd.DataFrame(rows, columns=["ev", "day", "i", "j"])
    return P2[CL[P2.i.values, P2.j.values] >= 1000] if len(P2) else P2

GR = ["돌발 · 공급 차질", "돌발 · 정상 공급 가능(대조)", "파업·협력사", "계획된 중단(정기보수·감산·이전·철수)"]
P_("# 코덱스 3번 — 경쟁사 돌발 생산중단 뒤 대체 공급업체 매수 (2026-11-18)\n")
P_("사건(2016~, 정정 제외·같은 회사 10거래일 안 중복 제외): %d건 · 묶음 %s" % (len(E), E.grp.value_counts().to_dict()))
P_("B 를 찾은 사건: 제품 일치 %d건(사건당 B 중앙 %d곳) · 업종 코드 %d건(중앙 %d곳)" % ((E.Bp.str.len() > 0).sum(), E[E.Bp.str.len() > 0].Bp.str.len().median(), (E.Bk.str.len() > 0).sum(), E[E.Bk.str.len() > 0].Bk.str.len().median()))
P_("\n## A사 자신 — 사건이 값에 닿았나(비용 없음)\n\n| 묶음 | 건 | 매출 비중 중앙 | 공시일 등락 평균(중앙) | 다음 날 시가 갭 평균 | 다음 날 시가→5일째 종가 평균(중앙) |\n|---|---|---|---|---|---|")
A5 = fwd(sh(OP, 1), sh(CL, 5), cost=0)
for g in GR:
    z = E[(E.grp == g) & E.ticker.isin(ti)]; j = z.ticker.map(ti).values; i = z.i.values
    P_("| %s | %d | %.0f%% | %+.2f%% (%+.2f) | %+.2f%% | %+.2f%% (%+.2f) |" % (g, len(z), z.share_pct.median(), np.nanmean(R0[i, j]), np.nanmedian(R0[i, j]), np.nanmean(G1[i, j]), np.nanmean(A5[i, j]), np.nanmedian(A5[i, j])))

def block(title, col, sets, rets):
    P_("\n## %s\n\n| 사건 묶음 | 판 | 사건 수 %s\n|---|---|---|---|---|---|---|---|---|---|---|" % (title, HEAD))
    for nm, m in sets.items():
        Z = E[m]; P2 = pairs(Z, col)
        for k in rets:
            if not len(P2): P_("| %s | %s | 0 | – |" % (nm, k)); continue
            Q = P2.copy(); Q["r"] = RET[k][Q.i.values, Q.j.values]; Q["m"] = MK[k][Q.i.values]
            P_("| %s | %s | %d | %s |" % (nm, k, Q.ev.nunique(), both(Q)))

base = {g: E.grp == g for g in GR}
block("B = 제품 일치(말한 판에 가장 가까운 것) — 보유 기간 변형", "Bp", {GR[0]: base[GR[0]], GR[1]: base[GR[1]]}, list(RET))
block("B = 제품 일치 — 다른 사건 묶음", "Bp", {GR[2]: base[GR[2]], GR[3]: base[GR[3]], "돌발 전부": E.grp.isin(GR[:2])}, [k0, "D+1 시가→D+10 종가"])
big = E.share_pct.fillna(0) >= 10
block("B = 제품 일치 — 큰 사건만(매출 비중 10%↑ · 전부 멈춤 · 사고·재해만 · 자회사 아님)", "Bp",
      {"공급 차질 · 매출 10%↑": base[GR[0]] & big, "공급 차질 · 전부 멈춤": base[GR[0]] & E.whole, "공급 차질 · 사고·재해만": base[GR[0]] & (E.kind == "사고·재해"),
       "공급 차질 · 당국 명령만": base[GR[0]] & (E.kind == "당국 명령"), "공급 차질 · 자회사 아님": base[GR[0]] & ~E["sub"],
       "공급 차질 · A사 공시일 -3%↓": base[GR[0]] & pd.Series([R0[i, ti[t]] <= -3 if t in ti else False for i, t in zip(E.i, E.ticker)], index=E.index)}, [k0, "D+1 시가→D+10 종가"])
block("B = 업종 코드가 같은 상장사(변형 · 폐지 포함)", "Bk", {GR[0]: base[GR[0]], GR[1]: base[GR[1]], GR[2]: base[GR[2]], GR[3]: base[GR[3]], "공급 차질 · 매출 10%↑": base[GR[0]] & big}, [k0, "D+1 시가→D+10 종가"])
P_("\n## 돌발 · 공급 차질 · B 제품 일치 · 말한 판 해마다\n\n| 해 | 사건 | B 건 | 건당 | 중앙 | 승률 | 시장 대비 |\n|---|---|---|---|---|---|---|")
Q = pairs(E[base[GR[0]]], "Bp"); Q["r"] = RET[k0][Q.i.values, Q.j.values]; Q["m"] = MK[k0][Q.i.values]; Q = Q.dropna(subset=["r"])
for y, z in Q.groupby(Q.day.str[:4]):
    P_("| %s | %d | %d | %+.2f%% | %+.2f%% | %.0f%% | %+.2f |" % (y, z.ev.nunique(), len(z), z.r.mean(), z.r.median(), (z.r > 0).mean() * 100, (z.r - z.m).mean()))
P_("\n## 본보기 — 돌발 · 공급 차질 사건과 고른 B(제품 일치)\n")
nm = dict(zip(C.ticker, C.corp))
for r in E[base[GR[0]] & (E.Bp.str.len() > 0)].sort_values("share_pct", ascending=False).head(14).itertuples():
    P_("- %s %s(%s, 매출 %s%%) %s → %s" % (r.day, r.corp, r.kind, r.share_pct, r.products, ", ".join(nm.get(b, b) for b in r.Bp[:8])))
P_("\n- 비용 0.23% 뺀 값(A사 표만 비용 없음). 날 바구니 = 같은 공시일의 B 전부를 하루 한 표본으로. 시장 대비 = 같은 날 종가 1,000원↑ 전 종목 평균을 뺀 값.")
P_("- 제품 일치 판의 B 는 **지금 시점 KIND 주요제품 목록**으로 골랐다(당시 사업보고서 대조·같은 고객 확인은 못 함). 낱말 하나에 %d곳 넘게 걸리면 그 낱말은 버렸다." % GEN)
save("halt_test_1118.md")
