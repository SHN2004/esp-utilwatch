# Builds kicad/carrier/utilwatch-carrier.kicad_pcb: a bare board that the parts you already have
# solder onto (the perfboard build in kicad/perfboard, as a PCB). Run with KiCad's own Python;
# pipeline.sh then routes it with Freerouting.
#   build_carrier.py <out.kicad_pcb>
# On the board: ESP32-C6 SuperMini (on its pin headers), the OLED's 4-pin header, 3 right-angle
# 6x6 mm buttons, 2 resistors + 1 capacitor (through-hole), a right-angle SS-12F23 slide switch at
# the bottom edge, and pads for the TP4056 module's OUT+/OUT- wires. The battery solders to the TP4056, not to this board.
import sys
import pcbnew

OUT = sys.argv[1]
FPDIR = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
W, H = 34.0, 36.0          # same outline as kicad/board, so it fits the same case
OX, OY = 100.0, 100.0
mm = pcbnew.FromMM

# SuperMini, measured off a photo of the real board (not a datasheet): 25.6 x 18 mm, 10 pins a side
# at 2.54 mm, rows about 16 mm apart. The holes are slots, so rows anywhere from ~14.5 to 17.5 mm fit.
SM_X, SM_Y = 1.0, 4.5      # top-left of the SuperMini's own board, USB end at the left edge
SM_LEN, SM_W = 25.6, 18.0
SM_PIN0 = 1.5              # USB edge to the first pin
SM_ROWS = 16.0
# Header order with the USB end first, as printed on the SuperMini. Seen from the top with the USB
# pointing left, the 5V row is on top (12 o'clock side) and the TX row at the bottom.
SM_TOP = ["5V", "GND", "3V3", "20", "19", "18", "15", "14", "9", "8"]      # pins 11-20
SM_BOTTOM = ["TX", "RX", "0", "1", "2", "3", "4", "5", "6", "7"]          # pins 1-10

NETS = {  # (ref, pin) -> net, from kicad/perfboard (same circuit)
    ("U1", "11"): "VSYS", ("U1", "12"): "GND", ("U1", "13"): "3V3", ("U1", "14"): "SCL",
    ("U1", "15"): "SDA", ("U1", "3"): "VBAT_SENSE", ("U1", "7"): "BTN_UP", ("U1", "8"): "BTN_DOWN",
    ("U1", "9"): "BTN_SELECT",   # pin 10 (GPIO7) is free: Back is a long press of Select
    ("J1", "1"): "3V3", ("J1", "2"): "GND", ("J1", "3"): "SCL", ("J1", "4"): "SDA",   # OLED, VCC GND SCL SDA as printed on the module
    ("SW2", "1"): "BTN_UP", ("SW3", "1"): "BTN_DOWN", ("SW4", "1"): "BTN_SELECT",
    ("SW2", "2"): "GND", ("SW3", "2"): "GND", ("SW4", "2"): "GND",
    ("R1", "1"): "VSYS", ("R1", "2"): "VBAT_SENSE", ("R2", "1"): "VBAT_SENSE", ("R2", "2"): "GND",
    ("C1", "1"): "VBAT_SENSE", ("C1", "2"): "GND",
    ("SW1", "3"): "VSYS", ("SW1", "2"): "VOUT",        # pin 1 (the switch's other throw) is unused
    ("J2", "1"): "VOUT", ("J2", "2"): "GND",           # TP4056 OUT+ / OUT-
}

# Three buttons on the right edge (the hand side on a left wrist) at 11 mm pitch, so a thumb finds
# each one without looking. Back is a long press of Select, firmware-wide (see remote/remote.ino),
# so there is no fourth button. The left edge is the USB-C plus the SuperMini's pin row, which
# leaves no room for the slider there; it goes on the bottom edge at the left end.
BUTTONS = (("SW2", "Up", 4.75), ("SW4", "Select", 15.75), ("SW3", "Down", 26.75))

# ref -> (library, footprint, value, x, y, rotation). Board coords: origin top-left, y down.
# The right-angle buttons' actuators point away from the board at rotation -90 (right) / 90 (left).
PARTS = {
    "J1": ("Connector_PinHeader_2.54mm", "PinHeader_1x04_P2.54mm_Vertical", "OLED", 13.19, 2.25, 90),
    # The three buttons are in BUTTONS below; the power slider is built in slide_switch().
    "R1": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical", "100k", 23.0, 25.0, 0),
    "R2": ("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical", "100k", 23.0, 28.0, 0),
    "C1": ("Capacitor_THT", "C_Disc_D3.0mm_W2.0mm_P2.50mm", "100nF", 23.0, 31.0, 0),
    "J2": ("Connector_PinHeader_2.54mm", "PinHeader_1x02_P2.54mm_Vertical", "TP4056 OUT", 17.0, 24.8, 90),
}


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def line(fp, layer, x0, y0, x1, y1, width=0.12):
    s = pcbnew.PCB_SHAPE(fp, pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(x0, y0))
    s.SetEnd(P(x1, y1))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    fp.Add(s)


