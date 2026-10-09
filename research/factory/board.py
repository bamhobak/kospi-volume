# -*- coding: utf-8 -*-
"""사이트 '규칙 후보' 페이지 데이터 (2026-10-10 사용자: "새 페이지 하나 만들어서 규칙 후보군 한 번에 볼 수 있게, 언제든 볼 수 있게").

검토 대기·채택 명세의 카드 숫자(card.data) + 형제 묶음 + 못 옮긴 조건 모음 + 공장 현황 → Supabase 상태 '__factory__'.
사이트 assets/factory.html 이 읽는다(데이 후보 '__day__' 와 같은 방식). 밤 작업 끝·채택/조정 뒤에 부른다.
    python research/factory/run.py board
"""
import re, time, json
import common as C


def supa_set(pin, data):
    import requests
    js = (C.BASE / "assets" / "sb.js").read_text(encoding="utf-8")
    url = re.search(r"url:'([^']+)'", js).group(1); key = re.search(r"key:'([^']+)'", js).group(1)
    H = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(f"{url}/rest/v1/rpc/kospi_state_set", headers=H, json={"p_pin": pin, "p_data": data}, timeout=60)
    r.raise_for_status()


def build():
    import lab, card, needs, harvest
    from verdict import trial_count
    L = lab.load()
    act = [x for x in L if x.get("status") in ("review", "adopted")]
    cands = []
    for x in act:
        d = card.data(x, L)
        card.make(x, d)
        cands.append(d)
    order = {"adopted": 0, "review": 1}
    cands.sort(key=lambda d: (order.get(d["status"], 9), -((d["res"].get("va") or {}).get("mean") or 0)))
    by = {}
    for x in L: by[x.get("status")] = by.get(x.get("status"), 0) + 1
    return {"updated": time.strftime("%Y-%m-%d %H:%M"), "cands": cands,
            "counts": by, "trials": trial_count("factory"), "usage": harvest.usage_report()[0],
            "needs": needs.rows(), "shadow": [{"id": x["id"], "desc": x.get("desc"), "fwd": x.get("fwd") or {}} for x in L if x.get("status") in ("shadow", "propose")]}


def publish():
    D = build()
    supa_set("__factory__", D)
    C.jsave(C.DATA / "board.json", D)
    C.log("후보 페이지 갱신: 후보 %d" % len(D["cands"]))
    return D
