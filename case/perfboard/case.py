# Printable case for the perfboard watch (one-port layout, kicad/perfboard). Two parts: a shell printed
# face down with flex buttons in its top, and a back plate with its own posts and a hook at 6 o'clock.
#   uv run --with build123d python case/perfboard/case.py
# Writes case/perfboard/build/: fit-test.stl (print first), shell.stl, back.stl, and watch.glb + viewer.html to look at.
#
# Coordinates follow the solder map: x = board column direction (0 at c1's edge, 45.72 at c18's),
# row = 0 at the 12 o'clock edge to 38.1 at 6 o'clock, z = up out of the screen with the board's
# underside at 0. Part sizes are typical, not measured: measure yours and fix them here.
import base64
from pathlib import Path
from build123d import (Align, Axis, Box, Color, Compound, Cone, Cylinder, Plane, Polygon, Pos, Rectangle,
                       RectangleRounded, Circle, export_gltf, export_stl, extrude, loft)

OUT = Path(__file__).parent / "build"

# ---- the watch inside, from the solder map (kicad/perfboard/utilwatch-solder-map.html) ----
P = 2.54
def hx(c): return 1.27 + P * (c - 1)
def hr(r): return 1.27 + P * (r - 1)
BOARD_W, BOARD_H, BOARD_T = 18 * P, 15 * P, 1.6
OLED_Z, OLED_PCB_T, GLASS_T = 4.14, 1.2, 1.5          # module PCB sits on its 2.54 mm header
SCREEN = (17.7, 16.8, 29.42, 14.7)                     # lit area: centre x, centre row, width, height
BUTTON_ROWS = [(hr(2) + hr(5)) / 2, (hr(6) + hr(9)) / 2, (hr(10) + hr(13)) / 2]
BUTTON_X, STEM_TOP, STEM_D = 41.91, 6.2, 3.5           # 6 x 6 mm tactile switches, stems up
SLIDER_X, SLIDER_ROW, LEVER_TOP = 41.91, hr(14), 8.0   # lever moves along x
ESP_FACE = -3.54                                       # ESP32's wrist face (header plastic is 2.54 + 1 mm PCB)
USB = (-1.5, 6.0, 25.21, 33.21, -6.69, -3.54)          # USB-C shell: x0, x1, row0, row1, z0, z1
LOWEST = -6.7                                          # USB shell and battery bottoms

# ---- the case ----
GAP, WALL, TOP_T, BACK_T = 0.3, 2.0, 1.2, 1.6
STRAP_W, SLOT_W, BAR_W = 20, 3.2, 3.0                  # strap width; slot and bar at each end
TOP_IN = LEVER_TOP - 0.9                               # ceiling: 0.26 mm over the OLED glass
TOP_OUT = TOP_IN + TOP_T
BACK_IN = LOWEST - 0.3
BACK_OUT = BACK_IN - BACK_T
IX0, IX1 = -GAP, 46.26 + GAP                           # the slider overhangs the board edge by 0.54 mm
IR0, IR1 = -GAP, BOARD_H + 1.0                         # 1 mm at 6 o'clock: the button wires run along that edge
LUG = SLOT_W + BAR_W
OX0, OX1 = IX0 - WALL, IX1 + WALL
OR0, OR1 = IR0 - WALL - LUG, IR1 + WALL + LUG
CX = (OX0 + OX1) / 2
SCREWS = [(x, OR0 + LUG / 2) for x in (OX0 + 3, OX1 - 3)]   # M2.5 x 5 countersunk, from the back, in the 12 o'clock lugs
HOOK = (26.0, 42.0, 1.0, 2.2)                          # 6 o'clock: x0, x1, lip height above the plate, tongue height
PILOT_D, SCREW_D, HEAD_D, HEAD_T = 2.1, 2.8, 5.2, 1.2   # M2.5 cuts its own thread in the 2.1 mm pilot; 90-degree countersink
MARGIN, COVER_T = 1.5, 0.5                             # window past the lit area; optional clear cover sheet in a pocket
TAB_W, TAB_T, TAB_X0, TAB_X1, CUT = 5.0, 0.8, 36.6, 46.5, 0.6  # flex buttons: a tab cut into the top, hinged at the outer edge