def rect(fp, layer, x0, y0, x1, y1, width=0.12):
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        line(fp, layer, *a, *b, width)


def supermini(board):
    """The SuperMini on its headers: slotted holes, so the row spacing doesn't have to be exact."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("utilwatch", "ESP32-C6_SuperMini_Slotted"))
    fp.SetReference("U1")
    fp.SetValue("ESP32-C6 SuperMini")
    fp.SetPosition(P(0, 0))
    rows = ((SM_Y + (SM_W - SM_ROWS) / 2 + SM_ROWS, SM_BOTTOM, 1), (SM_Y + (SM_W - SM_ROWS) / 2, SM_TOP, 11))
    for y, names, first in rows:
        for i, name in enumerate(names):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(first + i))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetLayerSet(pad.PTHMask())
            pad.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_OVAL)
            pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(1.7), mm(3.4)))
            pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
            pad.SetDrillSize(pcbnew.VECTOR2I(mm(1.0), mm(2.4)))
            pad.SetPosition(P(SM_X + SM_PIN0 + i * 2.54, y))
            fp.Add(pad)
            t = pcbnew.PCB_TEXT(fp)  # pin name, inside the rows (outside them sit the other headers)
            t.SetText(name)
            t.SetLayer(pcbnew.B_SilkS)
            t.SetMirrored(True)
            t.SetTextSize(pcbnew.VECTOR2I(mm(0.7), mm(0.7)))
            t.SetTextThickness(mm(0.12))
            t.SetPosition(P(SM_X + SM_PIN0 + i * 2.54, y + (-2.4 if first == 1 else 2.4)))
            fp.Add(t)
    rect(fp, pcbnew.F_Fab, SM_X, SM_Y, SM_X + SM_LEN, SM_Y + SM_W, 0.1)  # outline, for the fit-check print
    rect(fp, pcbnew.F_Fab, SM_X - 1.0, SM_Y + 5.5, SM_X + 6.5, SM_Y + 12.5, 0.1)  # the USB-C socket
    rect(fp, pcbnew.F_CrtYd, SM_X - 0.25, SM_Y - 0.25, SM_X + SM_LEN + 0.25, SM_Y + SM_W + 0.25, 0.05)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    board.Add(fp)
    return fp


def npth(fp, x, y, d):
    pad = pcbnew.PAD(fp)
    pad.SetNumber("")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    pad.SetLayerSet(pad.UnplatedHoleMask())
    pad.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(d), mm(d)))
    pad.SetDrillSize(pcbnew.VECTOR2I(mm(d), mm(d)))
    pad.SetPosition(P(x, y))
    fp.Add(pad)


def button(board, ref, value, x, y, rot):
    """6x6 right-angle tactile switch with bracket (Daier KFC-A06W1, C&K PTS645Vx31, Omron
    B3F-315x): pins 4.5 mm apart, bracket legs 7 mm apart 2.5 mm behind them. Same holes as KiCad's
    Omron footprint, but the leg holes are unplated and the courtyard is tight, so three fit on one
    edge. Built with the actuator pointing -y, then rotated about pin 1."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("utilwatch", "SW_Tactile_6mm_Angled_Bracket"))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.SetPosition(P(x, y))
    for n, dx in (("1", 0.0), ("2", 4.5)):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(n)
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pad.PTHMask())
        pad.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(1.8), mm(1.8)))
        pad.SetDrillSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
        pad.SetPosition(P(x + dx, y))
        fp.Add(pad)
    for dx in (-1.25, 5.75):
        npth(fp, x + dx, y + 2.5, 1.3)
    rect(fp, pcbnew.F_Fab, x - 1.5, y - 2.4, x + 6.0, y + 4.1, 0.1)      # body and bracket
    rect(fp, pcbnew.F_Fab, x + 0.5, y - 6.7, x + 4.0, y - 2.4, 0.1)      # 4.3 mm actuator
    rect(fp, pcbnew.F_CrtYd, x - 2.15, y - 2.65, x + 6.65, y + 4.35, 0.05)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    return fp


