import sys, subprocess
from faster_whisper import WhisperModel
m = WhisperModel("small", device="cpu", compute_type="int8")
for v in sys.argv[1:]:
    subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "-f", "bestaudio[ext=m4a]/bestaudio", "-o", v + ".%(ext)s", "https://www.youtube.com/watch?v=" + v], check=True)
    import glob
    f = [x for x in glob.glob(v + ".*") if not x.endswith(".txt")][0]
    segs, info = m.transcribe(f, language="ko", vad_filter=True)
    txt = " ".join(s.text.strip() for s in segs)
    open(v + ".txt", "w", encoding="utf-8").write("(STT)\n" + txt)
    print(v, len(txt), flush=True)
