# LoKey Loop: Possible Pod Leak / Uncertain Insulin Absorption

**Status:** Proposed, design-only. No runtime code is modified by this document.

## Why this is different from an uncertain bolus

Loop's Event History "Certain/Uncertain" concerns the pump's communication/delivery record. A physical leak at the pod or cannula may mean that less insulin entered the body than the pump reports, with an *unknowable absorbed amount*. We must not overwrite pump history or assume a percentage was lost.

## Feature 1: Report a possible leak

Accessible from Insulin > Event History, with a secondary entry in Settings > LoKey Settings.

- A prominent, user-confirmed **Report Possible Pod Leak** action (never inferred solely from glucose).
- Incident date/time (defaults to now, editable); status *Suspected*, *Observed Leak*, or *Resolved*.
- Link to one or more recent native bolus records, if available, with their **pump-reported units and timestamps only**; do not relabel as units absorbed.
- Optional observations: wet adhesive, insulin smell, visible fluid, loose pod, unexpected glucose response, free-text notes; time of pod replacement; no required estimate of units missed.
- Preserve the observation locally in a namespaced record, with unique ID, user edits and resolution history; never mutate native DoseStore, HealthKit, Loop insulin history, IOB or carb records.
- Avoid patient-identifying data in exports; make exports explicitly user initiated.

## Feature 2: Warning while unresolved

- Small, clearly visible banner on the Dashboard and existing Bolus review: **Possible pod leak — the amount of insulin absorbed is unknown. Loop IOB may not reflect the insulin actually received.**
- During manual bolus review, provide a way to view the incident and acknowledge the uncertainty **without changing the existing calculated dose or confirmation flow**.
- Keep native pump/CGM/Loop warnings visible; do not hide or replace a critical alert. No automatic bolus, basal adjustment, extra correction, dose withholding, or unvalidated changes to insulin math.
- Add a clear marker to Event History and optional charts, distinct from communication-related "Uncertain" dose events.
- Let the user resolve the incident, retaining an auditable record. Never silently infer resolution from a time window or a later CGM value.

## Feature 3: Adaptive Shadow research annotation

- When shadow recording is opted in, allow the event ID and time span to be included as **read-only context** in subsequent shadow analysis and exported research data.
- Avoid claiming that glucose trends prove leakage or how many units were absorbed.
- No automatic IOB rewrite, therapy adjustment, or dosing decision based on the flag. Any future adaptive dosing use must be separately reviewed, tested and explicitly approved in the *different* LoKey Adaptive app.

## Safety and quality gates

- No change to pump pairing, pump commands, basal schedules, bolus dose calculations, insulin ledger, or native safety alerts.
- Display missing values as unknown; never guess the amount absorbed.
- Test event creation, linkage, edits, persistence across relaunch, re-review, resolution, export, and alert visibility.
- Test that creating/resolving an event makes no changes to computed dosing values or native delivery records.
- Implement on a **separate branch and PR after** restoring the user-approved compact Build 32 dashboard and validating that baseline on the phone.
- If a leak is occurring, UI can direct to established pump-failure instructions, inspection/replacement of a suspicious pod, and glucose/ketone checks as appropriate, but never prescribe an invented correction dose.

**References:** LoopDocs *Bolus* (Event History certainty) and *Displays* (uncertain pump reporting); Omnipod manufacturer pod-site troubleshooting instructions.
