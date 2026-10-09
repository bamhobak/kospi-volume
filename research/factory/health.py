# -*- coding: utf-8 -*-
"""공장 점검기 (2026-10-08 사용자: "잘한다고 가정하지 말고 … 자체적으로 잘 돌아가고 있는지 매일 체크해").

매일 09:20(예약 \\BamhobakFactory\\Check) — 지난 24시간 공장이 '돌았나'가 아니라 '맞게 돌았나'를 본다.
  A 예약 작업    4개(Morning·Close·Evening·Night) 마지막 실행 시각·결과 코드
  B 밤 작업      오늘 밤 보고서 · 수집 일꾼이 실제로 읽었나(이틀 연속 0이면 검색·자막 막힘) · 진화기 평가 수 ·
                 깔때기에 묵은 줄·오류 · 크레딧 한 달 예상이 한도를 넘나
  C 오늘 아침    (거래일) 전이표 파일(날짜·밤·종목 수) · 장전 호가 녹화(횟수·종목 수·마지막 시각) · NXT 체결가 녹화
  D 전 거래일    마감 녹화 · 1분봉 일봉 · 정답지 기록 · **숫자 점검**(유니버스 크기, 재료 빈칸 비율,
                 장전 예상 갭 - 실제 갭 오차, 전이표 예상 갭과 실제 갭 상관)
  E 기대는 자료  투자자 수급(flow11) 날짜 · 미장 일봉 날짜 · 남은 .busy_* 표시(남아 있으면 1분봉 과거 채우기가 영원히 쉰다 → 지운다) · 디스크
텔레그램: 문제 있을 때만(🚨/⚠ 목록) + 월요일에 지난 7일 한 줄(조용한 게 '죽어서 조용한' 것과 구별되게).
기록: data/factory/health/YYYYMMDD.md · health.csv. 밤 작업은 어제 점검 기록이 없으면 알린다(점검기 자체 감시).
"""
import json, os, re, shutil, sqlite3, subprocess, time, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd

import common as C

HD = C.DATA / "health"; HD.mkdir(exist_ok=True)
HCSV = HD / "health.csv"
TASKS = ["Morning", "Close", "Evening", "Night"]
REC_START = "20261012"        # 장전·마감 녹화·전이표 첫 실전일(10-09 한글날 휴장) — 그 전 날짜는 녹화 점검 안 함
FAC_START = "20261008"        # 공장 저녁 작업(정답지·매일 일봉) 첫날 — 그 전 날짜는 저녁 점검 안 함
PS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")   # 이름으로 부르면 이 PC PATH 함정(%SystemRoot% 미확장)에 걸린다


def calendar():
    """(오늘 YYYYMMDD, 오늘 거래일?, 직전 거래일)."""
    M = C.toss(5)
    cal = M.get("/api/v1/market-calendar/KR") or {}
    today = C.now().strftime("%Y%m%d")
    trading = bool((cal.get("today") or {}).get("integrated"))
    prev = (cal.get("previousBusinessDay") or {}).get("date", "").replace("-", "")
    return today, trading, prev


