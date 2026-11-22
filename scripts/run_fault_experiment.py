import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAULTS = subprocess.run(["bash", str(ROOT / "scripts/inject_fault.sh"), "list"],
                        capture_output=True, text=True, check=True).stdout.split()
FIELDS = ["fault", "pipeline", "caught", "stage", "blocked_before_deploy", "time_to_detection_s",
          "mode", "not_run", "detail"]


def sh(cmd, cwd=None, check=False, env=None):
    return subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True,
                          check=check, env=env)


def tool(name, env_var):
    path = os.getenv(env_var) or shutil.which(name)
    return path if path and Path(path).exists() else None


def docker_ok():
    d = tool("docker", "DOCKER_BIN")
    return d if d and sh([d, "info"]).returncode == 0 else None


def local_stages(base: str):
    trivy = tool("trivy", "TRIVY_BIN")
    gitleaks = tool("gitleaks", "GITLEAKS_BIN")
    docker = docker_ok()
    vuln_db = os.getenv("TRIVY_VULN_DB_OK") == "1"
    py = sys.executable

    def ref_profile(wt):
        out = sh(["git", "show", f"{base}:backend/data/profile.json"], cwd=wt)
        p = Path(wt) / ".ref-profile.json"
        p.write_text(out.stdout)
        return p

    return [
        ("lint", {"basic", "full"}, None,
         lambda wt: ([py, "-m", "ruff", "check", "."], wt / "backend")),
        ("data-validation", {"full"}, None,
         lambda wt: ([py, "scripts/validate_data.py", "data/sales.csv", "--reference", str(ref_profile(wt))],
                     wt / "backend")),
        ("unit-tests", {"basic", "full"}, None,
         lambda wt: ([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], wt / "backend")),
        ("business-gate", {"full"}, None,
         lambda wt: ([py, "scripts/policy_gate.py"], wt / "backend")),
        ("trivy-secret", {"basic", "full"}, None if trivy else "trivy",
         lambda wt: ([trivy, "fs", "--scanners", "secret", "--severity", "HIGH,CRITICAL", "--exit-code", "1",
                      "--skip-dirs", "frontend/node_modules", "--quiet", "."], wt)),
        ("trivy-vuln", {"basic", "full"}, None if (trivy and vuln_db) else "trivy vulnerability DB",
         lambda wt: ([trivy, "fs", "--scanners", "vuln", "--severity", "HIGH,CRITICAL", "--ignore-unfixed",
                      "--exit-code", "1", "--skip-dirs", "frontend/node_modules", "--quiet", "."], wt)),
        ("trivy-misconfig", {"full"}, None if trivy else "trivy",
         lambda wt: ([trivy, "fs", "--scanners", "misconfig", "--severity", "HIGH,CRITICAL", "--exit-code", "1",
                      "--skip-check-update", "--skip-dirs", "frontend/node_modules", "--quiet", "."], wt)),
        ("gitleaks", {"full"}, None if gitleaks else "gitleaks",
         lambda wt: ([gitleaks, "git", "--no-banner", "--redact", "--log-opts", f"{base}..HEAD", "."], wt)),
        ("docker-build", {"basic", "full"}, None if docker else "docker",
         lambda wt: ([docker, "build", "-q", "-t", "fault-backend:test", "backend"], wt)),
        ("container-smoke-test", {"full"}, None if docker else "docker",
         lambda wt: (["bash", "-c", (
                      "docker rm -f fsmoke >/dev/null 2>&1; "
                      "docker run -d --name fsmoke -p 18765:8000 -e DATABASE_URL=sqlite:////tmp/s.db "
                      "fault-backend:test >/dev/null && "
                      "for i in $(seq 1 30); do curl -s localhost:18765/health >/dev/null && break; sleep 2; done; "
                      "code=$(curl -s -o /dev/null -w '%{http_code}' localhost:18765/ready); "
                      "docker rm -f fsmoke >/dev/null; echo ready=$code; [ \"$code\" = 200 ]")], wt)),
        ("trivy-image", {"basic", "full"}, None if (docker and trivy and vuln_db) else "docker + trivy DB",
         lambda wt: ([trivy, "image", "--severity", "HIGH,CRITICAL", "--ignore-unfixed", "--exit-code", "1",
                      "--quiet", "fault-backend:test"], wt)),
        ("sonarqube", {"basic", "full"}, "SonarQube Cloud (GitHub only)", None),
    ]


