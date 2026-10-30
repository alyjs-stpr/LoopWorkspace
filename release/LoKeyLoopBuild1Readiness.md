# LoKey Loop — Fresh Build 1 readiness

This document defines the **LoKey Loop Build 1 release baseline** for the approved dashboard and insulin/pod screens. It is an internal **release label**, not a request to reset Apple's CFBundleVersion or change the app's bundle identifier.

## Included in the candidate
- Purple glucose dashboard, green insulin overview, native safety indicators and Loop's unchanged dosing workflow.
- Pod Info screen with a shortcut to native Omnipod management (does NOT initiate deactivation).
- Native-accurate last successful Loop (green through 6 minutes, yellow through 16, then red), tap for exact completion time and native status.
- Report a suspected leak against **Current Pod** or **Previous Pod** when the Omnipod manager supplies its retained previous activation timestamp.
- Existing report can be reassigned to Previous Pod, correcting a late report without erasing the original event.
- Six-hour observational watch measured from replacement pod activation, not the report time, with old-pod attribution and expiry. If a report comes in after that window, history is retained, but the expired watch is not restarted.
- Four consecutive glucose increases each **strictly above 7 mg/dL** across five fresh CGM samples. Tier 1 observation of rising glucose below 180; tier 2 high glucose with sustained rise at 180+; tier 3 independently warns for very high glucose at 250+.
- More serious alerts bypass the 30-minute lower-priority cooldown. No automatic insulin or correction amount.
- Visible last CGM freshness warning and a scrollable incident history.

## Release gates
- [ ] PR source installation, Swift parsing, and simulator compilation all pass; investigate any simulator-bundle validator exemptions.
- [ ] Compare installed UI with three approved screenshots, including small landscape/large text.
- [ ] Verify exact Loop completion timestamp; check native green/yellow/red and tapping details.
- [ ] Confirm Pod Info Change Pod opens existing native pump UI, **never** deactivates immediately.
- [ ] With a simulated/past test event, report Current Pod and Previous Pod independently and verify the correct persisted identity.
- [ ] Confirm a late report of an already-replaced pod uses replacement activation for its six-hour boundary.
- [ ] Verify existing misattributed report can be explicitly reassigned; never auto-infer another pod.
- [ ] Confirm four >7 mg/dL rises, four samples vs five, missing readings, stale timestamps, and no false correction prompt for normal-range rises.
- [ ] Confirm elevated glucose bypasses the lower alert's cooldown and urgent 250+ warning triggers independently.
- [ ] Confirm warning/bolus uncertainty remains informational and no dosing or IOB algorithms changed.
- [ ] Confirm the watch expires, is persistent through app restart, leaves history intact, and its CGM freshness warning is obvious.
- [ ] Confirm notification permissions and actual iOS background behavior; background alerts are best effort only.
- [ ] Verify Adaptive Shadow remains observation-only, with no coupling to future LoKey Adaptive repo.
- [ ] Confirm a signed App Store/TestFlight workflow succeeds before replacing current app.

## Build numbering
`fastlane/Fastfile` currently sets the TestFlight build number to the **latest TestFlight build + 1**. Maintain that monotonically increasing Apple build number for installation compatibility. Call the newly approved release **LoKey Loop Build 1** in release notes and, *only after validated*, mark the exact merge commit with a release tag. Do not reset or change the existing bundle ID, provisioning or data store just to display "1".

## Safety
This is a supplementary pattern watcher, not a physically verified leak sensor and not a replacement for Dexcom safety alerts, glucose/ketone checks or a pump-failure plan. It does not administer corrections.
