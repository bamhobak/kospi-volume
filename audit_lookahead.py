# -*- coding: utf-8 -*-
"""**재료 데이터 미래참조 점검** (2026-09-12). 가격 감사(audit_contam.py)가 끝난 뒤 남은 구멍.

가격 오염은 성적을 희석했지만 **재료에 미래참조가 있으면 성적을 부풀린다** — 공시 전 값을
미리 알고 산 게 되기 때문이다. 규칙 조건에 들어가는 재료를 하나씩 본다.

  ① srd(공매도잔고) — KRX 는 T+2 에 공시한다. 그날 값을 그날 쓰면 이틀 미래를 본다.
  ② cr_chg20(신용잔고) — 금투협 공시 시차.
  ③ dil(희석 공시) — '공시일 <= 오늘' 인가, 미래 공시가 섞였나.
  ④ bb(자사주 취득결정) — 그날 공시를 그날 조건으로 쓰면 장중 발표분은 못 산다.
  ⑤ ins60(내부자 보고) — 보고일 기준인가 거래일 기준인가.
  ⑥ PBR/PER — KRX 일별 지표는 당일 종가 기준이라 시차 없음(확인만).
  ⑦ 부채비율 — DART 공시 가능 시점(+90일) 이후부터 적용됐나.
  ⑧ u(업종 수익률) — 같은 날 단면이라 미래참조 아님(확인만) · 업종 매핑 시점.
  ⑨ marcap/shares — 2018~2022 를 기존 패널에서 보완했는데 그게 '그때 값' 인가.
  ⑩ **직접 검정** — 각 재료를 하루·이틀 늦춰 적용하면 규칙 성적이 떨어지는가.
     미래참조가 있으면 늦출수록 성적이 크게 빠진다. 이게 가장 확실한 판별이다.

    python audit_lookahead.py
"""
import gc, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
W = 108


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)
def sec(t): print("\n" + "=" * W + f"\n{t}\n" + "=" * W)
def flag(ok, msg): print(("  ✅ " if ok else "  ❌ ") + msg)


# ── ① 각 재료의 출처와 기간 ─────────────────────────────────────────────────
sec("① 재료의 출처·기간 — 규칙이 쓰는 열이 실제로 어디서 오나")
SRC = [
    ("srd·sr20 (공매도)", "kospi.db", "daily", "short_ratio",
     "당일 장 마감 후 공시 → 다음날 시가 매수면 미래참조 아님"),
    ("cr_chg20 (신용잔고)", "kis/market.db", "credit", "loan_rmnd",
     "금투협 익영업일 공시 — 시차 확인 필요"),
    ("PBR·PER", "krx_daily.db", "fundamental", "pbr",
     "KRX 일별지표, 당일 종가 기준"),
    ("공매도 잔고(미사용?)", "krx_daily.db", "short_balance", "bal_qty",
     "T+2 공시 — 쓰인다면 미래참조"),
    ("공매도 거래량", "krx_daily.db", "short_volume", "short_vol",
     "당일 마감 후 공시"),
]
for nm, path, tb, col, note in SRC:
    p0 = BASE / "data" / path
    if not p0.exists():
        print(f"  {nm:<22} 파일 없음 ({path})"); continue
    c = sqlite3.connect(f"file:{p0}?mode=ro", uri=True, timeout=300)
    try:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({tb})")]
        if col not in cols:
            print(f"  {nm:<22} {tb}.{col} 없음 (열: {cols[:6]})"); c.close(); continue
        d = pd.read_sql(f"SELECT MIN(date) a, MAX(date) b, COUNT({col}) n FROM {tb}", c)
        print(f"  {nm:<22} {path}/{tb}.{col}")
        print(f"  {'':<22} {d.a[0]}~{d.b[0]} · 유효 {d.n[0]:,}행 — {note}")
    except Exception as e:
        print(f"  {nm:<22} {str(e)[:80]}")
    c.close()

