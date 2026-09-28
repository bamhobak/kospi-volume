# -*- coding: utf-8 -*-
"""미장 [상승장 신고가](N1)·[잔잔한 급등주](N5)·[실적 서프라이즈](N6) 정밀 점검 (2026-09-29 사용자 요청).

"실거래 해보니 매도일 전 과정이라지만 생각보다 하락률이 높다" — [자사주 낙폭](N4)은 그대로 둔다.

① 보유 중 경로(폐지 포함 · 2016~ 과 2023~): 매수 후 5·10·20·40·60일째 수익 분포(10·25·50·75·90 분위),
   보유 중 최저점(MAE) 분포, 최저점 구간별 최종 수익 — "지금 이만큼 빠진 게 정상인가" 의 잣대
② 조정 후보를 계좌로(6규칙 · N4 포함 · 매일 평가 · 세 구간 A09~15·B16~20·C21~ · 100시드 짝비교)
   · 업종 상한 2/3종목(같은 sic2, 미장 전체) — 2026-09-15 '보류(사전등록 후 재검증)' 안
   · 변동성 맞춤 비중(N1·N5·N6): 비중 × clip(중앙 변동성 ÷ 종목 20일 변동성, 하한, 상한) — (0.5,1.5)·(0.67,1.33)·(0.5,2.0)
   · [실적 서프라이즈] 반응일 상승 +8/+10/+15% 초과 제외(너무 큰 갭)
   채택 기준(미리 정함): 세 구간 모두 낙폭이 얕은 시드 60%↑ · 두 구간 이상 수익이 높은 시드 50%↑ · 이웃 칸 같은 방향.

    python research/us_n156.py
"""
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
src = (ROOT / "us_capture.py").read_text(encoding="utf-8").split("# ── ① 미장 계좌", 1)[0]
src = src.replace('S = S[S.date >= "20160101"]', 'S = S[S.date >= "20090101"]')
src = src.replace('x = fdr.DataReader(sym, "2015-06-01")', 'x = fdr.DataReader(sym, "2008-06-01")')
src = src.replace('x = x[x.index >= "20160101"]', 'x = x[x.index >= "20090101"]')
exec(compile(src, "us_capture.py", "exec"))

NS = 100
PER = [("A 2009~15", "20090101", "20151231"), ("B 2016~20", "20160101", "20201231"), ("C 2021~", "20210101", "20991231")]
O = ["# 미장 N1·N5·N6 정밀 점검 · %s" % time.strftime("%Y-%m-%d"), ""]

# ── 신호별 재료: 업종·20일 변동성·신호일 등락 ─────────────────────────
log("신호 재료")
Kk = K[["ticker", "date", "sic2", "px"]].copy()
Kk["r1"] = Kk.px.groupby(Kk.ticker, sort=False).pct_change() * 100
Kk["v20"] = Kk.r1.groupby(Kk.ticker, sort=False).transform(lambda s: s.rolling(20, min_periods=15).std())
S = S.merge(Kk[["ticker", "date", "sic2", "r1", "v20"]], on=["ticker", "date"], how="left")
sic_last = K.groupby("ticker").sic2.last()
S["sic2"] = S.sic2.fillna(S.ticker.map(sic_last)).fillna("??").astype(str)
del Kk

# ── ① 보유 중 경로 ────────────────────────────────────────────────────
O += ["## ① 보유 중 경로 — 매수 후 k일째 수익(%) 분위 · 보유 중 최저점", "",
      "매수 = 신호 다음날 시가. 비용 전. 폐지 포함. **이 표가 '지금 빠진 게 정상인가' 의 잣대다.**", ""]
for lo_lbl, lo in (("2016~", "20160101"), ("2023~", "20230101")):
    O += ["### 진입 %s" % lo_lbl, "", "| 규칙 | 건수 | k일째 | 10% | 25% | 중앙 | 75% | 90% |", "|---|---|---|---|---|---|---|---|"]
    for r in ("N1", "N5", "N6"):
        ids = S.index[(S.rid == r) & (S.date >= lo)]
        for k in (5, 10, 20, 40, 60):
            if k > HOLD[r]:
                continue
            v = [(PATH[n][1][k - 1] - 1) * 100 for n in ids if len(PATH[n][1]) >= k]
            if len(v) < 30:
                continue
            q = np.percentile(v, [10, 25, 50, 75, 90])
            O.append("| [%s] | %s | %d일 | %+.1f | %+.1f | **%+.1f** | %+.1f | %+.1f |" % (NAME[r], f"{len(v):,}", k, *q))
    O.append("")
