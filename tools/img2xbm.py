# Convert an image to a 1-bit XBM header for u8g2.drawXBMP().
#
#   python3 tools/img2xbm.py photo.jpg watch/couple.h couple --size 128x64 \
#       --rotate 90 --crop 400,160,1840,880 --contrast 1.4 --thresh 120 \
#       --vignette 0,-10,72,90 --vignette 56,0,124,90 --preview out.png
#
# Dithering (default) keeps shading; --thresh gives clean shapes on busy photos.
# --vignette ellipses (output pixel coords) keep those areas and fade the rest to black.
import argparse
from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFilter, ImageChops

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out"); ap.add_argument("name")
ap.add_argument("--size", default="64x64", help="WxH")
ap.add_argument("--rotate", type=int, default=0, help="degrees counter-clockwise")
ap.add_argument("--crop", help="left,top,right,bottom in source pixels (after rotate)")
ap.add_argument("--contrast", type=float, default=2.2)
ap.add_argument("--thresh", type=int, help="0-255 cutoff instead of dithering")
ap.add_argument("--vignette", action="append", default=[], help="x0,y0,x1,y1 ellipse to keep")
ap.add_argument("--preview", help="save a 4x PNG preview here")
a = ap.parse_args()

w, h = map(int, a.size.split("x"))
img = Image.open(a.src).convert("L").rotate(a.rotate, expand=True)
if a.crop:
    img = img.crop(tuple(map(int, a.crop.split(","))))
img = ImageOps.autocontrast(img.resize((w, h), Image.LANCZOS), cutoff=2)
img = ImageEnhance.Contrast(img).enhance(a.contrast)
if a.vignette:
    mask = Image.new("L", (w, h), 0)
    for e in a.vignette:
        ImageDraw.Draw(mask).ellipse(tuple(map(int, e.split(","))), fill=255)
    img = ImageChops.multiply(img, mask.filter(ImageFilter.GaussianBlur(6)))
bw = img.point(lambda p: 255 if p > a.thresh else 0).convert("1") if a.thresh is not None else img.convert("1")

if a.preview:
    bw.resize((w * 4, h * 4), Image.NEAREST).save(a.preview)

px = bw.load()
data = []
for y in range(h):
    for x0 in range(0, w, 8):
        b = 0
        for i in range(8):  # XBM is LSB-first; white pixel = lit
            if x0 + i < w and px[x0 + i, y]:
                b |= 1 << i
        data.append(b)

with open(a.out, "w") as f:
    f.write(f"#define {a.name}_W {w}\n#define {a.name}_H {h}\n")
    f.write(f"static const unsigned char {a.name}_bits[] PROGMEM = {{\n")
    for i in range(0, len(data), 16):
        f.write("  " + ", ".join(f"0x{b:02x}" for b in data[i:i + 16]) + ",\n")
    f.write("};\n")
