#!/usr/bin/env python3
"""No-device tests for LoKey quiet UI and unread Pod Info indicator."""
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "install_lokey_quiet_dashboard.py"
spec = importlib.util.spec_from_file_location("quiet_dashboard", PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Minimal generated Swift anchors from the previous, separate UI-only
# installer. The dashboard source preflight applies both installers to the
# full patched Loop controller and parses the resulting Swift source.
SOURCE = r'''    private weak var loKeyCGMAlertButton: UIButton?
    // Compact, actionable status notices replace the legacy 3-tile strip.
    // Keep the underlying native HUD alive for Loop's status and warning logic.
    private func loKeyInstallDeviceAlertBar(in header: UIView, below tabs: UISegmentedControl) {
    }
    private func loKeyRefreshDeviceAlertBar() {
    }
    @objc private func loKeyOpenSensorNotice(_ sender: UIButton) {
    }
    @objc private func loKeyOpenPumpNotice(_ sender: UIButton) {
    }
    @objc private func loKeyOpenLoopNotice(_ sender: UIButton) {
    }
    private final class LoKeyGlucoseCard: UITableViewCell {
        private let insulin = UILabel()
        func initView() {
            let row = UIStackView(arrangedSubviews: [heading, insulin])
        }
        func update() {
            insulin.text = "IOB " + iob
        }
    }
    private func refreshHeader() {
        loKeyGlucoseHeaderCard?.update(glucose: glucose, detail: detail, iob: lokeySnapshot.iob, trend: trend)
    }
    private final class LoKeyBasalChangeStepView: UIView {
        override func draw(_ rect: CGRect) {
            let vertical = max(8, min(15, rect.height / 3))
            path.move(to: CGPoint(x: rect.minX + 19, y: center))
            path.move(to: CGPoint(x: rect.maxX - 19, y: center))
            path.lineWidth = 3
        }
    }
    private final class LoKeyQuickStatsCell: UITableViewCell {
        func update() {
            // Isolated net basal adjustment card; no pod reservoir HUD.
            let basalTitle = UILabel()
            let basalCard = UIStackView(arrangedSubviews: [basalTitle])
            let stack = UIStackView(arrangedSubviews: [values, basalCard, targetStack])
        }
    }
    private var loKeyNoticeHeight: CGFloat = 0
'''


class QuietDashboardTests(unittest.TestCase):
    def setUp(self):
        self.updated = module.transform(SOURCE)

    def test_unread_dot_tracks_new_pod_issue_and_acknowledges_view(self):
        s = self.updated
        self.assertIn("loKeyPodUnreadDot", s)
        self.assertIn("loKeyTabsControl?.accessibilityValue = unread", s)
        self.assertIn('let seenKeyName = "LoKeyLastSeenPodIssueV1"', s)
        self.assertIn("pumpAttention && loKeyPage == .pod", s)
        self.assertIn("UserDefaults.standard.set(issueKey, forKey: seenKeyName)", s)
        self.assertIn("podIdentity + \"|\" + severity", s)
        self.assertIn('pumpLifecycle == .critical ? "critical"', s)

    def test_sensor_alerts_never_appear_as_standalone_tiles(self):
        s = self.updated
        self.assertNotIn('item("⚠ Sensor"', s)
        self.assertNotIn("loKeyOpenSensorNotice", s)
        self.assertNotIn("loKeyCGMAlertButton", s)
        self.assertIn("loopOverdue && deviceManager.isGlucoseValueStale", s)
        self.assertIn("⚠ Loop overdue · Check CGM", s)
        self.assertIn("loKeyPumpAlertButton?.isHidden = !(pumpAttention && loKeyPage == .pod)", s)
        self.assertIn("loKeyDeviceAlertBar?.isHidden = !(loopOverdue || (pumpAttention && loKeyPage == .pod))", s)
        self.assertIn("loKeyOpenPumpNotice", s)

    def test_basal_change_compact_below_iob_and_no_separate_card(self):
        s = self.updated
        self.assertIn("let rightMetrics = UIStackView(arrangedSubviews: [insulin, basalCompact])", s)
        self.assertIn("basalChangeText.text = unavailable ? \"\" : loKeyBasalChange", s)
        self.assertIn("loKeyGlucoseHeaderCard?.loKeyBasalChange = loKeyBasalChange", s)
        self.assertIn("let stack = UIStackView(arrangedSubviews: [values, targetStack])", s)
        self.assertNotIn("let basalCard = UIStackView", s)
        self.assertIn("let vertical = max(3, min(5, rect.height / 3))", s)
        self.assertNotIn("enactBolus", s)
        self.assertNotIn("enactTempBasal", s)

    def test_requires_original_patch_and_fails_closed(self):
        with self.assertRaises(RuntimeError):
            module.transform(SOURCE.replace("loKeyInstallDeviceAlertBar", "otherFunction"))
        with self.assertRaises(RuntimeError):
            module.transform(self.updated)
        with self.assertRaises(RuntimeError):
            module.transform(SOURCE.replace('insulin.text = "IOB " + iob', 'insulin.text = "missing"'))


if __name__ == "__main__":
    unittest.main()