O += ["### 보유 중 최저점(MAE)과 최종 수익 (진입 2016~ · 끝난 거래)", "",
      "| 규칙 | 건수 | 최저점 중앙 | 최저 -10% 이하 닿은 비율 | -20% 이하 | 최저 0~-5% 거래 최종 | -5~-10% | -10~-20% | -20% 이하 |",
      "|---|---|---|---|---|---|---|---|---|"]
for r in ("N1", "N5", "N6"):
    ids = [n for n in S.index[(S.rid == r) & (S.date >= "20160101")] if len(PATH[n][1]) >= HOLD[r]]
    mae = np.array([(PATH[n][1][:HOLD[r]].min() - 1) * 100 for n in ids])
    fin = np.array([(PATH[n][1][HOLD[r] - 1] - 1) * 100 - S.cost[n] for n in ids])
    b = lambda lo_, hi_: fin[(mae <= lo_) & (mae > hi_)]
    cells = []
    for lo_, hi_ in ((0, -5), (-5, -10), (-10, -20), (-20, -1000)):
        x = b(lo_, hi_)
        cells.append("%+.1f%% (%d%%)" % (x.mean(), len(x) / len(fin) * 100) if len(x) >= 10 else "-")
    O.append("| [%s] | %s | %+.1f%% | %.0f%% | %.0f%% | %s |" % (NAME[r], f"{len(fin):,}", np.median(mae), (mae <= -10).mean() * 100,
                                                            (mae <= -20).mean() * 100, " | ".join(cells)))
O += ["", "괄호 = 그 최저점 구간에 속한 거래 비율. 최저점이 깊었어도 최종이 플러스면 '버티면 회복' 형이다.", ""]


# ── ② 계좌 변형 ──────────────────────────────────────────────────────
def sim2(Sx, pct, seed, seccap=None):
    """us_capture.sim + 신호별 비중(pct 배열) + 업종 상한."""
    rng = np.random.default_rng(seed)
    by = {}
    for n in range(len(Sx)):
        if Sx.ok.values[n]:
            by.setdefault(Sx.di.values[n], []).append(n)
    cash, pos, navs = 1.0, [], np.empty(len(ud))
    cnt, sec = {}, {}
    rid, cost, hold, sc = Sx.rid.values, Sx.cost.values, Sx.hold.values, Sx.sic2.values
    for d in range(len(ud)):
        keep, val = [], 0.0
        for p in pos:
            n, alloc, ent = p
            ddi, ratio = PATH_X[n]
            k = np.searchsorted(ddi, d, "right") - 1
            cur = ratio[k] if k >= 0 else 1.0
            if d >= ent + hold[n] or d > ddi[-1]:
                cash += alloc * (cur - cost[n] / 100); cnt[rid[n]] -= 1; sec[sc[n]] -= 1
            else:
                keep.append(p); val += alloc * cur
        pos = keep
        nav = cash + val; navs[d] = nav
        L = by.get(d)
        if not L:
            continue
        L = list(L); rng.shuffle(L)
        for n in L:
            r = rid[n]
            if cnt.get(r, 0) >= MX[r]:
                continue
            if seccap and sc[n] != "??" and sec.get(sc[n], 0) >= seccap:
                continue
            a = nav * pct[n] / 100
            if a > cash + 1e-12:
                continue
            cash -= a; pos.append((n, a, d)); cnt[r] = cnt.get(r, 0) + 1; sec[sc[n]] = sec.get(sc[n], 0) + 1
    return pd.Series(navs, index=ud)


