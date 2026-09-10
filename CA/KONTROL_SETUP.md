# Kontrol — Installation & Operations (this Codespace)

Status: ✅ INSTALLED & VERIFIED (Docker route)

## Setup
- Image: `runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255` (9.8 GB, newest tag; NO `latest` tag exists)
- Docker data-root relocated to `/tmp/docker-data` (`/etc/docker/daemon.json`); dockerd
  must be started manually after container rebuild:
  `sudo service docker restart` won't work — use:
  `sudo pkill dockerd; (sudo setsid dockerd --containerd /run/containerd/containerd.sock --dns 168.63.129.16 </dev/null >/tmp/dockerd.log 2>&1 &)`
- Swap: 16 GB at `/tmp/swapfile` (re-create if missing:
  `sudo fallocate -l 16G /tmp/swapfile && sudo chmod 600 /tmp/swapfile && sudo mkswap /tmp/swapfile && sudo swapon /tmp/swapfile`)
- Foundry 1.5.1 + cast bundled in image; kontrol at `/home/user/.local/bin/kontrol`

## Container quirks (learned the hard way)
1. Container user is uid 1010 (`user`), host is uid 1000 (`codespace`), no sudo in image.
   After a container writes to a mounted volume, fix perms with a root container:
   `docker run --rm -u 0 -v <dir>:/work --entrypoint bash <img> -c 'chmod -R a+rwX /work'`
2. `--test` flag is NOT repeatable in 1.0.255 → use `--match-test 'Regex.*'`
3. `kontrol --version` errors (needs subcommand) — not a broken install

## Verified end-to-end test (2026-09-10, /tmp/kontrol-test/testproj)
- `kontrol build` → ✅ 4m33s first time (digest-cached afterward)
- `kontrol prove --match-test 'CounterTest.testFuzz_.*' --auto-abstract-gas`:
  - `testFuzz_SetNumber` ✅ PASSED (41s)
  - `testFuzz_IncrementIsExact` ❌ FAILED — correctly! Proof found x = MAX_UINT256
    (overflow/revert edge case no fuzzer would sample)
- `kontrol get-model CounterTest.testFuzz_IncrementIsExact` → `KV0_x = maxUInt256` ✅
- `--generate-counterexample` produced `CounterTestCounterexampleTest.t.sol`
  (experimental: symbolic vars NOT substituted in generated file — use
  `kontrol get-model` for concrete values; also `--fail-fast` default truncates)

## Standard command template (bytecode harness)
```bash
IMG=runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255
docker run --rm -v /tmp/audit:/work -w /work/<proj> $IMG \
  kontrol build --rekompile          # only when sources/lemmas change
docker run --rm -v /tmp/audit:/work -w /work/<proj> $IMG \
  kontrol prove --match-test 'TargetContract\.test.*' \
  --auto-abstract-gas --no-break-on-calls --use-booster \
  --bmc-depth 10 --smt-timeout 10000 --workers 2
docker run --rm -v /tmp/audit:/work -w /work/<proj> $IMG \
  kontrol get-model <Contract>.<test>
```
