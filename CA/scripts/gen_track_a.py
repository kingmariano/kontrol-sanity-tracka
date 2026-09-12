#!/usr/bin/env python3
"""Track A light-batch generator (controls first).

Emits chunks in the reusable-CI layout:
    harness/stages/stage<id>/Stage<id>Chunk_<c>.sol
    harness/stages/stage<id>/chunk_<c>.tests
    harness/stages/stage<id>/manifest.json

Reuses the validated ProbeBase/SINGLE templates from gen_stage.py.

`tracka_batch1` = combined light-batch control chunk for stages A1/A2/A6/A7.
Later batches add scoped templates (ROUNDTRIP / VALUE / REENTRANT / UNAUTH_PULL)
for A4/A5/A8/A9; A3 needs a signer template (Track B).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_stage  # noqa: E402  (HDR, SINGLE)

ROOT = os.path.dirname(HERE)
CTRL = os.path.join(ROOT, "harness", "controls")
OUTROOT = os.path.join(ROOT, "harness", "stages")

# (stage_id, kind, contract, test_name)
BATCH1 = [
    ("a1_init", "MUST_FAIL", "VulnerableInit", "test_a1_vulnerable"),
    ("a1_init", "MUST_PASS", "SafeInit", "test_a1_safe"),
    ("a2_upgrade", "MUST_FAIL", "VulnerableUpgrade", "test_a2_vulnerable"),
    ("a2_upgrade", "MUST_PASS", "SafeUpgrade", "test_a2_safe"),
    ("a6_fee", "MUST_FAIL", "VulnerableFee", "test_a6_vulnerable"),
    ("a6_fee", "MUST_PASS", "SafeFee", "test_a6_safe"),
    ("a7_unchecked", "MUST_FAIL", "VulnerableUnchecked", "test_a7_vulnerable"),
    ("a7_unchecked", "MUST_PASS", "SafeUnchecked", "test_a7_safe"),
]


def control_code(name):
    with open(os.path.join(CTRL, name + ".hex")) as f:
        c = f.read().strip()
    return c[2:] if c.startswith("0x") else c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="tracka_batch1")
    args = ap.parse_args()
    outdir = os.path.join(OUTROOT, "stage" + args.stage)
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.startswith("Stage") or f.startswith("chunk_") or f == "manifest.json":
            os.remove(os.path.join(outdir, f))

    parts, tests = [], []
    for stage_id, kind, cname, tname in BATCH1:
        parts.append(gen_stage.SINGLE.format(
            label=f"{kind} {stage_id} {cname}", name=tname,
            base=0x1000000, idx=0, code=control_code(cname)))
        tests.append(tname)

    src = gen_stage.HDR.format(stage=args.stage, chunk=0, cls="CONTROLS-BATCH1") + "".join(parts) + "}\n"
    with open(os.path.join(outdir, f"Stage{args.stage}Chunk_0.sol"), "w") as f:
        f.write(src)
    with open(os.path.join(outdir, "chunk_0.tests"), "w") as f:
        f.write("\n".join(tests) + "\n")
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump({"stage": args.stage,
                   "chunks": [{"chunk": 0, "class": "CONTROLS-BATCH1",
                               "tests": tests, "targets": []}]}, f, indent=1)
    print(f"wrote {outdir}/Stage{args.stage}Chunk_0.sol ({len(tests)} controls)")


if __name__ == "__main__":
    main()
