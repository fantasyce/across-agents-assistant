# E2E Failure Triage

Use this skill when the solidified Loop Engineering E2E fails or returns an incomplete candidate promotion packet.

## Triage Order

1. Read the solidified summary JSON, then the copied E2E summary JSON, then the E2E log.
2. Separate product capability failures from validation-only failures. Computer Use attach, GUI click reachability, and screen automation are validation-only unless the product change explicitly targets frontend capability.
3. Classify the failure by layer: Trigger, Contract, Memory and State, Tool, Agent Orchestration, Verification and Promotion.
4. For `spec.invalid` or `capability.missing`, inspect LoopSpec `required_capabilities`, `runtime_policy`, and dry-run `capability_preflight`.
5. For candidate failures, inspect source-ref pins, deterministic quality findings, validation commands, self-hosting probe, semantic review, and promotion attestation before editing code.
6. For model failures, confirm builder and reviewer are distinct, then inspect host model command JSON repair evidence.

## Required Commands

Run these before declaring the chain fixed:

```bash
scripts/loop_engineering_skill_tool_matrix.sh --json --strict
scripts/run_loop_engineering_solidified_e2e.sh
```

If the failure is in Autopilot runtime code, also run:

```bash
npm run check
```

If the failure is in AAA API or Workbench decoding, also run the relevant Python and Swift behavior checks.
