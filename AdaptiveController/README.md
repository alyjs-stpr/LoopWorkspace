# LoKey Adaptive — Read-Only Live Shadow Pilot

This feature is an **opt-in, native iOS observation system**. It observes
successfully completed normal Loop cycles and records evaluations from the
same Swift shadow policy used by the standalone replay program.

**It cannot administer insulin or change Loop settings.** Normal Loop remains
the sole insulin controller. This PR stays separate from Build 23 and PR #13.

## On-phone behavior (after this PR is validated, merged, and built)

1. Open **Theme Park Mode → Adaptive Shadow → Record live shadow decisions**.
2. When enabled, each normal Loop completion can trigger a read-only snapshot,
   including when Loop runs in the background. iOS does **not** guarantee a
   certain background recording frequency.
3. Snapshots contain current CGM reading, native Loop glucose predictions,
   recorded IOB and COB, native recommended automatic bolus (if available),
   and DoseStore-reported programmed and *delivered* insulin entries.
4. The identical tested Swift policy evaluates a hypothetical target
   preference within your currently active park target. If inactive, stale,
   or uncertain, it records the reason instead of an eligible preference.
5. Open **Export Shadow Records** to share the recorded JSONL files for replay
   and outcome analysis. Export is **user initiated only**.

The switch defaults to **OFF** and is independent of actual Theme Park Mode.
Once explicitly turned ON, recording continues on completed normal Loop
cycles **even outside the active park target session** until turned OFF.
Actual insulin delivery and temporary target overrides remain Loop-owned.

## Local handling of sensitive data

Records are kept locally in Application Support, protected after first unlock,
excluded from system backups, and removed after 14 days. No shadow records
are uploaded automatically. Files are **sensitive medical data**; treat an
export like a medical record and share only intentionally. There is no cloud
synchronization, model training, or automatic adjustment of therapy settings.

## Run the exact policy and retrospective analysis off-device

    swift test --package-path AdaptiveController

Replay real shadow-record files:

    swift run --package-path AdaptiveController lokey-adaptive-replay < export.jsonl

Evaluate actual later CGM readings versus **normal Loop's original forecast**:

    swift run --package-path AdaptiveController lokey-adaptive-replay --outcomes < export.jsonl

The `--outcomes` report measures forecast errors at 30, 60, 120 and 180
minutes **only where a subsequent real CGM reading exists**. It does not
claim to observe or measure what would have happened if the shadow target
had controlled insulin instead.

## Current safeguards and limits

- Native capture runs from Loop's **LoopCompleted** event, not the dashboard.
  A successfully completed Loop cycle must occur for each record.
- Missing, stale or invalid data, delivery uncertainty, or IOB disagreement
  block eligible adaptive recommendations.
- Recent pump data and a successful DoseStore read are a **limited proxy**
  for reconciliation; not proof that all delivery commands were executed.
  This proxy is strictly observation-only and must never authorize dosing.
- Every observation captures native requested/programmed and confirmed
  delivered insulin separately. An unconfirmed programmed dose is **not**
  treated as delivered insulin.
- The policy is kept byte-for-byte identical in its native iOS copy and
  its Swift package; CI checks this before accepting any app integration.
- Normal Loop therapy behavior must not change, even if shadow recording
  fails, freezes, or is disabled.

## Next work before any live experimental controller

- Validate recorded streams for completeness, especially overnight and
  app restarts; explicitly track missed cycles and data quality.
- Add clinically and technically appropriate glucose-response modeling,
  training/hold-out separation, calibration checks and drift detection.
- Build an end-to-end simulated pump and verify pending-command handling,
  IOB reconciliation, scheduling conflicts, target expiration and failover.
- Review failure modes and independent evidence before considering live
  automatic insulin-delivery integration.

Passing Swift tests and simulator compilation **does not validate the
experimental policy as safe to administer insulin.**
