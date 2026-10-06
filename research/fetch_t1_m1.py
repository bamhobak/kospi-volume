# -*- coding: utf-8 -*-
"""T1 후보인데 1분봉이 없던 종목-일만 토스에서 받는다 (2026-10-06, 사용자 "759종목 받아서 다시 돌려줘 · 미장 멈추고 먼저").
과거 채우기(collect_m1 backfill)는 지금 상위 1,000종목 × 전 기간이라, 그 사이 작아지거나 폐지된 종목이 빠졌다.
여기서는 **후보 날만**(종목당 하루~몇 날) 받아 data/m1/KR/bf/{종목}.parquet 에 더한다 — 나중 backfill 은 있는 날을 건너뛴다.
폐지 종목은 토스에 1분봉이 없을 수 있다 → 받은/못 받은 수를 적는다.
    python research/fetch_t1_m1.py
"""
import json, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import collect_m1 as M
import t1_exit as T


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    C = T.t1()
    bf = BASE / "data" / "m1" / "KR" / "bf"
    need = []
    for t, g in C.groupby("ticker"):
        f = bf / (t + ".parquet")
        have = set()
        if f.exists():
            D = pd.read_parquet(f, columns=["ts"])
            have = set(pd.to_datetime(D.ts, unit="s", utc=True).dt.tz_convert("Asia/Seoul").dt.strftime("%Y%m%d"))
        for d in sorted(set(g.date) - have): need.append((t, d))
    print("받을 종목-일 %d · 종목 %d" % (len(need), len({t for t, _ in need})), flush=True)
    got, miss, done = {}, [], 0
    with ThreadPoolExecutor(M.WORKERS) as ex:
        for (t, d), rows in zip(need, ex.map(lambda x: M.fetch_day("KR", x[0], x[1]), need)):
            done += 1
            if len(rows) >= 200: got.setdefault(t, []).extend(rows)
            else: miss.append((t, d, len(rows)))
            if done % 100 == 0: print("  %d/%d · 받음 %d · 없음 %d · %.1f분" % (done, len(need), sum(len(v) for v in got.values()) and done - len(miss), len(miss), (time.time() - t0) / 60), flush=True)
    for t, rows in got.items():
        f = bf / (t + ".parquet"); D = M.frame(rows)
        if f.exists(): D = pd.concat([pd.read_parquet(f), D]).drop_duplicates(["t", "ts"]).sort_values("ts")
        D.to_parquet(f, index=False, compression="zstd")
    (ROOT / "cache" / "fetch_t1_m1_miss.json").write_text(json.dumps(miss), encoding="utf-8")
    print("끝 — 받은 종목-일 %d · 종목 %d · 못 받은 종목-일 %d(종목 %d) · %.1f분" % (
        len(need) - len(miss), len(got), len(miss), len({t for t, _, _ in miss}), (time.time() - t0) / 60), flush=True)


if __name__ == "__main__":
    main()