def task_info():
    ps = ("Get-ScheduledTask -TaskPath '\\BamhobakFactory\\' | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{n=$_.TaskName; last=$i.LastRunTime.ToString('yyyy-MM-dd HH:mm'); res=$i.LastTaskResult; nxt=$i.NextRunTime.ToString('yyyy-MM-dd HH:mm'); st=[string]$_.State} } | ConvertTo-Json")
    try:
        out = subprocess.run([PS, "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                             creationflags=0x08000000).stdout.decode("utf-8", "replace")
        j = json.loads(out)
        return {x["n"]: x for x in (j if isinstance(j, list) else [j])}
    except Exception as ex:
        return {"_err": str(ex)[:200]}


def check():
    P = []                                    # (등급, 글)
    ok = []                                   # 정상 확인한 것(보고서용)
    bad = lambda lv, s: P.append((lv, s))
    today, trading, prev = calendar()
    now = C.now()

    # ── A 예약 작업 ────────────────────────────────────────────────
    T = task_info()
    if "_err" in T:
        bad("⚠", "예약 작업 상태를 못 읽음: %s" % T["_err"])
    for n in (TASKS + ["Check"]) if "_err" not in T else []:
        x = T.get(n)
        if not x:
            bad("🚨", "예약 작업 %s 가 없음(지워졌나? 아직 등록 안 함?)" % n)
            continue
        if n == "Check": continue
        try: last = dt.datetime.strptime(x["last"], "%Y-%m-%d %H:%M").replace(tzinfo=C.KST)
        except Exception: last = None
        if last and last.year < 2001:                                  # 아직 한 번도 안 돎 — 첫 실행 전이면 정상
            ok.append("작업 %s 첫 실행 전(다음 %s)" % (n, x.get("nxt", "")[5:])); continue
        if not last or (now - last).total_seconds() > 27 * 3600:
            bad("🚨", "예약 작업 %s 가 27시간 넘게 안 돎(마지막 %s) — PC 꺼짐·작업 고장?" % (n, x.get("last")))
        elif int(x.get("res") or 0) not in (0, 267009):          # 267009 = 지금 실행 중
            bad("⚠", "예약 작업 %s 마지막 결과 코드 %s(0 이 정상) — %s" % (n, x.get("res"), x.get("last")))
        else:
            ok.append("작업 %s %s 정상" % (n, x["last"][5:]))

    # ── B 밤 작업 ──────────────────────────────────────────────────
    rp = C.REP / ("%s.md" % today)
    if not rp.exists():
        bad("🚨", "오늘 밤 보고서 없음(research/reports/factory/%s.md) — 밤 작업 안 돌았거나 중간에 죽음" % today)
    else:
        t = rp.read_text(encoding="utf-8")
        for sec in ("AI 수집 일꾼 실패", "진화기 실패", "정답지 후보 실패"):
            if sec in t: bad("⚠", "밤 작업 일부 실패: %s(보고서 확인)" % sec)
        m = re.search(r"진화기 — (\d+)개 평가", t)
        if not m or int(m.group(1)) == 0: bad("⚠", "진화기가 0개 평가")
        else: ok.append("진화기 %s개" % m.group(1))
    U = C.DATA / "llm_usage.jsonl"
    days_llm = set()
    if U.exists():
        for l in U.read_text(encoding="utf-8").splitlines():
            if l.strip(): days_llm.add(json.loads(l)["ts"][:10].replace("-", ""))
    y1 = (now - dt.timedelta(days=1)).strftime("%Y%m%d")
    if today not in days_llm and y1 not in days_llm and len(days_llm) > 0:
        bad("⚠", "수집 일꾼이 이틀째 클로드를 한 번도 안 부름 — 유튜브 검색·자막이 막혔거나 새 영상 0")
    try:
        import harvest
        rep = harvest.usage_report()[0]
        ok.append(rep)
        mm = re.search(r"한 달 예상 약 \$([\d.]+) \(한도 \$([\d.]+)\)", rep)
        if mm and float(mm.group(1)) > float(mm.group(2)):
            bad("⚠", "크레딧 한 달 예상 $%s 가 한도 $%s 를 넘음" % (mm.group(1), mm.group(2)))
    except Exception as ex:
        bad("⚠", "크레딧 기록 못 읽음: %s" % str(ex)[:100])
    try:
        import lab
        L = lab.load()
        err = [x["id"] for x in L if x.get("status") == "error"]
        old = [x["id"] for x in L if x.get("status") == "queued" and x.get("created", "9")[:10].replace("-", "") < y1]
        if err: bad("⚠", "깔때기 판정 오류 %d개: %s" % (len(err), ", ".join(err[:5])))
        if old: bad("⚠", "깔때기에 하루 넘게 묵은 명세 %d개(판정 안 됨)" % len(old))
        ok.append("명세 %d개(그림자 %d)" % (len(L), sum(x.get("status") in ("shadow", "propose", "review", "adopted") for x in L)))
    except Exception as ex:
        bad("🚨", "명세 등록부를 못 읽음: %s" % str(ex)[:150])
    gp = C.DATA / "gp_pop.json"
    if not gp.exists() or time.time() - gp.stat().st_mtime > 27 * 3600: bad("⚠", "진화기 개체군 파일이 하루 넘게 안 바뀜")

    # ── C 오늘 아침(거래일) ────────────────────────────────────────
    if trading and now.hour >= 9 and today >= REC_START:
        j = C.jload(C.DATA / "transfer" / ("%s.json" % today))
        if not j: bad("🚨", "오늘 전이표 없음(transfer/%s.json)" % today)
        else:
            npred = sum(1 for v in j["pred"].values() if v[3] is not None)
            if npred < 800: bad("⚠", "전이표 예상 갭 종목 %d개(800↑ 정상)" % npred)
            if j.get("inst", {}).get("EWY") is None: bad("⚠", "전이표에 EWY 밤사이 값 없음")
            nd = str(j.get("night"))
            if nd >= today or (dt.datetime.strptime(today, "%Y%m%d") - dt.datetime.strptime(nd, "%Y%m%d")).days > 4:
                bad("⚠", "전이표 '밤' 날짜 이상: %s(오늘 %s)" % (nd, today))
            else: ok.append("전이표 %d종목·밤 %s" % (npred, nd))
        _rec(bad, ok, today, "am", 4, "0855")
        fx = C.DATA / "auction" / ("KR_%s_nxt.parquet" % today)
        if not fx.exists(): bad("🚨", "오늘 NXT 장전 체결가 녹화 없음")
        else:
            X = pd.read_parquet(fx)
            ntag, ntk = X.tag.nunique(), X[X.today].ticker.nunique()
            if ntag < 40: bad("⚠", "NXT 녹화 %d번(1분마다 ~55번 정상)" % ntag)
            if ntk < 200: bad("⚠", "NXT 장전에 오늘 체결 찍힌 종목 %d개(수백 개 정상)" % ntk)
            if ntag >= 40 and ntk >= 200: ok.append("NXT 녹화 %d번·%d종목" % (ntag, ntk))

    # ── D 전 거래일(마감 녹화·저녁) ─────────────────────────────────
    if prev and prev >= FAC_START:
        if prev >= REC_START: _rec(bad, ok, prev, "pm", 2, "1526")
        m1 = C.BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % prev)
        if not m1.exists(): bad("🚨", "전 거래일 1분봉 매일 파일 없음(%s) — 공장 저녁·정답지가 못 돈다" % prev)
        try:
            import live
            A = pd.read_parquet(live.DAILY)
            n = int((A.date == prev).sum())
            if n < 2300: bad("🚨", "매일 일봉에 %s 종목 %d개(2,400↑ 정상) — 저녁 작업 확인" % (prev, n))
            else:
                on = A[A.date == prev].open.isna().mean() * 100
                if on > 10: bad("⚠", "%s 시가 빈칸 %.0f%%(첫 봉이 09:01 아닌 종목) — 1분봉 수집 확인" % (prev, on))
                ok.append("일봉 %s %d종목" % (prev, n))
                _quality(bad, ok, prev, A)
        except Exception as ex:
            bad("🚨", "매일 일봉 점검 실패: %s" % str(ex)[:150])
        icf = C.DATA / "answer" / "ic.csv"
        if not icf.exists() or (pd.read_csv(icf, dtype={"date": str}).date == prev).sum() < 15:
            bad("🚨", "정답지에 %s 기록 없음 — 저녁 작업 실패" % prev)
        else: ok.append("정답지 %s" % prev)

    # ── E 기대는 자료·청소 ─────────────────────────────────────────
    try:
        c = sqlite3.connect("file:" + str(C.BASE / "data" / "investor.db") + "?mode=ro", uri=True)
        fmax = c.execute("SELECT max(date) FROM flow11").fetchone()[0]
        if prev and fmax < prev and now.hour >= 9:
            bad("⚠", "투자자 수급(flow11) 마지막 %s < 전 거래일 %s — 외국인·개인 재료가 비어간다(20:30 연구 수집 확인)" % (fmax, prev))
        else: ok.append("수급 %s" % fmax)
    except Exception as ex:
        bad("⚠", "투자자 DB 못 읽음: %s" % str(ex)[:100])
    try:
        ud = pd.read_parquet(C.DATA / "us_daily.parquet", columns=["date"]).date.max()
        if (dt.datetime.strptime(today, "%Y%m%d") - dt.datetime.strptime(ud, "%Y%m%d")).days > 5:
            bad("⚠", "미장 일봉 마지막 %s — 전이표가 묵은 밤을 쓴다" % ud)
    except Exception as ex:
        bad("⚠", "미장 일봉 못 읽음: %s" % str(ex)[:100])
    for b in (C.BASE / "data" / "m1").glob(".busy_*"):
        age = (time.time() - b.stat().st_mtime) / 3600
        if age > 4:
            try: b.unlink()
            except Exception: pass
            bad("⚠", "%s 표시가 %.0f시간 남아 있어 지움(1분봉 과거 채우기가 그동안 멈춰 있었음)" % (b.name, age))
    rs = C.env().get("REDDIT_SESSION")                                   # 레딧 로그인 쿠키 만료 2주 전 미리 알림(2026-10-10 · 쿠키는 6개월짜리)
    if rs:
        try:
            import base64
            p = rs.split(".")[1]; exp = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))["exp"]
            left = (exp - time.time()) / 86400
            if left < 14: bad("⚠", "레딧 로그인 쿠키가 %.0f일 뒤 만료 — 크롬에서 reddit_session 값을 .env.reddit 에 새로 넣기" % left)
            else: ok.append("레딧 쿠키 %.0f일 남음" % left)
        except Exception: pass
    free = shutil.disk_usage(str(C.BASE)).free / 1e9
    if free < 20: bad("⚠", "G: 남은 공간 %.0fGB" % free)
    lg = C.LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-3000:] if C.LOG.exists() else []
    fails = [l for l in lg if l[:10].replace("-", "") in (today, y1) and "실패" in l and "자막 실패" not in l and "검색 실패" not in l]
    if fails: bad("⚠", "공장 로그 실패 %d줄 — 첫 줄: %s" % (len(fails), fails[0][20:160]))
    return today, trading, prev, P, ok


