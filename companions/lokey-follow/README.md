# LoKey Follow

Separate, read-only native companion for LoKey Loop: Android phones/tablets and iPhone/iPad. This directory is independent of the Loop workspace and its insulin-delivery build.

## Status

First implementation for review. Nightscout hosting has **not** been provisioned or connected to a real uploader. Simulator/device validation is required before relying on the display. No dosing, remote commands, treatment logging, or alarm service is implemented.

## Screens and widgets

- Dashboard: glucose, real elapsed-time delta, rate of change, Loop-supplied IOB, prediction graph, recent boluses and absolute temp basals/suspensions.
- Display mode: large glucose value and graph, dark purple/bright green theme, optional screen-awake behavior while visible. Suitable for a spare phone/tablet.
- Android: compact glucose and larger dashboard home-screen widgets; background polling requests every 15 minutes through WorkManager. Tap opens the app for an immediate refresh.
- iOS: small/medium home-screen and lock-screen WidgetKit widgets. A shared Keychain credential lets the extension fetch independently. Timeline reloads are requested after 15 minutes; iOS decides actual timing.
- Both apps show source timestamps and distinguish stale glucose from stale Loop/IOB. Predictions are hidden when Loop data is stale. Widgets are snapshots, not continuous monitors or primary CGM alarms.

Purple represents glucose; vivid green represents insulin. No sample glucose is shown as live data. Credentials are entered on each device and stored in Keychain/Android Keystore, never in the repository.

## Nightscout first

See [Nightscout setup](nightscout/SETUP.md). Each device gets its own `readable` token. A user can independently change their display preferences. Only HTTPS URLs without embedded credentials or tokens are accepted; API tokens travel in the `API-SECRET` header. The app rejects redirects to avoid forwarding the token elsewhere.

## Android build

Open `android/` in Android Studio (JDK 17, SDK 35). Install Gradle 8.11.1 or use the Follow check workflow, which installs it. Run `gradle testDebugUnitTest assembleDebug`. The debug APK is for installation testing; publishing needs a stable signing key and release workflow. Minimum Android 8.0.

## iOS build

On a Mac with Xcode 16+ and XcodeGen, run `xcodegen generate` in `ios/`, open `LoKeyFollow.xcodeproj`, and select your Apple Developer team for the app and widget. Register `net.lokey.follow`, `net.lokey.follow.widgets`, and App Group `group.net.lokey.follow` (or consistently rename all three). Enable the App Group for both identifiers. Both targets use the same Keychain access group. Simulator builds do not require signing. Minimum iOS 17.

The new app needs its own App Store Connect/TestFlight app record and provisioning; existing LoKey Loop signing profiles do not automatically cover it. Do not run Build Loop Manual expecting it to create Follow.

## Data limits

Predictions are the uploaded Loop forecast, not a calculation by Follow. Delta uses adjacent distinct glucose readings 2–10 minutes apart and labels the actual interval. IOB uses its own timestamp. An active **temp** basal is displayed only if a non-cancelled, absolute treatment is still within its duration; the scheduled basal is not inferred. Uploaded boluses are not a total daily insulin estimate. Treatment lists are limited to the last six hours/1,000 records and glucose to 24 hours/1,000 records. Gaps are not joined in the measured glucose chart.

## Validation before live use

Verify readings/timestamps, IOB including negative values, prediction horizon, suspensions and boluses against LoKey and Nightscout. Test token revocation, no connectivity, old glucose with new Loop data and the reverse, background/widget behavior, font scaling, landscape and sleep/lock. Keep primary device alerts in use.

Sources: [Loop upload mapping](https://github.com/LoopKit/NightscoutService/blob/2cef4896f0704fb112575ab34b596ee7de78e48d/NightscoutServiceKit/Extensions/StoredDosingDecision.swift), [dose mapping](https://github.com/LoopKit/NightscoutService/blob/2cef4896f0704fb112575ab34b596ee7de78e48d/NightscoutServiceKit/Extensions/DoseEntry.swift), [Nightscout API authorization](https://github.com/nightscout/cgm-remote-monitor/wiki/API-v1-Security), [Android refresh rules](https://developer.android.com/develop/ui/views/appwidgets/advanced), [WidgetKit timelines](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date).
