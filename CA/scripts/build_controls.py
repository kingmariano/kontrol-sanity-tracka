#!/usr/bin/env python3
"""Compile the harness controls and extract their runtime bytecode to .hex.

The probes `vm.etch(target, hex"<code>")` a compiled control, so the generator
needs `CA/harness/controls/<Name>.hex`. This script makes that step explicit and
reproducible (recover.sh only ever did VulnerableControl/SafeControl).

It runs `forge build` in the skeleton (local forge is allowed; only Kontrol/docker
must run in CI), then for every requested contract name finds the matching
`out/**/<Name>.json`, takes `deployedBytecode.object`, and writes the .hex.

Usage:
    python3 build_controls.py [--no-build] [--check]

`--check` verifies every .hex is present and non-empty without writing.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKEL = os.path.join(ROOT, "harness", "skeleton")
OUT = os.path.join(SKEL, "out")
CTRL = os.path.join(ROOT, "harness", "controls")

# Everything the Track A / stage generators may etch, plus the tokens/mocks.
NAMES = [
    # stage controls
    "VulnerableControl", "SafeControl",
    "VulnerableTransient", "SafeTransient",
    "NaiveProxy", "SafeProxy", "KillerImpl",
    "VulnerableProfit", "SafeProfit", "VulnerableAmplify", "SafeAmplify",
    # Track A controls (v2)
    "VulnerableInit", "SafeInit",
    "VulnerableUpgrade", "SafeUpgrade",
    "VulnerableFee", "SafeFee",
    "VulnerableUnchecked", "SafeUnchecked",
    "VulnerablePull", "SafePull",
    "VulnerableValue", "SafeValue",
    # tokens
    "ConsentToken", "MockERC20",
]


def build():
    print("[build_controls] forge build ...", flush=True)
    r = subprocess.run(["forge", "build"], cwd=SKEL, capture_output=True, text=True)
    tail = "\n".join((r.stdout + r.stderr).splitlines()[-4:])
    print(tail, flush=True)
    if r.returncode != 0:
        raise SystemExit("forge build failed")


def find_artifact(name):
    """Return the deployed bytecode hex for `name` (first exact contract match)."""
    for dirpath, _dirs, files in os.walk(OUT):
        for f in files:
            if not f.endswith(".json") or f == "build-info.json":
                continue
            if os.path.splitext(f)[0] != name:
                continue
            try:
                d = json.load(open(os.path.join(dirpath, f)))
            except Exception:
                continue
            obj = (d.get("deployedBytecode") or {}).get("object")
            if obj:
                return obj[2:] if obj.startswith("0x") else obj
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not args.no_build and not args.check:
        build()

    os.makedirs(CTRL, exist_ok=True)
    ok, missing, stale = [], [], []
    for name in NAMES:
        path = os.path.join(CTRL, name + ".hex")
        if args.check:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                ok.append(name)
            else:
                missing.append(name)
            continue
        code = find_artifact(name)
        if not code:
            if os.path.exists(path):
                stale.append(name)
            else:
                missing.append(name)
            continue
        with open(path, "w") as fh:
            fh.write(code)
        ok.append(name)
        print(f"  wrote {name}.hex ({len(code) // 2} bytes)")

    print(f"[build_controls] ok={len(ok)} missing={len(missing)} kept-stale={len(stale)}")
    if missing:
        print("  MISSING: " + ", ".join(missing))
    if stale:
        print("  KEPT (no artifact, existing .hex retained): " + ", ".join(stale))
    if args.check and missing:
        sys.exit(1)


if __name__ == "__main__":
    main()