# -*- coding: utf-8 -*-
"""**가설 등록부** — 아이디어마다 한 줄. 같은 원리를 이름만 바꿔 다시 시험하는 걸 막는다 (2026-09-19).

왜 필요한가: 지금까지는 아이디어 하나에 스크립트 하나였다(파이썬 파일 684개). 기각 기록은 기억 파일에
흩어져 있어서, 같은 돌파 매매가 이름만 바뀌어 들어오면 기계가 알아채지 못했다. 여기 한 파일에
출처·원리·필요 데이터·상태·결과·기각 이유를 쌓고, 새 가설은 **시험 전에** 여기서 먼저 찾는다.

파일: research/hypotheses.jsonl (한 줄 = 한 가설, JSON)

  번호 id · 이름 name · 계열 family(아래 FAMILIES) · 시장 market(KR/US/both) · 출처 source ·
  원리 mechanism · 필요 데이터 data · 상태 status(아래 STATUS) · 결과 result · 기각 이유 reason ·
  시험 주제 trials(data/trials.json 의 by_topic 키) · 스크립트 scripts · 기억 memory · 날짜 date

⚠ 이 저장소는 **공개**다. 원리·결과는 적되 사이트 규칙의 정확한 문턱값 같은 건 portfolio.py 에 이미
   있으니 여기 반복하지 않는다. research/** 커밋은 사이트 빌드를 안 탄다(collect.yml paths-ignore).

    python research/registry.py find 돌파 거래량          # 원리가 같은 기록이 있나 (0단계)
    python research/registry.py find --family 눌림
    python research/registry.py show H0042
    python research/registry.py check                     # 형식 점검 + 등록부에 없는 시험 주제
    python research/registry.py stats
"""
import json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REG = ROOT / "hypotheses.jsonl"
TRIALS = ROOT.parent / "data" / "trials.json"

STATUS = ["보류", "시험중", "기각", "그림자", "후보", "부분채택", "채택", "기록"]
FAMILIES = ["돌파", "눌림", "추세추종", "낙폭반전", "급등추격", "박스권", "수급", "외인", "신용", "공매도",
            "대차", "프로그램", "내부자", "자사주", "실적", "재무·밸류", "이벤트", "캘린더", "캔들", "이평",
            "보조지표", "패턴", "거래량", "변동성", "업종", "국면", "유동성", "청산·손절", "비중·계좌", "조율"]
FIELDS = ["id", "name", "family", "market", "source", "mechanism", "data", "status", "result", "reason",
          "trials", "scripts", "memory", "date"]


def load():
    if not REG.exists():
        return []
    return [json.loads(x) for x in REG.read_text(encoding="utf-8").splitlines() if x.strip()]


def save(H):
    REG.write_text("\n".join(json.dumps({k: x.get(k, "" if k not in ("family", "trials", "scripts") else [])
                                          for k in FIELDS}, ensure_ascii=False) for x in H) + "\n",
                   encoding="utf-8")


def next_id(H):
    return "H%04d" % (max([int(x["id"][1:]) for x in H] or [0]) + 1)


def add(**kw):
    """새 가설을 등록하고 번호를 돌려준다. 시험 **전에** 부른다 — 명세가 고정되는 순간이다."""
    H = load()
    bad = [f for f in kw.get("family", []) if f not in FAMILIES]
    if bad:
        raise ValueError("모르는 계열 %s — FAMILIES 에서 고를 것" % bad)
    st = kw.get("status", "시험중")
    if st not in STATUS:
        raise ValueError("모르는 상태 %s" % st)
    x = {k: kw.get(k, [] if k in ("family", "trials", "scripts") else "") for k in FIELDS}
    x["id"] = next_id(H); x["status"] = st
    H.append(x); save(H)
    return x["id"]


def update(hid, **kw):
    H = load()
    for x in H:
        if x["id"] == hid:
            if "status" in kw and kw["status"] not in STATUS:
                raise ValueError("모르는 상태 %s" % kw["status"])
            x.update(kw); save(H); return x
    raise KeyError(hid)


