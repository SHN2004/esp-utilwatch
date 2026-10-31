# 3D model of the watch: the real main board (from KiCad), the OLED, battery and a case around them,
# so we can see if it fits before printing or ordering.
#   uv run python case/watch.py
# Writes case/build/: watch.step (everything, opens in KiCad/FreeCAD/Fusion), watch.json (for
# case/viewer.html), and case_body.stl + case_back.stl + button_cap.stl (to 3D print; print 4 caps).
# X = across the face (left to right), Y = 12 o'clock is +Y, Z = up out of the screen.
import base64
import json
import subprocess
from pathlib import Path
from build123d import (Align, Axis, Box, Color, Compound, Cylinder, Pos, Rot, export_gltf, export_step,
                       export_stl, fillet, import_step)

HERE = Path(__file__).parent
PCB = HERE.parent / "kicad/board/utilwatch.kicad_pcb"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# All sizes in mm. The OLED and battery sizes are typical datasheet sizes, not measured: measure your
# parts with calipers and fix them here, everything else follows. The board comes from KiCad.
WALL, TOP, BACK = 2.0, 1.2, 1.5  # case side wall, bezel over the screen, back plate
GAP = 0.3                        # clearance around parts
BOARD = (34.0, 36.0, 1.6)        # kicad/board, centred here
OLED_PCB = (35.4, 33.5, 1.2)     # 1.3" SH1106 module
OLED_GLASS = (34.5, 23.0, 1.5)
OLED_ACTIVE = (29.42, 14.7)      # the lit pixels
OLED_GLASS_Y = -1.0              # glass centre below the PCB centre (header pins are on top)
OLED_GAP = 4.5                   # board top to OLED PCB: clears the 3.3 mm USB-C socket and the OLED's own parts
BATTERY = (30.0, 20.0, 5.0)      # 502030 LiPo, about 250 mAh, under the board
BATTERY_Y = 4.0                  # kept clear of the ESP32 antenna strip at the bottom of the board

# Where things sit on the board, from kicad/board/gen/build_board.py (board coords: origin top-left, y down).
def on_board(x, y):
    return x - BOARD[0] / 2, BOARD[1] / 2 - y


USB_Y = on_board(3.0, 6.5)[1]
SWITCH_Y = on_board(1.8, 26.3)[1]                       # the lever, not the switch body
BUTTONS = {"Up": (1, on_board(0, 6.0)[1]), "Select": (1, on_board(0, 15.0)[1]),
           "Down": (1, on_board(0, 24.0)[1]), "Back": (-1, on_board(0, 16.5)[1])}  # side (-1 left, 1 right), y
STEM_Z = 0.8                     # side-button stem height above the board (EVQ-PUA is 1.65 tall)
STEM_OUT = 0.5                   # stems stick out of the board edge by this much

IN_X = max(OLED_PCB[0], BOARD[0]) + 2 * GAP + 1.0       # 1 mm more: room for the button caps' flanges
IN_Y = max(OLED_PCB[1], BOARD[1]) + 2 * GAP
BOARD_Z = BACK + BATTERY[2] + 0.5                        # bottom of the board
BOARD_TOP = BOARD_Z + BOARD[2]
OLED_Z = BOARD_TOP + OLED_GAP
GLASS_TOP = OLED_Z + OLED_PCB[2] + OLED_GLASS[2]
OUT_X, OUT_Y, OUT_Z = IN_X + 2 * WALL, IN_Y + 2 * WALL, GLASS_TOP + TOP


def block(sx, sy, sz, x=0, y=0, z=0):
    """A box with its bottom face at z, centred on x, y."""
    return Pos(x, y, z) * Box(sx, sy, sz, align=(Align.CENTER, Align.CENTER, Align.MIN))


def part(shape, label, rgb, alpha=1.0):
    shape.label, shape.color = label, Color(*rgb, alpha)
    return shape


def side_cylinder(side, y, z, d, x0, x1):
    """A cylinder along X from x0 to x1 (outward on that side)."""
    return Pos(side * (x0 + x1) / 2, y, z) * Rot(0, 90, 0) * Cylinder(d / 2, x1 - x0)


def main_board():
    """The KiCad board with its parts, plus boxes for the three parts KiCad has no 3D model for."""
    step = HERE / "build/board.step"
    subprocess.run([KICAD_CLI, "pcb", "export", "step", PCB, "-o", step, "--user-origin", "117x118mm",
                    "--subst-models", "-f"], check=True, capture_output=True)
    # Flattened to plain solids: the STEP nests each part's position inside another, which booleans misread.
    # The pin-header models stand for the OLED's own pins and the battery leads: leave them out.
    children = []
    for c in import_step(step).children:
        if c.label.startswith("PinHeader"):
            continue
        color = next((s.color for s in c.children if s.color), c.color)
        for s in c.solids():
            s.label, s.color = c.label, color
            children.append(s)
    dark, metal = (0.15, 0.15, 0.16), (0.75, 0.76, 0.78)
    esp_x, esp_y = on_board(17.0, 25.0 + 2.7)          # module 13.2 x 16.6, antenna end on the bottom edge
    children += [
        part(block(13.2, 16.6, 2.4, esp_x, esp_y, BOARD[2]), "ESP32-C6-MINI-1", metal),
        part(block(7.3, 8.94, 3.26, -BOARD[0] / 2 + 3.0, USB_Y, BOARD[2]), "USB-C", metal),
        part(block(2.8, 6.7, 1.4, -BOARD[0] / 2 + 1.8, on_board(0, 25.5)[1], BOARD[2]), "Power switch", dark),
        part(block(1.45, 1.3, 1.0, -BOARD[0] / 2 - 0.33, SWITCH_Y, BOARD[2] + 0.2), "Switch lever", dark),
    ]
    board = Pos(0, 0, BOARD_Z) * Compound(children=children)
    board.label = "Main board"
    return board


