# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "자료 모으는 중 추가해줘 · 얼마나 걸리고 언제쯤 마무리될지도" — 규칙 후보 페이지(assets/factory.html) '자료 모으는 중' 칸.
자료가 다 모여야 시험할 수 있는 가설(등록부 '보류')의 쌓인 거래일·목표·예상 날짜를 Supabase '__collect__' 에 올린다.
ops_status.py(30분마다)가 끝에 부른다 — 새 예약 작업 없음.
    python research/collecting.py        올리기
    python research/collecting.py dry    보기만
목표(1차 보기 → 판정)는 미리 정한 값 — 결과 보고 옮기지 않는다.
  H0418 [시간외 단일가 낙폭]: 60거래일 1차 보기(거래 단위 성적·겹침) → 120거래일 판정(앞 60 학습 · 뒤 60 검증)
  H0419 [KRX 예상체결 되돌림]: 20거래일 1차 보기 → 60거래일 판정"""
import datetime as dt, glob, json, sys, time
from pathlib import Path
import pandas as pd
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research" / "factory"))
CACHE = BASE / "research" / "cache"
FIRST_KAH = "20260914"                 # 토스에 NXT 아닌 종목 시간외 봉이 남아 있는 첫날(11-15 확인 — 09-11 까지는 15:30 까지만)
# 앞으로 휴장일(거래일 세기용 · 대략 — 바뀌면 고칠 것)
HOLI = {"20260924", "20260925", "20261005", "20261009", "20261225", "20261231", "20270101", "20270208", "20270209", "20270301", "20270505", "20270513", "20270603", "20270815", "20270816",
        "20270914", "20270915", "20270916", "20271003", "20271004", "20271009", "20271011", "20271225", "20271231"}


def add_tdays(start, n):
    """start(YYYYMMDD, 그날 빼고) 뒤 n 번째 거래일(주말·HOLI 뺌)."""
    d = dt.datetime.strptime(start, "%Y%m%d")
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y%m%d") not in HOLI: n -= 1
    return d.strftime("%Y%m%d")


def tdays_between(a, b):
    """a 부터 b 전날까지 거래일(주말·HOLI 뺌)."""
    d = dt.datetime.strptime(a, "%Y%m%d"); e = dt.datetime.strptime(b, "%Y%m%d"); out = []
    while d < e:
        if d.weekday() < 5 and d.strftime("%Y%m%d") not in HOLI: out.append(d.strftime("%Y%m%d"))
        d += dt.timedelta(days=1)
    return out


def stage(have, last, goals):
    out = []
    for lab, g in goals:
        out.append(dict(lab=lab, goal=g, done=have >= g, eta=None if have >= g else add_tdays(last, g - have)))
    return out


def krx_ah():
    out = CACHE / "bf_krx_ah"
    fs = glob.glob(str(out / "done_*.parquet"))
    dn = pd.concat([pd.read_parquet(f, columns=["t", "d"]) for f in fs]) if fs else pd.DataFrame(columns=["t", "d"])
    J = json.loads((CACHE / "toss_nxt_kr.json").read_text(encoding="utf-8")); nt = sum(1 for v in J.values() if not v.get("nxt"))
    per = dn.groupby("d").t.nunique() if len(dn) else pd.Series(dtype=int)
    full = sorted(per[per >= 0.95 * nt].index)                       # 그날 종목 95%↑ 받은 날 = 쌓인 날
    st = {}
    try: st = json.loads((BASE / "data" / "backfill" / "state.json").read_text(encoding="utf-8")).get("krx_ah", {})
    except Exception: pass
    today = dt.datetime.now().strftime("%Y%m%d")
    full = [d for d in full if d >= FIRST_KAH]
    tdays = tdays_between(FIRST_KAH, today)                              # 받을 수 있는 날(토스 기록 첫날~어제, 달력)
    have = len(full); exp = max(have, len(tdays)); last = max(tdays) if tdays else today
    left = int(st.get("left") or 0); catch = left > 5 * nt                # 밀린 날 받는 중(첫 밤)
    return dict(id="H0418", name="[시간외 단일가 낙폭]", parent="[장후 낙폭] 형제",
                what="NXT 아닌 종목 %d개 · KRX 시간외 1분봉(15:31~18:00) · 토스에 2026-09-14 부터만 있음" % nt,
                how="밤 과거 받기(20:10~07:30) — 9월부터 밀린 날을 받고, 그 뒤 매일 밤 그날 치를 이어 받음",
                have=have, expect=exp, first=min(full) if full else None, last=max(full) if full else None, partial=int((per < 0.95 * nt).sum()),
                backfill=dict(left=left, total=int(st.get("total") or 0), eta_h=st.get("eta_hours"), rate=st.get("rate_per_s"), updated=st.get("updated"), catching=catch),
                goals=stage(exp, last, [("1차 보기(거래 성적·겹침)", 60), ("판정(학습 60 · 검증 60)", 120)]))


def kis_exp():
    import common as C
    fs = sorted(glob.glob(str(C.DATA / "auction" / "KR_*_kisexp.parquet")))
    ds = sorted(Path(f).name.split("_")[1] for f in fs)
    today = dt.datetime.now().strftime("%Y%m%d")
    have = len(ds); last = ds[-1] if ds else today
    return dict(id="H0419", name="[KRX 예상체결 되돌림]", parent="[장전 되돌림] 형제", expect=have,
                what="08:40:30·08:45:30 KRX 예상체결가(한국투자증권 API) · NXT 장전 체결 종목 전부",
                how="녹화기(auction.py) 매일 아침 — 과거 자료는 없음(11-16 부터)",
                have=have, first=ds[0] if ds else None, last=ds[-1] if ds else None, partial=0, backfill=None,
                goals=stage(have, last, [("1차 보기", 20), ("판정", 60)]))


RATE_DEF, WIN = 3.0, ((20, 10), (7, 30))       # 밤 받기 초당(실측 3.0~3.9) · 받는 시간 20:10~07:30


def _done_n(out):
    fs = glob.glob(str(CACHE / out / "done_*.parquet"))
    return sum(len(pd.read_parquet(f, columns=["t"])) for f in fs) if fs else 0


def queue():
    """밤 받기 줄(jobs.json 순서) — 일감마다 (전체, 받은 것, 남은 것). 남은 것 = 상태 파일 left, 없으면 목록 − 받은 것."""
    J = json.loads((BASE / "research" / "backfill" / "jobs.json").read_text(encoding="utf-8"))
    st = {}
    try: st = json.loads((BASE / "data" / "backfill" / "state.json").read_text(encoding="utf-8"))
    except Exception: pass
    Q = []
    for j in J:
        if not j.get("enabled", True) or not j.get("out") or st.get(j["id"], {}).get("finished"): continue
        done = _done_n(j["out"]); s = st.get(j["id"], {})
        if j.get("pairs"): total = len(pd.read_parquet(CACHE / j["pairs"], columns=["t"]))
        else: total = int(s.get("total") or done)
        left = max(0, total - done) if j.get("pairs") or not s.get("left") else int(s["left"])
        Q.append(dict(id=j["id"], total=total, done=done, left=left, rate=float(s.get("rate_per_s") or RATE_DEF)))
    return Q


def at_after(sec):
    """지금부터 받는 시간만 sec 초 흘렀을 때의 시각(밤 20:10~07:30 만 셈)."""
    t = dt.datetime.now(); left = sec
    while left > 0:
        a = t.replace(hour=WIN[0][0], minute=WIN[0][1], second=0, microsecond=0)
        if t.hour * 60 + t.minute < WIN[1][0] * 60 + WIN[1][1]: a -= dt.timedelta(days=1)   # 새벽이면 어젯밤 창
        b = a + dt.timedelta(hours=11, minutes=20)
        if t < a: t = a
        if t >= b: t = a + dt.timedelta(days=1); continue
        use = min(left, (b - t).total_seconds()); t += dt.timedelta(seconds=use); left -= use
        if left > 0: t = a + dt.timedelta(days=1)
    return t


def fetch_item(hid, name, parent, what, how, job, marks):
    """과거 자료를 밤에 받는 가설 — 받은 쌍·목표(전체의 몇 %)·예상 날짜(앞 일감 남은 것까지 줄 서서)."""
    Q = queue(); ahead = 0.0; me = None
    for q in Q:
        if q["id"] == job: me = q; break
        ahead += q["left"] / max(q["rate"], 0.5)
    if me is None:
        return dict(id=hid, name=name, parent=parent, what=what, how=how, unit="쌍", unit_lab="받은 종목·날", have=0, expect=0, goals=[], err="일감 없음")
    G = []
    for lab, f in marks:
        need = max(0, int(f * me["total"]) - me["done"])
        G.append(dict(lab=lab, goal=int(f * me["total"]), done=need == 0,
                      eta=None if need == 0 else at_after(ahead + need / max(me["rate"], 0.5)).strftime("%Y%m%d")))
    first = at_after(ahead + 1).strftime("%Y-%m-%d %H:%M") if me["done"] == 0 else None
    return dict(id=hid, name=name, parent=parent, what=what, how=how + (" · 앞 일감 끝나고 %s 무렵 시작" % first if first else ""),
                unit="쌍", unit_lab="받은 종목·날", have=me["done"], expect=me["done"], first=None, last=None, partial=0,
                backfill=dict(left=me["left"], total=me["total"], eta_h=round(me["left"] / max(me["rate"], 0.5) / 3600, 1), rate=me["rate"], catching=False),
                goals=G)


def us_pre():
    return fetch_item("H0420", "[미장 장전 얇은 갭하락]", "[갭하락]·[장전 되돌림] 미장판",
                      "소형주(20일 거래대금 $0.5M~$30M)가 개장 갭 -2%↓ 로 연 날의 06:41~10:00 ET 1분봉 · 2022-06~",
                      "밤 과거 받기 — 다 받으면 바로 학습(2022-06~2024)·검증(2025~) 판정", "us_pre", [("다 받음 → 판정", 1.0)])


def us_on():
    return fetch_item("H0421", "[주간거래 낙폭]", "[장후 낙폭] 미장판",
                      "거래대금 상위 1,000 종목의 한국 낮 주간거래(00:41~04:00 ET) 1분봉 · 토스에 2023-02 부터",
                      "밤 과거 받기 — 날짜를 무작위 순서로 받으니 30% 받으면 표본으로 1차 보기", "us_on", [("1차 보기(30%)", 0.3), ("다 받음 → 판정", 1.0)])


def build():
    items = []
    for fn in (krx_ah, kis_exp, us_pre, us_on):
        try: items.append(fn())
        except Exception as ex: items.append(dict(id=fn.__name__, name=fn.__name__, err=repr(ex)[:200]))
    return dict(updated=time.strftime("%Y-%m-%d %H:%M"), items=items)


def publish(dry=False):
    J = build()
    if dry:
        print(json.dumps(J, ensure_ascii=False, indent=1)); return J
    import board
    board.supa_set("__collect__", J)
    return J


if __name__ == "__main__":
    publish(dry=(sys.argv[1:2] == ["dry"]))
