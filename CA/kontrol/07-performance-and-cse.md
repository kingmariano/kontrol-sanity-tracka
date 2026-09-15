# 07 — Performance, CSE, and backend debugging

## Flags that make the biggest difference (in order)
1. `--no-break-on-calls` (default) — fewer KCFG nodes = less writing/proving.
2. `--auto-abstract-gas` — drop gas reasoning (big branching reduction). Do NOT combine with
   `--use-gas` unless gas is the property.
3. `--use-booster` (default) — fast rewriting engine.
4. `--bmc-depth <n>` — replace loops with bounded unrolling when you don't want loop invariants.
5. `--workers n` — parallelism. **Guidance: ≤ (RAM_GB - 8)/8.** On a 2-core box keep small (1–2).
6. `--max-depth` / `--max-iterations` — bound work so a proof checkpoints instead of hanging.
7. `--cse` — Compositional Symbolic Execution (below).

## Compositional Symbolic Execution (CSE)
Use `--cse` to prove functions compositionally (summaries reused across proofs; node merging).
Good when the same internal call is proven repeatedly. See the docs CSE guide.

## Reduce symbolic branching
- **Kill symbolic-address branching** with `vm.assume(addr != address(this)); vm.assume(addr != address(vm)); vm.assume(addr != address(<other deployed>));`
- Constrain ranges early with `vm.assume` (not `bound`).
- Avoid short-circuit `&&`/`||` where possible (each introduces branching).
- Avoid `*Int`/division-heavy arithmetic in hot paths; add lemmas for recurring shapes.

## Why a proof stalls → Haskell-backend logging
Turn on per-request logs:
```
kontrol prove --match-test 'MyC.testThing()' \
  --haskell-log-dir hlog --verbose
# entries default: DebugAttemptEquation,DebugApplyEquation,DebugTerm,Proxy,Detail,Abort,Simplify,Rewrite
# add --booster-only-simplify to see what Booster does without the Kore pass
```
Each RPC request writes `hlog/<request-id>.jsonl` (one JSON object per line:
`{"context":[tags...],"message":...}`). Grep/`jq` by the lowercase `context` tags
(`kore`, `booster`, `abort`, `simplification`, `failure`).

Recipes:
```bash
# lemmas Kore applied (label + location), by frequency
jq -rc 'select(.message.label?) | "\(.message.label)\t\(.message.location)"' hlog/*.jsonl | sort | uniq -c | sort -rn
# where Booster aborted & fell back to Kore
jq -c 'select(.context|index("abort")) | .message' hlog/*.jsonl
# why Booster rejected a rule
jq -rc 'select((.context|index("booster")) and (.context|index("failure"))) | .message' hlog/*.jsonl | grep -v '^{' | sort | uniq -c | sort -rn
```
Booster failure reasons → fixes:
| Reason | Meaning | Fix |
|---|---|---|
| `Uncertain about definedness … non-total symbol Lbl<f>` | can't establish RHS defined | add `[total]` to `<f>` or `[preserves-definedness]` to the rule |
| `Concreteness constraint violated: term has variables` | `concrete(...)` rule met a symbolic arg | add `symbolic(...)` variant or a lemma |
| `Symbols differ` / `Values differ` | LHS pattern didn't match | reshape the lemma / normalise earlier |
| `Condition simplified to #Bottom.` | a `requires` couldn't be discharged | supply the missing fact (often an `[smt-lemma]`) |
Logging requires pyk support (`kframework>=7.1.333`) and kevm_pyk `legacy_explore` forwarding;
applies to `prove`, `simplify-node`, `step-node`, `section-edge`, `get-model`, `show --failure-info`.

## Isolating one slow step
```
kontrol prove --match-test 'MyC.testThing()' --max-iterations 1          # advance frontier
kontrol prove --match-test 'MyC.testThing()' --max-iterations 1 --max-depth 1 \
  --haskell-log-dir hlog --verbose                                     # log just the next step
kontrol section-edge 'MyC.testThing()' <edge>                          # if the edge is too big
```

## Resource notes
- Docs: 16 GB RAM recommended for running Kontrol locally; Booster RPC and Z3 are the memory hogs.
- Our CI runs one job per suite in `runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255`
  with `--workers 2` (we never run Kontrol locally — CI only).
