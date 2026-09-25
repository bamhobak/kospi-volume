# -*- coding: utf-8 -*-
"""명세 여러 개를 **패널 한 번 읽고** 이어서 돌린다 — run_spec.main 을 그대로 부른다 (2026-09-25).

run_spec.py 는 명세마다 2.5~3.6GB 패널을 다시 읽는다(한 번에 1~2분). 외국 기법 수십 개를 돌리려고 만들었다.
판정·기록·명세 고정은 run_spec 과 **완전히 같다** — 패널 읽기만 가로채 재사용하고, 명세마다 덧붙은 열
(derive·_di·재료)을 지워 다음 명세가 깨끗한 패널에서 시작하게 한다. 한 시장씩만 돌린다(메모리).

    python research/run_batch.py research/specs/H0092.json research/specs/H0093.json ...
    python research/run_batch.py --from H0092 --to H0120 --market KR
"""
import gc, json, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run_spec as R

_CACHE = {}
_orig_load = R.load_market


def cached_load(mk):
    if mk not in _CACHE:
        A, uni, since = _orig_load(mk)
        _CACHE[mk] = (A, uni, since, list(A.columns))
    A, uni, since, cols = _CACHE[mk]
    extra = [c for c in A.columns if c not in cols]
    if extra:
        A.drop(columns=extra, inplace=True)
    return A, uni, since


R.load_market = cached_load


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    paths = [Path(a) for a in argv if a.endswith(".json")]
    if "--from" in argv:
        lo, hi = argv[argv.index("--from") + 1], argv[argv.index("--to") + 1]
        mk = argv[argv.index("--market") + 1] if "--market" in argv else None
        for p in sorted((ROOT / "specs").glob("H*.json")):
            if lo <= p.stem <= hi:
                if mk and json.loads(p.read_text(encoding="utf-8"))["market"] != mk:
                    continue
                paths.append(p)
    mks = {json.loads(p.read_text(encoding="utf-8"))["market"] for p in paths}
    if len(mks) > 1:
        print("❌ 한 번에 한 시장만 — --market 으로 나눌 것:", mks); return 2
    t0 = time.time(); done = []
    for i, p in enumerate(paths, 1):
        R.OUT.clear()
        print("\n" + "=" * 100 + "\n[%d/%d] %s\n" % (i, len(paths), p.name) + "=" * 100, flush=True)
        try:
            rc = R.main([str(p)] + (["--dry"] if "--dry" in argv else []))
        except Exception:
            traceback.print_exc(); rc = "에러"
        done.append((p.stem, rc))
        gc.collect()
    print("\n## 묶음 끝 — %d개 · %.0f분" % (len(done), (time.time() - t0) / 60))
    for hid, rc in done:
        print("-", hid, "" if rc == 0 else "rc=%s" % rc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
