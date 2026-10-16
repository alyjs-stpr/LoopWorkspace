# LoKey T1D — Build 17 consolidated review and release checklist

This document describes **source-code review and pre-release checks**, not a medical-device safety certification. TestFlight build numbers advance on every upload and are not equal to feature numbers.

## Scope reviewed
- All `customizations/*.patch` currently on `main`, their application order and overlapping files
- Manual and automatic GitHub Actions build workflows, validation workflow, Fastlane versioning, Xcode scheme and submodule pins
- Dashboard charts, history selection, time-in-range (CGM versus Loop target), reporting and PDF export paths
- Carb entry and LoKey meal-tracking persistence, history, and confirmed native Loop carb handoff
- Missed-meal notification suppression heuristic and test coverage
- Nightscout/T1Pal onboarding fallback, Omnipod reservoir information handling, custom assets
- Previously open draft PRs are separate work and are **not** merged into this release

## Build 17 changes
- `LoKeyBuild17MealHistoryCleanup.patch`: one primary meal-entry form and a separate **history/settings-only** screen
- Keep existing V1 saved meal data unchanged; do not duplicate or migrate it
- Observational meal save is **not** proof of a completed Loop carb entry; do not store a proposed carb amount as if it were entered
- Native Loop carb quantity, date/absorption settings, Continue, final bolus review and delivery code untouched
- Manual workflow builds exactly `github.sha` and cannot silently upstream-sync
- Scheduled automatic sync/build only if repository variables are explicitly `SCHEDULED_SYNC=true` or `SCHEDULED_BUILD=true`; monthly/scheduled rebuilds no longer occur by default
- Validation triggers on **any** customization patch; check the full patch chain and run the existing missed-meal regression tests in the simulator
- Keep true pod reservoir behavior: **50+ U** when above the hardware threshold; no inferred/estimated unit count

## Pre-merge automated gates
- [ ] GitHub patch application succeeds against the pinned submodules **in production order**
- [ ] Swift parse and unsigned iOS simulator compilation succeed
- [ ] `LoopTests/MealDetectionManagerTests` actually **run** on iOS simulator and pass (source greps are not sufficient)
- [ ] Review the complete CI log for bypassed bundle validation, warnings, and test-scheme misconfiguration
- [ ] No modifications to pump commands, dose calculations, insulin predictions, or automatic dosing settings
- [ ] Signed TestFlight build is a separate manual action **after merge**, not a side effect of PR validation

## Pre-release UI and behavior checklist
- [ ] Main carb-entry screen shows actual carbs and actual protein separately
- [ ] Copy actual carbs into the native Loop field requires explicit confirmation; cancel makes no change
- [ ] Protein is **not** silently added to Loop carbs; native carb field remains manually editable
- [ ] Saving an observation never delivers insulin or creates a Loop carb entry
- [ ] Native Continue and separate final bolus confirmation remain available; do not deliver a dose solely to test UI
- [ ] History & settings shows only saved observations and baseline settings; no second entry form
- [ ] Existing historical observations survive updating an installed TestFlight app using the **same bundle ID**; uninstalling may remove local history
- [ ] History labels and deleted observations update as expected; default baselines persist
- [ ] Missed-meal notification guard suppresses redundant prompts near logged meals without hiding genuinely separate missed meals in the regression fixtures
- [ ] Dashboard CGM graphs, timeline selection, glucose delta, and Loop forecast are visually readable in light and dark mode
- [ ] CGM TIR uses the user's selected reporting range (e.g., **80–180 mg/dL**), distinct from Loop correction targets
- [ ] PDF settings export uses current settings and does not alter pump/Loop configuration
- [ ] Dexcom updates, Nightscout sync, and Omnipod control remain normal
- [ ] Pod displays the real reservoir reading at 50 U or below, and `50+` above that
- [ ] Watch/widget state, system alerts and accessibility sizing still behave appropriately
- [ ] Confirm TestFlight package validity, app signing and on-device behavior after signed build

## Known limits / remaining risks
- A source/simulator pass is not a proof of clinical safety or pump compatibility. On-device checks are still required.
- Existing missed-meal alert suppression is **heuristic**: it may hide a legitimate unlogged meal near an already logged meal. Never interpret a missing alert as proof all meals were entered.
- LoKey Adaptive Meals records observations and baselines; it has **no validated automatic CGM-learning or protein-dosing algorithm**.
- Meal history is stored locally in UserDefaults and is not automatically backed up to Nightscout or HealthKit. Keeping the same app installation should retain data; uninstalling can remove it.
- The existing T1Pal onboarding fallback tolerates certain 5xx authentication probe errors; routine data transfer should be checked separately and errors must not be hidden.
- The existing settings PDF contains sensitive therapy configuration: share and store it carefully.
- TestFlight builds expire; new uploads should be planned rather than scheduled unnecessarily.
- Do not assume every upstream or Omnipod firmware update is compatible with the pinned custom patch chain. Update upstream separately and review before building.

## Release discipline
1. Keep all work on a draft PR until CI passes and the review is completed.
2. Merge once for the consolidated update; only then trigger **Build Loop Manual**.
3. Compare the selected main commit, workflow run SHA, TestFlight build number, and installed app version.
4. Avoid repeated TestFlight uploads for cosmetic adjustments; batch nonurgent ideas for the next planned rebuild.
