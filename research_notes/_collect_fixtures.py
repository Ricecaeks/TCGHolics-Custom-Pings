import json
import pathlib

out = pathlib.Path("tests/fixtures/warehouse")
out.mkdir(parents=True, exist_ok=True)

# widget.json  <-  the 32 KB widget response ("fullBody" was the raw text)
src = json.loads(pathlib.Path("research_notes/warehouse-store-call-1.json").read_text(encoding="utf-8"))
out.joinpath("widget.json").write_text(src["fullBody"], encoding="utf-8")

# region-auckland.json  <-  the 47 KB Auckland region response
src2 = json.loads(pathlib.Path("research_notes/warehouse-region-auckland-full.json").read_text(encoding="utf-8"))
out.joinpath("region-auckland.json").write_text(src2["regionBody"], encoding="utf-8")

# spot check
w = (out / "widget.json").read_text(encoding="utf-8")
a = (out / "region-auckland.json").read_text(encoding="utf-8")
print("widget.json len", len(w), "action:", w[:200].split('"action": "',1)[-1].split('"',1)[0])
print("region-auckland.json len", len(a), "IN_STOCK count:", a.count("store-availability__IN_STOCK"), "OUT count:", a.count("store-availability__NOT_AVAILABLE") + a.count("store-availability__OUT_OF_STOCK"))
