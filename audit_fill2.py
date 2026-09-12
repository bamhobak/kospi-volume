# -*- coding: utf-8 -*-
"""체결 감사 보충 (2026-09-12) — audit_fill.py 가 못 잰 둘.

  ⑥ 수급 열(fw5·fw60·ow20·ow60·ins60·bb)은 kr_scan 에 없고 **panel_kp/kq** 에만 있다.
     거기서 미래참조를 본다. 비율 열은 inf 가 섞여 상관이 nan 이 되므로 걸러서 잰다.
  ⑧ **매수일 상한가 잠김** — 진짜 물어야 할 것. 신호 다음날(사는 날) 시가가 그날 상한가이고
     고가=저가면 **하루 종일 잠겨** 그 가격에 못 산다. audit_fill 은 '신호일' 상한가를 쟀는데
     그건 다음날 시가로 사면 되니 문제가 아니다(갭은 buy 가 이미 치른다).
  ⑨ 매도일 하한가 잠김도 같은 방식으로.

    python audit_fill2.py
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 112


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)
def flag(ok, msg): print(("  ✅ " if ok else "  ⚠ ") + msg)


log("panel_kp.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/panel_kp.pkl")
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
g = K.groupby("ticker", sort=False)
log(f"  {len(K):,}행 · 열 {len(K.columns)}")

sec("⑥ 수급·재료 열의 미래참조 — 내일값과 어제값 중 어느 쪽을 더 닮았나")
print("  같은 열을 하루 앞당긴 값(내일)과 하루 미룬 값(어제)에 각각 상관을 낸다.")
print("  정상이면 대칭이다. **내일 쪽이 뚜렷이 높으면** 미래를 섞어 쓴 것이다.")
cand = [c for c in ("fw5", "fw20", "fw60", "ow20", "ow60", "ins60", "bb", "srd", "sr20",
                    "su1", "r16", "rw1", "marcap", "PBR") if c in K.columns]
print(f"\n  {'열':<8}{'유효%':>7}{'내일과 동일':>11}{'내일 상관':>10}{'어제 상관':>10}{'차이':>8}  판정")
for c in cand:
    s = K[c]
    if s.dtype == bool: s = s.astype(float)
    s = s.replace([np.inf, -np.inf], np.nan)
    fut = s.groupby(K.ticker).shift(-1)
    pas = s.groupby(K.ticker).shift(1)
    m = s.notna() & fut.notna() & pas.notna()
    if m.sum() < 5000:
        print(f"  {c:<8}{s.notna().mean()*100:>6.0f}%  표본 부족"); continue
    same = ((s - fut).abs() < 1e-9)[m].mean() * 100
    cf = float(s[m].corr(fut[m])); cp = float(s[m].corr(pas[m]))
    d = cf - cp
    v = "정상" if abs(d) < 0.02 else ("⚠ 미래 쪽이 높다" if d > 0 else "과거 쪽이 높다(정상)")
    print(f"  {c:<8}{s.notna().mean()*100:>6.0f}%{same:>10.2f}%{cf:>10.3f}{cp:>10.3f}{d:>+8.3f}  {v}")

sec("⑧ 매수일 상한가 잠김 — 신호 다음날 시가가 그날 상한가이고 하루 종일 잠겼나")
pc = g.close.shift(1)
lim = np.where(K.date.values < "20150615", 0.15, 0.30)
# 사는 날(t+1)의 값들
o1 = g.open.shift(-1); h1 = g.high.shift(-1); l1 = g.low.shift(-1); c0 = K.close
up_open = (o1 / c0 - 1) >= (lim - 0.005)        # 시가가 상한가 근처
locked = (h1 == l1) & (h1 == o1)                 # 고가=저가=시가 → 하루 종일 한 가격
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
print(f"  전체 {len(K):,}행 중")
print(f"     사는 날 시가가 상한가 {int((up_open & UNI).fillna(False).sum()):,}행 (유니버스)")
print(f"     그날 하루 종일 잠김(고가=저가=시가) {int((up_open & locked & UNI).fillna(False).sum()):,}행")
JW = K.jw if "jw" in K.columns else pd.Series(False, index=K.index)
CONDS = [
    ("폭락반등 (ret20≤-25)", (K.ret20 <= -25)),
    ("깊은이격 (dev25≤-25)", (K.dev25 <= -25)) if "dev25" in K.columns else None,
    ("신고가 (fromhi≥-5)", (K.fromhi >= -5) & (K.ret250 > 0)) if "ret250" in K.columns else None,
    ("업종붕괴 (u≤-20)", (K.u <= -20)),
]
CONDS = [x for x in CONDS if x]
print(f"\n  {'계열':<24}{'신호':>10}{'매수일 상한가':>14}{'잠겨서 못 삼':>14}")
for nm, c in CONDS:
    m = (c & UNI & ~JW).fillna(False)
    n = int(m.sum())
    if n < 100: print(f"  {nm:<24}{n:>10}  (부족)"); continue
    a = int((m & up_open.fillna(False)).sum()); b = int((m & (up_open & locked).fillna(False)).sum())
    print(f"  {nm:<24}{n:>10,}{a:>10,}({a/n*100:>4.2f}%){b:>10,}({b/n*100:>4.2f}%)")

sec("⑨ 매도일 하한가 잠김 — 정해진 날 종가에 못 파는 경우")
dn_open = (K.close / pc - 1) <= (-lim + 0.005)
locked_d = (K.high == K.low)
lk = (dn_open & locked_d).fillna(False)
for h in (20, 60):
    sell_locked = lk.groupby(K.ticker).shift(-h).fillna(False)
    for nm, c in CONDS[:2]:
        m = (c & UNI & ~JW).fillna(False) & K[f"n{h}"].notna()
        n = int(m.sum())
        if n < 100: continue
        b = int((m & sell_locked).sum())
        print(f"  {nm:<24} 보유 {h}일 · 신호 {n:>8,} 중 청산일 하한가 잠김 {b:>5,} ({b/n*100:.2f}%)")
log("끝")