def bx(x0, x1, r0, r1, z0, z1):
    """Box between two x, two rows and two heights. Rows run toward 6 o'clock, which is -Y."""
    return Pos((x0 + x1) / 2, -(r0 + r1) / 2, z0) * Box(x1 - x0, r1 - r0, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def cyl(x, r, z0, z1, d):
    return Pos(x, -r, z0) * Cylinder(d / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def outline(z0, z1, radius=3.0):
    return Pos(CX, -(OR0 + OR1) / 2, z0) * extrude(RectangleRounded(OX1 - OX0, OR1 - OR0, radius), z1 - z0)


def slots(z0, z1):
    return [bx(CX - (STRAP_W + 1) / 2, CX + (STRAP_W + 1) / 2, r0, r0 + SLOT_W, z0, z1)
            for r0 in (IR0 - WALL - SLOT_W, IR1 + WALL)]


def ramp(end):
    """Cuts the lugs at 45 degrees from the body's top edge, so the shell prints face down with no supports."""
    edge = IR0 - WALL if end == 12 else IR1 + WALL                 # the body's outer wall, as a row
    s = 1 if end == 12 else -1                                     # Y direction outward
    y0, run = -edge, LUG + 1
    pts = [(y0, TOP_OUT), (y0 + s * run, TOP_OUT - run), (y0 + s * run, TOP_OUT + 1), (y0, TOP_OUT + 1)]
    tri = Polygon(*(pts if s > 0 else pts[::-1]), align=None)      # same winding at both ends, or the cut lands beside the case
    return Pos(OX0 - 1, 0, 0) * extrude(Plane.YZ * tri, OX1 - OX0 + 2)


def window():
    """The screen opening, MARGIN past the lit area, opening out at 45 degrees."""
    x, r, w, h = SCREEN
    m = 2 * MARGIN
    lo = Plane.XY.offset(TOP_IN - 0.01) * Pos(x, -r) * Rectangle(w + m, h + m)
    hi = Plane.XY.offset(TOP_OUT + 0.01) * Pos(x, -r) * Rectangle(w + m + 2 * TOP_T, h + m + 2 * TOP_T)
    return loft([lo, hi])


def shell():
    s = outline(BACK_IN, TOP_OUT)
    s -= Pos(0, 0, 0) * bx(IX0, IX1, IR0, IR1, BACK_IN - 1, TOP_IN)
    s -= ramp(12) + ramp(6)
    for sl in slots(BACK_IN - 1, TOP_OUT + 1):
        s -= sl
    s -= window()
    x, r, w, h = SCREEN                                              # pocket for a 0.5 mm clear sheet over the glass
    s -= bx(x - w / 2 - MARGIN - 2, x + w / 2 + MARGIN + 2, r - h / 2 - MARGIN - 2, r + h / 2 + MARGIN + 2, TOP_IN - 0.01, TOP_IN + COVER_T)
    for r in BUTTON_ROWS:                                           # flex buttons: U-shaped cut, thinned tab, nub onto the stem
        s -= bx(TAB_X0 - CUT, TAB_X1, r - TAB_W / 2 - CUT, r - TAB_W / 2, TOP_IN - 1, TOP_OUT + 1)
        s -= bx(TAB_X0 - CUT, TAB_X1, r + TAB_W / 2, r + TAB_W / 2 + CUT, TOP_IN - 1, TOP_OUT + 1)
        s -= bx(TAB_X0 - CUT, TAB_X0, r - TAB_W / 2, r + TAB_W / 2, TOP_IN - 1, TOP_OUT + 1)
        s -= bx(TAB_X0, TAB_X1, r - TAB_W / 2, r + TAB_W / 2, TOP_IN - 0.01, TOP_OUT - TAB_T)
        s += cyl(BUTTON_X, r, STEM_TOP + 0.15, TOP_OUT - TAB_T + 0.01, 3.0)
    s -= bx(SLIDER_X - 2.5, SLIDER_X + 2.5, SLIDER_ROW - 1.3, SLIDER_ROW + 1.3, TOP_IN - 1, TOP_OUT + 1)
    ux0, ux1, ur0, ur1, uz0, uz1 = USB                              # room for the plug's moulded grip
    s -= Pos(OX0 - 1, -(ur0 + ur1) / 2, (uz0 + uz1) / 2) * Box(IX0 - OX0 + 2, 12.4, 6.6, align=(Align.MIN, Align.CENTER, Align.CENTER))
    for x, r in SCREWS:
        s -= cyl(x, r, BACK_IN - 1, BACK_IN + 6, PILOT_D)
    s += bx(0.6, 37.5, 0.2, 2.3, BOARD_T, TOP_IN)                    # rib: holds the board down along 12 o'clock
    # marks on the buttons themselves: up, select, down
    up, down = Polygon((-1.1, -0.9), (1.1, -0.9), (0, 1.0)), Polygon((-1.1, 0.9), (1.1, 0.9), (0, -1.0))
    for r, mark in zip(BUTTON_ROWS, (up, Circle(0.9), down)):
        s -= Pos(BUTTON_X, -r, TOP_OUT - 0.3) * extrude(mark, 1)
    x0, x1, lip, tall = HOOK                                         # groove in the 6 o'clock wall for the back plate's hook
    s -= bx(x0 - 0.4, x1 + 0.4, IR1 - 0.1, IR1 + 1.0, BACK_IN + lip - 0.2, BACK_IN + tall + 0.3)  # the wall below it holds the lip
    return s


def back():
    b = outline(BACK_OUT, BACK_IN)
    for sl in slots(BACK_OUT - 1, BACK_IN + 1):
        b -= sl
    ux0, ux1, ur0, ur1, uz0, uz1 = USB
    b -= bx(OX0 - 1, ux0, (ur0 + ur1) / 2 - 6.2, (ur0 + ur1) / 2 + 6.2, BACK_OUT - 1, BACK_IN + 1)  # the plug's grip reaches 0.8 mm into the wall
    x0, x1, lip, tall = HOOK                                         # 6 o'clock hook: hooks into the wall's groove, then the plate swings shut
    b += bx(x0, x1, IR1 - 1.0, IR1 - 0.1, BACK_IN, BACK_IN + tall) + bx(x0, x1, IR1 - 0.1, IR1 + 0.8, BACK_IN + lip, BACK_IN + tall)
    b += cyl(hx(1), hr(1), BACK_IN, 0, 2.6) + cyl(hx(18), hr(1), BACK_IN, 0, 2.6)  # posts: push the board up at 12 o'clock
    b += bx(27.5, 33.5, 25, 31, BACK_IN, 0)                         # and beside the ESP32, where the spacer was
    for x, r in SCREWS:
        b -= cyl(x, r, BACK_OUT - 1, BACK_IN + 1, SCREW_D) + Pos(x, -r, BACK_OUT - 0.01) * Cone(HEAD_D / 2, SCREW_D / 2, HEAD_T, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return b


def fit_plate(sh):
    """The shell's top and the top 2 mm of its walls: a 10-minute print to lay on the real board first."""
    return sh & bx(OX0 - 1, OX1 + 1, OR0 - 1, OR1 + 1, TOP_IN - 2, TOP_OUT + 1)


def parts_inside():
    """The watch's own parts as boxes, to check the case clears them."""
    joints = [bx(hx(c) - 0.9, hx(c) + 0.9, hr(r) - 0.9, hr(r) + 0.9, -1.2, 0)
              for c, r in [(16, 2), (18, 2), (16, 5), (18, 5), (16, 6), (18, 6), (16, 9), (18, 9),
                           (16, 10), (18, 10), (16, 13), (18, 13), (16, 14), (17, 14), (18, 14)]]
    return {
        "board": bx(0, BOARD_W, 0, BOARD_H, 0, BOARD_T),
        "OLED": bx(0, 35.4, 2.6, 36.1, OLED_Z, OLED_Z + OLED_PCB_T) + bx(1.2, 34.2, 6, 29, OLED_Z + OLED_PCB_T, OLED_Z + OLED_PCB_T + GLASS_T)
                + bx(hx(6) - 1.27, hx(9) + 1.27, hr(14) - 1.27, hr(14) + 1.27, BOARD_T, OLED_Z),
        "OLED wires": bx(1.5, 24.5, 34.5, 37.0, BOARD_T, 6.5),
        "edge wires": bx(12.5, 33.0, 37.0, 38.9, BOARD_T - 0.3, 2.9),   # button wires along the 6 o'clock edge, top side
        "buttons": sum((bx(38.91, 44.91, r - 3, r + 3, BOARD_T, 4.85) + cyl(BUTTON_X, r, 4.85, STEM_TOP, STEM_D) for r in BUTTON_ROWS[1:]),
                       bx(38.91, 44.91, BUTTON_ROWS[0] - 3, BUTTON_ROWS[0] + 3, BOARD_T, 4.85) + cyl(BUTTON_X, BUTTON_ROWS[0], 4.85, STEM_TOP, STEM_D)),
        "slider": bx(37.56, 46.26, 32.44, 36.14, BOARD_T, 5) + bx(39.9, 42.9, 33.4, 35.2, 5, LEVER_TOP),
        "row 15 pins": bx(0.6, 24.8, hr(15) - 0.5, hr(15) + 0.5, BOARD_T, 3.6),
        "ESP32": bx(0, 25.6, 20.21, 38.21, ESP_FACE - 1.1, 0),
        "USB-C": bx(USB[0], USB[1], USB[2], USB[3], USB[4], USB[5]),
        "battery": bx(4, 36.2, 0, 19.8, LOWEST, -0.95),   # 502030P is 32 mm with its protection board
        "resistors": bx(26.4, 32.7, 20.5, 24.7, -2.2, 0),
        "joints": sum(joints[1:], joints[0]),
    }


def painted(shape, label, rgb, alpha=1.0):
    shape.label, shape.color = label, Color(*rgb, alpha)
    return shape


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    sh, bk = shell(), back()
    inside = parts_inside()
    case = {"shell": sh, "back plate": bk}
    names = list(case)
    for i, a in enumerate(names):                                   # case parts don't run into each other
        for b in names[i + 1:]:
            v = (case[a] & case[b]).volume
            assert v < 0.01, f"{a} / {b} overlap {v:.2f} mm3"
    for a, s in case.items():                                       # or into the watch
        for b, p in inside.items():
            v = (s & p).volume
            assert v < 0.01, f"{a} runs into {b}: {v:.2f} mm3"
    for p in (inside["ESP32"], inside["battery"], inside["USB-C"]):  # nothing hangs below the back plate's inside
        assert p.bounding_box().min.Z >= BACK_IN
    assert sh.is_valid and bk.is_valid

    export_stl(Pos(0, 0, TOP_OUT) * sh.rotate(Axis.X, 180), OUT / "shell.stl")  # face down, as it prints
    export_stl(Pos(0, 0, -BACK_OUT) * bk, OUT / "back.stl")
    export_stl(Pos(0, 0, TOP_OUT) * fit_plate(sh).rotate(Axis.X, 180), OUT / "fit-test.stl")
    (OUT / "button.stl").unlink(missing_ok=True)                    # the buttons are part of the shell now
    view = Compound(label="UtilWatch", children=[
        painted(sh, "Shell", (0.86, 0.88, 0.9)), painted(bk, "Back plate", (0.3, 0.32, 0.35)),
        *[painted(p, n, rgb) for n, p, rgb in [
            ("Perfboard", inside["board"], (0.12, 0.48, 0.33)), ("OLED", inside["OLED"], (0.1, 0.2, 0.55)),
            ("Buttons", inside["buttons"], (0.15, 0.16, 0.18)), ("Slider", inside["slider"], (0.76, 0.78, 0.8)),
            ("ESP32-C6", inside["ESP32"] + inside["USB-C"], (0.08, 0.09, 0.1)), ("LiPo", inside["battery"], (0.73, 0.75, 0.76)),
            ("Resistors", inside["resistors"], (0.85, 0.76, 0.6))]]])
    export_gltf(view, str(OUT / "watch.glb"), binary=True, linear_deflection=0.02, angular_deflection=0.2)
    size = (OX1 - OX0, OR1 - OR0, TOP_OUT - BACK_OUT)
    page = (Path(__file__).parent / "viewer.html").read_text()      # the viewer with the model inside it
    glb = base64.b64encode((OUT / "watch.glb").read_bytes()).decode()
    assert '"/*GLB*/"' in page and "/*DIMS*/" in page
    (OUT / "viewer.html").write_text(page.replace('"/*GLB*/"', '"%s"' % glb).replace("/*DIMS*/", "[%.1f, %.1f, %.1f]" % size))
    print("case %.1f x %.1f x %.1f mm (12-6 o'clock length includes the strap bars); nothing overlaps" % (size[0], size[1], size[2]))
    print("screws: 2 x M2.5 x 5 mm countersunk")