def _rec(bad, ok, day, part, min_tags, last_tag):
    f = C.DATA / "auction" / ("KR_%s_%s.parquet" % (day, part))
    nm = "장전" if part == "am" else "마감"
    if not f.exists():
        bad("🚨", "%s %s 호가 녹화 없음" % (day, nm)); return
    X = pd.read_parquet(f, columns=["tag", "ticker"])
    per = X.drop_duplicates().groupby("tag").ticker.nunique()
    if len(per) < min_tags: bad("⚠", "%s %s 호가 녹화 %d번(%d번↑ 정상)" % (day, nm, len(per), min_tags))
    if per.min() < 800: bad("⚠", "%s %s 호가 한 번에 %d종목뿐(1,000 안팎 정상)" % (day, nm, per.min()))
    if per.index.max() < last_tag: bad("⚠", "%s %s 마지막 녹화 %s(%s 이후여야)" % (day, nm, per.index.max(), last_tag))
    if len(per) >= min_tags and per.min() >= 800: ok.append("%s 녹화 %d번·%d종목" % (nm, len(per), per.min()))


def _quality(bad, ok, day, A):
    """숫자가 말이 되나 — 전 거래일 재료를 다시 만들어 본다."""
    import live
    U = live.frame(days=[day], A=A)
    n = len(U)
    if not 800 <= n <= 1200: bad("⚠", "%s 유니버스 %d종목(약 1,000 정상)" % (day, n))
    nan = lambda k: U[k].isna().mean() * 100 if k in U.columns else 100
    lim = {"gap": 3, "vm": 10, "r20": 15, "fr": 30}
    if (C.DATA / "transfer" / ("%s.json" % day)).exists(): lim["tr_pred"] = 35
    for k, v in lim.items():
        if nan(k) > v: bad("⚠", "%s 재료 %s 빈칸 %.0f%%(%d%% 이하 정상)" % (day, k, nan(k), v))
    if (C.DATA / "auction" / ("KR_%s_am.parquet" % day)).exists():
        if nan("a_eq") > 20: bad("⚠", "%s 장전 예상 갭(a_eq) 빈칸 %.0f%% — 녹화·계산 확인" % (day, nan("a_eq")))
        e = U.a_err.abs().median()
        if e == e:
            if e > 1.0: bad("⚠", "%s 장전 예상 갭이 실제 갭과 중앙 %.2f%%p 어긋남(0.3 안팎 정상) — 균형가격 계산·녹화 시각 확인" % (day, e))
            else: ok.append("장전 예상 갭 오차 중앙 %.2f%%p" % e)
    Z = U[["tr_pred", "gap"]].dropna()
    if len(Z) > 300:
        cr = float(np.corrcoef(Z.tr_pred, Z.gap)[0, 1])
        hist = HD / "tr_corr.csv"
        H = pd.read_csv(hist, dtype={"date": str}) if hist.exists() else pd.DataFrame(columns=["date", "corr"])
        H = pd.concat([H[H.date != day], pd.DataFrame([[day, cr]], columns=["date", "corr"])]).tail(60)
        H.to_csv(hist, index=False)
        r10 = H["corr"].tail(10).mean()
        if len(H) >= 10 and r10 < 0.1: bad("⚠", "전이표 예상 갭과 실제 갭 상관이 최근 10일 평균 %.2f — 짝이 낡았거나 밤 날짜 어긋남" % r10)
        else: ok.append("전이표 상관 %.2f" % cr)