def _toks(s):
    return {t for t in re.split(r"[\s·,()\[\]/+→\-~%·'\"]+", str(s)) if len(t) >= 2}


def find(words=(), family=None, market=None, top=10):
    """단어·계열이 겹치는 기록을 점수순으로. 점수 = 계열 일치×3 + 단어 일치."""
    H = load()
    q = set()
    for w in words:
        q |= _toks(w)
    out = []
    for x in H:
        s = 0
        if family:
            fam = [family] if isinstance(family, str) else family
            s += 3 * len(set(fam) & set(x["family"]))
        if market and x["market"] not in (market, "both"):
            continue
        blob = " ".join(str(x.get(k, "")) for k in ("name", "mechanism", "result", "reason", "source", "data"))
        blob += " " + " ".join(x["family"])
        s += sum(1 for t in q if t in blob)
        if s:
            out.append((s, x))
    out.sort(key=lambda z: -z[0])
    return out[:top]


def check():
    H = load()
    probs = []
    ids = Counter(x["id"] for x in H)
    probs += ["번호 중복 %s" % k for k, v in ids.items() if v > 1]
    for x in H:
        if x["status"] not in STATUS:
            probs.append("%s 상태 '%s'" % (x["id"], x["status"]))
        for f in x["family"]:
            if f not in FAMILIES:
                probs.append("%s 계열 '%s'" % (x["id"], f))
        if x["status"] == "기각" and not (x.get("result") or x.get("reason")):
            probs.append("%s 기각인데 결과·이유가 없다" % x["id"])
    topics = set()
    if TRIALS.exists():
        topics = set(json.loads(TRIALS.read_text(encoding="utf-8")).get("by_topic", {}))
    mapped = {t for x in H for t in x["trials"]}
    return probs, sorted(topics - mapped), sorted(mapped - topics)


def _line(x):
    return "%s  %-6s %-4s %-44s %s" % (x["id"], x["status"], x["market"], x["name"][:44], x["result"][:70])


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return
    cmd, rest = argv[0], argv[1:]
    if cmd == "find":
        fam = None; mk = None; words = []
        it = iter(rest)
        for a in it:
            if a == "--family": fam = next(it)
            elif a == "--market": mk = next(it)
            else: words.append(a)
        res = find(words, fam, mk)
        if not res:
            print("  겹치는 기록 없음 — 새 가설로 등록할 수 있다")
        for s, x in res:
            print("  [%2d] %s" % (s, _line(x)))
            if x.get("reason"):
                print("        이유: %s" % x["reason"])
    elif cmd == "show":
        for x in load():
            if x["id"] == rest[0]:
                for k in FIELDS:
                    print("  %-9s %s" % (k, x.get(k)))
    elif cmd == "check":
        probs, unmapped, ghost = check()
        print("  형식 문제 %d건" % len(probs))
        for p in probs: print("   -", p)
        print("  등록부에 안 걸린 시험 주제 %d개: %s" % (len(unmapped), ", ".join(unmapped) or "-"))
        print("  trials.json 에 없는 주제 %d개: %s" % (len(ghost), ", ".join(ghost) or "-"))
    elif cmd == "stats":
        H = load()
        print("  가설 %d개" % len(H))
        print("  상태: " + " · ".join("%s %d" % kv for kv in Counter(x["status"] for x in H).most_common()))
        fam = Counter(f for x in H for f in x["family"])
        print("  계열: " + " · ".join("%s %d" % kv for kv in fam.most_common()))
        for f, _ in fam.most_common():
            z = [x for x in H if f in x["family"]]
            a = sum(1 for x in z if x["status"] in ("채택", "부분채택"))
            r = sum(1 for x in z if x["status"] == "기각")
            print("    %-6s 채택 %2d · 기각 %2d" % (f, a, r))
    else:
        print("모르는 명령:", cmd)


if __name__ == "__main__":
    main(sys.argv[1:])
