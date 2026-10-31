# Generated the first kicad/board/utilwatch.kicad_sch (the schematic is edited in KiCad now; rerunning
# this overwrites it).  uv run python kicad/board/gen/make_board_sch.py kicad/board
import re, sys, uuid
from pathlib import Path

OUT = Path(sys.argv[1])
STOCK = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
ROOT = str(uuid.uuid4())
U = lambda: str(uuid.uuid4())
FH = '(effects (font (size 1.27 1.27)) (hide yes))'


def block(t, start):
    d = 0
    for i in range(start, len(t)):
        if t[i] == '(':
            d += 1
        elif t[i] == ')':
            d -= 1
            if d == 0:
                return t[start:i + 1]


def lib_symbol(lib, name):
    t = open(f"{STOCK}/{lib}.kicad_sym").read()
    b = block(t, t.find(f'\n\t(symbol "{name}"\n') + 2)
    m = re.search(r'\(extends "([^"]+)"\)', b)
    if not m:
        return b
    # Derived symbol (e.g. AO3401A from TP0610T): parent's drawing and pins, child's fields.
    parent = block(t, t.find(f'\n\t(symbol "{m.group(1)}"\n') + 2)
    parent = parent.replace(f'"{m.group(1)}', f'"{name}')
    for field in ("Value", "Footprint", "Datasheet", "Description"):
        child = re.search(rf'\(property "{field}"', b)
        par = re.search(rf'\(property "{field}"', parent)
        if child and par:
            parent = parent.replace(block(parent, par.start()), block(b, child.start()), 1)
    return parent


SYMS = {}
for lib, name in [("RF_Module", "ESP32-C6-MINI-1"), ("Connector", "USB_C_Receptacle_USB2.0_16P"),
                  ("Battery_Management", "MCP73831-2-OT"), ("Regulator_Linear", "ME6211C33M5"),
                  ("Transistor_FET", "AO3401A"), ("Device", "D_Schottky"), ("Device", "LED"),
                  ("Device", "R"), ("Device", "C"), ("Connector_Generic", "Conn_01x02"),
                  ("Connector_Generic", "Conn_01x04"), ("Switch", "SW_Push"), ("Switch", "SW_SPDT"), ("Jumper", "SolderJumper_2_Open"),
                  ("power", "GND"), ("power", "PWR_FLAG")]:
    SYMS[f"{lib}:{name}"] = lib_symbol(lib, name)

PINS = {k: {n: (float(x), float(y), int(float(a))) for x, y, a, n in
            re.findall(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)[\s\S]*?\(number "([^"]*)"', v)}
        for k, v in SYMS.items()}

items = []
count = {"pwr": 0, "flg": 0}


def lib_prop(lib_id, name, value, x, y):
    t = SYMS[lib_id]
    b = block(t, t.index(f'(property "{name}"'))
    m = re.search(r'\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', b)
    px, py, a = map(float, m.groups())
    b = b.replace(m.group(0), f"(at {round(x + px, 2)} {round(y - py, 2)} {int(a)})", 1)
    return re.sub(rf'^\(property "{name}" "[^"]*"', f'(property "{name}" "{value}"', b)


def symbol(lib_id, ref, value, x, y, footprint="", lcsc="", in_bom=True):
    pin_lines = " ".join(f'(pin "{n}" (uuid "{U()}"))' for n in PINS[lib_id])
    extra = f'(property "LCSC" "{lcsc}" (at {x} {y} 0) {FH})' if lcsc else ""
    items.append(f'''(symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit 1)
  (exclude_from_sim no) (in_bom {"yes" if in_bom else "no"}) (on_board yes) (dnp no) (uuid "{U()}")
  {lib_prop(lib_id, "Reference", ref, x, y)}
  {lib_prop(lib_id, "Value", value, x, y)}
  (property "Footprint" "{footprint}" (at {x} {y} 0) {FH})
  (property "Datasheet" "" (at {x} {y} 0) {FH})
  (property "Description" "" (at {x} {y} 0) {FH})
  {extra}
  {pin_lines}
  (instances (project "utilwatch" (path "/{ROOT}" (reference "{ref}") (unit 1))))
)''')
    return {n: (round(x + px, 2), round(y - py, 2), a) for n, (px, py, a) in PINS[lib_id].items()}


def gnd(x, y):
    count["pwr"] += 1
    symbol("power:GND", f"#PWR0{count['pwr']:02d}", "GND", x, y)


def wire(x1, y1, x2, y2):
    items.append(f'(wire (pts (xy {x1} {y1}) (xy {x2} {y2})) (stroke (width 0) (type default)) (uuid "{U()}"))')


def label(net, x, y, a):
    angle, just = {0: (180, "right"), 180: (0, "left"), 90: (270, "right"), 270: (90, "left")}[a]
    items.append(f'(label "{net}" (at {x} {y} {angle}) (effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{U()}"))')


