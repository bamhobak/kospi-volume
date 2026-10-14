# -*- coding: utf-8 -*-
"""데이 '돈 없어서 못 산' 주문을 사이트에만 기록 (2026-10-14 사용자: "돈 없어서 안 사진 것들 1주씩 살 돈 있었다 치고,
원래대로라면 체결된 것들이면 토스 실제 매매는 신경 쓰지 말고 사이트에서 1주 매수한 걸로 넣고 오늘 종가에 매도한 걸로 처리").

data/day/paper_YYYYMMDD.json(못 낸 주문 · 지정가 · 실제 KRX 시가 · fill) 중 fill 인 것만:
  buy  — 사이트 데이 보유(positions_scalp)에 1주 · 매수가 = 실제 시가 단일가 · paper=True(토스 주문 없음 표시)
  sell — 15:31 뒤 그날 KRX 종가(1분봉 마지막 봉 = 종가 단일가)로 매도 기록
    python day_paper.py buy 20261014
    python day_paper.py sell 20261014        (15:32 이후)
"""
import json, sys, time
import day_alert as D

BASE = D.OUT


def load(day):
    return [x for x in json.loads((BASE / ("paper_%s.json" % day)).read_text(encoding="utf-8")) if x.get("fill")]


def buy(day):
    X = load(day)
    def add(P):
        have = {(p.get("code"), tuple(p.get("filters") or []), p.get("date")) for p in P if p.get("paper")}
        n = 0
        for i, x in enumerate(X):
            if (x["t"], (x["rid"],), day) in have: continue
            P.append({"id": int(time.time() * 1000) + i, "code": x["t"], "name": x["name"], "date": day, "price": x["open"],
                      "qty": 1, "filters": [x["rid"]], "auto": False, "day": True, "paper": True})
            n += 1
        return n > 0
    D.scalp_update(add, "데이 가상 매수(돈 없어 못 낸 주문) %d건" % len(X))
    print("가상 매수:", [(x["name"], x["rid"], x["open"]) for x in X])


def close_px(t, day):
    rows = sorted((r for r in D.M.fetch_day("KR", t, day) if r[6] > 0), key=lambda r: r[1])
    return float(rows[-1][5]) if rows else None


def sell(day):
    X = load(day)
    px = {x["t"]: close_px(x["t"], day) for x in X}
    def mark(P):
        ch = False
        for p in P:
            if p.get("paper") and p.get("date") == day and not p.get("sell") and px.get(p.get("code")):
                p["sell"] = px[p["code"]]; p["sellDate"] = day; ch = True
        return ch
    D.scalp_update(mark, "데이 가상 매도(종가) %d건" % len(X))
    lines = ["🧾 <b>데이 가상 매매</b> %s/%s (돈 없어 못 낸 주문 — 토스 주문 없음, 사이트 기록만)" % (day[4:6], day[6:])]
    for x in X:
        c = px.get(x["t"])
        if c: lines.append("%s [%s] 1주 %s → %s원 %+.2f%%(비용 뒤)" % (x["name"], D.RNAME.get(x["rid"], x["rid"]), f"{x['open']:,.0f}", f"{c:,.0f}", (c / x["open"] - 1) * 100 - D.COST))
    D.telegram("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    cmd, day = sys.argv[1], sys.argv[2]
    if cmd == "buy": buy(day)
    elif cmd == "sell":
        while D.AT.now().strftime("%H%M") < "1532":            # 종가 단일가(15:30) 끝난 뒤
            time.sleep(30)
        sell(day)