# ── ② srd 의 2018+ 출처 추적 — 옛 운영 패널에서 보완한 값이 무엇인가 ──────────
sec("② srd 의 2018년 이후 출처 — 공매도 '거래량' 인가 '잔고' 인가")
print("  kospi.db 의 short_ratio 는 2017-12 에서 끊긴다. build_panel 은 2018+ 를")
print("  kp_ow/kq_ow(옛 운영 패널)에서 메운다. 그 값이 잔고 기반이면 T+2 미래참조다.")
_ow = BASE / "data" / "kp_ow.pkl"
if _ow.exists():
    OW = pd.read_pickle(_ow)
    print(f"  kp_ow.pkl 열: {[c for c in OW.columns if 'sr' in c.lower() or 'short' in c.lower()]}")
    sub = OW[OW.date >= "20200101"][["date", "ticker"] + [c for c in ("sr", "sr20", "srd") if c in OW.columns]]
    print("  2020+ 표본:"); print(sub.head(3).to_string(index=False))
    # 같은 날 KRX 거래량 비율·잔고 비율과 상관을 본다
    c = sqlite3.connect(f"file:{BASE}/data/krx_daily.db?mode=ro", uri=True, timeout=300)
    SV = pd.read_sql("SELECT date,ticker,vol_rto FROM short_volume WHERE date BETWEEN '20200101' AND '20200331'", c)
    SB = pd.read_sql("SELECT date,ticker,bal_rto FROM short_balance WHERE date BETWEEN '20200101' AND '20200331'", c)
    c.close()
    m = sub[(sub.date >= "20200101") & (sub.date <= "20200331")]
    if "sr" in m.columns:
        m = m.merge(SV, on=["date", "ticker"], how="left").merge(SB, on=["date", "ticker"], how="left")
        ok = m.dropna(subset=["sr"])
        print(f"  2020 1분기 대조 {len(ok):,}행")
        for c2, lbl in (("vol_rto", "거래량 비율"), ("bal_rto", "잔고 비율")):
            if c2 in ok.columns:
                z = ok.dropna(subset=[c2])
                if len(z) > 100:
                    print(f"     sr vs {lbl:<8} 상관 {z.sr.corr(z[c2]):+.3f} · 값 차이 중앙 {(z.sr - z[c2]).abs().median():.4f}")
    del OW; gc.collect()
else:
    print("  kp_ow.pkl 없음 — 보완 경로를 직접 확인할 수 없다")

# ── ④ 직접 검정: 재료를 늦춰 적용하면 성적이 떨어지는가 ──────────────────────
sec("④ 직접 검정 — 재료를 1·2·5일 늦춰 적용하면 규칙 성적이 얼마나 빠지나")
print("  미래참조가 있으면 늦출수록 크게 빠진다. 시차가 이미 반영돼 있으면 거의 그대로다.")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
UNI = (K.groupby("date").amt20.rank(pct=True) >= 0.6).fillna(False)
g = K.groupby("ticker", sort=False)
BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20,)}
ud = sorted(K.date.unique()); DI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DI).astype(np.int32)
jw = K.jw if "jw" in K.columns else pd.Series(False, index=K.index)


def dd(cond, h=20):
    X = K[(cond & UNI & ~jw).fillna(False)].dropna(subset=[f"n{h}"]).sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + h; keep.append(ix)
    d = X.loc[keep].copy()
    d["r"] = d[f"n{h}"].astype(float); d["ex"] = d.r - d.date.map(BEN[h])
    return d[d.r.notna()]


def lagcol(c, k):
    return g[c].shift(k) if k else K[c]


# 재료를 쓰는 대표 조건들 — 각 재료를 늦춰 본다
TESTS = [
    ("srd (공매도잔고 감소)", "srd", lambda s: (K.ret20 <= -25) & (s == True)),
    ("PBR ≤ 0.8 (저PBR)", "PBR", lambda s: (K.ret20 <= -10) & (s > 0) & (s <= 0.8)),
    ("dil (희석 공시 없음)", "dil", lambda s: (K.ret20 <= -25) & (~s.fillna(False))),
    ("부채비율 ≤ 200", "부채비율", lambda s: (K.ret20 <= -25) & (s.isna() | (s <= 200))),
    ("u ≤ -20 (업종 붕괴)", "u", lambda s: (K.dev25 <= -25) & (s <= -20)),
]
print(f"\n  {'조건':<24}{'지연':>5}{'n':>8}{'승률':>7}{'중앙':>8}{'초과':>8}{'초과 변화':>11}")
for nm, col, fn in TESTS:
    if col not in K.columns:
        print(f"  {nm:<24} — 열 없음"); continue
    base_ex = None
    for k in (0, 1, 2, 5):
        d = dd(fn(lagcol(col, k)))
        if len(d) < 50:
            print(f"  {nm if k==0 else '':<24}{k:>4}일{len(d):>8}  (표본 부족)"); continue
        ex = d.ex.mean()
        if k == 0: base_ex = ex
        dlt = "" if k == 0 else f"{ex-base_ex:+.2f}"
        print(f"  {nm if k==0 else '':<24}{k:>4}일{len(d):>8,}{(d.r>0).mean()*100:>6.1f}%"
              f"{d.r.median():>8.2f}{ex:>8.2f}{dlt:>11}")
    print()
log("끝")
