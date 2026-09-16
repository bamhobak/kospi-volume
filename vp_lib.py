# -*- coding: utf-8 -*-
"""볼륨 프로파일 POC 눌림목 — 실측 엔진.

유튜브 'How to Find The Strongest Stocks to Swing Trade' (B The Trader, 2024-11-11,
게스트 Jimmy) 에서 설명된 기법을 일봉 데이터로 재현한다. 영상 원문 요지:

  ① 톱다운으로 강한 것부터 고른다 — 지수 → 섹터 → 업종 → 개별종목(상대강도).
  ② 그 종목의 **스윙 저점 → 스윙 고점** 구간에 볼륨 프로파일을 그린다.
     "구조가 깨지면(더 낮은 저점) 그리기를 멈추고 새 저점부터 다시 그린다."
  ③ 거래가 가장 많이 몰린 가격대(POC)에 박스를 친다. 그 박스로 눌림이 오면 매수.
     "박스에 닿은 다음 초록 캔들이 내 진입."
  ④ POC 아래에서 알짱거리기 시작하면 확률이 확 떨어진다. 오히려 숏 자리로 뒤집힌다.
  ⑤ 손절은 스윙 저점 아래. 목표가는 하락 스윙의 볼륨 프로파일 고밀도 구간(위쪽 매물대),
     절반씩 분할 청산.

일봉으로 옮길 때의 원칙 — **없는 것을 지어내지 않는다.**
  · 볼륨 프로파일은 원래 체결 단위지만 우리에겐 일봉뿐이다. 그래서 각 봉의 거래량을
    그 봉의 [저가, 고가] 구간에 **균등 분배**해 가격대별로 누적한다(업계 표준 근사).
    스윙이 수십 봉이므로 스윙 단위 POC 는 이 근사로도 충분히 잡힌다.
  · 스윙 저점/고점은 W일 창 안의 최고가 위치를 스윙 고점으로 잡고, 그 이전 구간의
    최저가를 스윙 저점으로 잡는다. 즉 "저점 → 고점" 상승 레그다.
  · 매수는 언제나 **다음날 시가**(패널의 buy), 비용 차감. 다른 규칙과 같은 규율.
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# 1. POC 계산
# ══════════════════════════════════════════════════════════════════════
def compute_poc(A, W=120, NB=24, minleg=15.0, maxback=40, minlen=10,
                pull_lo=1.0, pull_hi=35.0, cand_mask=None):
    """행마다 '지금 눌림 중인 스윙 레그' 의 POC 박스를 구한다.

    W       스윙 고점을 찾는 창(거래일)
    NB      볼륨 프로파일 가격 구간 수 (POC 박스 두께 = 레그 폭 / NB)
    minleg  레그 상승폭 하한(%) — 스윙이라 부를 만한 크기
    maxback 스윙 고점 이후 경과일 상한 — 오래된 고점은 이미 다른 국면
    minlen  레그 최소 봉수
    pull_*  스윙 고점 대비 현재 낙폭(%) 범위 — 이 안에 있을 때만 계산(비용 절감)
    cand_mask 유니버스 마스크(불리언 Series) — 여기서만 계산

    반환: poc_lo, poc_hi, leg_lo, leg_hi, leglen, leggain (float32 배열, 없으면 NaN)
    """
    n = len(A)
    poc_lo = np.full(n, np.nan, np.float32); poc_hi = np.full(n, np.nan, np.float32)
    leg_lo = np.full(n, np.nan, np.float32); leg_hi = np.full(n, np.nan, np.float32)
    leglen = np.full(n, np.nan, np.float32); leggain = np.full(n, np.nan, np.float32)

    H = A.high.to_numpy(np.float64); L = A.low.to_numpy(np.float64)
    C = A.close.to_numpy(np.float64); V = A.volume.to_numpy(np.float64)
    cm = np.ones(n, bool) if cand_mask is None else np.asarray(cand_mask, bool)

    # 종목 경계
    tk = A.ticker.to_numpy()
    bnd = np.flatnonzero(np.r_[True, tk[1:] != tk[:-1], True])
    from numpy.lib.stride_tricks import sliding_window_view

    ncand = 0
    for s, e in zip(bnd[:-1], bnd[1:]):
        m = e - s
        if m < W + 5: continue
        h = H[s:e]; l = L[s:e]; c = C[s:e]; v = V[s:e]
        # 창 안 최고가 위치(로컬 인덱스)
        sw = sliding_window_view(h, W)
        hi_rel = sw.argmax(1)
        hi_idx = np.full(m, -1, np.int64)
        hi_idx[W - 1:] = hi_rel + np.arange(m - W + 1)
        ok = (hi_idx >= 0)
        # 고점은 이미 지났고(오늘 아님) 너무 오래되지도 않았다
        tpos = np.arange(m)
        ok &= (hi_idx < tpos) & (tpos - hi_idx <= maxback)
        # 스윙 고점 대비 현재 낙폭
        with np.errstate(invalid="ignore"):
            dd = np.where(ok, (c / h[np.clip(hi_idx, 0, m - 1)] - 1) * 100, np.nan)
        ok &= (dd <= -pull_lo) & (dd >= -pull_hi)
        ok &= cm[s:e]
        idxs = np.flatnonzero(ok)
        if not len(idxs): continue
        ncand += len(idxs)
        for t in idxs:
            hi = hi_idx[t]
            w0 = max(0, t - W + 1)
            # 스윙 저점 = 창 시작 ~ 스윙 고점 사이의 최저가
            lo = w0 + int(np.argmin(l[w0:hi + 1]))
            if hi - lo + 1 < minlen: continue
            top = h[lo:hi + 1].max(); bot = l[lo:hi + 1].min()
            if not (top > bot > 0): continue
            gain = (top / bot - 1) * 100
            if gain < minleg: continue
            bh = h[lo:hi + 1]; bl = l[lo:hi + 1]; bv = v[lo:hi + 1]
            edges = np.linspace(bot, top, NB + 1)
            e0 = edges[:-1]; e1 = edges[1:]
            ov = np.minimum(bh[:, None], e1[None, :]) - np.maximum(bl[:, None], e0[None, :])
            np.clip(ov, 0, None, out=ov)
            rs = ov.sum(1)
            rs[rs <= 0] = np.nan                    # 도지봉 등 — 아래서 제외
            vp = np.nansum(ov / rs[:, None] * bv[:, None], axis=0)
            k = int(vp.argmax())
            j = s + t
            poc_lo[j] = e0[k]; poc_hi[j] = e1[k]
            leg_lo[j] = bot; leg_hi[j] = top
            leglen[j] = hi - lo + 1; leggain[j] = gain
    return dict(poc_lo=poc_lo, poc_hi=poc_hi, leg_lo=leg_lo, leg_hi=leg_hi,
                leglen=leglen, leggain=leggain, ncand=ncand)


# ══════════════════════════════════════════════════════════════════════
# 2. 판정
# ══════════════════════════════════════════════════════════════════════
def boot_ci(r, alpha=0.10, n=8000, seed=0):
    """월 블록 부트스트랩 하한 — r 은 월별 평균 수익률."""
    r = np.asarray(pd.Series(r).dropna(), float)
    if len(r) < 8: return np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), (n, len(r)))
    return float(np.percentile(r[idx].mean(axis=1), alpha * 100))


class Runner:
    """유니버스·벤치마크를 한 번만 만들어 두고 조건마다 성적을 낸다."""

    def __init__(self, A, uni, label, since=TR0):
        self.A = A; self.uni = uni; self.label = label; self.since = since
        self.dates = sorted(A.date.unique())
        self.di = {d: i for i, d in enumerate(self.dates)}
        A["di"] = A.date.map(self.di).astype(np.int32)
        self._ben = {}
        self.months = len({d[:6] for d in A.date[uni].unique()}) or 1

    def bench(self, h):
        if h not in self._ben:
            col = f"n{h}"
            self._ben[h] = self.A[self.uni].dropna(subset=[col]).groupby("date")[col].mean()
        return self._ben[h]

    def run(self, tag, cond, hold=20, minn=40, quiet=False):
        col = f"n{hold}"
        X = self.A[(self.uni & cond).fillna(False)].dropna(subset=[col])
        X = X[X.date >= self.since].sort_values("di")
        if len(X) < minn:
            if not quiet: print(f"  {tag:<38} {len(X):>5} (부족)")
            return None
        keep, last = [], {}
        for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
            if last.get(t, -10 ** 9) >= i: continue
            last[t] = i + hold; keep.append(ix)
        Y = X.loc[keep].copy()
        if len(Y) < minn:
            if not quiet: print(f"  {tag:<38} {len(Y):>5} (부족)")
            return None
        Y["r"] = Y[col].astype(float)
        Y["ym"] = Y.date.str[:6]; Y["yr"] = Y.date.str[:4]
        Y["ex"] = Y.r - Y.date.map(self.bench(hold))
        tr = Y[Y.date <= TR1]; va = Y[Y.date >= VA0]
        yr = Y.groupby("yr").r.median()
        ci = boot_ci(Y.groupby("ym").r.mean())
        cit = boot_ci(tr.groupby("ym").r.mean()) if len(tr) >= 25 else np.nan
        trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
        pos = int((yr > 0).sum()); ny = len(yr)
        # ⚠ 2026-09-16 부터 **유니버스 대비 초과는 판정에서 뺀다**(사용자 지시).
        #   우리 목표가 지수·유니버스를 이기는 게 아니기 때문이다([[goal-not-beating-index]]).
        #   초과가 막아 주던 함정('다 오르던 때만 신호가 나서 절대수익이 좋아 보인다')은
        #   **연도별 양수 개수**와 **학습·검증 분리**가 겸해서 막는다 — 아래 조건에 이미 있다.
        #   ex 는 계산만 해 두고(진단용) 통과 여부와 표에서는 쓰지 않는다.
        ok = (Y.r.median() > 0 and trim > 0
              and cit == cit and cit > 0 and ci == ci and ci > 0
              and len(va) >= 20 and va.r.median() > 0 and pos / max(ny, 1) >= 0.6)
        res = dict(tag=tag, hold=hold, n=len(Y), mean=Y.r.mean(), med=Y.r.median(),
                   trim=trim, win=(Y.r > 0).mean() * 100, ex=Y.ex.mean(),
                   trm=tr.r.median() if len(tr) else np.nan,
                   vam=va.r.median() if len(va) else np.nan, nva=len(va),
                   ci=ci, cit=cit, pos=pos, ny=ny, per=len(Y) / self.months, ok=ok, Y=Y)
        if not quiet: print(fmt(res))
        return res


HDR = (f"  {'조건':<38} {'n':>5} {'평균':>7} {'중앙':>7} {'절삭':>7} {'승률':>6} "
       f"{'학습중앙':>8} {'검증중앙':>8} {'학습CI':>7} {'전체CI':>7} {'양수해':>7} {'월':>6}")


def hdr(title=None):
    if title: print(f"\n## {title}")
    print(HDR)


def fmt(r):
    return (f"  {r['tag']:<38} {r['n']:>5} {r['mean']:>7.2f} {r['med']:>7.2f} "
            f"{r['trim']:>7.2f} {r['win']:>5.0f}% {r['trm']:>8.2f} {r['vam']:>8.2f} "
            f"{r['cit']:>7.2f} {r['ci']:>7.2f} {r['pos']:>3}/{r['ny']:<3} {r['per']:>6.1f}"
            f"{'  ✅' if r['ok'] else ''}")


# ══════════════════════════════════════════════════════════════════════
# 3. 지그재그 레그 POC · 영상식 청산 (vp_zz.py 에서 옮김 — vp_probe.py 에서도 쓴다)
# ══════════════════════════════════════════════════════════════════════
def compute_poc_zz(A, pct=8.0, NB=24, maxback=30, minleg=10.0, minlen=6, cand_mask=None):
    """지그재그로 잡은 '직전 확정 상승 레그' 의 POC 박스."""
    n = len(A)
    out = {k: np.full(n, np.nan, np.float32) for k in
           ("poc_lo", "poc_hi", "leg_lo", "leg_hi", "leglen", "leggain", "legage")}
    H = A.high.to_numpy(np.float64); L = A.low.to_numpy(np.float64)
    V = A.volume.to_numpy(np.float64)
    cm = np.ones(n, bool) if cand_mask is None else np.asarray(cand_mask, bool)
    tk = A.ticker.to_numpy()
    bnd = np.flatnonzero(np.r_[True, tk[1:] != tk[:-1], True])
    up, dn = 1 + pct / 100, 1 - pct / 100
    nleg = 0
    for s, e in zip(bnd[:-1], bnd[1:]):
        m = e - s
        if m < 30: continue
        h = H[s:e]; l = L[s:e]; v = V[s:e]
        # ── 지그재그(인과적) ──
        # dirn=+1 상승 중(직전 확정 저점 lo_i 에서 출발), -1 하락 중
        dirn = 1; lo_i = 0; lo_v = l[0]; hi_i = 0; hi_v = h[0]
        conf_lo = -1; conf_hi = -1          # 확정된 직전 상승 레그 (저점, 고점)
        cur_lo, cur_hi = -1, -1
        cache = {}
        for i in range(1, m):
            if dirn == 1:
                if h[i] > hi_v: hi_v = h[i]; hi_i = i
                if l[i] <= hi_v * dn:                 # 고점 확정 → 하락 전환
                    conf_lo, conf_hi = lo_i, hi_i
                    dirn = -1; lo_v = l[i]; lo_i = i
            else:
                if l[i] < lo_v: lo_v = l[i]; lo_i = i
                if h[i] >= lo_v * up:                 # 저점 확정 → 상승 전환
                    dirn = 1; hi_v = h[i]; hi_i = i
            if conf_hi < 0 or not cm[s + i]: continue
            if i - conf_hi > maxback: continue        # 고점이 너무 오래됨
            lo, hi = conf_lo, conf_hi
            if hi - lo + 1 < minlen: continue
            key = (lo, hi)
            if key not in cache:
                bh = h[lo:hi + 1]; bl = l[lo:hi + 1]; bv = v[lo:hi + 1]
                top = bh.max(); bot = bl.min()
                if not (top > bot > 0) or (top / bot - 1) * 100 < minleg:
                    cache[key] = None
                else:
                    edges = np.linspace(bot, top, NB + 1)
                    e0 = edges[:-1]; e1 = edges[1:]
                    ov = np.minimum(bh[:, None], e1[None, :]) - np.maximum(bl[:, None], e0[None, :])
                    np.clip(ov, 0, None, out=ov)
                    rs = ov.sum(1); rs[rs <= 0] = np.nan
                    vp = np.nansum(ov / rs[:, None] * bv[:, None], axis=0)
                    k = int(vp.argmax())
                    cache[key] = (e0[k], e1[k], bot, top, hi - lo + 1, (top / bot - 1) * 100)
                    nleg += 1
            c = cache[key]
            if c is None: continue
            j = s + i
            out["poc_lo"][j], out["poc_hi"][j], out["leg_lo"][j], out["leg_hi"][j] = c[0], c[1], c[2], c[3]
            out["leglen"][j], out["leggain"][j] = c[4], c[5]
            out["legage"][j] = i - conf_hi
    out["nleg"] = nleg
    return out


# ══════════════════════════════════════════════════════════════════════
# 영상식 청산 — 스윙저점 손절 / 스윙고점 목표 / 최대보유
# ══════════════════════════════════════════════════════════════════════
def sim_exit(A, sigmask, maxhold=20):
    """종가로 판정하고 다음날 시가에 청산한다(집안 규율). 수익률 %(비용 차감)."""
    C = A.close.to_numpy(np.float64); O = A.open.to_numpy(np.float64)
    BUY = A.buy.to_numpy(np.float64); COST = A.cost.to_numpy(np.float64)
    SL = A.leg_lo.to_numpy(np.float64); TP = A.leg_hi.to_numpy(np.float64)
    tk = A.ticker.to_numpy()
    bnd = np.flatnonzero(np.r_[True, tk[1:] != tk[:-1], True])
    endof = np.empty(len(A), np.int64)
    for s, e in zip(bnd[:-1], bnd[1:]): endof[s:e] = e
    idx = np.flatnonzero(sigmask)
    ret = np.full(len(idx), np.nan); hold = np.zeros(len(idx), np.int32)
    for z, j in enumerate(idx):
        b = BUY[j]
        if not (b > 0): continue
        lim = min(endof[j] - 1, j + maxhold)
        ex = np.nan
        for k in range(j + 1, lim + 1):
            if C[k] < SL[j] or C[k] >= TP[j]:
                ex = O[k + 1] if k + 1 <= endof[j] - 1 else C[k]
                hold[z] = k - j; break
        if not (ex == ex):
            ex = C[lim]; hold[z] = lim - j
        ret[z] = (ex / b - 1) * 100 - COST[j]
    return idx, ret, hold


def judge(tag, A, sigmask, uni, ben, maxhold=20, minn=40):
    idx, ret, hold = sim_exit(A, sigmask.to_numpy(), maxhold)
    X = A.iloc[idx].copy(); X["r"] = ret; X["hd"] = hold
    X = X[X.r.notna() & (X.date >= "20160101")].sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i: continue
        last[t] = i + maxhold; keep.append(ix)
    Y = X.loc[keep]
    if len(Y) < minn:
        print(f"  {tag:<38} {len(Y):>5} (부족)"); return None
    Y = Y.copy(); Y["ym"] = Y.date.str[:6]; Y["yr"] = Y.date.str[:4]
    Y["ex"] = Y.r - Y.date.map(ben)
    tr = Y[Y.date <= TR1]; va = Y[Y.date >= VA0]
    yr = Y.groupby("yr").r.median()
    ci = boot_ci(Y.groupby("ym").r.mean()); cit = boot_ci(tr.groupby("ym").r.mean()) if len(tr) >= 25 else np.nan
    trim = Y.r[Y.r <= Y.r.quantile(0.95)].mean()
    pos, ny = int((yr > 0).sum()), len(yr)
    ok = (Y.r.median() > 0 and trim > 0 and cit == cit and cit > 0
          and ci == ci and ci > 0 and len(va) >= 20 and va.r.median() > 0 and pos / max(ny, 1) >= 0.6)
    print(f"  {tag:<38} {len(Y):>5} {Y.r.mean():>7.2f} {Y.r.median():>7.2f} "
          f"{trim:>7.2f} {(Y.r>0).mean()*100:>5.0f}% {tr.r.median():>8.2f} {va.r.median():>8.2f} "
          f"{cit:>7.2f} {ci:>7.2f} {pos:>3}/{ny:<3} {Y.hd.mean():>6.1f}{'  ✅' if ok else ''}")
    return Y


