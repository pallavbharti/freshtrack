import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / ".github" / "action-pins.json"

if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != PINS:
    raise SystemExit(f"pins are read from {PINS.relative_to(ROOT)} only")
pins = json.loads(PINS.read_text())
pattern = re.compile(r"uses: ([\w.-]+/[\w.-]+)@[\w.-]+(?:\s+#.*)?$", re.M)

for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
    text = wf.read_text()

    def repl(m):
        repo = m.group(1)
        if repo not in pins:
            raise SystemExit(f"{wf}: no pin for {repo}")
        return f"uses: {repo}@{pins[repo]['sha']} # {pins[repo]['tag']}"

    new = pattern.sub(repl, text)
    if new != text:
        wf.write_text(new)
        print(f"pinned {wf}")