def slide_switch(board, cx, cy, rot):
    """SS-12F23 right-angle slide switch, built with its knob pointing +y and then rotated by rot about
    the middle pin at (cx, cy). Three pins at
    3.0 mm plus a mounting tab at each end of the body. The tab spots come from the vendor drawing,
    not a measured part, so they are slots: check them on the fit-check print before ordering."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPID(pcbnew.LIB_ID("utilwatch", "SW_Slide_SS-12F23_Angled"))
    fp.SetReference("SW1")
    fp.SetValue("Power switch")
    fp.SetPosition(P(cx, cy))  # pin row; the knob face is 3.3 mm from it toward the edge
    for i in range(3):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(i + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pad.PTHMask())
        pad.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(1.7), mm(1.7)))
        pad.SetDrillSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
        pad.SetPosition(P(cx + (i - 1) * 3.0, cy))
        fp.Add(pad)
    for sx in (-6.2, 6.2):     # mounting tabs: 0.45 mm sheet metal, long axis toward the edge
        pad = pcbnew.PAD(fp)
        pad.SetNumber("")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pad.PTHMask())
        pad.SetShape(pcbnew.F_Cu, pcbnew.PAD_SHAPE_OVAL)
        pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(1.6), mm(2.6)))
        pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
        pad.SetDrillSize(pcbnew.VECTOR2I(mm(0.8), mm(1.8)))
        pad.SetPosition(P(cx + sx, cy))
        fp.Add(pad)
    rect(fp, pcbnew.F_Fab, cx - 6.45, cy - 2.2, cx + 6.45, cy + 3.3, 0.1)       # body, face at the edge
    rect(fp, pcbnew.F_Fab, cx - 1.5, cy + 3.3, cx + 1.5, cy + 8.3, 0.1)         # 5 mm knob, mid-travel
    rect(fp, pcbnew.F_CrtYd, cx - 6.7, cy - 2.45, cx + 6.7, cy + 3.55, 0.05)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    return fp


board = pcbnew.CreateEmptyBoard()
board.SetCopperLayerCount(2)
ds = board.GetDesignSettings()
ds.m_CopperEdgeClearance = mm(0.3)

nets = {}
for name in sorted(set(NETS.values())):
    nets[name] = pcbnew.NETINFO_ITEM(board, name)
    board.Add(nets[name])

fps = {"U1": supermini(board), "SW1": slide_switch(board, 10.3, 33.0, 0)}
for ref, value, y in BUTTONS:
    fps[ref] = button(board, ref, value, 31.2, y, -90)
for ref, (lib, name, value, x, y, rot) in PARTS.items():
    fp = pcbnew.FootprintLoad(f"{FPDIR}/{lib}.pretty", name)
    fp.SetReference(ref)
    fp.SetValue(value)
    board.Add(fp)
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    fps[ref] = fp
for ref, fp in fps.items():
    for pad in fp.Pads():
        net = NETS.get((ref, pad.GetNumber()))
        if net:
            pad.SetNet(nets[net])

r = 3.0
edge = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
edge.SetStart(P(0, 0))
edge.SetEnd(P(W, H))
edge.SetCornerRadius(mm(r))
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetWidth(mm(0.1))
board.Add(edge)


def outline(zone, x0, y0, x1, y1):
    ol = zone.Outline()
    ol.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        ol.Append(mm(OX + x), mm(OY + y))


for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(nets["GND"])
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    outline(z, 0, 0, W, H)
    board.Add(z)

def keepout(pts, zones, tracks):
    keep = pcbnew.ZONE(board)
    keep.SetIsRuleArea(True)
    keep.SetDoNotAllowZoneFills(zones)
    keep.SetDoNotAllowTracks(tracks)
    keep.SetDoNotAllowVias(tracks)
    keep.SetDoNotAllowPads(False)
    keep.SetDoNotAllowFootprints(False)
    keep.SetLayerSet(pcbnew.LSET.AllCuMask())
    ol = keep.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(keep)


def box(x0, y0, x1, y1):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


# No ground plane under the SuperMini's chip antenna (the far end from the USB), or BLE range drops.
keepout(box(SM_X + SM_LEN - 4.0, SM_Y + 3.0, SM_X + SM_LEN + 0.5, SM_Y + SM_W - 3.0), True, False)


def silk(s, x, y, size=0.8, layer=pcbnew.F_SilkS, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetTextAngleDegrees(angle)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(size * 0.15, 0.12)))
    t.SetMirrored(layer == pcbnew.B_SilkS)
    board.Add(t)


B = pcbnew.B_SilkS  # the top side is covered by the SuperMini and OLED: labels go on the back
silk("VCC GND SCL SDA", 17.0, 0.9, 0.7, B)
silk("UP", 28.0, 6.9, 0.8, B)
silk("SEL", 28.0, 17.9, 0.8, B)
silk("DOWN", 28.0, 28.9, 0.8, B)
silk("TP4056", 15.2, 26.1, 0.6, B, 90)
silk("+", 17.0, 26.9, 0.8, B)
silk("-", 19.54, 26.9, 0.8, B)
silk("SWITCH", 10.3, 35.3, 0.6, B)
silk("UtilWatch carrier v0.1", 14.0, 13.5, 0.7, B)

board.SetFileName(OUT)
pcbnew.SaveBoard(OUT, board)
print("saved", OUT, len(fps), "parts", len(nets), "nets")
