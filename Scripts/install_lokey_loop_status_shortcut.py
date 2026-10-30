#!/usr/bin/env python3
"""Add a tappable, native-freshness LoKey last-successful-Loop indicator.

Run after all previously approved UI and pod leak supervisor customizations.
Only touches display and navigation to existing native Loop status messaging.
"""
from pathlib import Path

TARGET = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")

def replace_once(source: str, old: str, new: str, label: str) -> str:
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {found}")
    return source.replace(old, new, 1)

def install() -> None:
    source = TARGET.read_text()
    source = replace_once(
        source,
        '''        loop.adjustsFontForContentSizeCategory = true
        loKeyStatusText = loop''',
        '''        loop.adjustsFontForContentSizeCategory = true
        loop.numberOfLines = 2
        loop.isUserInteractionEnabled = true
        loop.accessibilityTraits.insert(.button)
        loop.accessibilityHint = "Shows the exact time of the last successful Loop and native Loop status"
        loop.addGestureRecognizer(UITapGestureRecognizer(
            target: self, action: #selector(loKeyLastSuccessfulLoopTapped(_:))
        ))
        loKeyStatusText = loop''',
        "tappable Loop header")

    source = replace_once(
        source,
        '''        tableView.tableHeaderView = header
        loKeyRefreshHeader()''',
        '''        tableView.tableHeaderView = header
        loKeyRefreshHeader()
        // Mirror the native Loop HUD's minute-by-minute age changes even
        // between CGM updates, without creating a retained Timer cycle.
        Timer.publish(every: 60, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in self?.loKeyRefreshHeader() }
            .store(in: &cancellables)''',
        "freshness refresh timer")

    source = replace_once(
        source,
        '''    private func loKeyRefreshHeader() {
        if let last = deviceManager.loopManager.lastLoopCompleted {
            let age = max(0, Int(Date().timeIntervalSince(last) / 60))
            loKeyStatusText?.text = age <= 10 ? "● Loop running" : "● Loop overdue · \(age)m"
            loKeyStatusText?.textColor = age <= 10 ? .systemGreen : .systemOrange
        } else {
            loKeyStatusText?.text = "● Loop waiting"
            loKeyStatusText?.textColor = .secondaryLabel
        }
        loKeyAgeText?.text = "CGM " + lokeySnapshot.glucoseAge''',
        '''    private func loKeyRefreshHeader() {
        // LoopCompletionFreshness is native Loop's 6m green / 16m yellow /
        // older red policy. Use the same value, rather than the old 10m rule.
        let last = deviceManager.loopManager.lastLoopCompleted
        let freshness = LoopCompletionFreshness(lastCompletion: last)
        let timeAgo = last.map { max(0, Int(Date().timeIntervalSince($0) / 60)) }
        let statusText: String
        let statusColor: UIColor
        switch freshness {
        case .fresh:
            statusText = "● Last Loop · \(timeAgo ?? 0)m ›"
            statusColor = .systemGreen
        case .aging:
            statusText = "● Last Loop · \(timeAgo ?? 0)m ›"
            statusColor = .systemOrange
        case .stale:
            statusText = timeAgo.map { "● Last Loop · \($0)m ›" } ?? "● Last Loop · none ›"
            statusColor = .systemRed
        }
        let composedStatus = NSMutableAttributedString(
            string: statusText,
            attributes: [
                .foregroundColor: statusColor,
                .font: UIFont.preferredFont(forTextStyle: .caption1)
            ]
        )
        loKeyStatusText?.accessibilityLabel = last.map {
            "Last successful Loop at " +
            DateFormatter.localizedString(from: $0, dateStyle: .medium, timeStyle: .short)
        } ?? "No successful Loop yet"
        loKeyAgeText?.text = "CGM " + lokeySnapshot.glucoseAge''',
        "native Loop freshness in header")

    source = replace_once(
        source,
        r'''        let leakWatch = deviceManager.loKeyLeakSupervisorState()
        if leakWatch.isWatching {
            if leakWatch.isPreviousPod, let minutes = leakWatch.minutesRemaining {
                loKeyStatusText?.text = "● Loop · WATCH \(minutes / 60)h"
            } else {
                loKeyStatusText?.text = "● Loop · LEAK WATCH"
            }
            loKeyStatusText?.textColor = .systemOrange
        }''',
        r'''        let leakWatch = deviceManager.loKeyLeakSupervisorState()
        if leakWatch.isWatching {
            // Keep both safety facts: the last completed Loop age retains its
            // own native traffic-light color; the leak banner stays orange.
            let notice = leakWatch.isPreviousPod
                ? "⚠ Previous pod leak watch"
                : "⚠ Suspected pod leak"
            composedStatus.append(NSAttributedString(
                string: "\n" + notice,
                attributes: [
                    .foregroundColor: UIColor.systemOrange,
                    .font: UIFont.preferredFont(forTextStyle: .caption2)
                ]
            ))
        }
        loKeyStatusText?.attributedText = composedStatus''',
        "preserve separate prior-pod leak notice")

    source = replace_once(
        source,
        r'''    @objc private func loKeyChangePage(_ sender: UISegmentedControl) {''',
        r'''    @objc private func loKeyLastSuccessfulLoopTapped(_ sender: UITapGestureRecognizer) {
        let last = deviceManager.loopManager.lastLoopCompleted
        let exactTime = last.map {
            DateFormatter.localizedString(from: $0, dateStyle: .medium, timeStyle: .short)
        } ?? "No successful Loop yet"
        let nativeStatus = hudView?.loopCompletionHUD.loopCompletionMessage
        // The original Loop status message is preserved, including closed
        // loop ON/OFF and communication warnings, plus exact success time.
        let message = "Last successful Loop: " + exactTime +
            "\n\n" + (nativeStatus?.message ?? "Native Loop status details unavailable.")
        presentLoopCompletionMessage(
            title: nativeStatus?.title ?? "Loop Status", message: message
        )
    }

    @objc private func loKeyChangePage(_ sender: UISegmentedControl) {''',
        "native status details shortcut")

    TARGET.write_text(source)
    print("PASS: native 6/16-minute Loop freshness, exact timestamp, clickable status, separate pod leak warning.")

if __name__ == "__main__":
    install()
