#!/usr/bin/env python3
"""Build-1 hardening for the read-only LoKey pod-leak supervisor.

Apply AFTER install_lokey_pod_leak_supervisor.py and
install_lokey_loop_status_shortcut.py. No changes to dose prediction, IOB,
insulin commands, or pump control.
"""
from pathlib import Path

UI = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")
DEVICE = Path("Loop/Loop/Managers/DeviceDataManager.swift")
OMNI_HUD = Path("OmnipodKit/OmnipodKit/PumpManagerUI/OmniHUDProvider.swift")

def replace_one(text: str, before: str, after: str, why: str) -> str:
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{why}: expected exactly one anchor; found {count}")
    return text.replace(before, after, 1)

def replace_method(text: str, signature: str, replacement: str) -> str:
    needle = "    " + signature
    if text.count(needle) != 1:
        raise RuntimeError(f"Ambiguous Swift method {signature}")
    start = text.index(needle)
    opening = text.index("{", start)
    depth = 0
    end = None
    for i in range(opening, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"Unclosed Swift method {signature}")
    return text[:start] + replacement.strip("\n") + text[end:]

def install() -> None:
    ui = UI.read_text()
    dev = DEVICE.read_text()
    omni = OMNI_HUD.read_text()

    # The Omnipod manager *already retains* the previous pod's state.
    # Only publish its activation timestamp for read-only identity selection.
    omni = replace_one(omni,
        '        rawValue["podActivatedAt"] = pumpManager.podActivatedAt',
        '''        rawValue["podActivatedAt"] = pumpManager.podActivatedAt
        if let previousActivatedAt = pumpManager.previousPodDetails?.activatedAt {
            rawValue["previousPodActivatedAt"] = previousActivatedAt
        }''',
        "previous pod read-only HUD identity")

    # Keep the six-hour expiry and explicit manual-clear bookkeeping tidy.
    dev = replace_one(dev,
        '''            defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.set(false, forKey: "LoKeyDeliveryLeakActiveV1")''',
        '''            defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")
            defaults.removeObject(forKey: "LoKeyLeakWatchLastSeverityV1")
            defaults.set(false, forKey: "LoKeyDeliveryLeakActiveV1")''',
        "end leak supervisor without leaving prior alert throttle")

    dev = replace_one(dev,
        '''            let sustainedSpike = consecutiveRises >= 4
            // Retain the existing independent very-high glucose safety alert.
            let veryHigh = glucose >= 250
            guard sustainedSpike || veryHigh else { return }''',
        '''            let sustainedSpike = consecutiveRises >= 4
            // Advisory severity levels are NOT insulin doses or dose recommendations.
            // 1: sustained rise, 2: sustained rise and high, 3: very high
            // independent of the sustained-rise criterion.
            let severity = glucose >= 250 ? 3 : (sustainedSpike && glucose >= 180 ? 2 : (sustainedSpike ? 1 : 0))
            guard severity > 0 else { return }''',
        "tier advisory alert severity")

    dev = replace_one(dev,
        '''            if let lastAlert = defaults.object(forKey: "LoKeyLeakWatchLastAlertV1") as? Date,
               now.timeIntervalSince(lastAlert) < 30 * 60 { return }''',
        '''            let priorSeverity = defaults.integer(forKey: "LoKeyLeakWatchLastSeverityV1")
            if let lastAlert = defaults.object(forKey: "LoKeyLeakWatchLastAlertV1") as? Date,
               now.timeIntervalSince(lastAlert) < 30 * 60,
               severity <= priorSeverity { return }''',
        "do not suppress escalation with a routine cooldown")

    dev = replace_one(dev,
        '''            defaults.set(now, forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.set(latest.startDate, forKey: "LoKeyLeakLastAlertSampleV1")
            let phase = updated.isPreviousPod ? "Post-replacement" : "Suspected pod leak"
            let riseText = sustainedSpike ? "4 consecutive increases greater than 7 mg/dL." : "Very high glucose."
            let summary = String(format: "CGM %.0f mg/dL. %@", glucose, riseText)''',
        '''            defaults.set(now, forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.set(severity, forKey: "LoKeyLeakWatchLastSeverityV1")
            defaults.set(latest.startDate, forKey: "LoKeyLeakLastAlertSampleV1")
            let phase = updated.isPreviousPod ? "Previous pod" : "Suspected pod leak"
            let detail = severity == 3
                ? "Very high glucose. Check your pump-failure plan and ketones as appropriate."
                : (severity == 2
                    ? "High glucose with 4 consecutive rises greater than 7 mg/dL."
                    : "Glucose rising: 4 consecutive increases greater than 7 mg/dL.")
            let summary = String(format: "CGM %.0f mg/dL. %@", glucose, detail)''',
        "rising observation vs correction review copy")

    dev = replace_one(dev,
        '''                "fourConsecutiveRises": sustainedSpike,
                "previousPodReplaced": updated.isPreviousPod''',
        '''                "fourConsecutiveRises": sustainedSpike,
                "alertSeverity": severity,
                "previousPodReplaced": updated.isPreviousPod''',
        "log alert severity")

    dev = replace_one(dev,
        '''            notification.title = "LoKey · " + phase + " glucose watch"
            notification.body = summary + " Review Loop and check whether a correction is appropriate under your pump-failure plan. Do not assume how much insulin was absorbed."''',
        '''            notification.title = severity == 3
                ? "LoKey · Very high glucose"
                : (severity == 2 ? "LoKey · High glucose rising" : "LoKey · Glucose rising")
            let instruction = severity == 1
                ? " Keep monitoring and review Loop if needed."
                : " Check your glucose and review whether a correction is appropriate under your pump-failure plan."
            notification.body = phase + ": " + summary + instruction +
                " Earlier pod insulin absorption may be uncertain; no insulin was automatically calculated or delivered."''',
        "do not imply correction for in-range glucose rise")

    # Make the last CGM ingestion explicit. The watch does not guarantee
    # background delivery if iOS or CGM updates are delayed.
    ui = replace_method(ui,
        "private func loKeyLeakSupervisorDescription() -> String {",
        r'''
    private func loKeyLeakSupervisorDescription() -> String {
        let state = deviceManager.loKeyLeakSupervisorState()
        let latest = deviceManager.glucoseStore.latestGlucose
        let freshnessText: String
        if let sample = latest {
            let ageSeconds = Date().timeIntervalSince(sample.startDate)
            let minutes = max(0, Int(ageSeconds / 60))
            if ageSeconds >= 0 && ageSeconds <= 10 * 60 &&
               !deviceManager.isGlucoseValueStale {
                freshnessText = "CGM received \(minutes)m ago; checks on new readings."
            } else {
                freshnessText = "No fresh CGM readings (\(minutes)m old); supervisor alerts may be delayed."
            }
        } else {
            freshnessText = "No recent CGM reading; supervisor cannot currently evaluate rises."
        }
        if state.isPreviousPod, let minutes = state.minutesRemaining {
            return "Previous pod: suspected leak · \(minutes / 60)h \(minutes % 60)m remaining. Current pod is separate. \(freshnessText) Loop IOB remains unchanged."
        }
        return "Current pod: suspected leak. Six-hour watch starts when replacement is confirmed. \(freshnessText) Loop IOB remains unchanged."
    }
''')

    # Complete reporting flow. Always let the user select current or previous
    # pod when both known; never silently attribute a late report to a new pod.
    ui = replace_method(ui,
        "private func loKeyReviewSuspectedPodLeak() {",
        r'''
    private func loKeyReviewSuspectedPodLeak() {
        let defaults = UserDefaults.standard
        let raw = deviceManager.pumpManagerHUDProvider?.hudViewRawState ?? [:]
        let currentPod = raw["podActivatedAt"] as? Date
        let previousPod = raw["previousPodActivatedAt"] as? Date
        let hasPreviousPod = currentPod != nil && previousPod != nil &&
            currentPod! > previousPod!.addingTimeInterval(60)

        func report(_ podStart: Date, replacement: Date?, note: String) {
            self.loKeyStoreLeakEvent(kind: "suspected", podStart: podStart, note: note)
            defaults.set(podStart, forKey: "LoKeyLeakFlagPodStartV1")
            if let replacement {
                defaults.set(replacement, forKey: "LoKeyLeakReplacedAtV1")
            } else {
                defaults.removeObject(forKey: "LoKeyLeakReplacedAtV1")
            }
            defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
            defaults.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")
            defaults.removeObject(forKey: "LoKeyLeakWatchLastSeverityV1")
            self.loKeySyncLeakNotice()
            self.loKeyRefreshHeader()
            self.tableView.reloadData()
        }

        if let flagged = defaults.object(forKey: "LoKeyLeakFlagPodStartV1") as? Date {
            let currentIsFlagged = currentPod.map { abs($0.timeIntervalSince(flagged)) < 60 } ?? false
            let alert = UIAlertController(
                title: "Suspected Pod Leak",
                message: "The incident is tied to the reported pod, not automatically to the new one. Six-hour post-replacement watching ends six hours after replacement activation. IOB and Loop dosing stay unchanged.",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "Keep Watch", style: .cancel))
            if currentIsFlagged && hasPreviousPod,
               let previousPod, let currentPod {
                alert.addAction(UIAlertAction(title: "Actually Previous Pod", style: .default) { [weak self] _ in
                    guard let self else { return }
                    // Preserve the original log; append the explicit correction.
                    self.loKeyStoreLeakEvent(
                        kind: "report-reassigned-to-previous-pod",
                        podStart: previousPod,
                        note: "User reassigned incident from currently active pod."
                    )
                    defaults.set(previousPod, forKey: "LoKeyLeakFlagPodStartV1")
                    defaults.set(currentPod, forKey: "LoKeyLeakReplacedAtV1")
                    defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
                    defaults.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")
                    defaults.removeObject(forKey: "LoKeyLeakWatchLastSeverityV1")
                    self.loKeySyncLeakNotice()
                    self.loKeyRefreshHeader()
                    self.tableView.reloadData()
                })
            }
            alert.addAction(UIAlertAction(title: "Clear Flag", style: .destructive) { [weak self] _ in
                guard let self else { return }
                self.loKeyStoreLeakEvent(kind: "cleared", podStart: flagged)
                defaults.removeObject(forKey: "LoKeyLeakFlagPodStartV1")
                defaults.removeObject(forKey: "LoKeyLeakReplacedAtV1")
                defaults.removeObject(forKey: "LoKeyLeakWatchLastAlertV1")
                defaults.removeObject(forKey: "LoKeyLeakLastAlertSampleV1")
                defaults.removeObject(forKey: "LoKeyLeakWatchLastSeverityV1")
                self.loKeySyncLeakNotice()
                self.loKeyRefreshHeader()
                self.tableView.reloadData()
            })
            present(alert, animated: true)
            return
        }

        guard let currentPod else {
            let alert = UIAlertController(
                title: "Pod Identity Unavailable",
                message: "The current pod identity is unavailable. A leak cannot be reliably attributed right now; check native Omnipod status.",
                preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .cancel))
            present(alert, animated: true)
            return
        }
        let alert = UIAlertController(
            title: "Which Pod Leaked?",
            message: hasPreviousPod
                ? "Choose the pod you actually suspect. Previous Pod starts a six-hour watch from the new pod's real activation time, not from when you report it."
                : "Only the current pod is identifiable. If a removed pod leaked, its identity is unavailable; do not label the new pod by mistake.",
            preferredStyle: .alert)
        alert.addTextField { field in
            field.placeholder = "What did you notice? (optional)"
            field.autocapitalizationType = .sentences
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        if hasPreviousPod, let previousPod {
            alert.addAction(UIAlertAction(title: "Previous Pod", style: .default) { [weak self, weak alert] _ in
                guard let self else { return }
                report(previousPod, replacement: currentPod, note: alert?.textFields?.first?.text ?? "")
            })
        }
        alert.addAction(UIAlertAction(title: "Current Pod", style: .default) { [weak self, weak alert] _ in
            guard let self else { return }
            report(currentPod, replacement: nil, note: alert?.textFields?.first?.text ?? "")
        })
        present(alert, animated: true)
    }
''')

    ui = replace_one(ui,
        '''        var onChangePod: (() -> Void)?
        @objc private func changePodTapped() { onChangePod?() }''',
        '''        var onChangePod: (() -> Void)?
        @objc private func changePodTapped() { onChangePod?() }
        var onLeakHistory: (() -> Void)?
        @objc private func leakHistoryTapped() { onLeakHistory?() }''',
        "pod card history callback")

    ui = replace_one(ui,
        '''            stack.addArrangedSubview(changePodButton)
            stack.layer.cornerRadius = 20''',
        '''            stack.addArrangedSubview(changePodButton)
            let leakHistoryButton = UIButton(type: .system)
            leakHistoryButton.setTitle("Leak History", for: .normal)
            leakHistoryButton.contentHorizontalAlignment = .leading
            leakHistoryButton.accessibilityHint = "Review recorded pod leak incidents and glucose alerts"
            leakHistoryButton.addTarget(self, action: #selector(leakHistoryTapped), for: .touchUpInside)
            leakHistoryButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true
            stack.addArrangedSubview(leakHistoryButton)
            stack.layer.cornerRadius = 20''',
        "history access from Pod Info")

    ui = replace_one(ui,
        '''                cell.onChangePod = { [weak self] in''',
        '''                cell.onLeakHistory = { [weak self] in self?.loKeyShowLeakHistory() }
                cell.onChangePod = { [weak self] in''',
        "history button action")

    ui = replace_one(ui,
        '''    @objc private func loKeyLastSuccessfulLoopTapped(_ sender: UITapGestureRecognizer) {''',
        r'''
    private func loKeyShowLeakHistory() {
        let events = UserDefaults.standard.array(forKey: "LoKeyLeakEventHistoryV1")
            as? [[String: Any]] ?? []
        let sorted = events.sorted {
            ($0["timestamp"] as? Date ?? .distantPast) >
            ($1["timestamp"] as? Date ?? .distantPast)
        }
        let text = sorted.prefix(200).map { entry -> String in
            let recordedAt = entry["timestamp"] as? Date ?? .distantPast
            let stamp = DateFormatter.localizedString(
                from: recordedAt, dateStyle: .medium, timeStyle: .short
            )
            let pod = (entry["podActivatedAt"] as? Date).map {
                DateFormatter.localizedString(from: $0, dateStyle: .short, timeStyle: .short)
            } ?? "Unknown pod"
            let replacement = (entry["replacementPodActivatedAt"] as? Date).map {
                "New pod: " + DateFormatter.localizedString(from: $0, dateStyle: .short, timeStyle: .short)
            } ?? ""
            let eventType = entry["event"] as? String ?? "Event"
            let observation = entry["observation"] as? String ?? ""
            return "\(stamp)\n\(eventType)\nReported pod activated: \(pod)\n\(replacement)\n\(observation)"
        }.joined(separator: "\n\n────────────────\n\n")

        let vc = UIViewController()
        vc.title = "Leak History"
        vc.view.backgroundColor = .systemBackground
        let log = UITextView()
        log.isEditable = false
        log.isSelectable = true
        log.font = UIFont.preferredFont(forTextStyle: .body)
        log.adjustsFontForContentSizeCategory = true
        log.text = sorted.isEmpty
            ? "No suspected pod leaks recorded yet."
            : text
        log.translatesAutoresizingMaskIntoConstraints = false
        vc.view.addSubview(log)
        NSLayoutConstraint.activate([
            log.topAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.topAnchor, constant: 12),
            log.bottomAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -12),
            log.leadingAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.leadingAnchor, constant: 18),
            log.trailingAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.trailingAnchor, constant: -18)
        ])
        vc.navigationItem.rightBarButtonItem = UIBarButtonItem(
            barButtonSystemItem: .done,
            target: self,
            action: #selector(loKeyDismissLeakHistory)
        )
        present(UINavigationController(rootViewController: vc), animated: true)
    }

    @objc private func loKeyDismissLeakHistory() {
        dismiss(animated: true)
    }

    @objc private func loKeyLastSuccessfulLoopTapped(_ sender: UITapGestureRecognizer) {''',
        "review all recorded leak events from pod info")

    # The same one-minute UI refresh that updates the last Loop also makes
    # the Pod Info supervisor's CGM freshness and remaining time current.
    ui = replace_one(ui,
        '''            .sink { [weak self] _ in self?.loKeyRefreshHeader() }''',
        '''            .sink { [weak self] _ in
                guard let self else { return }
                self.loKeyRefreshHeader()
                if self.loKeyPage == .pod {
                    self.tableView.reloadData()
                }
            }''',
        "keep visible pod monitoring freshness current")

    UI.write_text(ui)
    DEVICE.write_text(dev)
    OMNI_HUD.write_text(omni)
    print("PASS: previous-pod attribution, escalation, read-only history, fresh CGM indicator.")

if __name__ == "__main__":
    install()
