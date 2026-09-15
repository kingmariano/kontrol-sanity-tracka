# 06 — Lemmas, stuck nodes, and KCFG surgery

## When manual intervention is needed
- **stuck node**: execution not finished, not subsumed by the target, and Kontrol sees no further
  steps.
- **invalid path**: Kontrol failed to notice a contradiction in the path condition.
Both are fixed by supplying the missing reasoning as **lemmas**.

## Lemma = a K rewrite rule with the `[simplification]` attribute
```
rule [name-of-lemma]: <k> LHS(X, Y) => RHS(X, Y) </k>
  requires condition1(X) andBool condition2(Y)
  [simplification]
```
Attributes: `smt-lemma` (push to SMT; functions must have `smt-lib`), `concrete(VAR)`,
`symbolic(VAR)`. Combine: `[simplification, concrete(X), symbolic(Y)]`. `orBool` also allowed.

## Adding lemmas to a project
Create `myproject-lemmas.k`:
```
requires "foundry.md"
module MYPROJECT-LEMMAS
    imports BOOL
    imports FOUNDRY
    imports INFINITE-GAS
    imports INT-SYMBOLIC
// lemmas
endmodule
```
Then:
```
kontrol build --require test/myproject-lemmas.k \
              --module-import MyProjectTests:MYPROJECT-LEMMAS \
              --rekompile
```
(`--rekompile` is mandatory after changing lemmas.)

## `runLemma => doneLemma` probe
To test whether an expression simplifies, write a claim `runLemma(A) => doneLemma(B)`.
Running it includes an **implication check**, so a pass means `A` simplifies to some `B'` that
*implies* `B` — not necessarily exactly `B`.

## KCFG surgery commands (interactive debugging)
- `kontrol simplify-node <test> <node>` — simplify a node.
- `kontrol step-node <test> <node>` — take one step.
- `kontrol section-edge <test> <edge>` — split a long edge into pieces (isolate one slow/failing step).
- `kontrol split-node <test> <node> "<condition>"` — insert a user-chosen branch condition.
- `kontrol remove-node <test> <node>` — delete a node/branch.
- `kontrol merge-nodes <test> ...` — merge nodes.
- `kontrol refute-node <test> <node>` / `unrefute-node` — pause/unpause a branch (builds a
  refutation subproof; has known soundness caveats, haskell-backend#3605).
- `kontrol minimize-proof` — minimize the KCFG.

## Non-deterministic branch → split → refute workflow
1. `kontrol remove-node <test> <root-of-nondet>` to drop the non-deterministic branch.
2. `kontrol split-node <test> <node> "<cond>"` repeatedly to reconstruct the cases you care about
   as **splits** (e.g. `VV0_addr ==Int <each preexisting address>`).
3. `kontrol refute-node` the cases you don't care about (execution pauses there).
4. Resume: `kontrol prove --match-test <test>` (no `--reinit`).
5. Finally, make the refutations permanent by **adding assumptions to the test** and restarting
   (cleanest), or discharge them with lemmas. Upstream the generated `claim X => false` as a
   regression test for the new lemma.

## Simplifications tips
- After adding a lemma that removes an unnecessary branch, **delete the `split` node** from the
  KCFG before continuing; otherwise both branches remain and the unneeded one collapses to `#Bottom`.
- `kontrol show --to-kevm-claims` / `--to-kevm-rules` can emit the KCFG as claims/rules.