def connect(pins, nets):
    """nets: {pin number: net name, "GND", or None for not connected}. Stacked pins are done once."""
    done = set()
    for num, net in nets.items():
        x, y, a = pins[num]
        if (x, y) in done:
            continue
        done.add((x, y))
        if net is None:
            items.append(f'(no_connect (at {x} {y}) (uuid "{U()}"))')
        elif net == "GND" and a == 90:
            gnd(x, y)
        elif net == "GND":
            sx = x - 10.16 if a == 0 else x + 10.16
            wire(x, y, sx, y)
            gnd(sx, y)
        else:
            label(net, x, y, a)


def flag(net, x, y):
    """PWR_FLAG: tells ERC this net is powered from outside (USB, battery)."""
    count["flg"] += 1
    symbol("power:PWR_FLAG", f"#FLG0{count['flg']}", "PWR_FLAG", x, y)
    if net == "GND":
        gnd(x, y)
    else:
        label(net, x, y, 90)


def part(lib_id, ref, value, x, y, nets, footprint, lcsc, in_bom=True):
    connect(symbol(lib_id, ref, value, x, y, footprint, lcsc, in_bom), nets)


def text(s, x, y, size=1.27):
    s = s.replace('"', '\\"').replace("\n", "\\n")
    items.append(f'(text "{s}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size {size} {size})) (justify left top)) (uuid "{U()}"))')


R, C = "Device:R", "Device:C"
R06, C06 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
LCSC_R = {"10k": "C25804", "5.1k": "C23186", "1k": "C21190", "100k": "C25803", "470k": "C23178"}
LCSC_C = {"10uF": "C19702", "1uF": "C15849", "100nF": "C14663"}


def res(ref, value, x, y, top, bottom):
    part(R, ref, value, x, y, {"1": top, "2": bottom}, R06, LCSC_R[value])


def cap(ref, value, x, y, top, bottom="GND"):
    part(C, ref, value, x, y, {"1": top, "2": bottom}, C06, LCSC_C[value])


# ---- USB-C: power in + the ESP32-C6's own USB (flashing and serial, like the SuperMini)
part("Connector:USB_C_Receptacle_USB2.0_16P", "J1", "USB-C", 40.64, 76.2,
     {"A1": "GND", "A4": "VBUS", "A5": "CC1", "A6": "USB_DP", "A7": "USB_DN", "A8": None, "B5": "CC2",
      "B6": "USB_DP", "B7": "USB_DN", "B8": None, "SH": "GND"},
     "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", "C165948")
res("R1", "5.1k", 71.12, 101.6, "CC1", "GND")
res("R2", "5.1k", 81.28, 101.6, "CC2", "GND")
flag("VBUS", 68.58, 55.88)

# ---- charger: MCP73831, about 200 mA (1000 V / 5.1 kΩ)
part("Battery_Management:MCP73831-2-OT", "U2", "MCP73831", 121.92, 76.2,
     {"1": "CHG_LED", "2": "GND", "3": "BAT", "4": "VBUS", "5": "PROG"},
     "Package_TO_SOT_SMD:SOT-23-5", "C424093")
res("R3", "5.1k", 101.6, 101.6, "PROG", "GND")
cap("C1", "10uF", 109.22, 50.8, "VBUS")
cap("C2", "10uF", 142.24, 101.6, "BAT")
part("Device:LED", "D2", "Charging", 127.0, 45.72, {"1": "CHG_LED", "2": "LED_A"},
     "LED_SMD:LED_0603_1608Metric", "C2286")
res("R4", "1k", 142.24, 50.8, "VBUS", "LED_A")

# Battery leads solder into these two holes (pin 1 = +): no room for a JST plug on a watch-sized board.
part("Connector_Generic:Conn_01x02", "J2", "Battery (+ -)", 121.92, 127.0, {"1": "BAT", "2": "GND"},
     "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", "", in_bom=False)

# ---- power path: USB runs the watch through D1 when plugged in, else the battery through Q1
part("Device:D_Schottky", "D1", "B5819W", 177.8, 60.96, {"1": "VSYS", "2": "VBUS"},
     "Diode_SMD:D_SOD-123", "C8598")
part("Transistor_FET:AO3401A", "Q1", "AO3401A", 177.8, 83.82, {"1": "VBUS", "2": "VSYS", "3": "BAT"},
     "Package_TO_SOT_SMD:SOT-23", "C15127")
res("R5", "100k", 167.64, 101.6, "VBUS", "GND")
flag("VSYS", 195.58, 55.88)

# ---- 3.3 V regulator, turned on/off by the power switch
part("Regulator_Linear:ME6211C33M5", "U3", "ME6211C33", 233.68, 76.2,
     {"1": "VSYS", "2": "GND", "3": "PWR_EN", "4": None, "5": "3V3"},
     "Package_TO_SOT_SMD:SOT-23-5", "C82942")
