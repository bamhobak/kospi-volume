# -*- coding: utf-8 -*-
"""규칙 공장 지휘자 — 예약 작업이 이 파일을 시간대별로 부른다(2026-10-08).

  python research/factory/run.py morning     07:50  미장 밤사이 → 국장 아침 전이표 · 장전 동시호가 녹화(~09:00)
  python research/factory/run.py close       15:18  마감 동시호가 녹화(~15:31)
  python research/factory/run.py evening     16:45  1분봉 일봉 → 정답지 역추적 · 그림자 전진 성적 → 텔레그램
  python research/factory/run.py night       01:30  AI 수집 일꾼 · 정답지 후보 · 진화기 · 깔때기(+뒤집기 짝) → 보고서·텔레그램
  python research/factory/run.py usage              클로드 크레딧 이달 사용·한 달 예상
  python research/factory/run.py status             등록부 요약
  python research/factory/run.py add <명세.json>    손으로 명세 넣기(바로 판정)
국장 휴장일엔 morning·close·evening 이 알아서 쉰다. 실패하면 텔레그램 한 줄.
"""
import sys, time, json, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C


def morning():
    day, prev = C.kr_session()
    if not day:
        C.log("국장 휴장 — 아침 쉼"); return
    import transfer, auction
    try:
        transfer.morning(day)
    except Exception as ex:
        C.log("전이표 실패:", repr(ex)[:300]); C.tg("⚠ 공장 전이표 실패: %s" % str(ex)[:200])
    auction.morning(day)


def close():
    day, prev = C.kr_session()
    if not day:
        C.log("국장 휴장 — 마감 녹화 쉼"); return
    import auction
    auction.close(day)


def evening():
    day, prev = C.kr_session()
    if not day:
        C.log("국장 휴장 — 저녁 쉼"); return
    import live, answer, fshadow
    with C.Busy("fac"):
        A = live.update()
        if day not in set(A.date.unique()):
            C.log("오늘 1분봉 일봉 없음(매일 수집 전?) — 저녁 건너뜀"); C.tg("⚠ 공장 저녁: 오늘 1분봉 없음 — 정답지 못 만듦"); return
        names = live.names()
        U = live.frame(days=[day], A=A)
        msg = answer.daily(U, day, names)
        N = fshadow.daily(A, day)
    lines = ["🧾 <b>공장 저녁</b> %s/%s 정답지" % (day[4:6], day[6:])] + msg
    if N is not None and len(N):
        g = N.groupby("id").ret.agg(["size", "mean"])
        lines.append("그림자 오늘: " + " · ".join("%s %d건 %+.2f%%" % (i, r["size"], r["mean"]) for i, r in g.iterrows()))
    C.tg("\n".join(lines))


