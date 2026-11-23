import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class IntegrityError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path(model_path: Path) -> Path:
    return Path(model_path).with_name("manifest.json")


def write_manifest(model_path: Path, metrics_path: Path, data_path: Path | None = None) -> dict:
    manifest = {
        "model": {"file": Path(model_path).name, "sha256": sha256_file(model_path)},
        "metrics": {"file": Path(metrics_path).name, "sha256": sha256_file(metrics_path)},
        "data": {"file": Path(data_path).name, "sha256": sha256_file(data_path)} if data_path else None,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    manifest_path(model_path).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify(model_path: Path) -> dict:
    model_path = Path(model_path)
    mpath = manifest_path(model_path)
    if not mpath.exists():
        raise IntegrityError(f"no manifest next to {model_path.name}")
    manifest = json.loads(mpath.read_text())

    for key in ("model", "metrics"):
        entry = manifest[key]
        f = model_path.with_name(entry["file"])
        if not f.exists():
            raise IntegrityError(f"{entry['file']} listed in the manifest is missing")
        actual = sha256_file(f)
        if actual != entry["sha256"]:
            raise IntegrityError(f"{entry['file']} hash {actual[:12]} does not match manifest {entry['sha256'][:12]}")
    return manifest
