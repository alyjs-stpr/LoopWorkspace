#!/usr/bin/env python3
"""Install the bounded, pod-specific LoKey suspected-leak supervisor.

Run AFTER the existing leak annotation, approved UI, and Change Pod patches.
This deliberately leaves Loop dosing, IOB, predictions and pump commands alone.
"""
from pathlib import Path

ROOT = Path("Loop/Loop")
STATUS = ROOT / "View Controllers" / "StatusTableViewController.swift"
DEVICE = ROOT / "Managers" / "DeviceDataManager.swift"

def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return source.replace(old, new, 1)

def replace_section(source: str, first: str, next_marker: str, replacement: str, label: str) -> str:
    if source.count(first) != 1 or source.count(next_marker) != 1:
        raise RuntimeError(f"{label}: section markers not unique")
    start = source.index(first)
    end = source.index(next_marker, start)
    return source[:start] + replacement.rstrip() + "\n\n" + source[end:]

def install() -> None:
    ui = STATUS.read_text()
    data = DEVICE.read_text()

    data = replace_section(data,
        "    private func loKeyCheckSuspectedPodLeakAfterCGM() {",
        "    private func processCGMReadingResult(",
        r'''
    // The identity of the reported pod is its pump-reported activation time.
    // Persist the *replacement* activation time so the watch window does not
    // reset when app screens refresh or the phone is restarted.
    // Returning an active state does not imply the current pod is leaking.
    func loKeyLeakSupervisorState() -> (isWatching: Bool, isPreviousPod: Bool, minutesRemaining: Int?) {
        let defaults = UserDefaults.standard
        guard let reportedPod = defaults.object(forKey: "LoKeyLeakFlagPodStartV1") as? Date else {
            return (false, false, nil)
        }

        let activePod = pumpManagerHUDProvider?.hudViewRawState["podActivatedAt"] as? Date
        var replacement = defaults.object(forKey: "LoKeyLeakReplacedAtV1") as? Date

        if replacement == nil, let activePod,
           activePod > reportedPod.addingTimeInterval(60) {
            replacement = activePod
            defaults.set(activePod, forKey: "LoKeyLeakReplacedAtV1")
            var events = defaults.array(forKey: "LoKeyLeakEventHistoryV1") as? [[String: Any]] ?? []
            events.append([
                "timestamp": Date(),
                "podActivatedAt": reportedPod,
                "replacementPodActivatedAt": activePod,
                "event": "replacement-detected",
                "observation": "Six-hour post-replacement glucose supervisor started."
            ])
            defaults.set(Array(events.suffix(200)), forKey: "LoKeyLeakEventHistoryV1")
        }

        guard let replacement else {
            // No confirmed replacement yet: continue original leak surveillance.
            return (true, false, nil)
        }

        let seconds = replacement.addingTimeInterval(6 * 60 * 60).timeIntervalSinceNow
        if seconds <= 0 {
            // Automatic expiry stops monitoring, but preserves the incident log.
            var events = defaults.array(forKey: "LoKeyLeakEventHistoryV1") as? [[String: Any]] ?? []
            events.append([
                "timestamp": Date(),
                "podActivatedAt": reportedPod,
                "replacementPodActivatedAt": replacement,
                "event": "six-hour-watch-completed",
                "observation": "Post-replacement watch ended; history retained."
            ])
            defaults.set(Array(events.suffix(200)), forKey: "LoKeyLeakEventHistoryV1")
            defaults.removeObject(forKey: "LoKeyLeakFlagPodStartV1")
            defaults.removeObject(forKey: "LoKeyLeakReplacedAtV1")
            defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.set(false, forKey: "LoKeyDeliveryLeakActiveV1")
            return (false, true, 0)
        }

        return (true, true, Int(ceil(seconds / 60)))
    }

    // New CGM data triggers evaluation, including during permitted background
    // ingestion. Never guess missing readings or recommend replacement insulin.
    private func loKeyCheckSuspectedPodLeakAfterCGM() {
        let defaults = UserDefaults.standard
        let supervisor = loKeyLeakSupervisorState()
        guard supervisor.isWatching,
              let reportedPod = defaults.object(forKey: "LoKeyLeakFlagPodStartV1") as? Date else { return }

        let start = Date().addingTimeInterval(-27 * 60)
        glucoseStore.getGlucoseSamples(start: start, end: nil) { [weak self] result in
            guard let self, case .success(let samples) = result else { return }
            let readings = samples.sorted { $0.startDate < $1.startDate }
            guard let latest = readings.last,
                  latest.startDate.timeIntervalSinceNow >= -(10 * 60),
                  latest.startDate.timeIntervalSinceNow <= 60 else { return }

            let glucose = latest.quantity.doubleValue(for: .milligramsPerDeciliter)
            guard glucose.isFinite else { return }

            // Four consecutive *increases* >7 mg/dL means five distinct CGM
            // readings, each normally ~5 minutes apart; reject gaps/replays.
            var consecutiveRises = 0
            if readings.count >= 5 {
                for i in stride(from: readings.count - 1, through: 1, by: -1) {
                    let current = readings[i]
                    let previous = readings[i - 1]
                    let elapsed = current.startDate.timeIntervalSince(previous.startDate)
                    let currentMgDl = current.quantity.doubleValue(for: .milligramsPerDeciliter)
                    let previousMgDl = previous.quantity.doubleValue(for: .milligramsPerDeciliter)
                    guard elapsed >= 3 * 60, elapsed <= 7 * 60,
                          currentMgDl.isFinite, previousMgDl.isFinite,
                          currentMgDl - previousMgDl > 7 else { break }
                    consecutiveRises += 1
                    if consecutiveRises >= 4 { break }
                }
            }

            let sustainedSpike = consecutiveRises >= 4
            // Retain the existing independent very-high glucose safety alert.
            let veryHigh = glucose >= 250
            guard sustainedSpike || veryHigh else { return }
            // Recheck after async sample fetch, including expiry or manual clear.
            let updated = self.loKeyLeakSupervisorState()
            guard updated.isWatching,
                  defaults.object(forKey: "LoKeyLeakFlagPodStartV1") as? Date == reportedPod else { return }

            let now = Date()
            if let lastAlert = defaults.object(forKey: "LoKeyLeakWatchLastAlertV1") as? Date,
               now.timeIntervalSince(lastAlert) < 30 * 60 { return }
            // Protect against repeat callbacks with the same latest CGM sample.
            if let alertedSample = defaults.object(forKey: "LoKeyLeakLastAlertSampleV1") as? Date,
               alertedSample >= latest.startDate { return }

            defaults.set(now, forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.set(latest.startDate, forKey: "LoKeyLeakLastAlertSampleV1")
            let phase = updated.isPreviousPod ? "Post-replacement" : "Suspected pod leak"
            let riseText = sustainedSpike ? "4 consecutive increases greater than 7 mg/dL." : "Very high glucose."
            let summary = String(format: "CGM %.0f mg/dL. %@", glucose, riseText)

            var events = defaults.array(forKey: "LoKeyLeakEventHistoryV1") as? [[String: Any]] ?? []
            events.append([
                "timestamp": now,
                "podActivatedAt": reportedPod,
                "event": "supervisor-glucose-alert",
                "observation": summary,
                "cgmMgDl": glucose,
                "fourConsecutiveRises": sustainedSpike,
                "previousPodReplaced": updated.isPreviousPod
            ])
            defaults.set(Array(events.suffix(200)), forKey: "LoKeyLeakEventHistoryV1")

            let notification = UNMutableNotificationContent()
            notification.title = "LoKey · " + phase + " glucose watch"
            notification.body = summary + " Review Loop and check whether a correction is appropriate under your pump-failure plan. Do not assume how much insulin was absorbed."
            notification.sound = .default
            UNUserNotificationCenter.current().add(
                UNNotificationRequest(identifier: "lokey.leakwatch." + UUID().uuidString,
                                      content: notification, trigger: nil)
            )
        }
    }
''',
        "replace CGM supervisor")

    ui = replace_section(ui,
        "    private func loKeyCurrentPodLeakFlagged() -> Bool {",
        "    private func loKeySyncLeakNotice()",
        r'''
    private func loKeyCurrentPodLeakFlagged() -> Bool {
        return deviceManager.loKeyLeakSupervisorState().isWatching
    }

    private func loKeyLeakSupervisorDescription() -> String {
        let state = deviceManager.loKeyLeakSupervisorState()
        if state.isPreviousPod, let minutes = state.minutesRemaining {
            return "Previous pod: suspected leak · \(minutes / 60)h \(minutes % 60)m of post-replacement watch remaining. Current pod status appears above. Loop IOB is unchanged."
        }
        return "Current pod: suspected leak · insulin absorption uncertain. The six-hour watch will start when a new pod's activation is confirmed. Loop IOB is unchanged."
    }
''',
        "replace UI leak-state helper")

    ui = replace_once(ui,
        'message: "The reported insulin may not match what was absorbed. The watch stays active across pod changes until you clear it; Loop\'s IOB and recommendations remain unchanged.",',
        'message: "This incident belongs to the originally reported pod. Once a replacement is detected, its glucose supervisor continues for six hours and then ends automatically. Loop\'s IOB and recommendations remain unchanged.",',
        "replace review explanation")
    ui = replace_once(ui,
        '                UserDefaults.standard.removeObject(forKey: "LoKeyLeakFlagPodStartV1")\n                UserDefaults.standard.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")',
        '                UserDefaults.standard.removeObject(forKey: "LoKeyLeakFlagPodStartV1")\n                UserDefaults.standard.removeObject(forKey: "LoKeyLeakReplacedAtV1")\n                UserDefaults.standard.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")\n                UserDefaults.standard.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")',
        "clear replacement keys on manual clear")
    ui = replace_once(ui,
        '            UserDefaults.standard.set(podStart, forKey: "LoKeyLeakFlagPodStartV1")\n            UserDefaults.standard.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")',
        '            UserDefaults.standard.set(podStart, forKey: "LoKeyLeakFlagPodStartV1")\n            UserDefaults.standard.removeObject(forKey: "LoKeyLeakReplacedAtV1")\n            UserDefaults.standard.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")\n            UserDefaults.standard.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")',
        "reset replacement state on new incident")
    ui = replace_once(ui,
        'message: "Starts a CGM high/rising watch even if you later replace the pod. It will NOT adjust Loop IOB or give replacement insulin. Follow your pump-failure plan if delivery may have failed.",',
        'message: "Tracks this pod using its activation time. After replacement, a six-hour CGM watch looks for four successive increases greater than 7 mg/dL. It will NOT change Loop IOB or administer insulin. Follow your pump-failure plan if delivery may have failed.",',
        "new report explanation")
    ui = replace_once(ui,
        '                warning.text = "Suspected pod leak · delivered insulin uncertain. Loop IOB is unchanged."',
        '                warning.text = leakStatus',
        "label previous versus current pod")
    ui = replace_once(ui,
        '                    age: String, expires: String, remaining: String, leakFlagged: Bool) {',
        '                    age: String, expires: String, remaining: String, leakFlagged: Bool, leakStatus: String) {',
        "pod card leak status parameter")
    ui = replace_once(ui,
        '                            leakFlagged: loKeyCurrentPodLeakFlagged())',
        '                            leakFlagged: loKeyCurrentPodLeakFlagged(),\n                            leakStatus: loKeyLeakSupervisorDescription())',
        "pod card leak text caller")
    ui = replace_once(ui,
        '''        if loKeyCurrentPodLeakFlagged() {
            loKeyStatusText?.text = "● Loop · LEAK WATCH"
            loKeyStatusText?.textColor = .systemOrange
        }''',
        '''        let leakWatch = deviceManager.loKeyLeakSupervisorState()
        if leakWatch.isWatching {
            if leakWatch.isPreviousPod, let minutes = leakWatch.minutesRemaining {
                loKeyStatusText?.text = "● Loop · WATCH \\(minutes / 60)h"
            } else {
                loKeyStatusText?.text = "● Loop · LEAK WATCH"
            }
            loKeyStatusText?.textColor = .systemOrange
        }''',
        "header post-replacement notice")

    STATUS.write_text(ui)
    DEVICE.write_text(data)
    print("PASS: 6h pod-specific supervisor, four >7 mg/dL rises, native Loop-only dose review.")

if __name__ == "__main__":
    install()