def run():
    today, trading, prev, P, ok = check()
    lines = ["# 공장 점검 %s (%s · 전 거래일 %s)" % (today, "거래일" if trading else "휴장", prev), ""]
    lines += ["## 문제 %d개" % len(P), ""] + ["- %s %s" % p for p in P] + ["", "## 정상 확인", ""] + ["- " + s for s in ok]
    (HD / ("%s.md" % today)).write_text("\n".join(lines) + "\n", encoding="utf-8")
    H = pd.read_csv(HCSV, dtype={"date": str}) if HCSV.exists() else pd.DataFrame(columns=["date", "n", "crit", "first"])
    H = pd.concat([H[H.date != today], pd.DataFrame([[today, len(P), sum(p[0] == "🚨" for p in P), P[0][1][:80] if P else ""]], columns=H.columns)])
    H.to_csv(HCSV, index=False, encoding="utf-8-sig")
    if P:
        C.tg("🩺 <b>공장 점검 %s/%s — 문제 %d개</b>\n" % (today[4:6], today[6:], len(P)) + "\n".join("%s %s" % p for p in P[:12]))
    elif C.now().weekday() == 0:
        w = H.tail(7)
        C.tg("🩺 공장 점검 주간: 지난 %d번 중 문제 없음 %d번 · 녹화·전이표·정답지·밤 작업 정상" % (len(w), int((w.n.astype(int) == 0).sum())))
    C.log("점검: 문제 %d · 정상 %d" % (len(P), len(ok)))
    return P, ok


def deadman():
    """밤 작업이 부른다 — 어제 점검 기록이 없으면 알린다(점검기 자체가 죽은 경우)."""
    y = (C.now() - dt.timedelta(days=1)).strftime("%Y%m%d")
    if HCSV.exists() and not (HD / ("%s.md" % y)).exists():
        C.tg("🩺 ⚠ 공장 점검기가 어제(%s/%s) 안 돌았음 — 예약 작업 \\BamhobakFactory\\Check 확인" % (y[4:6], y[6:]))