def run_stage(build, wt):
    cmd, cwd = build(wt)
    t0 = time.monotonic()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
    return p.returncode == 0, time.monotonic() - t0, tail[0][:160]


def preflight(stages, base):
    wt = Path(tempfile.mkdtemp(prefix="fault-preflight-"))
    sh(["git", "worktree", "add", "-f", "--detach", str(wt), base], cwd=ROOT, check=True)
    print("=== preflight on unmodified", base)
    checked = []
    try:
        for name, pipes, missing, build in stages:
            if not missing:
                ok, dt, detail = run_stage(build, wt)
                print(f"  {name:22} {'ok' if ok else 'FAILS ON MAIN'} {dt:6.1f}s")
                if not ok:
                    missing = f"working environment (fails on unmodified {base}: {detail[:60]})"
            checked.append((name, pipes, missing, build))
    finally:
        sh(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)
    return checked


def run_local(faults, base):
    rows = []
    stages = preflight(local_stages(base), base)
    for fault in faults:
        r = sh(["bash", "scripts/inject_fault.sh", fault, base], cwd=ROOT)
        if r.returncode:
            sys.exit(f"inject {fault} failed: {r.stderr}")
        sh(["git", "checkout", "-q", base], cwd=ROOT, check=True)
        wt = Path(tempfile.mkdtemp(prefix=f"fault-{fault}-"))
        sh(["git", "worktree", "add", "-f", str(wt), f"fault/{fault}"], cwd=ROOT, check=True)
        print(f"\n=== {fault}")
        try:
            results = []
            for name, pipes, missing, build in stages:
                if missing:
                    results.append((name, pipes, "not run", 0.0, f"needs {missing}"))
                    print(f"  {name:22} not run ({missing})")
                    continue
                ok, dt, detail = run_stage(build, wt)
                outcome = "pass" if ok else "FAIL"
                results.append((name, pipes, outcome, dt, detail))
                print(f"  {name:22} {outcome:4} {dt:6.1f}s  {detail[:90]}")
        finally:
            sh(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT)

        for pipeline in ("basic", "full"):
            elapsed, caught, not_run = 0.0, None, []
            for name, pipes, outcome, dt, detail in results:
                if pipeline not in pipes:
                    continue
                if outcome == "not run":
                    not_run.append(name)
                    continue
                elapsed += dt
                if outcome == "FAIL" and caught is None:
                    caught = (name, elapsed, detail)
            if caught:
                status = "yes"
            elif not_run:
                status = "not caught by the stages that ran"
            else:
                status = "no"
            rows.append({
                "fault": fault, "pipeline": pipeline,
                "caught": status if fault != "control" else ("FALSE POSITIVE" if caught else "ok (no alarm)"),
                "stage": caught[0] if caught else "",
                "blocked_before_deploy": "yes" if caught else ("unknown" if not_run else "no"),
                "time_to_detection_s": round(caught[1], 1) if caught else "",
                "mode": "local", "not_run": " ".join(not_run), "detail": caught[2] if caught else "",
            })
    return rows


