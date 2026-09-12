# -*- coding: utf-8 -*-
"""**체결 가정과 수급 열 점검** (2026-09-12). 감사의 마지막 조각.

앞의 둘과 방향이 다르다. 가격 오염은 성적을 **희석**했고 미래참조는 없었지만,
체결 가정은 **낙관 방향**이다 — 여기서 나오는 것은 기대치를 낮춘다.

  ① 상한가 잠김 — 신호일 종가가 상한가면 다음날 시가에 못 사는 경우가 많다
  ② 하한가 잠김 — 파는 날 하한가면 그 종가에 못 판다
  ③ 갭 — '다음날 시가' 가 신호일 종가 대비 얼마나 뛰나(이미 오른 값에 사는가)
  ④ 주문 크기 대비 거래대금 — 300만원을 시가에 밀어 넣을 수 있나
  ⑤ 시가 = 종가인 날 — 거래가 거의 없어 시가가 기준가로 찍힌 경우
  ⑥ 수급 열(fw5·fw60·ow20·ow60·su1) 정의 — 오늘까지만 보는가(미래참조 검사)
  ⑦ 규칙 신호에 ①~⑤ 가 얼마나 섞여 있나 — 실제 영향

    python audit_fill.py
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


log("kr_scan.pkl 읽는 중")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
g = K.groupby("ticker", sort=False)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
JW = K.jw if "jw" in K.columns else pd.Series(False, index=K.index)
pc = g.close.shift(1)
# 가격제한폭 — 2015-06-15 부터 ±30%, 그 전 ±15%
lim = np.where(K.date.values < "20150615", 0.15, 0.30)
chg = (K.close / pc - 1)
log(f"  {len(K):,}행 · 유니버스 {int(UNI.sum()):,}행")

sec("① 상한가 잠김 — 신호일 종가가 상한가면 다음날 시가에 못 사는 일이 잦다")
up_lim = (chg >= lim - 0.005) & pc.notna()
# 상한가 마감 다음날: 시가가 얼마나 더 뛰었나 = 실제로 사려면 얼마를 더 줘야 했나
nxt_open_gap = (K.buy / K.close - 1) * 100
print(f"  상한가 마감 {int(up_lim.sum()):,}행 ({up_lim.mean()*100:.2f}%) · 유니버스 안 {int((up_lim & UNI).sum()):,}")
for nm, m in (("상한가 마감 다음날", up_lim & K.buy.notna()), ("평소", ~up_lim & K.buy.notna())):
    s = nxt_open_gap[m].dropna()
    if len(s): print(f"     {nm:<18} 시가 갭 중앙 {s.median():+.2f}% · 평균 {s.mean():+.2f}% · +5%↑ {(s > 5).mean()*100:.1f}%")

sec("② 하한가 잠김 — 파는 날 하한가면 그 종가에 못 판다")
dn_lim = (chg <= -lim + 0.005) & pc.notna()
print(f"  하한가 마감 {int(dn_lim.sum()):,}행 ({dn_lim.mean()*100:.2f}%) · 유니버스 안 {int((dn_lim & UNI).sum()):,}")
for h in (20, 60):
    sellday = g.date.shift(-h).notna()
    sell_at_limit = pd.Series(dn_lim.values, index=K.index).groupby(K.ticker).shift(-h).fillna(False)
    m = sell_at_limit & K[f"n{h}"].notna() & UNI
    print(f"     보유 {h}일 청산일이 하한가인 신호 {int(m.sum()):,}건 "
          f"(유니버스 신호의 {m.sum()/max(int((UNI & K[f'n{h}'].notna()).sum()),1)*100:.2f}%)")

sec("③ 갭 — '다음날 시가' 로 사는 가정이 얼마나 비싼가")
s = nxt_open_gap[UNI & K.buy.notna()].dropna()
print(f"  유니버스 {len(s):,}행 · 시가 갭 중앙 {s.median():+.3f}% · 평균 {s.mean():+.3f}%")
print(f"     +3%↑ {(s > 3).mean()*100:.2f}% · +5%↑ {(s > 5).mean()*100:.2f}% · -3%↓ {(s < -3).mean()*100:.2f}%")
print("  (평균이 0 근처면 '시가 매수' 가정 자체는 편향이 없다는 뜻)")

sec("④ 주문 크기 대비 거래대금 — 종목당 300만원을 시가에 넣을 수 있나")
amt = K.amt20 * 1e8 if K.amt20.median() < 1e4 else K.amt20     # 억 단위면 원으로
ORD = 3_000_000
r = ORD / amt.replace(0, np.nan)
su = r[UNI].dropna()
print(f"  유니버스 {len(su):,}행 · 주문/20일평균거래대금 중앙 {su.median()*100:.4f}%")
print(f"     0.1%↑ {(su > 0.001).mean()*100:.2f}% · 1%↑ {(su > 0.01).mean()*100:.3f}% · 5%↑ {(su > 0.05).mean()*100:.3f}%")
flag(su.median() < 0.001, f"  중앙값 기준 주문이 하루 거래대금의 {su.median()*100:.4f}% — 시장충격 무시 가능")

sec("⑤ 시가 = 종가 — 거래가 거의 없어 기준가로 찍힌 날")
same = (K.open == K.close) & (K.volume.fillna(0) > 0)
print(f"  시가=종가 {int(same.sum()):,}행 ({same.mean()*100:.2f}%) · 유니버스 안 {int((same & UNI).sum()):,}")

sec("⑥ 수급·거래량 열이 오늘까지만 보는가 (미래참조 검사)")
print("  각 열을 하루 **앞당겨** 보고 오늘 값과 같으면 그 열은 미래를 보고 있다.")
for c in ("fw5", "fw60", "ow20", "ow60", "su1", "r16", "rw1", "vm3", "a40"):
    if c not in K.columns:
        print(f"     {c:<6} 열 없음"); continue
    fut = g[c].shift(-1)
    m = K[c].notna() & fut.notna()
    if m.sum() < 1000:
        print(f"     {c:<6} 표본 부족"); continue
    same_r = ((K[c] - fut).abs() < 1e-9)[m].mean()
    corr_f = K[c][m].corr(fut[m])
    corr_p = K[c][m].corr(g[c].shift(1)[m])
    print(f"     {c:<6} 내일값과 동일 {same_r*100:5.2f}% · 내일값 상관 {corr_f:+.3f} · 어제값 상관 {corr_p:+.3f}")
print("  (내일값 상관이 어제값 상관보다 **뚜렷이 높으면** 미래를 섞어 쓴 것)")

sec("⑦ 실제 규칙 신호에 ①~⑤ 가 얼마나 섞였나")
CONDS = [
    ("폭락반등 계열 (ret20≤-25)", (K.ret20 <= -25)),
    ("깊은이격 계열 (dev25≤-25)", (K.dev25 <= -25)),
    ("신고가 계열 (fromhi≥-5)", (K.fromhi >= -5) & (K.ret250 > 0)),
    ("업종붕괴 계열 (u≤-20)", (K.u <= -20)),
]
print(f"  {'계열':<26}{'신호':>9}{'전일 상한가':>12}{'시가갭 +3%↑':>13}{'시가=종가':>11}")
for nm, c in CONDS:
    m = (c & UNI & ~JW).fillna(False)
    n = int(m.sum())
    if n < 100: print(f"  {nm:<26}{n:>9}  (부족)"); continue
    a = int((m & up_lim).sum()); b = int((m & (nxt_open_gap > 3)).sum()); d = int((m & same).sum())
    print(f"  {nm:<26}{n:>9,}{a:>9,}({a/n*100:>4.1f}%){b:>8,}({b/n*100:>4.1f}%){d:>7,}({d/n*100:>4.1f}%)")
log("끝")
