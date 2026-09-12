# -*- coding: utf-8 -*-
"""미국 연구 패널(us_scan.pkl) 오염 수리 (2026-09-12 감사에서 발견).

  ① **음수 수정주가** — yfinance 의 adj 계수가 음수로 나온 종목이 3개(VATE·CBIO·DEC · 5,650행).
     원주가는 멀쩡한데 수정주가가 -2,788 같은 값이라 fromhi +527%, n60 inf/-1,007% 가 나왔다.
     수익률이 -100% 아래로 갈 수는 없다 — 그 종목을 통째로 뺀다(0.03%).
  ② **거래일 공백을 넘는 선행수익** — buy 가 '다음 행' 시가라 정지 구간이 빠지면 몇 달 뒤가 된다.
     한국과 같은 병(5,764행). 공백 자리의 buy 와, 공백을 지나는 n{h} 를 결측으로.
  ③ **거래량 0 다음날 매수·거래량 0 인 날 매도** — 못 사고 못 파는 가격. 미국은 거래 없는 날이
     흔해(3.9%) 유니버스 밖이 대부분이지만 안쪽 6백여 행은 결측이 맞다.
  ④ **꼬리** — 마지막 날(2026-09-07)이 1종목뿐. 유니버스 자체가 틀어지므로 잘라낸다.

  미국은 가격제한폭이 없어 ±50% 하룻밤 점프가 진짜 사건(바이오 임상 결과)일 수 있으므로
  한국처럼 점프 자체를 결측 처리하지 **않는다**. 수정주가라 분할은 이미 반영돼 있다.

원본은 us_scan.pkl.bak 으로 남긴다. 마스터(panel_us.pkl · 11GB)는 손대지 않는다 —
다음 빌드는 us_panel.py 에 같은 가드를 넣어 두었다.

    python fix_us_scan.py [--dry]
"""
import gc, shutil, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
DRY = "--dry" in sys.argv
HZ = [5, 10, 20, 40, 60]


def log(m): print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


p = BASE / "data/us_scan.pkl"
log("us_scan.pkl 읽는 중")
df = pd.read_pickle(p)
n0 = len(df)
log(f"  {n0:,}행 · {df.ticker.nunique():,}종목")

# ① 음수·0 수정주가 종목
badt = sorted(set(df.loc[(df.close <= 0) | (df.buy <= 0), "ticker"]))
log(f"  ① 수정주가 ≤0 종목 {len(badt)}개 {badt[:8]} → 제거 {int(df.ticker.isin(badt).sum()):,}행")
df = df[~df.ticker.isin(badt)].copy(); gc.collect()

# ④ 꼬리
cnt = df.groupby("date").size(); med = cnt.rolling(60, min_periods=20).median()
thin = cnt[(cnt < med * 0.6)].index
if len(thin):
    log(f"  ④ 반쪽 수집일 {len(thin)}일 제거: {list(thin)[:5]}")
    df = df[~df.date.isin(thin)].copy()

df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
ud = sorted(df.date.unique()); DI = {d: i for i, d in enumerate(ud)}
pos = df.date.map(DI).astype(np.int64)
g = df.groupby("ticker", sort=False)
nxt = g.date.shift(-1).map(DI)
lastpos = g.date.transform("max").map(DI)

# ② ③ 매수 불가
buybad = ((nxt - pos != 1) & (pos != lastpos)) | (g.volume.shift(-1).fillna(0) <= 0)
log(f"  ②③ 매수 불가(공백·다음날 거래량 0) {int(buybad.sum()):,}행")
for h in HZ:
    col = f"n{h}"
    if col not in df.columns: continue
    sp = g.date.shift(-h).map(DI)
    endlife = (pos + h) > lastpos
    spanbad = (~endlife) & (sp - pos != h)
    sv0 = (g.volume.shift(-h).fillna(1) <= 0)
    bad = (buybad | spanbad | sv0) & df[col].notna()
    df.loc[bad, col] = np.nan
    if h in (20, 60): log(f"     n{h}: 결측 처리 {int(bad.sum()):,}행")
df.loc[buybad, "buy"] = np.nan

for c in ("n20", "n60"):
    s = df[c].dropna().astype(float)
    log(f"     {c} 남은 {len(s):,}행 · 최소 {s.min():,.0f}% · 최대 {s.max():,.0f}% · -100%↓ {int((s < -100).sum()):,} · inf {int((~np.isfinite(s)).sum()):,}")
log(f"     fromhi 최대 {df.fromhi.max():.2f} · fromlo 최소 {df.fromlo.min():.2f}")

if DRY:
    log("  (--dry) 저장하지 않음")
else:
    bak = p.with_suffix(".pkl.bak")
    if not bak.exists():
        log(f"  원본 백업 → {bak.name}"); shutil.copy2(p, bak)
    df.to_pickle(p)
    log(f"  저장 {len(df):,}행 (원본 {n0:,} · -{n0-len(df):,})")
