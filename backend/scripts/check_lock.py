import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = [("requirements.txt", "requirements.lock"), ("requirements-dev.txt", "requirements-dev.lock")]
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;\\]+)")
REGEN = ("uv pip compile {src} --python-version 3.12 --python-platform x86_64-manylinux_2_28 "
         "--generate-hashes --no-header -o {lock}")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def pins(path: Path) -> dict[str, str]:
    found = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("-r "):
            found.update(pins(path.parent / line[3:].strip()))
            continue
        m = PIN.match(line)
        if m:
            found[normalize(m.group(1))] = m.group(2)
    return found


def check(root: Path = ROOT) -> list[str]:
    problems = []
    for src, lock in PAIRS:
        wanted = pins(root / src)
        locked = pins(root / lock)
        for name, version in sorted(wanted.items()):
            if locked.get(name) != version:
                problems.append(f"{lock}: {name} is {locked.get(name, 'missing')}, {src} pins {version}")
        if any(problem.startswith(lock) for problem in problems):
            problems.append(f"regenerate with: {REGEN.format(src=src, lock=lock)}")
    return problems


def main():
    problems = check()
    for p in problems:
        print(p)
    if not problems:
        print("lock files match the pinned requirements")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
