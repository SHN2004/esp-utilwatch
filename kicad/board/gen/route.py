# export DSN / import SES and fill zones:  route.py dsn <pcb> <dsn>  |  route.py ses <pcb> <ses>
import sys, pcbnew
mode, pcb, f = sys.argv[1:4]
board = pcbnew.LoadBoard(pcb)
if mode == "dsn":
    # Freerouting keeps only the net clearance (0.25) from the outline, less than the board's edge
    # rule; hand it a rounded-rectangle outline inset by 0.1 mm. Not saved, so the real edge stays.
    # (Before the zone removal: GetDrawings() stops iterating once a zone has been removed.)
    d = pcbnew.FromMM(0.1)
    for sh in board.GetDrawings():
        if sh.GetLayer() == pcbnew.Edge_Cuts and sh.GetShape() == pcbnew.SHAPE_T_RECTANGLE:
            sh.SetStart(sh.GetStart() + pcbnew.VECTOR2I(d, d))
            sh.SetEnd(sh.GetEnd() - pcbnew.VECTOR2I(d, d))
            sh.SetCornerRadius(max(sh.GetCornerRadius() - d, 0))
    for z in list(board.Zones()):  # route GND as real tracks; the planes go back on after
        if not z.GetIsRuleArea():
            board.Remove(z)
    print("dsn", pcbnew.ExportSpecctraDSN(board, f))
else:
    print("ses", pcbnew.ImportSpecctraSES(board, f))
    w = board.GetDesignSettings().m_TrackMinWidth  # Freerouting necks tracks down at pads; DRC rejects that
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T and t.GetWidth() < w:
            t.SetWidth(w)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(pcb, board)
