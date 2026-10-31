# Writes everything JLCPCB needs to make and assemble the board, into kicad/board/fab/:
#   utilwatch-gerbers.zip   board files (upload this first)
#   bom.csv                 parts list with LCSC numbers (assembly step)
#   cpl.csv                 where each part goes (assembly step)
#   fit-check-1to1.pdf      print at 100% and lay your parts on it before ordering
# Run after any change in KiCad:  uv run python kicad/board/export_fab.py
import csv, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path

KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
HERE = Path(__file__).parent
PCB, SCH, FAB = HERE / "utilwatch.kicad_pcb", HERE / "utilwatch.kicad_sch", HERE / "fab"


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

with (FAB / "cpl.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for p in placed:
        if p["Ref"] in parts:
            w.writerow([p["Ref"], f'{float(p["PosX"]):.3f}mm', f'{float(p["PosY"]):.3f}mm', "Top", f'{float(p["Rot"]):.1f}'])

print(f"{FAB}: gerbers zip, bom.csv ({len(groups)} lines, {len(parts)} parts), cpl.csv, fit-check-1to1.pdf")
