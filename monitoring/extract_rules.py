import sys
from pathlib import Path

import yaml

rule = yaml.safe_load((Path(__file__).parent / "alert-rules.yaml").read_text())
yaml.safe_dump({"groups": rule["spec"]["groups"]}, sys.stdout, sort_keys=False)