def night():
    import lab, answer, evolve, harvest
    from verdict import trial_count
    t0 = time.time()
    rep = ["# 규칙 공장 밤 보고 · %s" % time.strftime("%Y-%m-%d %H:%M"), ""]
    L = lab.load()
    added = []
    # ① AI 수집 일꾼
    try:
        specs, hrep = harvest.run()
        for sp in specs: added.append(lab.add(sp, L))
        rep += ["## AI 수집 일꾼(유튜브)", ""] + (hrep or ["새 기법 영상 없음"]) + [""]
    except Exception as ex:
        rep += ["## AI 수집 일꾼 실패", "", repr(ex)[:300], ""]; C.log(traceback.format_exc()[-800:])
    # ② 정답지 후보
    try:
        cs = answer.candidates()
        for f, ic, t, n, hi, sp in cs: added.append(lab.add(sp, L))
        rep += ["## 정답지 후보(최근 %d거래일↑ 꾸준한 재료)" % answer.MIN_DAYS, ""]
        rep += ["- %s: ic %+.3f · t %.1f · %d일 · 과거 ic %s" % (f, ic, t, n, "없음" if hi != hi else "%+.3f" % hi) for f, ic, t, n, hi, sp in cs] or ["- 아직 없음(정답지가 20거래일 쌓여야)"]
        rep.append("")
    except Exception as ex:
        rep += ["## 정답지 후보 실패", "", repr(ex)[:300], ""]
    # ③ 진화기
    try:
        prom, best, ev = evolve.run()
        for sp, f, n in prom: added.append(lab.add(sp, L))
        rep += ["## 규칙 진화기 — %d개 평가(학습 2016~22 만 봄)" % ev, "", "| 적합도(하루 t) | 학습 건수 | 방식 | 조건 |", "|---|---|---|---|"]
        rep += ["| %.2f | %s | %s | %s |" % (f, f"{n:,}", ind["mode"], " & ".join("%s %s %.2f" % tuple(c) for c in ind["conds"])) for f, n, ind in best[:8]]
        rep.append("")
    except Exception as ex:
        rep += ["## 진화기 실패", "", repr(ex)[:300], ""]; C.log(traceback.format_exc()[-800:])
    # ④ 깔때기 (+ 뒤집기 짝은 add 가 같이 세운다)
    done = lab.process(L)
    lab.save(L)
    rep += ["## 깔때기 — 오늘 판정 %d개 (공장 누적 시험 %s)" % (len(done), f"{trial_count('factory'):,}"), "",
            "| id | 출처 | 명세 | 결과 | 학습 | 검증 | 이유 |", "|---|---|---|---|---|---|---|"]
    for x in done:
        r = x.get("res") or {}
        rep.append("| %s | %s | %s | %s | %s | %s | %s |" % (x["id"], x.get("origin"), (x.get("desc") or "")[:90], lab.STAGE.get(x.get("stage"), x.get("stage")), lab.fmt_s(r.get("tr")), lab.fmt_s(r.get("va")), (x.get("why") or "통과 → 그림자")[:80]))
    sh = [x for x in L if x.get("status") in ("shadow", "propose")]
    rep += ["", "## 그림자 중 %d개" % len(sh), ""]
    rep += ["- %s %s · %s · 앞으로 %s" % (x["id"], x.get("status"), (x.get("desc") or "")[:80], json.dumps(x.get("fwd") or {}, ensure_ascii=False)) for x in sh] or ["- 없음"]
    rep += ["", "## 클로드 크레딧", ""] + ["- " + s for s in harvest.usage_report()]
    rep += ["", "(%.1f분)" % ((time.time() - t0) / 60)]
    f = C.REP / ("%s.md" % time.strftime("%Y%m%d")); f.write_text("\n".join(rep) + "\n", encoding="utf-8")
    passed = [x for x in done if x.get("status") == "shadow"]
    by = {}
    for x in done: by[x.get("origin")] = by.get(x.get("origin"), 0) + 1
    tg = ["🏭 <b>공장 밤</b> %s — 판정 %d개(%s)" % (time.strftime("%m/%d"), len(done), " · ".join("%s %d" % kv for kv in by.items())),
          "검증까지 통과 → 그림자: %d개%s" % (len(passed), (" — " + ", ".join("%s %s" % (x["id"], (x.get("desc") or "")[:50]) for x in passed[:3])) if passed else ""),
          "그림자 지켜보는 중 %d개 · 공장 누적 시험 %s" % (len(sh), f"{trial_count('factory'):,}"),
          harvest.usage_report()[0], "보고서: research/reports/factory/%s" % f.name]
    C.tg("\n".join(tg))
    C.log("밤 끝 — 판정 %d · 그림자 %d · %.1f분" % (len(done), len(sh), (time.time() - t0) / 60))


def status():
    import lab, collections
    L = lab.load()
    c = collections.Counter((x.get("origin"), x.get("status")) for x in L)
    for k, v in sorted(c.items(), key=lambda kv: str(kv[0])): print(k, v)
    for x in L:
        if x.get("status") in ("shadow", "propose"): print(x["id"], x["status"], x.get("desc"), x.get("fwd"))


def add_file(p):
    import lab
    sp = json.loads(Path(p).read_text(encoding="utf-8"))
    L = lab.load()
    for s in (sp if isinstance(sp, list) else [sp]): lab.add(dict(s, origin=s.get("origin", "manual")), L)
    done = lab.process(L); lab.save(L)
    for x in done: print(x["id"], x["status"], x.get("stage"), x.get("desc"), "|", lab.fmt_s((x.get("res") or {}).get("tr")), "|", lab.fmt_s((x.get("res") or {}).get("va")), "|", x.get("why"))


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""
    try:
        if cmd == "morning": morning()
        elif cmd == "close": close()
        elif cmd == "evening": evening()
        elif cmd == "night": night()
        elif cmd == "usage": print("\n".join(__import__("harvest").usage_report()))
        elif cmd == "status": status()
        elif cmd == "add": add_file(a[1])
        else: print(__doc__)
    except Exception as ex:
        C.log("실패:", cmd, traceback.format_exc()[-1500:])
        C.tg("⚠ 공장 %s 실패: %s" % (cmd, str(ex)[:300]))
        raise
