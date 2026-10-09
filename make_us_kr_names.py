# -*- coding: utf-8 -*-
"""미장 종목 한글 이름표 → assets/us_kr.json (2026-10-10 사용자: "미장 종목명 토스에서 한글 이름으로 — Meta Platforms Inc. → 메타").

토스 Open API /api/v1/stocks 의 name 이 한글(META → 메타 · PARR → 파 퍼시픽 홀딩스). 토스는 허용 IP 가 이 PC 뿐이라
Actions(미장 표 수집)에서는 못 부른다 → 이 PC 에서 이름표만 만들어 사이트 자산으로 올리고, 화면이 미장 표를 읽을 때 바꿔 끼운다.
새로 상장한 종목은 다음에 이걸 다시 돌릴 때까지 영어 이름 그대로(공장 저녁 작업이 7일마다 다시 만든다).
    python make_us_kr_names.py
"""
import json, re, sys, time
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
OUT = BASE / "assets" / "us_kr.json"


def main():
    import collect_m1 as M
    U = [s for s in M.universe("US") if s not in ("SPY", "QQQ", "IWM")]
    out, t0 = {}, time.time()
    for i in range(0, len(U), 100):
        for x in M.get("/api/v1/stocks", symbols=",".join(U[i:i + 100])) or []:
            n = (x.get("name") or "").strip()
            if n and re.search(r"[가-힣]", n): out[x["symbol"]] = n
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    old.update(out)
    OUT.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("미장 한글 이름 %d / %d종목 · %.0f초 → %s" % (len(out), len(U), time.time() - t0, OUT))
    return len(out)


if __name__ == "__main__":
    main()
