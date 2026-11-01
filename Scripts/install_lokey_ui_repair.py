#!/usr/bin/env python3
"""LoKey UI-only repair: preserve glucose dashboard under Park and restore Watch target chooser.

Applied AFTER existing LoKey patches in build/preflight workflows.
Intentionally NEVER touches dosing, pump commands, predictions or insulin storage.
Fail closed if any source anchor has changed.
"""
from pathlib import Path

STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")
WATCH_ACTIONS = Path("Loop/WatchApp Extension/Controllers/ActionHUDController.swift")
WATCH_PICKER = Path("Loop/WatchApp Extension/Controllers/OverrideSelectionController.swift")


def once(src: str, old: str, new: str, label: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, got {count}. Abort build.")
    return src.replace(old, new, 1)


def section(src: str, start: str, end: str, label: str):
    if src.count(start) != 1 or src.count(end) != 1:
        raise RuntimeError(f"{label}: section anchors changed. Abort build.")
    a = src.index(start)
    b = src.index(end, a)
    return a, b


def repair_dashboard(s: str) -> str:
    s = once(s,
        "    private var loKeyParkHeaderSignature: String?",
        """    private var loKeyParkHeaderSignature: String?
    private weak var loKeyPrimaryHeader: UIView?
    private weak var loKeyTabsControl: UISegmentedControl?
    private var loKeyParkBanner: UIButton?
    private var loKeyGlucoseTopConstraint: NSLayoutConstraint?""",
        "park header state")

    a, b = section(s, "    private func loKeyInstallPages() {",
                   "    private func loKeyRefreshHeader() {", "LoKey pages")
    pages = s[a:b]
    pages = once(pages,
        "        let tabs = UISegmentedControl(items: [\"DASHBOARD\", \"INSULIN\", \"POD INFO\"])",
        """        let tabs = UISegmentedControl(items: ["DASHBOARD", "INSULIN", "POD INFO"])
        loKeyTabsControl = tabs""",
        "dashboard tab reference")
    pages = once(pages,
        "        tableView.tableHeaderView = header",
        """        loKeyPrimaryHeader = header
        tableView.tableHeaderView = header""",
        "preserve native primary header")
    pages = once(pages,
        "            glucoseCard.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 16),",
        "            glucoseTopConstraint,",
        "glucose position")
    pages = once(pages,
        "        NSLayoutConstraint.activate([\n            glucoseTopConstraint,",
        """        let glucoseTopConstraint = glucoseCard.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 16)
        loKeyGlucoseTopConstraint = glucoseTopConstraint
        NSLayoutConstraint.activate([
            glucoseTopConstraint,""",
        "glucose constraint storage")
    s = s[:a] + pages + s[b:]

    a, b = section(s, "    @objc private func loKeyChangePage(_ sender: UISegmentedControl) {",
                   "    private func loKeyChartRow(at row: Int) -> ChartRow {", "page switching")
    switching = s[a:b]
    switching = once(switching, "        tableView.reloadData()",
                     "        updateParkDashboardHeader()\n        tableView.reloadData()",
                     "dashboard tab switching refresh")
    s = s[:a] + switching + s[b:]

    a, b = section(s, "    private func updateParkDashboardHeader() {",
                   "    @objc private func loKeyAnnounceParkMeal() {", "park banner render")
    render = r"""    private func updateParkDashboardHeader() {
        // Keep the brand, tabs and large purple glucose card in the PRIMARY
        // dashboard header. The previous implementation replaced the entire
        // tableHeaderView with the park banner, hiding critical CGM information.
        guard let header = loKeyPrimaryHeader,
              let tabs = loKeyTabsControl else { return }

        let active = activeParkOverride
        let paused = pausedParkSession
        let isParkVisible = (active != nil || paused != nil) && loKeyPage == .dashboard
        let expiry = active?.scheduledEndDate ?? paused?.end
        let range = active?.settings.targetRange
        let low = range?.lowerBound.doubleValue(for: .milligramsPerDeciliter) ?? paused?.low ?? 0
        let high = range?.upperBound.doubleValue(for: .milligramsPerDeciliter) ?? paused?.high ?? 0
        let stamp = expiry?.timeIntervalSince1970 ?? 0
        let signature = "\(loKeyPage.rawValue):\(stamp):\(low):\(high):\(active == nil):\(isParkVisible)"
        guard loKeyParkHeaderSignature != signature || tableView.tableHeaderView !== header else { return }
        loKeyParkHeaderSignature = signature

        if isParkVisible {
            let banner: UIButton
            if let existing = loKeyParkBanner {
                banner = existing
            } else {
                banner = UIButton(type: .system)
                banner.translatesAutoresizingMaskIntoConstraints = false
                banner.layer.cornerRadius = 16
                banner.clipsToBounds = true
                banner.titleLabel?.font = .systemFont(ofSize: 16, weight: .bold)
                banner.titleLabel?.numberOfLines = 3
                banner.titleLabel?.lineBreakMode = .byWordWrapping
                banner.contentHorizontalAlignment = .leading
                banner.contentEdgeInsets = UIEdgeInsets(top: 10, left: 14, bottom: 10, right: 12)
                banner.addTarget(self, action: #selector(presentParkMode), for: .touchUpInside)
                header.addSubview(banner)
                NSLayoutConstraint.activate([
                    banner.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 8),
                    banner.leadingAnchor.constraint(equalTo: header.leadingAnchor, constant: 12),
                    banner.trailingAnchor.constraint(equalTo: header.trailingAnchor, constant: -12),
                    banner.heightAnchor.constraint(equalToConstant: 92)
                ])
                loKeyParkBanner = banner
            }
            banner.isHidden = false
            banner.backgroundColor = active == nil
                ? UIColor(red: 0.49, green: 0.42, blue: 0.57, alpha: 1)
                : UIColor(red: 0.37, green: 0.15, blue: 0.62, alpha: 1)
            let endText: String
            if let expiry {
                // On a fall DST transition 1:40 AM occurs twice. Show EDT/EST
                // to distinguish actual instants; never shift stored Dates.
                let clock = DateFormatter.localizedString(from: expiry, dateStyle: .none, timeStyle: .short)
                let zone = TimeZone.current.abbreviation(for: expiry) ?? ""
                endText = "\(clock) \(zone)"
            } else {
                endText = "Unknown"
            }
            let state = active == nil ? "PAUSED" : "ACTIVE"
            banner.setTitle("🎢 THEME PARK \(state)\n\(Int(low.rounded()))–\(Int(high.rounded())) mg/dL · Until \(endText)\nTap to adjust, pause or end",
                            for: .normal)
            banner.setTitleColor(.white, for: .normal)
            banner.accessibilityLabel = "Theme Park \(state), target \(Int(low.rounded())) to \(Int(high.rounded())) milligrams per deciliter, until \(endText)"
        } else {
            loKeyParkBanner?.isHidden = true
        }

        loKeyGlucoseTopConstraint?.constant = isParkVisible ? 120 : 16
        let baseHeight: CGFloat = loKeyPage == .dashboard ? 310 : 118
        header.frame.size.height = baseHeight + (isParkVisible ? 104 : 0)
        tableView.tableHeaderView = header
    }

"""
    s = s[:a] + render + s[b:]
    if "tableView.tableHeaderView = header" not in render:
        raise RuntimeError("Missing header retention")
    return s


def repair_watch_actions(s: str) -> str:
    s = once(s,
        'overrideButtonLabel?.setText(NSLocalizedString("Preset", comment: "The text for the Watch button for enabling a custom preset"))',
        'overrideButtonLabel?.setText(NSLocalizedString("Workout / Targets", comment: "Watch shortcut for selecting Workout and other temporary targets"))',
        "watch action label")
    s = once(s,
        """            overrideButtonGroup.state == .on
                ? sendOverride(nil)
                : presentController(withName: OverrideSelectionController.className, context: self as OverrideSelectionControllerDelegate)""",
        """            // Opening the chooser while a park target is active must not
            // silently end it or prevent choosing Workout.
            presentController(withName: OverrideSelectionController.className, context: self as OverrideSelectionControllerDelegate)""",
        "active watch chooser")
    s = once(s,
        """    func overrideSelectionController(_ controller: OverrideSelectionController, didSelectPreset preset: TemporaryScheduleOverridePreset) {
        let override = preset.createOverride(enactTrigger: .local)
        sendOverride(override)
    }""",
        """    func overrideSelectionController(_ controller: OverrideSelectionController, didSelectPreset preset: TemporaryScheduleOverridePreset) {
        let override = preset.createOverride(enactTrigger: .local)
        sendOverride(override)
    }

    func overrideSelectionControllerDidEndCurrentOverride(_ controller: OverrideSelectionController) {
        sendOverride(nil)
    }

    func overrideSelectionControllerDidSelectLegacyWorkout(_ controller: OverrideSelectionController) {
        guard loopManager.settings.legacyWorkoutTargetRange != nil else { return }
        sendOverride(loopManager.settings.legacyWorkoutOverride(for: .infinity))
    }""",
        "watch delegate end and legacy workout")
    return s


def repair_watch_picker(s: str) -> str:
    s = once(s,
        """    func overrideSelectionController(_ controller: OverrideSelectionController, didSelectPreset preset: TemporaryScheduleOverridePreset)
}""",
        """    func overrideSelectionController(_ controller: OverrideSelectionController, didSelectPreset preset: TemporaryScheduleOverridePreset)
    func overrideSelectionControllerDidEndCurrentOverride(_ controller: OverrideSelectionController)
    func overrideSelectionControllerDidSelectLegacyWorkout(_ controller: OverrideSelectionController)
}""",
        "watch picker delegate")
    s = once(s,
        "    private lazy var presets = loopManager.settings.overridePresets",
        """    private lazy var presets = loopManager.settings.overridePresets
    private var showsEndAction: Bool {
        loopManager.settings.scheduleOverride?.isActive() == true
    }
    private var showsLegacyWorkout: Bool {
        loopManager.settings.legacyWorkoutTargetRange != nil &&
            !presets.contains { $0.name.localizedCaseInsensitiveContains("workout") }
    }""",
        "workout picker sources")
    s = once(s,
        """        guard !presets.isEmpty else {
            assertionFailure("Instantiating override selection controller without configured presets")
            return
        }""",
        """        guard !presets.isEmpty || showsEndAction || showsLegacyWorkout else {
            assertionFailure("Instantiating override selection controller without available targets")
            return
        }""",
        "watch empty list check")
    a, b = section(s, "    private func configureTable() {",
                   "    override func willActivate() {", "watch picker table")
    table = """    private func configureTable() {
        table.setRowTypes([OverridePresetRow.className])
        let offset = (showsEndAction ? 1 : 0) + (showsLegacyWorkout ? 1 : 0)
        table.setNumberOfRows(presets.count + offset, withRowType: OverridePresetRow.className)
        var index = 0
        if showsEndAction {
            let row = table.rowController(at: index) as! OverridePresetRow
            row.symbolLabel.setText("×")
            row.nameLabel.setText("End Current Targets")
            index += 1
        }
        if showsLegacyWorkout {
            let row = table.rowController(at: index) as! OverridePresetRow
            row.symbolLabel.setText("🏃")
            row.nameLabel.setText("Workout")
            index += 1
        }
        for preset in presets {
            let row = table.rowController(at: index) as! OverridePresetRow
            row.symbolLabel.setText(preset.symbol)
            row.nameLabel.setText(preset.name)
            index += 1
        }
    }

"""
    s = s[:a] + table + s[b:]
    s = once(s,
        """        let preset = presets[rowIndex]
        delegate?.overrideSelectionController(self, didSelectPreset: preset)
        dismiss()""",
        """        var index = rowIndex
        if showsEndAction {
            if index == 0 {
                delegate?.overrideSelectionControllerDidEndCurrentOverride(self)
                dismiss()
                return
            }
            index -= 1
        }
        if showsLegacyWorkout {
            if index == 0 {
                delegate?.overrideSelectionControllerDidSelectLegacyWorkout(self)
                dismiss()
                return
            }
            index -= 1
        }
        guard presets.indices.contains(index) else { return }
        delegate?.overrideSelectionController(self, didSelectPreset: presets[index])
        dismiss()""",
        "watch picker selection")
    return s


def main():
    files = {
        STATUS: repair_dashboard,
        WATCH_ACTIONS: repair_watch_actions,
        WATCH_PICKER: repair_watch_picker,
    }
    # All or nothing: validate every anchor before touching any source file.
    updated = {path: operation(path.read_text()) for path, operation in files.items()}
    for path, result in updated.items():
        path.write_text(result)
        print(f"LoKey display/Watch repair applied: {path}")
    print("No dosing algorithm, insulin storage or pump command file modified.")


if __name__ == "__main__":
    main()
