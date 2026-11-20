#!/usr/bin/env python3
"""Source-only, no-pump regression tests for compact LoKey status UI."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "install_lokey_compact_status_ui.py"
spec = importlib.util.spec_from_file_location("lokey_compact_status", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


# Minimal post-UI-repair Swift anchors. The live preflight independently tests
# this installer against the fully patched Loop source, then parses it with swiftc.
FIXTURE = r'''    private var loKeyParkHeaderSignature: String?
    private func loKeyInstallPages() {
        loKeyPrimaryHeader = header
        tableView.tableHeaderView = header
    }
    private func loKeyRefreshHeader() {
    }
    private func updateParkDashboardHeader() {
        let isParkVisible = (active != nil || paused != nil) && loKeyPage == .dashboard
        let signature = "\(loKeyPage.rawValue):\(stamp):\(low):\(high):\(active == nil):\(isParkVisible)"
                NSLayoutConstraint.activate([
                    banner.topAnchor.constraint(equalTo: tabs.bottomAnchor, constant: 8),
        loKeyGlucoseTopConstraint?.constant = isParkVisible ? 120 : 16
        header.frame.size.height = baseHeight + (isParkVisible ? 104 : 0)
    }
    private final class LoKeyQuickStatsCell: UITableViewCell {
        var onTarget: ((Int) -> Void)?
        func update() {
            let stack = UIStackView(arrangedSubviews: [values, targetStack])
        }
    }
    private func updateStatus() {
                if let netBasal = netBasal {
                    self.hudView?.pumpStatusHUD.basalRateHUD.setNetBasalRate(netBasal.rate, percent: netBasal.percent, at: netBasal.start)
        if Section(rawValue: indexPath.section) == .hud && !loKeyNeedsNativeStatusHUD {
            hudView?.isHidden = !loKeyNeedsNativeStatusHUD
                cell.update(lastBolus: lokeySnapshot.lastBolus, carbs: lokeySnapshot.cob,
                self.loKeyQuickStatsCell?.update(
    }
'''


class CompactStatusTests(unittest.TestCase):
    def test_status_strip_is_hidden_while_native_view_is_preserved(self):
        result = module.transform(FIXTURE)
        self.assertIn("if Section(rawValue: indexPath.section) == .hud {", result)
        self.assertIn("hudView?.isHidden = true", result)
        self.assertIn("self.hudView?.pumpStatusHUD.basalRateHUD.setNetBasalRate", result)
        self.assertIn("loKeyOpenSensorNotice", result)
        self.assertIn("loKeyOpenPumpNotice", result)
        self.assertIn("loKeyOpenLoopNotice", result)
        self.assertIn("deviceManager.cgmStatusBadge != nil", result)
        self.assertIn("deviceManager.pumpStatusBadge != nil", result)
        self.assertIn("executeHUDTapAction(deviceManager.didTapOnCGMStatus()", result)

    def test_basal_indicator_is_separate_from_pod(self):
        result = module.transform(FIXTURE)
        self.assertIn("let basalCard = UIStackView", result)
        self.assertIn("UIStackView(arrangedSubviews: [values, basalCard, targetStack])", result)
        self.assertIn("String(format: \"%+.2f U/hr\", $0.rate)", result)
        self.assertIn("Relative to scheduled basal", result)
        self.assertNotIn("pumpManager.enactBolus", result)
        self.assertNotIn("enactTempBasal", result)

    def test_theme_park_and_notices_compose_instead_of_overlapping(self):
        result = module.transform(FIXTURE)
        self.assertIn("loKeyParkBannerTopConstraint?.constant = 8 + loKeyNoticeHeight", result)
        self.assertIn("16 + loKeyNoticeHeight + (isParkVisible ? 104 : 0)", result)
        self.assertIn("baseHeight + loKeyNoticeHeight + (isParkVisible ? 104 : 0)", result)

    def test_reapplication_is_rejected_and_bad_anchors_fail_closed(self):
        result = module.transform(FIXTURE)
        with self.assertRaises(RuntimeError):
            module.transform(result)
        with self.assertRaises(RuntimeError):
            module.transform(FIXTURE.replace("loKeyPrimaryHeader = header", "header = header"))


if __name__ == "__main__":
    unittest.main()
