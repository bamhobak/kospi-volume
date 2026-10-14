# -*- coding: utf-8 -*-
"""유튜브 '피터 브랜트 헤드앤숄더 매매법'(머니크루, 3sbTuFH8BEE · 2026-10-14 사용자 링크) 실측 — H0333.

영상 규칙: 오른 종목에서 어깨·머리·어깨 → 종가가 목선 아래로 끝난 날(완성일) 공매도, 손절 = 그날 고가 위, 목표 = 목선 - (머리~목선 높이).
뒤집은 매수판(역헤드앤숄더): 내린 종목 → 종가가 목선 위 + 거래량 증가한 날 매수, 손절 = 그날 저가, 목표 = 목선 + 높이.
진짜 가리기: 앞선 추세 · 두 어깨 높이·기간 비슷 · 목선 수평에 가까움 · 종가 확인.

우리(개인, 공매도 불가)는
  A 역헤드앤숄더 매수 — 다음날 시가 매수 · 손절/목표/최대 60일(브랜트 청산) + 고정 20·60일 보유(같은 날 유니버스 대비 초과)
  B 헤드앤숄더 천장 완성 — 그 뒤 5·20·60일 유니버스 대비 초과(음수면 '보유 매도·매수 회피' 신호로 쓸 수 있나)
꼭짓점 = 앞뒤 K(5)거래일 최고·최저, K 일 뒤에야 확정(미래 안 봄). 유니버스 = 거래대금 상위 40%(국장)·20%(미장 패널 규칙).
비용: 국장 0.5%(세금·수수료·미끄러짐) · 미장 0.25%. 옛날 ~15 · 학습 16~22 · 검증 23~.
    python research/yt_hs.py KR|US
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from numba import njit
import run_spec as R

MK = sys.argv[1] if len(sys.argv) > 1 else "KR"
COST = 0.5 if MK == "KR" else 0.25
K = 5
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


@njit(cache=True)
def pivots(h, l, k):
    n = len(h); ph = np.zeros(n, np.bool_); pl = np.zeros(n, np.bool_)
    for i in range(k, n - k):
        mh = h[i]; ml = l[i]; okh = True; okl = True
        for j in range(i - k, i + k + 1):
            if j == i: continue
            if h[j] > mh or (h[j] == mh and j < i): okh = False
            if l[j] < ml or (l[j] == ml and j < i): okl = False
        ph[i] = okh; pl[i] = okl
    return ph, pl


def zigzag(idx_h, idx_l, h, l):
    """확정 꼭짓점을 시간순·번갈아(같은 종류가 이어지면 더 극단인 것)로."""
    ev = sorted([(i, "H", h[i]) for i in idx_h] + [(i, "L", l[i]) for i in idx_l])
    z = []
    for e in ev:
        if z and z[-1][1] == e[1]:
            if (e[1] == "H" and e[2] > z[-1][2]) or (e[1] == "L" and e[2] < z[-1][2]): z[-1] = e
        else: z.append(e)
    return z


def scan(o, h, l, c, v, v20, top):
    """top=False: 역헤드앤숄더(바닥) · True: 헤드앤숄더(천장). 반환 [(완성일, 목선값, 머리, 높이)]."""
    ph, pl = pivots(h, l, K)
    z = zigzag(np.flatnonzero(ph), np.flatnonzero(pl), h, l)
    out = []; n = len(c)
    sh, pk = ("H", "L") if top else ("L", "H")            # 어깨·머리 종류 / 목선 꼭짓점 종류
    for j in range(4, len(z)):
        L1, P1, H, P2, R2 = z[j - 4:j + 1]
        if L1[1] != sh or P1[1] != pk or H[1] != sh or P2[1] != pk or R2[1] != sh: continue
        span = R2[0] - L1[0]
        if not (15 <= span <= 150): continue
        if top:
            if not (H[2] > L1[2] and H[2] > R2[2]): continue
        else:
            if not (H[2] < L1[2] and H[2] < R2[2]): continue
        nk1, nk2 = P1[2], P2[2]
        neck_mid = (nk1 + nk2) / 2
        height = abs(H[2] - neck_mid)
        if height <= 0 or abs(nk2 - nk1) / neck_mid > 0.08: continue          # 목선이 너무 기울면 제외
        if abs(L1[2] - R2[2]) > 0.3 * height: continue                          # 두 어깨 높이 비슷
        d1, d2 = H[0] - L1[0], R2[0] - H[0]
        if d2 <= 0 or not (0.5 <= d1 / d2 <= 2.0): continue                     # 두 어깨 기간 비슷
        a = max(0, L1[0] - 60)
        if top:
            if c[a:L1[0] + 1].min() > L1[2] / 1.15: continue                    # 앞선 상승(+15%)
        else:
            if c[a:L1[0] + 1].max() < L1[2] * 1.15: continue                    # 앞선 하락
        slope = (nk2 - nk1) / (P2[0] - P1[0])
        neck = lambda t: nk1 + slope * (t - P1[0])
        start = R2[0] + K                                                       # 오른쪽 어깨가 확정된 뒤부터
        for t in range(max(start, R2[0] + 1), min(n, R2[0] + 21)):
            if top:
                if h[R2[0]:t + 1].max() > H[2]: break                            # 머리를 넘으면 모양이 깨짐
                if c[t] < neck(t) and c[t - 1] >= neck(t - 1): out.append((t, neck(t), H[2], height)); break
            else:
                if l[R2[0]:t + 1].min() < H[2]: break
                if c[t] > neck(t) and c[t - 1] <= neck(t - 1): out.append((t, neck(t), H[2], height)); break
    return out


def main():
    A, uni, since = R.load_market(MK)
    A["uni"] = uni.values
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    A = A[A.date >= ("20050101" if MK == "KR" else "20110101")].reset_index(drop=True)
    g = A.groupby("ticker", sort=False)
    A["v20"] = g.volume.transform(lambda s: s.shift(1).rolling(20, min_periods=10).mean())
    # 같은 날 유니버스 평균 보유 수익(다음날 시가 → h일 뒤 종가)
    for hd in (5, 20, 60):
        A["f%d" % hd] = (g.close.shift(-hd) / g.open.shift(-1) - 1) * 100
        A.loc[A["f%d" % hd].abs() > 300, "f%d" % hd] = np.nan
        A["u%d" % hd] = A["f%d" % hd].where(A.uni).groupby(A.date).transform("mean")
    rows = []
    for tk, idx in g.indices.items():
        sub = A.iloc[idx]
        o, h, l, c, v, v20 = (sub[k].values.astype(np.float64) for k in ("open", "high", "low", "close", "volume", "v20"))
        if len(c) < 120: continue
        for top in (False, True):
            for t, nk, head, ht in scan(o, h, l, c, v, v20, top):
                if t + 1 >= len(c): continue
                ii = idx[t]
                if not A.uni.values[ii]: continue
                r = dict(ticker=tk, date=sub.date.values[t], top=top, neck=nk, height=ht, vm=v[t] / v20[t] if v20[t] else np.nan,
                         f5=A.f5.values[ii], f20=A.f20.values[ii], f60=A.f60.values[ii], u5=A.u5.values[ii], u20=A.u20.values[ii], u60=A.u60.values[ii])
                if not top:                                                      # 브랜트 청산: 손절 = 완성일 저가 · 목표 = 목선 + 높이 · 최대 60일
                    ent = o[t + 1]; stop = l[t]; tgt = nk + ht; ex = None
                    for k in range(t + 1, min(len(c), t + 61)):
                        if l[k] <= stop: ex = min(o[k], stop) if k > t + 1 else (stop if o[k] > stop else o[k]); break
                        if h[k] >= tgt: ex = max(o[k], tgt); break
                    if ex is None: ex = c[min(len(c) - 1, t + 60)]
                    r["brandt"] = (ex / ent - 1) * 100 - COST
                    r["rr"] = (tgt - ent) / max(ent - stop, 1e-9)
                rows.append(r)
    E = pd.DataFrame(rows)
    E["per"] = np.where(E.date <= "20151231", 0, np.where(E.date <= "20221231", 1, 2))
    E.to_pickle(Path(__file__).resolve().parent / "cache" / ("yt_hs_%s.pkl" % MK))
    PER = ["옛날 ~15", "학습 16~22", "검증 23~"]
    P("## %s — 헤드앤숄더(꼭짓점 앞뒤 %d일 · 비용 %.2f%%)" % (MK, K, COST))
    def tbl(nm, m, col, sub_u=None):
        cells = []
        for p in range(3):
            x = E[m & (E.per == p)]
            y = (x[col] - (x[sub_u] if sub_u else 0)) if len(x) else pd.Series(dtype=float)
            y = y.dropna()
            cells.append("%d건 %+.2f%% · 승률 %.0f%%" % (len(y), y.mean(), (y > 0).mean() * 100) if len(y) else "-")
        P("| %s | %s | %s | %s |" % (nm, *cells))
    bot = ~E.top
    P("\n### A 역헤드앤숄더(바닥) 매수 — 다음날 시가")
    P("| 판 | %s | %s | %s |" % tuple(PER)); P("|---|---|---|---|")
    tbl("브랜트 청산(손절·목표·60일)", bot, "brandt")
    tbl("  거래량 1.5배↑ 완성", bot & (E.vm >= 1.5), "brandt")
    tbl("  거래량 평균 미만 완성", bot & (E.vm < 1.0), "brandt")
    for hd in (20, 60):
        tbl("%d일 보유(비용 전) − 같은 날 유니버스" % hd, bot, "f%d" % hd, "u%d" % hd)
        tbl("  거래량 1.5배↑ 완성 · %d일 초과" % hd, bot & (E.vm >= 1.5), "f%d" % hd, "u%d" % hd)
    P("\n### B 헤드앤숄더 천장 완성 뒤 — 같은 날 유니버스 대비(음수면 보유 매도·매수 회피 신호)")
    P("| 판 | %s | %s | %s |" % tuple(PER)); P("|---|---|---|---|")
    for hd in (5, 20, 60):
        tbl("천장 완성 뒤 %d일 초과" % hd, E.top, "f%d" % hd, "u%d" % hd)
    tbl("  천장 완성 · 거래량 1.5배↑ · 20일 초과", E.top & (E.vm >= 1.5), "f20", "u20")
    P("\n건수(연평균): 바닥 %.0f · 천장 %.0f" % (bot.sum() / E.date.str[:4].nunique(), E.top.sum() / E.date.str[:4].nunique()))
    (Path(__file__).resolve().parent / "cache" / ("yt_hs_%s.out" % MK)).write_text("\n".join(OUT), encoding="utf-8")


if __name__ == "__main__":
    main()
