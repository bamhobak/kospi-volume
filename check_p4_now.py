# -*- coding: utf-8 -*-
"""보유 종목 진행 + [업종붕괴 이탈] 이번 국면(2026-07~08) 실제 작동 분석.

물음 두 가지:
 ① 지금 들고 있는 HD현대중공업은 어디쯤 왔나 — 경과 거래일·수익률·손절선·예정 매도일
 ② 이번 국면 209건에서 5일 보유와 -15% 손절이 실제로 어떻게 굴렀나
    (손절 발동률·발동 건의 성적·손절이 없었다면 어땠을지)
"""
import io, os, sys, json, re, urllib.request, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
BASE = Path(__file__).parent

# ── ① 보유 종목
sb = (BASE/"assets"/"sb.js").read_text(encoding="utf-8")
URL = re.search(r"url:'([^']+)'", sb).group(1); KEY = re.search(r"key:'([^']+)'", sb).group(1)
PIN = re.search(r"DEFAULT_PIN='([^']+)'", (BASE/"index.html").read_text(encoding="utf-8")).group(1)
r = urllib.request.Request(f"{URL}/rest/v1/rpc/kospi_state_get", data=json.dumps({"p_pin": PIN}).encode(),
    headers={"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
pos = (json.loads(urllib.request.urlopen(r, timeout=40).read().decode()) or {}).get("positions") or []
HOLD = {"P1":40,"P2":10,"P3":20,"P4":5,"P5":10,"P6":5,"P7":60,"D1":20,"D2":40}
STOP = {"P1":0.15,"P4":0.15,"P6":0.10}
NM = {"P1":"조용한 신고가","P2":"조정매집","P3":"폭락반등","P4":"업종붕괴 이탈","P5":"자사주 낙폭",
      "P6":"깊은 이격","P7":"외인 매집","D1":"낙폭과대","D2":"저PBR 낙폭"}
print("① 보유 종목 진행")
for p in pos:
    rid = (p.get("filters") or ["?"])[0]; hold = HOLD.get(rid, 0); stop = STOP.get(rid)
    px = fdr.DataReader(p["code"], "2026-08-20")
    px.index = px.index.strftime("%Y%m%d")
    buyd = p["date"]; after = px[px.index >= buyd]
    cur = float(px.Close.iloc[-1]); last = px.index[-1]
    elapsed = len(after) - 1                      # 매수일 당일은 0일차
    ret = (cur/p["price"]-1)*100
    stopline = p["price"]*(1-stop) if stop else None
    low = float(after.Low.min()) if len(after) else float("nan")
    print(f"  {p['name']}({p['code']}) · [{NM.get(rid,rid)}] {hold}일 보유"
          + (f" · 손절 -{stop*100:.0f}%" if stop else " · 손절 없음"))
    print(f"    매수 {buyd} {p['price']:,}원 × {p['qty']}주 = {p['price']*p['qty']:,}원")
    print(f"    현재 {last} {cur:,.0f}원 → {ret:+.2f}%  ({(cur-p['price'])*p['qty']:+,.0f}원)")
    print(f"    경과 {elapsed}거래일 / {hold}일 → 남은 {max(hold-elapsed,0)}거래일")
    if stopline:
        print(f"    손절선 {stopline:,.0f}원 · 보유 중 최저 {low:,.0f}원 → "
              + ("⚠ 손절선 닿음" if low <= stopline else f"여유 {(low/stopline-1)*100:+.1f}%"))
    if elapsed >= hold: print(f"    ⚠ 보유기간 지남 — 매도 시점")

# ── ② 이번 국면 209건
print("\n② [업종붕괴 이탈] 2026-07~08 국면 · 5일 보유 · 손절 -15% 실측")
src = (BASE/"portfolio.py").read_text(encoding="utf-8"); ns = {"__file__": str(BASE/"portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
K, hold, stop, pct, mx, cond = ns["RULES"]["P4"]
g = K.groupby("ticker", sort=False)
low5 = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
hit = (low5 <= K.buy*(1-stop)).fillna(False)
r_stop = np.where(hit, -stop*100-K.cost, K[f"n{hold}"])
m = cond.fillna(False)
X = K[m].copy(); X["_r"] = r_stop[m.values]; X["_nostop"] = K.loc[m, f"n{hold}"].values; X["_hit"] = hit[m].values
X = X.dropna(subset=["_r"])
di = {x:i for i,x in enumerate(sorted(K.date.unique()))}
X["di"] = X.date.map(di); X = X.sort_values("di")
keep, last = [], {}
for t,i,ix in zip(X.ticker.values, X.di.values, X.index):
    if last.get(t,-10**9) >= i: continue
    last[t] = i+hold; keep.append(ix)
X = X.loc[keep]
for nm, z in (("2026-07~08 이번 국면", X[X.date>="20260701"]),
              ("2020-03~04 코로나", X[(X.date>="20200301")&(X.date<="20200430")]),
              ("기준 2016~ 전체", X[X.date>="20160101"])):
    if not len(z): continue
    print(f"  [{nm}] {len(z)}건")
    print(f"    손절 적용: 평균 {z._r.mean():+.2f}% · 중앙 {z._r.median():+.2f}% · 승률 {(z._r>0).mean()*100:.0f}% · 최악 {z._r.min():+.1f}%")
    print(f"    손절 없었다면: 평균 {z._nostop.mean():+.2f}% · 최악 {z._nostop.min():+.1f}%"
          f"  → 손절이 {'지켰다' if z._r.mean()>=z._nostop.mean() else '깎았다'} ({z._r.mean()-z._nostop.mean():+.2f}%p)")
    print(f"    손절 발동 {int(z._hit.sum())}건({z._hit.mean()*100:.0f}%)"
          + (f" · 그 건들 손절 없었으면 평균 {z.loc[z._hit,'_nostop'].mean():+.1f}%" if z._hit.any() else ""))
