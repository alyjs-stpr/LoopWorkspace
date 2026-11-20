#!/usr/bin/env python3
"""Display-only LoKey polish: compact device notices and a basal-change card.

Applies after existing LoKey patches and appearance installers. Native CGM,
pump, and Loop HUD instances remain installed and receive status updates.
No pump commands, dose calculations, or glucose/insulin history are changed.
Fail closed if expected source anchors move.
"""
from pathlib import Path

STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")


def once(source: str, old: str, new: str, name: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{name}: expected one source anchor, found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    if "loKeyInstallDeviceAlertBar" in source:
        raise RuntimeError("Compact alert bar is already installed")

    source = once(source,
        "    private var loKeyParkHeaderSignature: String?",
        """    private var loKeyParkHeaderSignature: String?
    private weak var loKeyDeviceAlertBar: UIStackView?
    private weak var loKeyCGMAlertButton: UIButton?
    private weak var loKeyPumpAlertButton: UIButton?
    private weak var loKeyLoopAlertButton: UIButton?
    private var loKeyParkBannerTopConstraint: NSLayoutConstraint?
    private var loKeyBasalChange = "Unavailable"
    private var loKeyBasalDirection = 0.0""",
        "read-only UI state")

    notices = r'''    // Compact, actionable status notices replace the legacy 3-tile strip.
    // Keep the underlying native HUD alive for Loop's status and warning logic.
    private func loKeyInstallDeviceAlertBar(in header: UIView, below tabs: UISegmentedControl) {
        func button(_ title: String, selector: Selector) -> UIButton {
            let item = UIButton(type: .system)
            item.setTitle(title, for: .normal)
            item.titleLabel?.font = .systemFont(ofSize: 13, weight: .semibold)
            item.titleLabel?.adjustsFontSizeToFitWidth = true
            item.titleLabel?.minimumScaleFactor = 0.75
            item.setTitleColor(.systemOrange, for: .normal)
            item.backgroundColor = .tertiarySystemGroupedBackground
            item.layer.cornerRadius = 12
            item.addTarget(self, action: selector, for: .touchUpInside)
            return item
        }
        let cgm = button("⚠ Sensor", selector: #selector(loKeyOpenSensorNotice(_:)))
        let pump = button("⚠ Pod / Pump", selector: #selector(loKeyOpenPumpNotice(_:)))
        let loop = button("⚠ Loop", selector: #selector(loKeyOpenLoopNotice(_:)))
        cgm.accessibilityHint = "Open the sensor's full status and warnings"
        pump.accessibilityHint = "Open the pump's full status and warnings"
        loop.accessibilityHint = "Open Loop's completion and error details"
        let bar = UIStackView(arrangedSubviews: [cgm, pump, loop])
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
        loKeyCGMAlertButton = cgm
        loKeyPumpAlertButton = pump
        loKeyLoopAlertButton = loop
    }

    private func loKeyRefreshDeviceAlertBar() {
        let sensorAttention = deviceManager.isGlucoseValueStale ||
            deviceManager.cgmStatusHighlight != nil || deviceManager.cgmStatusBadge != nil
        let pumpAttention = deviceManager.pumpStatusHighlight != nil ||
            deviceManager.pumpStatusBadge != nil
        let loopAttention = deviceManager.loopManager.lastLoopCompleted.map {
            Date().timeIntervalSince($0) > 600
        } ?? true
        loKeyCGMAlertButton?.isHidden = !sensorAttention
        loKeyCGMAlertButton?.setTitle(
            deviceManager.isGlucoseValueStale ? "⚠ CGM stale" : "⚠ Sensor",
            for: .normal)
        loKeyPumpAlertButton?.isHidden = !pumpAttention
        loKeyLoopAlertButton?.isHidden = !loopAttention
        loKeyDeviceAlertBar?.isHidden = !(sensorAttention || pumpAttention || loopAttention)
        // This also keeps Theme Park's banner and the glucose card below notices.
        updateParkDashboardHeader()
    }

    @objc private func loKeyOpenSensorNotice(_ sender: UIButton) {
        executeHUDTapAction(deviceManager.didTapOnCGMStatus(), from: sender)
    }

    @objc private func loKeyOpenPumpNotice(_ sender: UIButton) {
        let pumpHUD = hudView?.pumpStatusHUD.pumpManagerProvidedHUD
        executeHUDTapAction(deviceManager.didTapOnPumpStatus(pumpHUD), from: sender)
    }

    @objc private func loKeyOpenLoopNotice(_ sender: UIButton) {
        if hudView?.loopCompletionHUD.loopCompletionMessage != nil {
            showLoopCompletionMessage(sender)
        } else {
            showLastError(sender)
        }
    }

'''
    source = once(source,
        "    private func loKeyRefreshHeader() {",
        notices + "    private func loKeyRefreshHeader() {\n        defer { loKeyRefreshDeviceAlertBar() }",
        "status refresh hook and compact warning actions")
    source = once(source,
        "        loKeyPrimaryHeader = header\n        tableView.tableHeaderView = header",
        "        loKeyInstallDeviceAlertBar(in: header, below: tabs)\n"
        "        loKeyPrimaryHeader = header\n        tableView.tableHeaderView = header",
        "header notice installation")

    # The native HUD's content remains instantiated, updating and tappable
    # through the compact notices. It must never reclaim screen space.
    source = once(source,
        "if Section(rawValue: indexPath.section) == .hud && !loKeyNeedsNativeStatusHUD {",
        "if Section(rawValue: indexPath.section) == .hud {",
        "native status row layout")
    source = once(source,
        "hudView?.isHidden = !loKeyNeedsNativeStatusHUD",
        "hudView?.isHidden = true",
        "native status view visibility")

    source = once(source,
        "        let isParkVisible = (active != nil || paused != nil) && loKeyPage == .dashboard",
        """        let isParkVisible = (active != nil || paused != nil) && loKeyPage == .dashboard
        let loKeyNoticeHeight: CGFloat = loKeyDeviceAlertBar?.isHidden == false ? 48 : 0""",
        "reserve device notices below tabs")
    source = once(source,
        r'let signature = "\(loKeyPage.rawValue):\(stamp):\(low):\(high):\(active == nil):\(isParkVisible)"',
        r'let signature = "\(loKeyPage.rawValue):\(stamp):\(low):\(high):\(active == nil):\(isParkVisible):\(loKeyNoticeHeight)"',
        "notice layout refresh signature")
    source = once(source,
        "                NSLayoutConstraint.activate([\n                    banner.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 8),",
        """                let bannerTop = banner.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 8)
                loKeyParkBannerTopConstraint = bannerTop
                NSLayoutConstraint.activate([
                    bannerTop,""",
        "Theme Park banner position")
    source = once(source,
        "        loKeyGlucoseTopConstraint?.constant = isParkVisible ? 120 : 16",
        """        loKeyParkBannerTopConstraint?.constant = 8 + loKeyNoticeHeight
        loKeyGlucoseTopConstraint?.constant = 16 + loKeyNoticeHeight + (isParkVisible ? 104 : 0)""",
        "glucose card below compact alerts")
    source = once(source,
        "        header.frame.size.height = baseHeight + (isParkVisible ? 104 : 0)",
        "        header.frame.size.height = baseHeight + loKeyNoticeHeight + (isParkVisible ? 104 : 0)",
        "header fits notice and park banners")

    shape = r'''    // Orange step shape uses the already computed net basal change; it
    // is NOT the currently delivered absolute basal rate.
    private final class LoKeyBasalChangeStepView: UIView {
        var direction = 0.0 { didSet { setNeedsDisplay() } }
        override func draw(_ rect: CGRect) {
            let center = rect.midY
            let vertical = max(8, min(15, rect.height / 3))
            let offset: CGFloat = direction > 0 ? -vertical :
                                  (direction < 0 ? vertical : 0)
            let path = UIBezierPath()
            path.move(to: CGPoint(x: rect.minX + 3, y: center))
            path.addLine(to: CGPoint(x: rect.minX + 19, y: center))
            path.addLine(to: CGPoint(x: rect.minX + 19, y: center + offset))
            path.addLine(to: CGPoint(x: rect.maxX - 19, y: center + offset))
            path.addLine(to: CGPoint(x: rect.maxX - 19, y: center))
            path.addLine(to: CGPoint(x: rect.maxX - 3, y: center))
            path.lineWidth = 3
            path.lineJoinStyle = .round
            UIColor.systemOrange.setStroke()
            path.stroke()
        }
    }

'''
    source = once(source,
        "    private final class LoKeyQuickStatsCell: UITableViewCell {",
        shape + "    private final class LoKeyQuickStatsCell: UITableViewCell {",
        "basal step graphic declaration")
    source = once(source,
        '        var onTarget: ((Int) -> Void)?\n',
        '''        var onTarget: ((Int) -> Void)?
        var loKeyBasalChange = "Unavailable"
        var loKeyBasalDirection = 0.0
''',
        "basal visual state on dashboard cell")
    basal_card = r'''            // Isolated net basal adjustment card; no pod reservoir HUD.
            let basalTitle = UILabel()
            basalTitle.text = "BASAL CHANGE"
            basalTitle.textColor = .secondaryLabel
            basalTitle.font = .preferredFont(forTextStyle: .caption1)
            let graphic = LoKeyBasalChangeStepView()
            graphic.direction = loKeyBasalDirection
            graphic.backgroundColor = .clear
            graphic.translatesAutoresizingMaskIntoConstraints = false
            graphic.widthAnchor.constraint(equalToConstant: 86).isActive = true
            graphic.heightAnchor.constraint(equalToConstant: 40).isActive = true
            let basalAmount = UILabel()
            basalAmount.text = loKeyBasalChange
            basalAmount.font = .monospacedDigitSystemFont(ofSize: 21, weight: .bold)
            basalAmount.textColor = .systemOrange
            basalAmount.adjustsFontSizeToFitWidth = true
            basalAmount.minimumScaleFactor = 0.7
            let basalCaption = UILabel()
            basalCaption.text = "Relative to scheduled basal"
            basalCaption.font = .preferredFont(forTextStyle: .caption2)
            basalCaption.textColor = .secondaryLabel
            let basalText = UIStackView(arrangedSubviews: [basalAmount, basalCaption])
            basalText.axis = .vertical
            basalText.spacing = 3
            let basalRow = UIStackView(arrangedSubviews: [graphic, basalText])
            basalRow.axis = .horizontal
            basalRow.alignment = .center
            basalRow.spacing = 15
            let basalCard = UIStackView(arrangedSubviews: [basalTitle, basalRow])
            basalCard.axis = .vertical
            basalCard.spacing = 4
            basalCard.backgroundColor = .secondarySystemGroupedBackground
            basalCard.layer.cornerRadius = 18
            basalCard.isLayoutMarginsRelativeArrangement = true
            basalCard.directionalLayoutMargins = NSDirectionalEdgeInsets(
                top: 12, leading: 16, bottom: 12, trailing: 16)
            basalCard.isAccessibilityElement = true
            basalCard.accessibilityLabel = "Basal change: \(loKeyBasalChange), relative to scheduled basal"
'''
    source = once(source,
        "            let stack = UIStackView(arrangedSubviews: [values, targetStack])",
        basal_card + "            let stack = UIStackView(arrangedSubviews: [values, basalCard, targetStack])",
        "add basal infographic to dashboard only")

    # Reuse Loop's exact computed net basal value used by the original orange
    # native HUD; do not try to derive it from pod reservoir or dosing totals.
    source = once(source,
        "                if let netBasal = netBasal {\n                    self.hudView?.pumpStatusHUD.basalRateHUD.setNetBasalRate",
        """                self.loKeyBasalChange = netBasal.map {
                    String(format: "%+.2f U/hr", $0.rate)
                } ?? "Unavailable"
                self.loKeyBasalDirection = netBasal?.rate ?? 0
                if let netBasal = netBasal {
                    self.hudView?.pumpStatusHUD.basalRateHUD.setNetBasalRate""",
        "read-only Loop net basal snapshot")
    source = once(source,
        "                cell.update(lastBolus: lokeySnapshot.lastBolus, carbs: lokeySnapshot.cob,",
        """                cell.loKeyBasalChange = loKeyBasalChange
                cell.loKeyBasalDirection = loKeyBasalDirection
                cell.update(lastBolus: lokeySnapshot.lastBolus, carbs: lokeySnapshot.cob,""",
        "initial dashboard basal rendering")
    source = once(source,
        "                self.loKeyQuickStatsCell?.update(",
        """                self.loKeyQuickStatsCell?.loKeyBasalChange = self.loKeyBasalChange
                self.loKeyQuickStatsCell?.loKeyBasalDirection = self.loKeyBasalDirection
                self.loKeyQuickStatsCell?.update(""",
        "live dashboard basal rendering")

    return source


def install() -> None:
    original = STATUS.read_text(encoding="utf-8")
    updated = transform(original)
    if updated == original:
        raise RuntimeError("No presentation changes made")
    STATUS.write_text(updated, encoding="utf-8")
    print("PASS: LoKey compact device notices + dashboard basal-change graphic installed")
    print("PASS: native status HUD remains alive; dosing and pump commands unchanged")


if __name__ == "__main__":
    install()
