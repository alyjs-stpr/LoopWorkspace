# LoKey Adaptive Controller — Experimental Foundation

This is the **first implementation of the experimental decision policy**, not a
live insulin-dosing release. It is deliberately outside the signed LoKey app's
pump-command path. It does **not** link to OmnipodKit, request a bolus, adjust
basal, or modify Loop settings.

## What works now

- Deterministic evaluation of actual or recorded Loop-style glucose prediction
  snapshots against the user's selected Theme Park target range.
- A candidate *shadow* target within that selected range, with priority given
  to predicted lows when both low and high excursions appear in the forecast.
  **A shadow target does not affect real insulin delivery.**
- Fail-closed handling of stale CGM readings, stale Loop calculations,
  incomplete forecasts, unreconciled dose history, uncertain pump delivery,
  and unknown IOB.
- A test-only ownership/handoff model that preserves pending-delivery and
  reconciliation gates instead of assuming the handoff is automatically safe.
- Replay of newline-delimited JSON snapshots against this exact Swift policy.

## Run tests

From the repository root on a machine with Swift installed:

    swift test --package-path AdaptiveController

Run recorded snapshots (only input explicitly provided by the user):

    swift run --package-path AdaptiveController lokey-adaptive-replay < snapshots.jsonl

The JSON schema is the public \`LoKeyAdaptive.Snapshot\` Codable type in
\`Sources/LoKeyAdaptiveCore/Controller.swift\`, with ISO-8601 timestamps.

## Milestones required before consideration for a live controller

1. Create an audited, read-only bridge from native Loop glucose predictions and
   **DoseStore** IOB into Snapshot; confirm numerical units, timing, and
   provenance. Never reconstruct IOB from a UI string.
2. Define an actual adaptive insulin policy in consultation with appropriate
   safety expertise; no arbitrary increases or hidden changes to insulin delivery.
3. Establish replay fixtures from consented historical readings and deliverability
   events; separately compare real versus counterfactual predictions.
4. Test a simulated pump end to end, including retries, delayed acknowledgments,
   stale CGM data, disconnects, changes to effective targets, app restarts,
   and simultaneous controller requests.
5. Demonstrate atomic handoff with a **single** pump-command owner and
   preserved, reconciled dose history.
6. Independently review failure-mode coverage and test evidence before live use.

## Explicit non-goals of this PR

- It **does not** authorize or issue live insulin dosing.
- It **does not** affect the already deployed Theme Park UI or native Loop
  bolus/automatic dosing logic.
- Passing these unit tests is necessary engineering evidence; it does not
  demonstrate clinical safety or qualify a controller for live use.
