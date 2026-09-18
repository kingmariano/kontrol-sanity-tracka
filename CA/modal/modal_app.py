"""Run Track A wave chunks on Modal ($30/month free compute).

Design (checkpointed, resumable):
  * one container per stage; `kontrol build` runs ONCE per stage (all of the
    stage's chunk .sol files are copied into the probe project up front)
  * per chunk: tests run sequentially with a per-test timeout; after EVERY test
    the chunk's verdict file is uploaded to the HF bucket as
    verdicts_modal_<stage>_<chunk>.partial.txt
  * a chunk is marked final (verdicts_modal_<stage>_<chunk>.txt) only when it
    has no INCOMPLETE tests; final markers are skipped on rerun
  * partial verdict files are re-read on rerun, so completed tests are skipped
    (test-level checkpointing)

Usage:
  modal run CA/modal/modal_app.py --wave wave_funded_b2 --stages fundedb2_a1
  modal run CA/modal/modal_app.py --wave wave_funded_b2 \
      --stages fundedb2_a1,fundedb2_a2,fundedb2_a5,fundedb2_a6,fundedb2_a7,fundedb2_a9 \
      --deadline 21600
"""
import os
import re
import subprocess
import time
from pathlib import Path

import modal

BUCKET = "hf://buckets/Mariano234/kontrol-campaign"
PROVE_OPTS = (
    "--use-booster --no-break-on-calls --no-stack-checks --no-log-rewrites "
    "--max-frontier-parallel 2 --max-depth 50000 --max-iterations 100000 "
    "--smt-timeout 30000 --smt-retry-limit 2 --workers 3 --step-timeout 600 "
    "--auto-abstract-gas"
)

app = modal.App("kontrol-tracka-b2")
IMG = (
    modal.Image.from_registry("runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255")
    .apt_install("git", "curl", "python3", "python3-pip")
    .run_commands("ln -sf /usr/bin/python3 /usr/local/bin/python")
    .run_commands("python3 -m pip install --no-cache-dir --quiet huggingface_hub")
    .run_commands(
        "git clone --depth 1 https://github.com/kingmariano/kontrol-sanity-tracka.git /opt/repo"
    )
)


def run(cmd, timeout=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          timeout=timeout)


def verdict_of(out):
    m = re.search(r"PROOF (PASSED|FAILED)", out)
    if not m:
        return "INCOMPLETE", ""
    prop = ",".join(sorted(set(re.findall(r"P_[A-Z_]+", out)))[:3])
    return m.group(1), prop


def upload(text, dst):
    Path("/tmp/v.txt").write_text(text)
    run(f"hf cp /tmp/v.txt {BUCKET}/{dst} >/dev/null 2>&1")


@app.function(
    image=IMG,
    cpu=8,
    memory=32768,
    timeout=86400,
    max_containers=8,
    secrets=[modal.Secret.from_name("hf-token")],
)
def run_stage(stage: str, wave: str = "wave_funded_b2", budget_secs: int = 1800,
              deadline_s: int = 21600, chunk_limit: int = 0):
    os.environ["HOME"] = "/home/user"
    os.environ["PATH"] = "/home/user/.local/bin:" + os.environ.get("PATH", "/usr/bin:/bin")
    t0 = time.time()
    W = Path("/work")
    W.mkdir(exist_ok=True)

    r = run(f"hf cp {BUCKET}/{wave}.tgz {W}/{wave}.tgz")
    if not (W / f"{wave}.tgz").exists():
        return {"stage": stage, "error": f"wave fetch failed: {r.stderr[-200:]}"}
    run(f"tar xzf {W}/{wave}.tgz -C {W}")
    run("rm -rf /work/probe && cp -r /opt/repo/CA/harness/skeleton /work/probe")
    run(f"mkdir -p /work/probe/test && cp /work/stage{stage}/*.sol /work/probe/test/")

    b = run("cd /work/probe && kontrol build 2>&1 | tail -5")
    build_ok = "Success" in (b.stdout + b.stderr)
    build_tail = (b.stdout + b.stderr)[-500:]

    ls = run(f"hf buckets ls {BUCKET}").stdout
    done = set(re.findall(rf"verdicts_modal_{stage}_(\d+)\.txt", ls))

    tfiles = sorted((W / f"stage{stage}").glob("chunk_*.tests"),
                    key=lambda p: int(p.stem.split("_")[1]))
    if chunk_limit:
        tfiles = tfiles[:chunk_limit]

    results = []
    for tf in tfiles:
        chunk = int(tf.stem.split("_")[1])
        if str(chunk) in done:
            results.append({"chunk": chunk, "status": "already_done"})
            continue
        marker = f"verdicts_modal_{stage}_{chunk}"
        tests = [l.strip() for l in tf.read_text().splitlines() if l.strip()]

        lines = []
        p = run(f"hf cp {BUCKET}/{marker}.partial.txt /tmp/prev.txt")
        if Path("/tmp/prev.txt").exists():
            lines = Path("/tmp/prev.txt").read_text().splitlines()
        done_tests = set()
        for l in lines:
            m = re.match(r"=== (\S+) (?:PROOF )?(PASSED|FAILED)", l)
            if m:
                done_tests.add(m.group(1))
        todo = [t for t in tests if t not in done_tests]

        for t in todo:
            st = time.time()
            run(f'cd /work/probe && timeout -k 30s {budget_secs}s '
                f'kontrol prove --match-test {t} {PROVE_OPTS} > /tmp/one.log 2>&1')
            out = Path("/tmp/one.log").read_text(errors="ignore") if Path("/tmp/one.log").exists() else ""
            v, prop = verdict_of(out)
            el = int(time.time() - st)
            lines.append(f"=== {t} {v} ({prop}) [{el}s] ===")
            upload("\n".join(lines) + "\n", f"{marker}.partial.txt")
            if time.time() - t0 > deadline_s:
                results.append({"chunk": chunk, "status": "deadline"})
                return {"stage": stage, "build_ok": build_ok, "results": results,
                        "elapsed_s": int(time.time() - t0)}

        if not any("INCOMPLETE" in l for l in lines):
            upload("\n".join(lines) + "\n", f"{marker}.txt")
            results.append({"chunk": chunk, "status": "done", "tests": len(lines)})
        else:
            results.append({"stage": stage, "chunk": chunk, "status": "partial"})

    return {"stage": stage, "build_ok": build_ok, "build_tail": build_tail,
            "results": results, "elapsed_s": int(time.time() - t0)}


@app.local_entrypoint()
def main(wave: str = "wave_funded_b2",
         stages: str = "fundedb2_a1,fundedb2_a2,fundedb2_a5,fundedb2_a6,fundedb2_a7,fundedb2_a9",
         deadline: int = 21600, chunk_limit: int = 0, budget: int = 1800):
    calls = [run_stage.spawn(s.strip(), wave, budget, deadline, chunk_limit)
             for s in stages.split(",") if s.strip()]
    for c in calls:
        try:
            print(c.get(), flush=True)
        except Exception as e:
            print("stage failed:", str(e)[:200], flush=True)
