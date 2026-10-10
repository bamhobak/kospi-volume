# -*- coding: utf-8 -*-
"""토스 통합 일봉(KRX+NXT) + NXT 거래 여부 받기 (2026-10-11 실측 H0316·H0319 용).

토스 일봉은 NXT 장전(08:00~)·장후(~20:00)가 섞인 통합 봉이라, KRX 종가(kr_scan)와 비교하면
NXT 장후에 얼마나 움직였는지(장후 그림자), 시가 비교로 NXT 장전 움직임을 알 수 있다.
    python research/nxt_fetch.py        → research/cache/toss_daily_kr.pkl · toss_nxt_kr.json
"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / "factory"))
import pandas as pd
import common as C
from concurrent.futures import ThreadPoolExecutor

OUT = C.CACHE / "toss_daily_kr.pkl"
NXT = C.CACHE / "toss_nxt_kr.json"
PAGES = 3                                                    # 200봉 × 3 ≈ 2024-11 까지 (NXT 개장 2025-03-04 전 몇 달 포함)


def main():
    M = C.toss(9.0)
    syms = M.universe("KR")
    info = {}
    for i in range(0, len(syms), 50):
        r = M.get("/api/v1/stocks", symbols=",".join(syms[i:i + 50])) or []
        for x in r:
            d = x.get("koreanMarketDetail") or {}
            info[x["symbol"]] = {"nxt": bool(d.get("nxtSupported")), "market": x.get("market"), "list": x.get("listDate")}
    NXT.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    print("NXT 거래 종목 %d / %d" % (sum(v["nxt"] for v in info.values()), len(info)), flush=True)

    def one(s):
        rows, before = [], None
        for k in range(PAGES):
            q = dict(symbol=s, interval="1d", count=200)
            if before: q["before"] = before
            r = M.get("/api/v1/candles", **q) or {}
            for x in r.get("candles") or []:
                rows.append((s, x["timestamp"][:10].replace("-", ""), float(x["openPrice"]), float(x["highPrice"]),
                             float(x["lowPrice"]), float(x["closePrice"]), float(x["volume"])))
            before = r.get("nextBefore")
            if not before: break
        return rows

    t0 = time.time(); out = []
    with C.Busy("research"), ThreadPoolExecutor(6) as ex:
        for i, rows in enumerate(ex.map(one, [s for s in syms if s in info]), 1):
            out += rows
            if i % 300 == 0: print("  %d종목 · %.1f분" % (i, (time.time() - t0) / 60), flush=True)
    D = pd.DataFrame(out, columns=["ticker", "date", "to", "th", "tl", "tc", "tv"]).drop_duplicates(["ticker", "date"])
    D.to_pickle(OUT)
    print("끝: %d줄 %s~%s · %.1f분" % (len(D), D.date.min(), D.date.max(), (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