def seg(nav, lo, hi):
    s = nav[(nav.index >= lo) & (nav.index <= hi)]
    b = SPX.reindex(s.index).ffill()
    m = s.groupby(s.index.str[:6]).last().pct_change().dropna() * 100
    mb = b.groupby(b.index.str[:6]).last().pct_change().reindex(m.index) * 100
    return (((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1) * 100, (s / s.cummax() - 1).min() * 100,
            m[mb < 0].mean() / mb[mb < 0].mean())


def run(Sx, pct, seccap=None):
    global PATH_X
    PATH_X = [PATH[i] for i in Sx.index]
    pct = np.asarray(pct)[np.asarray(Sx.index)] if len(pct) == len(S) else pct
    Sx = Sx.reset_index(drop=True)
    R = np.zeros((NS, len(PER), 3))
    for s in range(NS):
        nav = sim2(Sx, pct, s, seccap)
        for k, (_, lo, hi) in enumerate(PER):
            R[s, k] = seg(nav, lo, hi)
    return R


base_pct = S.rid.map(PCT).values.astype(float)
VM = S.groupby("rid").v20.transform("median")


def volpct(lo, hi):
    f = (VM / S.v20).clip(lo, hi).fillna(1.0).values
    return np.where(S.rid.isin(["N1", "N5", "N6"]), base_pct * f, base_pct)


VAR = [("지금", S, base_pct, None),
       ("업종 상한 2종목", S, base_pct, 2), ("업종 상한 3종목", S, base_pct, 3),
       ("변동성 맞춤 (0.5~1.5)", S, volpct(0.5, 1.5), None), ("변동성 맞춤 (0.67~1.33)", S, volpct(0.67, 1.33), None),
       ("변동성 맞춤 (0.5~2.0)", S, volpct(0.5, 2.0), None)]
for g in (8, 10, 15):
    VAR.append(("실적 서프라이즈 반응일 +%d%% 초과 제외" % g, S[~((S.rid == "N6") & (S.r1 > g))], base_pct, None))
RES = {}
for lbl, Sx, pct, sc in VAR:
    log(lbl)
    RES[lbl] = run(Sx, pct, sc)
pickle.dump(RES, open(ROOT / "cache" / "us_n156.pkl", "wb"))
B = RES["지금"]
O += ["## ② 조정 후보 — 계좌(6규칙 · %d시드 짝비교 · 매일 평가)" % NS, "",
      "각 칸: 연수익 / 최대낙폭 / 하락 포착. 괄호 = 지금 대비 **낙폭 얕은 시드 %%** · **수익 높은 시드 %%**.", "",
      "| 구성 | " + " | ".join(p[0] for p in PER) + " | 기준 통과 |", "|---|" + "---|" * len(PER) + "---|"]
for lbl, *_ in VAR:
    R = RES[lbl]; cells = []; mdd_ok, ret_ok = 0, 0
    for k in range(len(PER)):
        med = np.median(R[:, k], axis=0)
        if R is B:
            cells.append("%+.1f%% / %.1f%% / %.2f" % tuple(med)); continue
        wm = (R[:, k, 1] > B[:, k, 1]).mean() * 100; wr = (R[:, k, 0] > B[:, k, 0]).mean() * 100
        mdd_ok += wm >= 60; ret_ok += wr >= 50
        cells.append("%+.1f%% / %.1f%% / %.2f (%.0f · %.0f)" % (*med, wm, wr))
    ok = "—" if R is B else ("✅" if (mdd_ok == 3 and ret_ok >= 2) else "")
    O.append("| %s | %s | %s |" % (lbl, " | ".join(cells), ok))
O += ["", "※ 기준(미리 정함): 세 구간 모두 낙폭 얕은 시드 60%↑ · 두 구간 이상 수익 높은 시드 50%↑ · 이웃 칸 같은 방향.",
      "※ 계좌는 사이트 모델(N1 자리 4 · 나머지 3 · 종목당 같은 금액)이다. 실거래(모든 신호 1주씩)와는 비중이 다르다."]
rp = ROOT / "reports" / ("us_n156_%s.md" % time.strftime("%Y%m%d"))
rp.write_text("\n".join(O) + "\n", encoding="utf-8")
print("\n".join(O))
