# False-positive / false-negative lessons (Kontrol property review)

A single wrong line invalidates a whole stage's CI. This file records the classes
we hit and the checklist every new stage must pass.

## What happened (stage 2)

| Class | Symptom | Root cause |
|---|---|---|
| **Synthetic `P_AUTH_WRITE`** | all 15 P3 proxy targets "FAILED", same path condition `attacker = 3235823838` (= `0xC0DEC0DE`) | `PROXY` template seeds `slot0 = canary(0xC0DEC0DE)` and asserts "no slot equals attacker" **without** `vm.assume(attacker != canary)` → solver sets attacker = canary |
| **Aborted proof counted as FAIL** | P4 chunk 11 `CHEATCODE_UNIMPLEMENTED` | a call inside execution hit unmodeled behavior; the proof aborted — not a property violation |
| **Over-loose target signal** | P4 targets selected on a lone `TLOAD` | `sig_transient_caller` = `(tstore OR tload) & caller`; a two-phase write needs a real `TSTORE` |

## Fixes applied
- `gen_stage.py` PROXY: `vm.assume(attacker != canary)`.
- `gen_stage.py` P4 query: `AND o.c_tstore > 0`; `opcode_scan.py`: `sig_transient_caller = tstore>0 and caller>0` (baked into next rescan).
- Live instances manually triaged (both guarded: hardcoded `sweeper` auth / role-gated).

## Mandatory checklist before any stage/property ships
1. **Symbolic/concrete collision:** every concrete value the harness seeds into
   state or addresses (canary, mocks, tokens, allowances, balances, target,
   HEVM/console/precompiles) must be excluded from symbolic `attacker`/args via
   `vm.assume`. Missing one ⇒ synthetic FAIL.
2. **Controls prove the property both ways:** a must-FAIL that violates *only*
   the property, and a must-PASS that exercises the property's positive branch —
   not merely a gated revert that could mask a broken assertion.
3. **Aborts are not verdicts:** `CHEATCODE_UNIMPLEMENTED`, OOM, timeouts must be
   reported as INCOMPLETE/abort, never FAIL. Triage must separate them.
4. **Signals must encode a necessary condition** (two-phase ⇒ TSTORE present),
   not a lookalike.
5. **Read the failing node** (property label + path condition + model) before
   trusting any matrix result.
6. **Negative-test the template** on its controls locally/CI before a full run.

## Cost asymmetry
- **FP** wastes a whole stage's CI + triage (what happened here).
- **FN** (a missing `vm.assume`, an over-tight filter, or a property that never
  fires) hides a real zero-day — strictly worse. When tightening, always ask
  "could a genuine instance of this bug fail the necessary condition?"
