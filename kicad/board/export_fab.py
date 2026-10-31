# Writes everything JLCPCB needs to make and assemble the board, into kicad/board/fab/:
#   utilwatch-gerbers.zip   board files (upload this first)
#   bom.csv                 parts list with LCSC numbers (assembly step)
#   bom-mpn.csv             same parts with manufacturer part numbers, for assemblers outside JLCPCB
#   cpl.csv                 where each part goes (assembly step)
#   fit-check-1to1.pdf      print at 100% and lay your parts on it before ordering
# Run after any change in KiCad:  uv run python kicad/board/export_fab.py
import csv, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
HERE = Path(__file__).parent
PCB, SCH, FAB = HERE / "utilwatch.kicad_pcb", HERE / "utilwatch.kicad_sch", HERE / "fab"


# LCSC number -> manufacturer part, for assemblers that don't use LCSC (looked up on lcsc.com).
MPN = {
    "C19702": ("Samsung Electro-Mechanics", "CL10A106KP8NNNC", "Cap ceramic 10uF 10V X5R 0603"),
    "C14663": ("YAGEO", "CC0603KRX7R9BB104", "Cap ceramic 100nF 50V X7R 0603"),
    "C15849": ("Samsung Electro-Mechanics", "CL10A105KB8NNNC", "Cap ceramic 1uF 50V X5R 0603"),
    "C8598": ("JSCJ", "B5819W SL", "Schottky diode 40V 1A SOD-123"),
    "C2286": ("Hubei KENTO", "KT-0603R", "LED red 0603"),
    "C165948": ("Korean Hroparts (HRO)", "TYPE-C-31-M-12", "USB-C receptacle 16-pin SMD"),
    "C15127": ("Alpha & Omega (AOS)", "AO3401A", "P-MOSFET 30V 4A SOT-23"),
    "C23186": ("UNI-ROYAL", "0603WAF5101T5E", "Resistor 5.1k 1% 0603"),
    "C21190": ("UNI-ROYAL", "0603WAF1001T5E", "Resistor 1k 1% 0603"),
    "C25803": ("UNI-ROYAL", "0603WAF1003T5E", "Resistor 100k 1% 0603"),
    "C23178": ("UNI-ROYAL", "0603WAF4703T5E", "Resistor 470k 1% 0603"),
    "C25804": ("UNI-ROYAL", "0603WAF1002T5E", "Resistor 10k 1% 0603"),
    "C431540": ("SHOU HAN", "MSK12C02", "Slide switch SPDT SMD, side lever"),
    "C128539": ("Panasonic", "EVQ-PUA02K", "Tactile switch SMD right-angle 2.2N"),
    "C5736265": ("Espressif", "ESP32-C6-MINI-1-N4", "Wi-Fi 6/BLE 5 module, 4MB flash"),
    "C424093": ("Microchip", "MCP73831T-2ACI/OT", "Li-ion charger SOT-23-5"),
    "C82942": ("MICRONE", "ME6211C33M5G-N", "LDO 3.3V 500mA SOT-23-5"),
}


def cli(*args):
    subprocess.run([KICAD_CLI, *map(str, args)], check=True, capture_output=True)


shutil.rmtree(FAB, ignore_errors=True)
gerbers = FAB / "gerbers"
gerbers.mkdir(parents=True)
cli("pcb", "export", "gerbers", PCB, "-o", f"{gerbers}/", "--layers",
    "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts")
cli("pcb", "export", "drill", PCB, "-o", f"{gerbers}/")
with zipfile.ZipFile(FAB / "utilwatch-gerbers.zip", "w") as z:
    for f in sorted(gerbers.iterdir()):
        z.write(f, f.name)
cli("pcb", "export", "pdf", PCB, "-o", FAB / "fit-check-1to1.pdf",
    "--layers", "F.Fab,F.Courtyard,Edge.Cuts,F.Silkscreen", "--mode-single")

with tempfile.TemporaryDirectory() as tmp:
    net, pos = Path(tmp, "board.net"), Path(tmp, "pos.csv")
    cli("sch", "export", "netlist", "--format", "kicadsexpr", SCH, "-o", net)
    cli("pcb", "export", "pos", PCB, "-o", pos, "--format", "csv", "--units", "mm", "--side", "front")
    netlist = net.read_text()
    placed = list(csv.DictReader(pos.open()))

# Only parts with an LCSC number are assembled; the OLED/battery holes and boot pads are not.
parts = {}
for c in re.finditer(r'\(comp\n\t\t\t\(ref "([^"]+)"\)([\s\S]*?)\n\t\t\)', netlist):
    lcsc = re.search(r'\(name "LCSC"\) "([^"]*)"\)', c.group(2))
    if lcsc and lcsc.group(1):
        value = re.search(r'\(value "([^"]*)"\)', c.group(2)).group(1)
        footprint = re.search(r'\(footprint "([^"]*)"\)', c.group(2)).group(1).split(":")[1]
        parts[c.group(1)] = (value, footprint, lcsc.group(1))

groups = {}  # one line per LCSC part
for ref, (value, footprint, lcsc) in parts.items():
    groups.setdefault((footprint, lcsc), []).append((ref, value))
natural = lambda r: (re.sub(r"\d", "", r), int(re.sub(r"\D", "", r) or 0))
with (FAB / "bom.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (footprint, lcsc), items in sorted(groups.items(), key=lambda g: natural(min(r for r, _ in g[1]))):
        refs = sorted((r for r, _ in items), key=natural)
        values = dict.fromkeys(v for _, v in sorted(items, key=lambda i: natural(i[0])))
        w.writerow(["/".join(values), ",".join(refs), footprint, lcsc])

with (FAB / "bom-mpn.csv").open("w", newline="") as f:  # same parts, for PCB Power and other assemblers
    w = csv.writer(f)
    w.writerow(["Qty", "Designator", "Value", "Description", "Manufacturer", "MPN", "Package", "LCSC Part #"])
    for (footprint, lcsc), items in sorted(groups.items(), key=lambda g: natural(min(r for r, _ in g[1]))):
        refs = sorted((r for r, _ in items), key=natural)
        maker, mpn, desc = MPN[lcsc]
        w.writerow([len(refs), ",".join(refs), "/".join(dict.fromkeys(v for _, v in items)), desc, maker, mpn,
                    footprint, lcsc])

with (FAB / "cpl.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for p in placed:
        if p["Ref"] in parts:
            w.writerow([p["Ref"], f'{float(p["PosX"]):.3f}mm', f'{float(p["PosY"]):.3f}mm', "Top", f'{float(p["Rot"]):.1f}'])

print(f"{FAB}: gerbers zip, bom.csv ({len(groups)} lines, {len(parts)} parts), cpl.csv, fit-check-1to1.pdf")
