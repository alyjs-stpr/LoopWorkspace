# LoKey / Omnipod-inspired UI overhaul — approved visual direction

## Guiding principle
Match the previously reviewed three-tab Omnipod-inspired LoKey screen closely: white cards on a very light gray canvas; prominent current glucose in saturated purple; small clean status indicators; a **solid observed historical glucose line** with a single most recent observed point; an explicitly separate **dashed/dotted future prediction**; accessible Meal / Bolus controls; vivid green for insulin. Avoid the old dense multi-chart dashboard. Sample screenshots / conceptual values are **not** sources of clinical data.

This is the visual specification, **not** an assertion that the full redesign has been implemented.

## Navigation
- Dashboard: large real-time glucose number, trend arrow, sample age, authentic Loop status, CGM/pod connectivity, minimal glucose chart, IOB and latest bolus / COB compact tiles; active mode and errors visible without scrolling.
- Insulin: green IOB graph, basal rate, insulin delivery, forecasts, delivered vs pending boluses, concise links into event history.
- Events: **new dedicated day-by-day history** (local midnight-to-midnight), calendar/date arrows, totals for delivered basal / automatic boluses / user-initiated boluses. Filters for All / Basal / Bolus; provenance filters Loop / User / Unknown. Every event: time, type, units (or U/hr for basal), duration, delivery status, originating system where recorded, and tap-for-details. Event histories remain viewable across days and daylight-saving boundaries, with no history silently truncated to today's one-hour chart window.
- Pod Info: native pump reading, **50+ U above the sensor's reporting threshold**; at/below the threshold display reported remaining units with up to two decimals (no mathematical estimate), last updated timestamp, activation/start time (if available), exact expiry timestamp, derived remaining days/hours/minutes, delivery state, and connection status. If data is stale or unknown, label it rather than asserting a fresh reading.
- Reports, Settings, TIR Purple Report and advanced tools: reachable, not removed. Navigation can have a fourth tab or a simple overflow to preserve sensible phone width.
- Persistent actions: Meal and Bolus, both routed to existing native Loop views and required confirmations.

## Hard preserve / safety boundaries
- Preserve the **actual Loop carb entry, carb editing, meal timing and absorption editing**; LoKey actual carbs / protein / user-adjustable protein fraction and review-before-copy workflow stay accessible.
- Preserve Pre-Meal, Workout, Theme Park temporary glucose targets, with active mode prominently identified and entry to each original control. No changes to target semantics or insulin math.
- New delivery/event history is read-only. Present verified dose type and source separately; do **not** equate the presence of a temp basal with its manual/automatic origin. Respect existing DoseStore flags only where reliable. Unknown provenance shows **Unknown**; never guess.
- Dose entries must distinguish programmed, delivered, pending, canceled and uncertain insulin. Never count merely programmed insulin as delivered in daily totals.
- Do not duplicate boluses or change delivery, automatic controller, pump communication, carb-store persistence, recommendations, prediction model, override scheduling, or underlying sensor timestamps.
- Never fill missing CGM samples by interpolation across meaningful gaps. Preserve actual samples in the native Loop data store. Prediction stays visually separate from observed history.
- Accessible light and dark modes, VoiceOver labels, Dynamic Type, safe-area spacing, and clear low/stale/disconnected alerts are non-negotiable.
- Avoid adding manual/auto mode labels from Omnipod 5; show genuine Loop-cycle / pump/CGM status instead.

## Incremental implementation status
- Build 29 draft patch `LoKeyBuild29SolidGlucoseHistory.patch`: changes **only LoKey opt-in dashboard chart presentation** to show historical samples connected by a solid purple trace, splitting at >12-minute gaps; predictions remain dashed, touch highlights remain intact.
- Build 29 draft patch `LoKeyBuild29PreciseReservoir.patch`: in Omnipod native reservoir HUD, allows up to two decimal places on reported U at/below 50; retains 50+ above threshold.
- Full native screen/card/navigation and day-by-day history overhaul are still to be built, tested, and visually compared to approved reference. This draft must not be merged as if the full overhaul is complete.

## Release review
1. Patch application on pinned LoopKit and OmnipodKit submodules with all earlier patches in production build order.
2. Swift parsing and unsigned simulator compilation. Do not claim passing unit tests if unsigned bundle failures or missing test runner prevent them.
3. Screenshot / visual comparison on iPhone to approved mockup, with dark mode / larger text.
4. Read-only events audit: same event IDs and source flags as authoritative logs; test temp basal, normal basal, user bolus, algorithm bolus, pending/canceled, and no-data cases; day boundaries and historic dates.
5. Test CGM gaps, chart real-vs-predicted styling, time axis, and hit testing, including the compressed 1-hour history / six-hour forecast projection.
6. Test actual pump >50 U, exact below-threshold reading, stale pump reading, expiry countdown, no pod.
7. On safe non-therapy setup validate modes, meal editing, protein calculator confirmation, carb persistence, bolus review and native delivery safeguards. **Do not deploy unreviewed changes to active dosing.**
