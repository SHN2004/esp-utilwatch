#!/bin/zsh
# Regenerates the board from scratch: schematic netlist -> placed board (build_board.py) ->
# Freerouting -> ground planes -> DRC. This OVERWRITES utilwatch.kicad_pcb, so only use it while
# the layout is still generated; once you hand-edit the board in KiCad, edit there instead.
# Needs: KiCad 10, Homebrew openjdk, ~/.local/share/freerouting/freerouting-2.5.0.jar
set -e
G=${0:a:h}; B=$G/../utilwatch.kicad_pcb; T=$(mktemp -d)
PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
JAVA=$(brew --prefix openjdk)/bin/java
quiet() { grep -v -i "fontconfig\|wxApp\|memory leak" || true; }
"$K" sch export netlist --format kicadsexpr $G/../utilwatch.kicad_sch -o $T/board.net >/dev/null 2>&1
$PY $G/build_board.py $T/board.net $B 2>&1 | quiet
$PY $G/route.py dsn $B $T/board.dsn 2>&1 | quiet
(cd $T && $JAVA -jar ~/.local/share/freerouting/freerouting-2.5.0.jar -de board.dsn -do board.ses -mp 60 --gui.enabled=false > fr.log 2>&1)
grep "Auto-routing stage completed" $T/fr.log | sed 's/.*completed: //' | cut -c1-100
$PY $G/route.py ses $B $T/board.ses 2>&1 | quiet
"$K" pcb drc $B -o $T/drc.rpt >/dev/null 2>&1 || true
grep -E "^\[" $T/drc.rpt | sed 's/(.*//' | sort | uniq -c
