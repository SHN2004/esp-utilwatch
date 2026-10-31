# Run watch/watch.ino on the Mac against the real U8g2 C library and save the
# screen as an animated GIF, so animations can be checked without flashing.
#
#   python3 tools/preview/preview.py [out.gif] [--seconds 9] [--frame-ms 25]
#
# --frame-ms is how long one sendBuffer() takes on the board (I2C speed dependent).
import argparse, glob, os, subprocess, tempfile
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
repo = os.path.dirname(os.path.dirname(here))
clib = os.path.expanduser("~/Documents/Arduino/libraries/U8g2/src/clib")

ap = argparse.ArgumentParser()
ap.add_argument("out", nargs="?", default=os.path.join(repo, "preview.gif"))
ap.add_argument("--seconds", type=float, default=9)
ap.add_argument("--frame-ms", type=int, default=25)
a = ap.parse_args()

main_cpp = f"""
#include "Arduino.h"
#include "U8g2lib.h"
#include <stdio.h>
uint32_t fake_ms = 0, frame_ms = {a.frame_ms};
std::vector<Frame> frames;
#include "{repo}/watch/watch.ino"
int main() {{
  setup();
  while (fake_ms < {int(a.seconds * 1000)}) loop();
  FILE *f = fopen(getenv("FRAMES_OUT"), "wb");
  for (auto &fr : frames) {{ fwrite(&fr.ms, 4, 1, f); fwrite(fr.buf.data(), 1, 1024, f); }}
  fclose(f);
}}
"""

with tempfile.TemporaryDirectory() as tmp:
    src, exe, raw = (os.path.join(tmp, n) for n in ("main.cpp", "main", "frames.bin"))
    open(src, "w").write(main_cpp)
    objs = []
    for c in glob.glob(os.path.join(clib, "*.c")):  # ponytail: rebuilds U8g2 every run (~seconds); cache objects if it gets slow
        o = os.path.join(tmp, os.path.basename(c) + ".o")
        objs.append(o)
        subprocess.run(["clang", "-O1", "-w", "-c", f"-I{clib}", c, "-o", o], check=True)
    subprocess.run(["clang++", "-std=c++17", "-O1", "-w", "-x", "c++", f"-I{here}", f"-I{clib}",
                    f"-I{repo}/watch", src, "-x", "none", *objs, "-o", exe], check=True)
    subprocess.run([exe], check=True, env={**os.environ, "FRAMES_OUT": raw})
    data = open(raw, "rb").read()

images, times = [], []
for i in range(0, len(data), 1028):
    times.append(int.from_bytes(data[i:i + 4], "little"))
    buf = data[i + 4:i + 1028]
    img = Image.new("RGB", (128, 64), (5, 7, 10))
    px = img.load()
    for page in range(8):  # SH1106 buffer: 8 pages of 128 vertical bytes
        for x in range(128):
            b = buf[page * 128 + x]
            for bit in range(8):
                if b >> bit & 1:
                    px[x, page * 8 + bit] = (90, 180, 255)
    images.append(img.resize((384, 192), Image.NEAREST))

durations = [max(20, t2 - t1) for t1, t2 in zip(times, times[1:])] + [1000]
images[0].save(a.out, save_all=True, append_images=images[1:], duration=durations, loop=0)
print(f"{len(images)} frames, {times[-1] / 1000:.1f}s -> {a.out}")
