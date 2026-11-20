#!/usr/bin/env python3
"""Source-only regression tests for the presentation-only active bolus banner."""
import importlib.util
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "install_lokey_bolus_progress_polish.py"
spec = importlib.util.spec_from_file_location("bolus_progress", INSTALLER)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# The dashboard CI also runs this installer against the complete, pinned
# upstream Swift source and parses it with swiftc after all other LoKey patches.
FIXTURE = '''public class BolusProgressTableViewCell: UITableViewCell {
    @IBOutlet weak var progressIndicator: RingProgressView!

    override public func awakeFromNib() {
        super.awakeFromNib()
        updateColors()
    }

    override public func layoutSubviews() {
        super.layoutSubviews()
    }
    private func updateColors() {
        progressIndicator.startColor = tintColor
        gradient.colors = [
            UIColor.cellBackgroundColor.withAlphaComponent(0).cgColor,
            UIColor.cellBackgroundColor.cgColor
        ]
    }
    private func updateProgress() {
        if let deliveredUnits = deliveredUnits {
            progressLabel.text = "Existing delivered value"
            progressIndicator.progress = deliveredUnits / totalUnits
        } else {
            progressLabel.text = String(format: NSLocalizedString("Bolusing %1$@", comment: "The format string for bolus in progress showing total volume. (1: total volume)"), totalUnitsString)
        }
    }

    override public func prepareForReuse() {
        super.prepareForReuse()
        progressIndicator.progress = 0
        CATransaction.flush()
        progressLabel.text = ""
    }
}
'''


class BolusProgressPresentationTests(unittest.TestCase):
    def setUp(self):
        self.source = module.transform(FIXTURE)

    def test_preserves_existing_reporter_and_cancellation_path(self):
        result = self.source
        self.assertIn('progressLabel.text = "Existing delivered value"', result)
        self.assertIn("progressIndicator.progress = deliveredUnits / totalUnits", result)
        self.assertIn("loKeyInstallBolusProgressPresentation()", result)
        self.assertIn("loKeyRefreshBolusProgressPresentation(animated: true)", result)
        self.assertNotIn("cancelBolus(", result)
        self.assertNotIn("enactBolus(", result)

    def test_bolus_amount_progress_and_clear_stop_label(self):
        result = self.source
        self.assertIn('loKeyTitle.text = NSLocalizedString(', result)
        self.assertIn('"DELIVERING INSULIN"', result)
        self.assertIn('deliveredString + " / " + totalString + " U"', result)
        self.assertIn("loKeyProgressBar.setProgress(Float(fraction), animated: animated)", result)
        self.assertIn("loKeyStopLabel.text = NSLocalizedString(", result)
        self.assertIn('"STOP BOLUS"', result)
        self.assertIn("loKeyStopSurface.isUserInteractionEnabled = false", result)
        self.assertIn("row.isUserInteractionEnabled = false", result)
        self.assertIn("accessibilityTraits.insert(.button)", result)

    def test_progress_is_bounded_and_reset_on_reuse(self):
        result = self.source
        self.assertIn("let safeDelivered = max(0, min(total, delivered))", result)
        self.assertIn("guard loKeyPresentationInstalled, let total = totalUnits, total > 0,", result)
        self.assertIn("loKeyProgressBar.setProgress(0, animated: false)", result)
        self.assertIn("loKeyDose.text = nil", result)
        self.assertIn("progressIndicator.progress = 0", result)

    def test_fail_closed_for_renamed_upstream_or_duplicate_installer(self):
        with self.assertRaises(RuntimeError):
            module.transform(FIXTURE.replace("RingProgressView!", "OtherView!"))
        with self.assertRaises(RuntimeError):
            module.transform(self.source)


if __name__ == "__main__":
    unittest.main()
