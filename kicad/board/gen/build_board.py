# Builds kicad/board/utilwatch.kicad_pcb from the schematic's netlist: outline, placement, nets, rules,
# ground planes. Run with KiCad's own Python. Routing is done afterwards by Freerouting.
#   build_board.py <netlist> <out.kicad_pcb>
import re, sys
import pcbnew

NETLIST, OUT = sys.argv[1], sys.argv[2]
FPDIR = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
W, H = 34.0, 36.0          # board, mm (case inside is 36 x 36.6)
OX, OY = 100.0, 100.0      # where the board sits on the KiCad page
mm = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


# ---- netlist (KiCad s-expression)
text = open(NETLIST).read()
comps = {}
for c in re.finditer(r"\(comp\n\t\t\t\(ref \"([^\"]+)\"\)([\s\S]*?)\n\t\t\)", text):
    body = c.group(2)
    get = lambda k: (re.search(rf'\({k} "([^"]*)"\)', body) or [None, ""])[1]
    lcsc = re.search(r"\(name \"LCSC\"\) \"([^\"]*)\"\)", body)
    comps[c.group(1)] = dict(value=get("value"), footprint=get("footprint"),
                             tstamp=[t for t in re.findall(r'\(tstamps "([^"]+)"\)', body) if t != "/"][-1],
                             lcsc=lcsc.group(1) if lcsc else "")
pin_net = {}
for n in re.finditer(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]+)"\)([\s\S]*?)\n\t\t\)', text):
    for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', n.group(2)):
        pin_net[(ref, pin)] = n.group(1).lstrip("/")

# ---- placement: ref -> (x, y, rotation°, side). Board coords, origin top-left, y down.
# Edges: left = USB-C, Back button, power switch; right = Up/Select/Down; top = OLED + battery holes;
# bottom = ESP32 antenna, with Espressif's copper keep-out strip across the board.
PLACE = {
    "U1": (17.0, 25.0, 180),          # antenna end flush with the bottom edge
    "J1": (3.0, 6.5, -90),            # USB-C, front 0.65 mm past the left edge
    "SW2": (31.75, 6.0, -90),         # Up      (stem 0.5 mm past the right edge)
    "SW4": (31.75, 15.0, -90),        # Select
    "SW3": (31.75, 24.0, -90),        # Down
    "SW5": (2.25, 16.5, 90),          # Back, left edge
    "SW1": (1.8, 25.5, -90),          # power slide switch, lever out of the left edge
    "J3": (13.19, 2.2, 90),           # OLED pins GND VCC SCL SDA, left to right
    "J2": (25.0, 2.2, 90),            # battery + -
    # USB / charger (row under the top header)
    "R1": (10.6, 5.0, 0), "C1": (10.6, 7.0, 0), "R2": (10.6, 9.0, 0),
    "U2": (14.6, 8.0, 0), "R3": (14.6, 11.6, 0), "C2": (18.4, 11.2, 0),
    "D2": (18.4, 5.6, 0), "R4": (18.4, 7.6, 0),
    # power path + regulator
    "D1": (22.6, 6.0, 0), "Q1": (22.6, 9.6, 0), "R5": (22.6, 12.8, 0),
    "U3": (26.6, 10.0, 90), "C3": (26.6, 6.2, 0), "C4": (26.6, 13.8, 0),
    # battery divider, boot/strap pull-ups: between the regulator and the module
    "R6": (22.6, 15.6, 0), "R7": (22.6, 17.6, 0), "C5": (19.0, 17.6, 0),
    "R9": (11.6, 16.6, 0), "R10": (14.8, 16.6, 0),
    # right of the module: EN reset RC and 3.3 V decoupling (3V3 pin is on this side)
    "R8": (26.1, 17.0, 0), "C8": (26.1, 19.0, 0), "C6": (26.1, 26.4, 0), "C7": (26.1, 28.4, 0),
    "JP1": (7.8, 26.6, 90),
}

board = pcbnew.CreateEmptyBoard()
board.SetCopperLayerCount(2)
ds = board.GetDesignSettings()
# JLCPCB 2-layer limits are 0.127 mm track/space and 0.3 mm drill; stay well above them.
ds.m_MinClearance = mm(0.15)
ds.m_TrackMinWidth = mm(0.15)
ds.m_ViasMinSize = mm(0.5)
ds.m_MinThroughDrill = mm(0.3)
ds.m_CopperEdgeClearance = mm(0.3)
ds.m_HoleToHoleMin = mm(0.25)
ds.m_TentViasFront = True  # solder mask over vias: some sit under the ESP32 module
ds.m_TentViasBack = True
ns = ds.m_NetSettings
default = ns.GetDefaultNetclass()
default.SetClearance(mm(0.2))
default.SetTrackWidth(mm(0.25))
default.SetViaDiameter(mm(0.6))
default.SetViaDrill(mm(0.3))
power = pcbnew.NETCLASS("Power")
power.SetClearance(mm(0.2))
power.SetTrackWidth(mm(0.5))
power.SetViaDiameter(mm(0.7))
power.SetViaDrill(mm(0.35))
ns.SetNetclass("Power", power)
for net in ("VBUS", "VSYS", "BAT", "3V3", "GND"):
    ns.SetNetclassPatternAssignment(net, "Power")

nets = {}
for name in sorted(set(pin_net.values())):
    ni = pcbnew.NETINFO_ITEM(board, name)
    board.Add(ni)
    nets[name] = ni

for ref, c in comps.items():
    lib, name = c["footprint"].split(":")
    fp = pcbnew.FootprintLoad(f"{FPDIR}/{lib}.pretty", name)
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    fp.SetPath(pcbnew.KIID_PATH(f"/{c['tstamp']}"))
    if c["lcsc"]:
        fp.SetField("LCSC", c["lcsc"])
        fp.GetField("LCSC").SetVisible(False)
    board.Add(fp)
    x, y, rot = PLACE[ref]
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    for pad in fp.Pads():
        net = pin_net.get((ref, pad.GetNumber()))
        if net:
            pad.SetNet(nets[net])
    fp.Reference().SetVisible(False)  # too dense for reference labels; the fab drawing has them
    fp.Value().SetVisible(False)

# ---- outline: rounded rectangle
r = 3.0
edge = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
edge.SetStart(P(0, 0))
edge.SetEnd(P(W, H))
edge.SetCornerRadius(mm(r))
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetWidth(mm(0.1))
board.Add(edge)

# ---- ground planes, both sides
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(nets["GND"])
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((0, 0), (W, 0), (W, H), (0, H)):
        ol.Append(mm(OX + x), mm(OY + y))
    board.Add(z)


def silk(s, x, y, size=0.8, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetMirrored(layer == pcbnew.B_SilkS)
    board.Add(t)


silk("+", 25.0, 4.0)
silk("-", 27.54, 4.0)
silk("GND VCC SCL SDA", 17.0, 4.5)
silk("UtilWatch v0.1", 17.0, 33.0, 1.0, pcbnew.B_SilkS)

board.SetFileName(OUT)
pcbnew.SaveBoard(OUT, board)
print("saved", OUT, len(comps), "parts", len(nets), "nets")
