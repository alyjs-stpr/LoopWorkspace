#!/usr/bin/env python3
"""LoKey presentation-only follow-up: quiet Dashboard and unread pod indicator.

Apply AFTER install_lokey_compact_status_ui.py. Retains native Loop/device HUD
callbacks, pump/sensor safety notifications, insulin math and therapy settings.
Makes no changes to insulin delivery or device communications.
"""
from pathlib import Path

STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")


def once(src: str, old: str, new: str, label: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor; found {count}")
    return src.replace(old, new, 1)


def replace_section(src: str, start: str, end: str, new: str, label: str) -> str:
    if src.count(start) != 1 or src.count(end) != 1:
        raise RuntimeError(f"{label}: section markers missing or ambiguous")
    a = src.index(start)
    b = src.index(end, a)
    if a >= b:
        raise RuntimeError(f"{label}: invalid marker order")
    return src[:a] + new + src[b:]


def transform(src: str) -> str:
    if "loKeyPodUnreadDot" in src:
        raise RuntimeError("Quiet Dashboard update already applied")
    if "loKeyInstallDeviceAlertBar" not in src:
        raise RuntimeError("Requires prior compact-status installer")

    src = once(src,
        "    private weak var loKeyCGMAlertButton: UIButton?",
        "    private weak var loKeyPodUnreadDot: UIView?",
        "swap retired sensor notice for unread pod dot")

    # Only an overdue Loop deserves a status notice on the Dashboard/Insulin
    # pages. Pod details are actionable on Pod Info. Dexcom owns lifecycle
    # alerts, while Loop retains stale CGM checks and its own notifications.
    notices = r'''    // Compact, tappable Loop notice on every page, Pod issue only on Pod Info.
    // Native pump, CGM and Loop HUD instances remain alive and update normally.
    private func loKeyInstallDeviceAlertBar(in header: UIView, below tabs: UISegmentedControl) {
        func item(_ text: String, selector: Selector) -> UIButton {
            let button = UIButton(type: .system)
            button.setTitle(text, for: .normal)
            button.titleLabel?.font = .systemFont(ofSize: 13, weight: .semibold)
            button.titleLabel?.adjustsFontSizeToFitWidth = true
            button.titleLabel?.minimumScaleFactor = 0.72
            button.setTitleColor(.systemOrange, for: .normal)
            button.backgroundColor = .tertiarySystemGroupedBackground
            button.layer.cornerRadius = 12
            button.addTarget(self, action: selector, for: .touchUpInside)
            return button
        }
        let pump = item("⚠ Pod / Pump", selector: #selector(loKeyOpenPumpNotice(_:)))
        let loop = item("⚠ Loop overdue", selector: #selector(loKeyOpenLoopNotice(_:)))
        pump.accessibilityHint = "View full pod and pump status"
        loop.accessibilityHint = "View the last successful Loop and error details"
        let bar = UIStackView(arrangedSubviews: [pump, loop])
        bar.axis = .horizontal
        bar.distribution = .fillEqually
        bar.spacing = 8
        bar.translatesAutoresizingMaskIntoConstraints = false
        bar.isHidden = true
        header.addSubview(bar)
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 8),
            bar.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 14),
            bar.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -14),
            bar.heightAnchor.constraint(equalToConstant: 40)
        ])
        loKeyDeviceAlertBar = bar
        loKeyPumpAlertButton = pump
        loKeyLoopAlertButton = loop

        let dot = UIView()
        dot.isUserInteractionEnabled = false
        dot.translatesAutoresizingMaskIntoConstraints = false
        dot.backgroundColor = .systemOrange
        dot.layer.cornerRadius = 5
        dot.isHidden = true
        tabs.addSubview(dot)
        NSLayoutConstraint.activate([
            dot.widthAnchor.constraint(equalToConstant: 10),
            dot.heightAnchor.constraint(equalToConstant: 10),
            dot.trailingAnchor.constraint(equalTo: tabs.trailingAnchor, constant: -10),
            dot.topAnchor.constraint(equalTo: tabs.topAnchor, constant: 4)
        ])
        loKeyPodUnreadDot = dot
    }

    private func loKeyRefreshDeviceAlertBar() {
        let pumpLifecycle = deviceManager.pumpLifecycleProgress?.progressState
        let pumpAttention = deviceManager.pumpStatusHighlight != nil ||
            deviceManager.pumpStatusBadge != nil ||
            pumpLifecycle == .warning || pumpLifecycle == .critical

        // Fingerprint the observed issue by pod activation and severity.
        // Acknowledging a warning does not clear the issue itself. Escalating
        // to critical or changing pods produces a fresh unread dot.
        let rawPod = deviceManager.pumpManagerHUDProvider?.hudViewRawState ?? [:]
        let podIdentity = (rawPod["podActivatedAt"] as? Date).map {
            String(Int($0.timeIntervalSince1970))
        } ?? "unknown"
        let severity = pumpLifecycle == .critical ? "critical" :
            (pumpLifecycle == .warning ? "warning" : "normal")
        let issueKey = podIdentity + "|" + severity + "|" +
            (deviceManager.pumpStatusHighlight == nil ? "0" : "1") +
            (deviceManager.pumpStatusBadge == nil ? "0" : "1")
        let seenKeyName = "LoKeyLastSeenPodIssueV1"
        if pumpAttention && loKeyPage == .pod {
            UserDefaults.standard.set(issueKey, forKey: seenKeyName)
        }
        let unread = pumpAttention &&
            UserDefaults.standard.string(forKey: seenKeyName) != issueKey &&
            loKeyPage != .pod
        loKeyPodUnreadDot?.isHidden = !unread
        loKeyTabsControl?.accessibilityValue = unread
            ? "New pod warning. Open Pod Info to review." : nil

        // No standalone sensor expiry or low-pod notice elsewhere.
        // A stale sensor can contribute to a delayed Loop; never claim it
        // definitively caused that delay without Loop's own error details.
        let loopOverdue = deviceManager.loopManager.lastLoopCompleted.map {
            Date().timeIntervalSince($0) > 600
        } ?? true
        loKeyLoopAlertButton?.setTitle(
            loopOverdue && deviceManager.isGlucoseValueStale
                ? "⚠ Loop overdue · Check CGM" : "⚠ Loop overdue",
            for: .normal)
        loKeyLoopAlertButton?.isHidden = !loopOverdue
        loKeyPumpAlertButton?.isHidden = !(pumpAttention && loKeyPage == .pod)
        loKeyDeviceAlertBar?.isHidden = !(loopOverdue || (pumpAttention && loKeyPage == .pod))
        updateParkDashboardHeader()
    }

    @objc private func loKeyOpenPumpNotice(_ sender: UIButton) {
        let providedHUD = hudView?.pumpStatusHUD.pumpManagerProvidedHUD
        executeHUDTapAction(deviceManager.didTapOnPumpStatus(providedHUD), from: sender)
    }

'''
    src = replace_section(src,
        "    // Compact, actionable status notices replace the legacy 3-tile strip.",
        "    @objc private func loKeyOpenLoopNotice(_ sender: UIButton) {",
        notices,
        "replace lifecycle/low-pod banners with Pod-tab-only warning plus unread badge")

    # No separate orange card: place a small step/rate below IOB in the
    # existing upper-right corner of LoKey's lavender glucose card.
    src = once(src,
        "        private let insulin = UILabel()",
        """        private let insulin = UILabel()
        private let basalChangeText = UILabel()
        private let basalChangeStep = LoKeyBasalChangeStepView()
        var loKeyBasalChange = "Unavailable"
        var loKeyBasalDirection = 0.0""",
        "glucose card owns inline basal view")
    src = once(src,
        "            let row = UIStackView(arrangedSubviews: [heading, insulin])",
        """            // Preserve green IOB. Keep orange net basal change beneath it
            // without another full-width card or any pod reservoir graphic.
            basalChangeText.textColor = .systemOrange
            basalChangeText.font = .monospacedDigitSystemFont(ofSize: 11, weight: .semibold)
            basalChangeText.adjustsFontSizeToFitWidth = true
            basalChangeText.minimumScaleFactor = 0.72
            basalChangeStep.backgroundColor = .clear
            basalChangeStep.translatesAutoresizingMaskIntoConstraints = false
            basalChangeStep.widthAnchor.constraint(equalToConstant: 36).isActive = true
            basalChangeStep.heightAnchor.constraint(equalToConstant: 14).isActive = true
            let basalCompact = UIStackView(arrangedSubviews: [basalChangeStep, basalChangeText])
            basalCompact.axis = .horizontal
            basalCompact.alignment = .center
            basalCompact.spacing = 3
            basalCompact.isAccessibilityElement = true
            basalCompact.accessibilityLabel = "Basal change relative to scheduled rate"
            let rightMetrics = UIStackView(arrangedSubviews: [insulin, basalCompact])
            rightMetrics.axis = .vertical
            rightMetrics.alignment = .trailing
            rightMetrics.spacing = 3
            let row = UIStackView(arrangedSubviews: [heading, rightMetrics])""",
        "compact basal under IOB")
    src = once(src,
        '            insulin.text = "IOB " + iob',
        '''            insulin.text = "IOB " + iob
            let unavailable = loKeyBasalChange == "Unavailable"
            basalChangeText.text = unavailable ? "" : loKeyBasalChange
            basalChangeStep.direction = loKeyBasalDirection
            basalChangeStep.isHidden = unavailable
            basalChangeText.isHidden = unavailable''',
        "display basal value on each glucose refresh")
    src = once(src,
        "        loKeyGlucoseHeaderCard?.update(glucose: glucose, detail: detail, iob: lokeySnapshot.iob, trend: trend)",
        """        loKeyGlucoseHeaderCard?.loKeyBasalChange = loKeyBasalChange
        loKeyGlucoseHeaderCard?.loKeyBasalDirection = loKeyBasalDirection
        loKeyGlucoseHeaderCard?.update(glucose: glucose, detail: detail, iob: lokeySnapshot.iob, trend: trend)""",
        "refresh inline basal from existing snapshot")

    # Scale down the preserved genuine net-basal step shape for the glucose
    # card, while retaining Loop's own already-calculated rate.
    src = once(src,
        "            let vertical = max(8, min(15, rect.height / 3))",
        "            let vertical = max(3, min(5, rect.height / 3))",
        "step graphic small vertical scale")
    src = src.replace("rect.minX + 19", "rect.minX + rect.width * 0.26")
    src = src.replace("rect.maxX - 19", "rect.maxX - rect.width * 0.26")
    src = once(src, "            path.lineWidth = 3", "            path.lineWidth = 2", "step graphic line weight")

    a = "            // Isolated net basal adjustment card; no pod reservoir HUD."
    b = "            let stack = UIStackView(arrangedSubviews: [values, basalCard, targetStack])"
    if src.count(a) != 1 or src.count(b) != 1:
        raise RuntimeError("Basal tile section missing; refusing to change layout")
    begin = src.index(a)
    end = src.index(b, begin)
    src = src[:begin] + src[end:]
    src = once(src, b, "            let stack = UIStackView(arrangedSubviews: [values, targetStack])",
        "remove full-width basal card")
    return src


def install() -> None:
    original = STATUS.read_text(encoding="utf-8")
    revised = transform(original)
    if revised == original:
        raise RuntimeError("No UI changes applied")
    STATUS.write_text(revised, encoding="utf-8")
    print("PASS: new pod issue dot, Pod-tab warning, Loop-only Dashboard notices")
    print("PASS: basal change compactly embedded below IOB in glucose card")
    print("PASS: original pump/CGM notifications and dosing algorithms unchanged")


if __name__ == "__main__":
    install()
