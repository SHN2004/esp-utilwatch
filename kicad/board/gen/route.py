# export DSN / import SES and fill zones:  route.py dsn <pcb> <dsn>  |  route.py ses <pcb> <ses>
import sys, pcbnew
mode, pcb, f = sys.argv[1:4]
board = pcbnew.LoadBoard(pcb)
if mode == "dsn":
    for z in list(board.Zones()):  # route GND as real tracks; the planes go back on after
        if not z.GetIsRuleArea():
            board.Remove(z)
    print("dsn", pcbnew.ExportSpecctraDSN(board, f))
else:
    print("ses", pcbnew.ImportSpecctraSES(board, f))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(pcb, board)