def case_body():
    shell = fillet(block(OUT_X, OUT_Y, OUT_Z - BACK, z=BACK).edges().filter_by(Axis.Z), 4)
    shell -= fillet(block(IN_X, IN_Y, GLASS_TOP - BACK, z=BACK).edges().filter_by(Axis.Z), 1)
    shell -= block(OLED_ACTIVE[0] + 2, OLED_ACTIVE[1] + 2, TOP + 1, y=OLED_GLASS_Y, z=GLASS_TOP - 0.5)
    left = -OUT_X / 2 + WALL / 2
    # USB-C: big enough for the plug's moulded grip, which stops at the socket face
    usb = fillet(block(WALL + 1, 12.4, 6.6).edges().filter_by(Axis.X), 3)
    shell -= Pos(left, USB_Y, BOARD_TOP + 1.63 - 3.3) * usb
    # power switch: a slot for the lever (push it with a fingernail or toothpick)
    shell -= Pos(left, SWITCH_Y, BOARD_TOP + 0.2 - 0.4) * block(WALL + 1, 3.6, 1.8)
    for side, y in BUTTONS.values():
        shell -= side_cylinder(side, y, BOARD_TOP + STEM_Z, 3.3, IN_X / 2 - 0.1, OUT_X / 2 + 0.1)
    return part(shell, "Case", (0.80, 0.82, 0.85), 0.35)


def button_cap(side, y):
    """Printed plunger: a flange inside the wall keeps it in, the shaft sticks out 1 mm."""
    stem_tip = BOARD[0] / 2 + STEM_OUT
    flange = side_cylinder(side, y, BOARD_TOP + STEM_Z, 4.2, stem_tip + 0.05, IN_X / 2 - 0.05)
    shaft = side_cylinder(side, y, BOARD_TOP + STEM_Z, 3.0, IN_X / 2 - 0.05, OUT_X / 2 + 1.0)
    return flange + shaft


def case_back():
    return part(fillet(block(OUT_X, OUT_Y, BACK).edges().filter_by(Axis.Z), 4), "Back plate", (0.62, 0.64, 0.68))


def oled():
    pcb = block(*OLED_PCB, z=OLED_Z)
    for sx in (-1, 1):
        for sy in (-1, 1):  # M2 mounting holes
            pcb -= Pos(sx * (OLED_PCB[0] / 2 - 2.5), sy * (OLED_PCB[1] / 2 - 2.5), OLED_Z) * Cylinder(1.1, 5)
    glass_z = OLED_Z + OLED_PCB[2]
    return Compound(label="OLED module", children=[  # one bought module; the pieces only give it colours
        part(pcb, "board", (0.10, 0.32, 0.72)),
        part(block(*OLED_GLASS, y=OLED_GLASS_Y, z=glass_z), "glass", (0.06, 0.06, 0.08)),
        part(block(*OLED_ACTIVE, 0.02, y=OLED_GLASS_Y, z=GLASS_TOP), "pixels", (0.12, 0.55, 0.85)),
    ])


def battery():
    cell = fillet(block(*BATTERY, y=BATTERY_Y, z=BACK).edges().filter_by(Axis.Z), 1.5)
    return part(cell, "LiPo battery", (0.78, 0.78, 0.74))


def watch():
    caps = Compound(label="Button caps", children=[
        part(button_cap(side, y), name, (0.92, 0.55, 0.15)) for name, (side, y) in BUTTONS.items()])
    return [case_body(), case_back(), oled(), main_board(), battery(), caps]


def overlaps(parts):
    """Pairs of parts that run into each other (touching is fine)."""
    bad = []
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            v = (a & b).volume
            if v > 0.01:
                bad.append(f"{a.label} / {b.label}: {v:.2f} mm³")
    return bad


def gltf_json(glb, out):
    """Wraps the .glb in a .json file as base64 (the artifact host serves .json but not .glb)."""
    data = json.dumps({"glb": base64.b64encode(glb.read_bytes()).decode()})
    out.write_text(data)
    # Same viewer with the model inside it, for publishing: public viewers can't fetch side files.
    page = (HERE / "viewer.html").read_text()
    three = '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js">'
    assert three in page, "viewer.html no longer loads three.min.js: update the anchor here"
    (out.parent / "viewer.html").write_text(page.replace(three, f"<script>window.WATCH = {data};</script>\n{three}", 1))


if __name__ == "__main__":
    out = HERE / "build"
    out.mkdir(exist_ok=True)
    parts = watch()
    clash = overlaps(parts)
    assert not clash, "parts overlap:\n  " + "\n  ".join(clash)

    everything = Compound(children=parts, label="UtilWatch")
    export_step(everything, out / "watch.step")
    export_gltf(everything, out / "watch.glb", binary=True, linear_deflection=0.02, angular_deflection=0.2)
    gltf_json(out / "watch.glb", out / "watch.json")
    export_stl(parts[0], out / "case_body.stl")
    export_stl(parts[1], out / "case_back.stl")
    export_stl(button_cap(1, 0), out / "button_cap.stl")
    print(f"case outside: {OUT_X:.1f} x {OUT_Y:.1f} x {OUT_Z:.1f} mm, no parts overlap")
