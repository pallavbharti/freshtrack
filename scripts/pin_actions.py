import json
import re
import sys
from pathlib import Path

pins = json.loads(Path(sys.argv[1]).read_text())
pattern = re.compile(r"uses: ([\w.-]+/[\w.-]+)@[\w.-]+(?:\s+#.*)?$", re.M)

for wf in sorted(Path(".github/workflows").glob("*.yml")):
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
