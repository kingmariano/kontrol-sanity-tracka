# 10 — Config snippets we use (CI, test lists, artifacts, git)

## 10.1 Where Kontrol runs for us
**Never locally** (2-core box). All Kontrol runs are GitHub Actions jobs in the pinned image
`runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255`.

## 10.2 Per-suite CI pattern (Resolv repo)
- One job per suite (`StUSR_Test`, `WstUSR_Test`, `UsrRedemption_Test`, `W4_Requests_Test`,
  `W3_Staking_Test`, `PriceStorage_Test`, `W5_Coordinator_Test`, `W6_OFT_Test`).
- `kontrol build` once, then a **per-test loop** from `tests/<Suite>.tests` (because 1.0.255 has no
  `--match-contract`), writing an explicit verdict line per test so a timeout never erases results.
- Steps: npm install (LayerZero JS deps) → `chmod -R a+rwX .` → `kontrol build` → per-test prove →
  `tar -czf kcfg_<Suite>.tgz -C out proofs || true` → upload verdicts+logs and the KCFG tar.
- `chmod -R a+rwX .` must run **before build** and **before every prove** (root container writes
  `out/`; non-root prove user then can't mkdir → `PermissionError: 'out/proofs/<id>:0'`).
- Timeouts: whole-suite budget (e.g. 300 min) split per test; `--step-timeout 600`.
- `if [ -d out/proofs ]; then tar -czf kcfg_<Suite>.tgz -C out proofs || true; fi` so a SIGKILLed
  container mid-write does not fail the job.

## 10.3 `tests/<Suite>.tests`
Plain list of test function names, one per line (read by the CI loop, passed as `--match-test`):
```
test_W2P1_noShareRoundTripGain
test_W2P2_noAssetRoundTripGain
...
```

## 10.4 Artifact names / retrieval
- Results: `resolv-<Suite>-results` (verdicts_<Suite>.txt, prove_<Suite>.log, build_output.log).
- KCFG: `resolv-<Suite>-kcfg` (`kcfg_<Suite>.tgz`, 14-day retention).
- Download: `GH_TOKEN=$CHRIS_TOKEN gh run download <run-id> -R artsbykriss/resolv-kontrol-audit -n <artifact> -D <dir>`.
- Proof dir name contains `:`; hence the tar.

## 10.5 Git / auth ops (artsbykriss = CHRIS account)
- The CHRIS classic token in `CA/.env` (`CHRIS_GITHUB_API_KEY`) authorises the `artsbykriss` repo;
  the main token (`kingmariano`) is **read-only** there (`push:false`) so it cannot push.
- **Gotcha:** `.env` had a trailing `\r` (CRLF) → token length 41 → `HTTP 401`. Strip it:
  `tr -d '"' | tr -d '\r' | tr -d '[:space:]'`.
- `git push` with the token without echoing it (askpass):
  ```
  printf '#!/bin/sh\ncase "$1" in *Username*) echo artsbykriss;; *) echo "$CHRIS_TOKEN";; esac\n' > /tmp/askpass.sh
  chmod +x /tmp/askpass.sh
  export CHRIS_TOKEN=$(sed -n 's/^CHRIS_GITHUB_API_KEY=//p' CA/.env | tr -d '"' | tr -d '\r' | tr -d '[:space:]')
  GIT_ASKPASS=/tmp/askpass.sh GIT_TERMINAL_PROMPT=0 git -c credential.helper= push https://github.com/artsbykriss/resolv-kontrol-audit.git HEAD:main
  rm -f /tmp/askpass.sh
  ```
  (`gh` with `GH_TOKEN` alone did NOT override the stored credential for `git push`.)

## 10.6 `kontrol.toml` (optional)
Options can also come from `kontrol.toml` keys by field name. If you add a flag, wire it in
`cli.py` + `options.py` (`default()` + `from_option_string()`) + toml — the same option can arrive
from any of the three. (Not required for our setup; we pass flags on the CLI.)

## 10.7 Docker image / build
- Image tag format: `runtimeverificationinc/kontrol:<ubuntu>-<kontrol-version>`, e.g.
  `ubuntu-jammy-1.0.255`.
- Run inside the project root: `docker run --rm -v "$PWD":/work -w /work <image> kontrol build|prove …`.