cap("C3", "10uF", 215.9, 99.06, "VSYS")
cap("C4", "10uF", 251.46, 99.06, "3V3")
part("Switch:SW_SPDT", "SW1", "Power", 233.68, 114.3, {"1": "VSYS", "2": "PWR_EN", "3": "GND"},
     "Button_Switch_SMD:SW_SPDT_Shouhan_MSK12C02", "C431540")

# ---- battery level: BAT/2 on IO0 (ADC1_CH0); 470k + 470k draws under 5 µA
res("R6", "470k", 187.96, 129.54, "BAT", "VBAT_SENSE")
res("R7", "470k", 187.96, 137.16, "VBAT_SENSE", "GND")
cap("C5", "100nF", 198.12, 137.16, "VBAT_SENSE")

# ---- ESP32-C6
part("RF_Module:ESP32-C6-MINI-1", "U1", "ESP32-C6-MINI-1-N4", 299.72, 129.54,
     {"3": "3V3", "1": "GND", "8": "EN", "12": "VBAT_SENSE", "13": None, "5": None, "6": None,
      "9": "BTN_UP", "10": "BTN_DOWN", "15": "BTN_SELECT", "16": "BTN_BACK", "22": "IO8", "23": "BOOT",
      "31": None, "30": None, "17": "USB_DN", "18": "USB_DP", "19": None, "20": None, "24": None,
      "25": "SDA", "26": "SCL", "27": None, "28": None, "29": None},
     "RF_Module:ESP32-C6-MINI-1", "C5736265")
cap("C6", "10uF", 279.4, 83.82, "3V3")
cap("C7", "100nF", 289.56, 83.82, "3V3")
res("R8", "10k", 254.0, 139.7, "3V3", "EN")
cap("C8", "1uF", 254.0, 160.02, "EN")
res("R9", "10k", 264.16, 139.7, "3V3", "BOOT")
res("R10", "10k", 274.32, 139.7, "3V3", "IO8")  # strapping pin: keep high
# Boot mode: short JP1 with tweezers while switching on (only needed if USB flashing stops working).
# Reset: flip the power switch off and on.
part("Jumper:SolderJumper_2_Open", "JP1", "Boot", 248.92, 175.26, {"1": "BOOT", "2": "GND"},
     "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", "", in_bom=False)

# ---- watch buttons on the side of the board (same GPIOs as the breadboard build)
EVQ = "Button_Switch_SMD:Panasonic_EVQPUJ_EVQPUA"
for i, (ref, net, name) in enumerate((("SW2", "BTN_UP", "Up"), ("SW3", "BTN_DOWN", "Down"),
                                       ("SW4", "BTN_SELECT", "Select"), ("SW5", "BTN_BACK", "Back"))):
    part("Switch:SW_Push", ref, name, 360.68, 104.14 + i * 12.7, {"1": net, "2": "GND"}, EVQ, "C128539")

# ---- OLED module: you solder its 4 pins into these holes
part("Connector_Generic:Conn_01x04", "J3", "OLED (GND VCC SCL SDA)", 365.76, 172.72,
     {"1": "GND", "2": "3V3", "3": "SCL", "4": "SDA"},
     "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "", in_bom=False)
flag("GND", 340.36, 200.66)

text("UtilWatch board", 25.4, 22.86, 2.54)
text("Factory-assembled (JLCPCB parts, LCSC numbers in each part's LCSC field). You solder the OLED and the battery leads.\n"
     "Same GPIOs as the breadboard build: buttons IO4-7 to GND, OLED SDA IO19 / SCL IO20. Flash over USB-C (IO12/IO13).", 25.4, 30.48)
text("Power:\n"
     "- USB plugged in: D1 feeds VSYS and Q1 is off, so the charger only charges the battery.\n"
     "- Unplugged: Q1 connects the battery to VSYS.\n"
     "- SW1 switches the 3.3 V regulator. Charging works with SW1 off; the watch (and USB flashing) needs SW1 on.\n"
     "- Use a LiPo with its own protection board (most hobby cells have one). Battery red lead to J2 pin 1 (+).", 25.4, 210.82)

sch = f'''(kicad_sch
  (version 20250114)
  (generator "eeschema")
  (generator_version "9.0")
  (uuid "{ROOT}")
  (paper "A3")
  (title_block (title "UtilWatch board") (rev "0.1") (comment 1 "ESP32-C6-MINI-1, factory assembled"))
  (lib_symbols
{chr(10).join(re.sub(r'^\(symbol "[^"]+"', f'(symbol "{k}"', v, count=1) for k, v in SYMS.items())}
  )
{chr(10).join(items)}
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
'''
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "utilwatch.kicad_sch").write_text(sch)
(OUT / "utilwatch.kicad_pro").write_text('{"meta": {"filename": "utilwatch.kicad_pro", "version": 3}}\n')
print("wrote", OUT)