def gh_json(args):
    out = sh(["gh", *args])
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout or "null")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def run_github(faults, base, timeout_min):
    if sh(["gh", "auth", "status"]).returncode:
        sys.exit("gh is not logged in: run `gh auth login` first")
    rows = []
    pending = {}
    for fault in faults:
        sh(["bash", "scripts/inject_fault.sh", fault, base], cwd=ROOT, check=True)
        sha = sh(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True).stdout.strip()
        sh(["git", "push", "-f", "-q", "origin", f"fault/{fault}"], cwd=ROOT, check=True)
        sh(["git", "checkout", "-q", base], cwd=ROOT, check=True)
        pending[fault] = sha
        print(f"pushed fault/{fault} @ {sha[:8]}")

    deadline = time.time() + timeout_min * 60
    done = {}
    while pending and time.time() < deadline:
        time.sleep(30)
        for fault, sha in list(pending.items()):
            runs = gh_json(["run", "list", "--commit", sha, "--json",
                            "databaseId,workflowName,status,conclusion,createdAt"])
            wanted = {r["workflowName"]: r for r in runs if r["workflowName"] in ("CI/CD", "CI basic (comparison)")}
            if len(wanted) == 2 and all(r["status"] == "completed" for r in wanted.values()):
                done[fault] = wanted
                del pending[fault]
                print(f"finished: {fault}")
    for fault in pending:
        print(f"timed out waiting for {fault}")

    for fault, runs in done.items():
        for pipeline, wf in (("basic", "CI basic (comparison)"), ("full", "CI/CD")):
            run = runs[wf]
            jobs = gh_json(["run", "view", str(run["databaseId"]), "--json", "jobs"])["jobs"]
            failed = sorted((j for j in jobs if j["conclusion"] == "failure"), key=lambda j: j["completedAt"])
            first = failed[0] if failed else None
            ttd = (ts(first["completedAt"]) - ts(run["createdAt"])).total_seconds() if first else ""
            failed_step = ""
            if first:
                steps = [s["name"] for s in first.get("steps", []) if s.get("conclusion") == "failure"]
                failed_step = steps[0] if steps else ""
            caught = bool(first)
            rows.append({
                "fault": fault, "pipeline": pipeline,
                "caught": ("FALSE POSITIVE" if caught else "ok (no alarm)") if fault == "control"
                else ("yes" if caught else "no"),
                "stage": f"{first['name']} / {failed_step}" if first else "",
                "blocked_before_deploy": "yes" if caught else "no",
                "time_to_detection_s": round(ttd) if first else "",
                "mode": "github", "not_run": "", "detail": f"run {run['databaseId']}",
            })
    return rows


def write(rows, mode):
    out = ROOT / "results" / f"fault_injection_{mode}.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    real = [r for r in rows if r["fault"] != "control"]
    lines = [f"# Fault-injection results ({mode} run, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)", ""]
    if mode == "local":
        lines += ["Local run: stages execute one after another on one machine (on GitHub, jobs run in",
                  "parallel). Stages marked *not run* needed a tool that was not available; a fault",
                  "that only those stages could catch is reported as not caught *by the stages that ran*.", ""]
    lines += ["| Fault | Basic pipeline | Full pipeline |", "|---|---|---|"]
    by = {(r["fault"], r["pipeline"]): r for r in rows}
    for fault in dict.fromkeys(r["fault"] for r in rows):
        cells = []
        for p in ("basic", "full"):
            r = by.get((fault, p))
            if not r:
                cells.append("-")
            elif r["stage"]:
                cells.append(f"{r['caught']} - {r['stage']} ({r['time_to_detection_s']} s)")
            else:
                cells.append(r["caught"])
        lines.append(f"| {fault} | {cells[0]} | {cells[1]} |")
    lines.append("")
    for p in ("basic", "full"):
        rs = [r for r in real if r["pipeline"] == p]
        caught = sum(r["caught"] == "yes" for r in rs)
        lines.append(f"- **{p}**: caught {caught} of {len(rs)} faults before deploy "
                     f"({100 * caught / len(rs):.0f}%)" if rs else f"- {p}: no runs")
    md = out.with_suffix(".md")
    md.write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print(f"\nwritten: {out.relative_to(ROOT)} and {md.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "github"], required=True)
    parser.add_argument("--faults", nargs="*", default=FAULTS)
    parser.add_argument("--base", default="main")
    parser.add_argument("--timeout-min", type=int, default=60)
    args = parser.parse_args()

    if sh(["git", "status", "--porcelain"], cwd=ROOT).stdout.strip():
        sys.exit("working tree not clean - commit or stash first")
    rows = run_local(args.faults, args.base) if args.mode == "local" else run_github(args.faults, args.base,
                                                                                       args.timeout_min)
    write(rows, args.mode)


if __name__ == "__main__":
    main()
