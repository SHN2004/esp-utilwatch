#!/bin/zsh
# Builds the carrier board from scratch: placed board (build_carrier.py) -> Freerouting -> ground
# planes -> DRC -> fab/ (gerber zip for any PCB maker + a 1:1 printout to check your parts against).
# This OVERWRITES utilwatch-carrier.kicad_pcb: once you hand-edit it in KiCad, edit there instead.
# Needs: KiCad 10, Homebrew openjdk, ~/.local/share/freerouting/freerouting-2.5.0.jar
set -e
G=${0:a:h}; C=$G/..; B=$C/utilwatch-carrier.kicad_pcb; T=$(mktemp -d)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
JAVA=$(brew --prefix openjdk)/bin/java
ROUTE=$C/../board/gen/route.py
quiet() { grep -v -i "fontconfig\|wxApp\|memory leak" || true; }
$PY $G/build_carrier.py $B 2>&1 | quiet
$PY $ROUTE dsn $B $T/board.dsn 2>&1 | quiet
(cd $T && $JAVA -jar ~/.local/share/freerouting/freerouting-2.5.0.jar -de board.dsn -do board.ses -mp 60 --gui.enabled=false > fr.log 2>&1)
grep "Auto-routing stage completed" $T/fr.log | sed 's/.*completed: //' | cut -c1-100
$PY $ROUTE ses $B $T/board.ses 2>&1 | quiet
"$K" pcb drc $B -o $T/drc.rpt >/dev/null 2>&1 || true
grep -E "^\[" $T/drc.rpt | sed 's/(.*//' | sort | uniq -c
rm -rf $C/fab && mkdir -p $C/fab/gerbers
"$K" pcb export gerbers $B -o $C/fab/gerbers/ --layers F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts >/dev/null 2>&1
"$K" pcb export drill $B -o $C/fab/gerbers/ >/dev/null 2>&1
(cd $C/fab/gerbers && zip -q ../utilwatch-carrier-gerbers.zip *)
"$K" pcb export pdf $B -o $C/fab/fit-check-1to1.pdf --layers F.Fab,F.Courtyard,Edge.Cuts,F.Silkscreen,F.Cu --mode-single >/dev/null 2>&1
echo "fab: $(ls $C/fab)"
