# -*- coding: utf-8 -*-
"""**내부자 매도는 어떤가** (2026-09-15 요청).

매수는 복권형(절삭 -0.05% · 상위5%가 수익의 101%)이라 채택이 막혔다. 반대쪽을 본다.

⚠ 매도는 매수와 성격이 다르다. 임원은 **분산투자·세금·생활비·스톡옵션 행사**로도 판다.
   그래서 '매도 = 나쁜 신호' 는 학술적으로도 약하다고 알려져 있다. 기대를 낮추고 본다.

  ① 매도 뒤 성적이 **유니버스보다 낮은가** — 낮아야 회피 신호로 쓸 수 있다
  ② 금액·직위·규모별
  ③ 매수 대비 매도 (한쪽만 vs 양쪽 다)
  ④ **기존 5규칙에 '내부자 매도 없을 것' 을 얹으면** — 이게 실제 쓸모다
     (우리는 [낙폭과대]에서 *내부자 매수가 있으면 오히려 나쁘다* 를 이미 봤다)

판정: 회피 신호로 쓰려면 **초과가 뚜렷한 음수**여야 하고, 얹었을 때 계좌가 나아져야 한다.

    python us_ins_sell.py
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
W = 140
SINCE = "20160101"
NS = 30
t0 = time.time()


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


log("us_ins.pkl")
K = pd.read_pickle(BASE / "data/us_ins.pkl")
KEEP = ["ticker", "date", "amt20", "buy", "pref", "rawclose", "n20", "n40", "n60",
        "bv", "bn", "sv", "sn", "sd", "so", "st", "sv20", "sv60", "net60",
        "marcap", "fromhi", "ret20", "ret60"]
K = K[[c for c in KEEP if c in K.columns]].copy()
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False)
ud = sorted(K.date.unique())
DD = {d: i for i, d in enumerate(ud)}
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
log("  %s행 · 매도 있는 행 %s" % (f"{len(K):,}", f"{int((K.sv.fillna(0) > 0).sum()):,}"))


def run(tag, cond, h=40, minn=150):
    z = K[cond.fillna(False)].dropna(subset=[f"n{h}"])
    z = z[(z.buy > 0) & (z.date >= SINCE)].sort_values("date")
    keep, last = [], {}
    for t, d_, ix in zip(z.ticker.values, z.date.values, z.index):
        i = DD[d_]
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h
        keep.append(ix)
    Y = z.loc[keep].copy()
    if len(Y) < minn:
        print("  %-40s%7s (부족)" % (tag, f"{len(Y):,}"))
        return None
    v = Y[f"n{h}"].astype(float)
    ex = (v - Y.date.map(BEN[h])).mean()
    yr = Y.assign(y=Y.date.str[:4]).groupby("y")[f"n{h}"].median()
    neg = int((yr < 0).sum())
    print("  %-40s%7s%9.2f%9.2f%8.0f%%%9.2f%8d/%d"
          % (tag, f"{len(Y):,}", v.mean(), v.median(), (v > 0).mean() * 100, ex, neg, len(yr)))
    return dict(tag=tag, n=len(Y), mean=v.mean(), med=v.median(), ex=ex, neg=neg, ny=len(yr))


HDR = "  %-40s%7s%9s%9s%8s%9s%10s" % ("조건", "n", "평균", "중앙", "승률", "초과", "음수해")
print("\n" + "=" * W)
print("내부자 매도 — 40일 보유 · 거래대금 상위40% · 초과가 **뚜렷한 음수**여야 회피 신호다")
print("=" * W)

print("\n## 대조군")
print(HDR)
run("유니버스 전체", UNI, minn=1000)
run("내부자 매수 100만$↑ (참고)", UNI & (K.bv >= 1e6))

print("\n## ① 매도 금액별")
print(HDR)
for v, lbl in ((1e5, "10만$"), (1e6, "100만$"), (5e6, "500만$"), (2e7, "2000만$")):
    run("내부자 매도 %s 이상" % lbl, UNI & (K.sv >= v))

print("\n## ② 직위별 (매도 100만$↑ 기준)")
print(HDR)
SB = UNI & (K.sv >= 1e6)
for c, nm in (("sd", "이사(director)"), ("so", "임원(officer)"), ("st", "10% 주주")):
    if c in K.columns:
        run("%s 매도 포함" % nm, SB & (K[c].fillna(0) > 0))

print("\n## ③ 매수·매도 조합")
print(HDR)
run("매도만 (매수 없음)", UNI & (K.sv >= 1e6) & (K.bv.fillna(0) <= 0))
run("매도가 매수의 3배 이상", UNI & (K.sv >= 1e6) & (K.sv >= 3 * K.bv.fillna(0)))
run("60일 순매수 음수", UNI & (K.net60.fillna(0) < 0) & (K.sv >= 1e6))
run("매수만 (매도 없음) 100만$↑", UNI & (K.bv >= 1e6) & (K.sv.fillna(0) <= 0))

print("\n## ④ 보유일별 — 매도 100만$↑")
print(HDR)
for h in (20, 40, 60):
    run("내부자 매도 100만$↑ · %d일" % h, SB, h=h)

print("\n## ⑤ 주가 위치와 겹치면 (매도 100만$↑)")
print(HDR)
for lo in (-5, -15):
    run("매도 & 고점대비 %d%% 이상" % lo, SB & (K.fromhi >= lo))
run("매도 & 고점대비 -30% 미만", SB & (K.fromhi < -30))

# ══════════════════════════════════════════════════════════════════════════
sec("⑥ 기존 5규칙에 '내부자 매도 없을 것' 을 얹으면 — 실제 쓸모")
SELL = {}
for w in (20, 60):
    col = f"sv{w}" if f"sv{w}" in K.columns else None
    if col:
        SELL[w] = set((K.ticker + K.date)[(K[col].fillna(0) > 0).values])
SELL[0] = set((K.ticker + K.date)[(K.sv.fillna(0) > 0).values])
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S0, DS, ADI, PCT = C["S"], C["DS"], C["ADI"], C["PCT"]
S0 = S0.copy()
S0["key"] = S0.ticker + S0.date


def sim(S, ds, seed=None, cash_cap=1.0):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100)
        gg = byd.get(d)
        if gg is None:
            continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r in gg.itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if sum(PCT[x[0]] for x in held) / 100 + r.pct / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


b30 = [sim(S0, DS, seed=k) for k in range(NS)]
BN = [x[0] for x in b30]
BM = [x[1] for x in b30]
n0, m0, e0 = sim(S0, DS)
print("  %-34s%8s%7s%9s%11s%9s%9s" % ("구성", "신호", "노출", "자산", "시드중앙", "자산승", "낙폭승"))
print("  %-34s%8s%6.0f%%%8.2f배%10.2f배%9s%9s"
      % ("5규칙 (지금)", f"{len(S0):,}", e0 * 100, n0, np.median(BN), "—", "—"))
for w, lbl in ((0, "그날 매도가 있으면 제외"), (20, "최근 20일 매도 있으면 제외"),
               (60, "최근 60일 매도 있으면 제외")):
    if w not in SELL:
        continue
    S = S0[~S0.key.isin(SELL[w])].reset_index(drop=True)
    a, mm, ee = sim(S, DS)
    rr = [sim(S, DS, seed=k) for k in range(NS)]
    wn = sum(1 for x, y in zip(rr, b30) if x[0] > y[0])
    wm = sum(1 for x, y in zip(rr, b30) if x[1] > y[1])
    print("  %-34s%8s%6.0f%%%8.2f배%10.2f배%7d/%d%7d/%d"
          % (lbl, f"{len(S):,}", ee * 100, a, np.median([x[0] for x in rr]), wn, NS, wm, NS))
print("\n  [반대 확인] 매도가 있는 것만 남기면 (나빠야 정상)")
for w, lbl in ((0, "그날 매도 있는 것만"), (60, "최근 60일 매도 있는 것만")):
    if w not in SELL:
        continue
    S = S0[S0.key.isin(SELL[w])].reset_index(drop=True)
    if len(S) < 200:
        print("  %-34s%8s (부족)" % (lbl, f"{len(S):,}"))
        continue
    a, mm, ee = sim(S, DS)
    print("  %-34s%8s%6.0f%%%8.2f배" % (lbl, f"{len(S):,}", ee * 100, a))
print("\n총 %.0f초" % (time.time() - t0))
