"""Install pinned external source dependencies for the standalone RF project."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def run(command):
    print("+ " + " ".join(str(value) for value in command), flush=True)
    subprocess.run([str(value) for value in command], check=True)


def checkout_dependency(root, pin, name, sparse_paths=None):
    dep = root/".deps"/name
    if not dep.exists():
        dep.parent.mkdir(exist_ok=True)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", pin["url"], dep])
        if sparse_paths:
            run(["git", "-C", dep, "sparse-checkout", "set", *sparse_paths])
        run(["git", "-C", dep, "checkout", "--detach", pin["commit"]])
    else:
        head = subprocess.check_output(["git", "-C", str(dep), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(dep), "status", "--porcelain"], text=True).strip()
        if head != pin["commit"] or dirty:
            raise SystemExit(f"Existing {dep} differs from the clean pin; resolve that checkout before rerunning.")
    return dep


def main():
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root/"sources.json").read_text())
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12 for this tested dependency lock (python3.12 or py -3.12).")
    dep = checkout_dependency(root, source["sionna_rt"], "sionna-rt")
    airs = checkout_dependency(root, source["projectairsim"], "ProjectAirSim",
                               sparse_paths=["client/python/projectairsim", "client/python/example_user_scripts"])
    environment = root/".venv"
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment/("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    installer = ([shutil.which("uv"), "pip", "install", "--python", str(python)] if shutil.which("uv")
                 else [str(python), "-m", "pip", "install"])
    run(installer + ["-r", root/"requirements-lock.txt", "-e", dep,
                     "-e", airs/"client/python/projectairsim", "-e", root])
    print(f"Ready. Run {python} -m pytest {root/'tests'}")
    print(f"RF example: {python} {root/'examples/distance2gol_radar.py'}")
    print("A simulator must be built or downloaded separately for live AirSim captures.")


if __name__ == "__main__":
    main()
