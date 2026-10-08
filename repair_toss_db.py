# -*- coding: utf-8 -*-
"""data/toss.db 손상 복구 (2026-10-08 — 10-02 20:50 마지막 쓰기 도중 파일 끝이 잘림: 표 안 연결이 파일 밖 쪽 340,8xx~ 를 가리킴).
증상: 10-05~ 매일 20:30 연구 수집 '토스 수급·프로그램매매' 단계가 'database disk image is malformed' 로 즉사 → 토스수급·프로그램매매·대차잔고 10-01 에 멈춤.
방법(블루스크린 때 교훈 그대로): 행 번호 구간별로 읽고, 깨진 구간은 반씩 쪼개 건너뛰며 살아 있는 행을 새 파일로 옮긴다.
원본은 data/toss_broken_YYYYMMDD.db 로 남긴다. 잃은 행(잘린 끝 = 최근 쓰기)은 collect_toss.py --days 25 로 다시 받는다.
    python repair_toss_db.py            # 새 파일 data/toss_rebuilt.db 만들고 비교만
    python repair_toss_db.py --swap     # 그다음 바꿔 끼우기
"""
import sqlite3, sys, time, shutil
from pathlib import Path

BASE = Path(__file__).parent
SRC = BASE / "data" / "toss.db"
DST = BASE / "data" / "toss_rebuilt.db"


def copy_table(src, dst, name, cols):
    mx = src.execute("SELECT max(rowid) FROM %s" % name).fetchone()[0] or 0
    ins = "INSERT OR IGNORE INTO %s(%s) VALUES(%s)" % (name, ",".join(cols), ",".join("?" * len(cols)))
    got, lost = 0, []

    def take(a, b):
        nonlocal got
        try:
            rows = src.execute("SELECT %s FROM %s WHERE rowid BETWEEN ? AND ?" % (",".join(cols), name), (a, b)).fetchall()
        except sqlite3.DatabaseError:
            if b - a < 64:
                lost.append((a, b)); return
            m = (a + b) // 2
            take(a, m); take(m + 1, b); return
        dst.executemany(ins, rows); got += len(rows)
    step = 50000
    for a in range(1, mx + 1, step):
        take(a, min(a + step - 1, mx))
    dst.commit()
    return got, lost


def main():
    t0 = time.time()
    src = sqlite3.connect("file:%s?mode=ro" % SRC.as_posix(), uri=True)
    if DST.exists(): DST.unlink()
    dst = sqlite3.connect(str(DST))
    dst.execute("PRAGMA journal_mode=OFF"); dst.execute("PRAGMA synchronous=OFF")
    for name, sql in src.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall():
        dst.execute(sql)
        cols = [r[1] for r in src.execute("PRAGMA table_info(%s)" % name)]
        got, lost = copy_table(src, dst, name, cols)
        mx = dst.execute("SELECT max(date) FROM %s" % name).fetchone()[0] if "date" in cols else "-"
        print("%-8s 살린 행 %s · 못 읽은 구간 %d개(행 번호 %s) · 마지막 날짜 %s · %.0f초" % (
            name, f"{got:,}", len(lost), ", ".join("%d~%d" % x for x in lost[:4]), mx, time.time() - t0), flush=True)
    dst.execute("PRAGMA journal_mode=WAL")
    print("quick_check:", dst.execute("PRAGMA quick_check").fetchone()[0], flush=True)
    dst.close(); src.close()
    if "--swap" in sys.argv:
        bk = BASE / "data" / ("toss_broken_%s.db" % time.strftime("%Y%m%d"))
        for ext in ("-wal", "-shm"):
            p = Path(str(SRC) + ext)
            if p.exists(): p.unlink()
        shutil.move(str(SRC), str(bk)); shutil.move(str(DST), str(SRC))
        print("바꿔 끼움: 원본 →", bk.name, flush=True)


if __name__ == "__main__":
    main()
