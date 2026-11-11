# -*- coding: utf-8 -*-
"""밤 연구 일 — [예상 하회] 조인 판 새 날 채점 (사전 등록 research/reports/prereg_a5_1112.md, 2026-11-12).

조인 판 = 상위 10%(a_err) 안에서 a_err ≥ 3%p · 시가가 어제 종가보다 2%↓. 새 날 = --from(기본 20261112) 이후만.
research/a5_tighten_1112.py 의 build()(장전 호가 녹화 × 1분봉 × 데이 snap) 재사용.
결과 → NIGHTLAB_OUT(json): metrics(days·n·mean·win·ex·pnl50·pnl100·t100) · trades/twin/mkt parquet(검토관용).
NIGHTLAB_DRY=1 이면 새 날이 없을 때 전체 날로 흐름만 확인(metrics.dry=1).
"""
import io, contextlib, json, math, os, sys
from pathlib import Path
BASE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE / "research")); sys.path.insert(0, str(BASE / "research" / "factory"))
import numpy as np, pandas as pd

FROM = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "20261112"
OUT_JSON = Path(os.environ["NIGHTLAB_OUT"]); OUT_DIR = Path(os.environ.get("NIGHTLAB_DIR") or OUT_JSON.parent)
DRY = bool(os.environ.get("NIGHTLAB_DRY"))
IMP_A, IMP_B, FILL_C = 0.143, 1.321, 3.0

import a5_tighten_1112 as A5                        # 모듈 맨 위가 stdout.reconfigure 를 불러 import 는 밖에서
with contextlib.redirect_stdout(io.StringIO()):
    A = A5.build()
A["date"] = A.date.astype(str)
new = A[A.date >= FROM]
dry = 0
if not len(new):
    if not DRY:
        OUT_JSON.write_text(json.dumps({"metrics": {"days": 0, "n": 0}, "table": "새 날 없음(%s~)" % FROM}, ensure_ascii=False), encoding="utf-8"); sys.exit(0)
    new, dry = A, 1
Z = new[(new.q >= 0.9) & (new.aerr >= 3) & (new.gap <= -2)].copy()
TW = new[(new.q <= 0.1) & (new.aerr <= -3) & (new.gap >= 2)].copy()           # 거울 판(뒤집은 짝)
mkt = new.groupby("date").ret.mean()
days = sorted(new.date.unique())


def money(T, amt):
    if not len(T): return 0.0, 0.0, 0.0
    a = T.a20.fillna(T.a20.median()); p = amt / a * 100
    loss = np.maximum(0, IMP_A + IMP_B * np.sqrt(p)); fill = 1 / (1 + FILL_C * p)
    d = (amt * fill * (T.ret - loss) / 100).groupby(T.date).sum().reindex(days).fillna(0)
    sd = d.std(ddof=1)
    return float(d.mean()), float(d.mean() / sd * math.sqrt(len(d))) if sd > 0 else 0.0, float(((T.ret - loss) * fill).sum() / fill.sum())


p50, t50, n50 = money(Z, 50e4); p100, t100, n100 = money(Z, 100e4)
ex = (Z.groupby("date").ret.mean() - mkt).dropna()
m = dict(days=len(days), n=int(len(Z)), perday=float(len(Z) / max(len(days), 1)), mean=float(Z.ret.mean()) if len(Z) else 0.0,
         win=float((Z.ret > 0).mean() * 100) if len(Z) else 0.0, ex=float(ex.mean()) if len(ex) else 0.0,
         pnl50=p50, t50=t50, net50=n50, pnl100=p100, t100=t100, net100=n100, dry=dry)
tr = OUT_DIR / "trades.parquet"; tw = OUT_DIR / "twin.parquet"; mk = OUT_DIR / "mkt.parquet"
Z.rename(columns={"t": "ticker"}).assign(amt20=lambda z: z.a20 / 1e8)[["date", "ticker", "ret", "amt20", "gap"]].to_parquet(tr, index=False)   # OUT_DIR
TW.rename(columns={"t": "ticker"}).assign(amt20=lambda z: z.a20 / 1e8)[["date", "ticker", "ret", "amt20"]].to_parquet(tw, index=False)       # OUT_DIR
mkt.rename("mkt").rename_axis("date").reset_index().to_parquet(mk, index=False)                                                              # OUT_DIR
tab = "| 날 | 종목 | 건당 | 시장 |\n|---|---|---|---|\n" + "\n".join(
    "| %s | %d | %s | %+.2f%% |" % (d, (Z.date == d).sum(), ("%+.2f%%" % Z[Z.date == d].ret.mean()) if (Z.date == d).any() else "-", mkt[d]) for d in days)
OUT_JSON.write_text(json.dumps({"metrics": m, "table": tab, "mode": "oc", "trades": str(tr), "twin": str(tw), "mkt": str(mk),
                                "sel": ["20261012", "20261111"], "conds": [{"f": "a_err", "q": True, "op": ">=", "v": 0.9}]}, ensure_ascii=False), encoding="utf-8")
print("끝", m)
