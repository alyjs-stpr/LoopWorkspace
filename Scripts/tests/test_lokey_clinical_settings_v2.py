"""No-build tests for readable ICR, ISF, basal, and historical settings reporting."""
from pathlib import Path
from unittest import mock
import importlib.util
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[1] / "install_lokey_clinical_settings_v2.py"
spec = importlib.util.spec_from_file_location("clinical_settings_v2", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SettingsTablesTests(unittest.TestCase):
    def test_formatted_schedules_and_saved_history(self):
        swift = module.HELPER
        for label in [
            "Insulin-to-carb ratio (ICR)",
            "Insulin sensitivity (ISF)",
            "Programmed basal schedule",
            "Glucose target schedule",
            "Pre-meal target",
            "Workout target",
            "Suspend threshold",
            "Maximum bolus",
            "Maximum basal rate",
            "Insulin action model",
            "LAST RECORDED BEFORE REPORT",
            "LAST SAVED DURING REPORT",
            "Documented settings changes",
            "No saved record means settings are unknown",
        ]:
            self.assertIn(label, swift, label)
        self.assertIn("t.carbRatioSchedule", swift)
        self.assertIn("t.insulinSensitivitySchedule", swift)
        self.assertIn("t.basalRateSchedule", swift)
        self.assertIn("t.glucoseTargetRangeSchedule", swift)
        self.assertIn("saved.filter { $0.date <= end }", swift)
        self.assertIn("last(where: { $0.date <= start })", swift)
        self.assertIn("last(where: { $0.date >= start })", swift)
        for forbidden in ["enactBolus(", "suspendDelivery(", "deactivatePod(", "setTempBasal("]:
            self.assertNotIn(forbidden, swift)

    def test_installer_swaps_out_truncated_json_and_paginates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SettingsView.swift"
            path.write_text('''
private enum LoKeyClinicalPDFV2 {
    static func make() {
        let bytes = pdf.pdfData { ctx in
            header("Pod Usage & Settings",range:headedRange,page:page)
            rule(385)
            text("CURRENT THERAPY SETTINGS",x:38,y:398,w:520,size:12,bold:true)
            text("Snapshot taken at export, not a reconstruction of historical settings.",
                 x:38,y:421,w:530,size:9,color:gray)
            if let blob = try? JSONEncoder().encode(settings) {
                let x = String(data:blob,encoding:.utf8)
            }
        }
        let path = FileManager.default.temporaryDirectory
    }
}
''')
            with mock.patch.object(module, "VIEW", path):
                module.install()
                result = path.read_text()
                self.assertEqual(result.count("private extension LoKeyClinicalPDFV2 {"), 1)
                self.assertIn("renderTherapySettings(ctx:ctx", result)
                self.assertIn("saved:data.savedTherapySettings", result)
                self.assertNotIn('text("CURRENT THERAPY SETTINGS"', result)
                self.assertNotIn("JSONEncoder().encode(settings)", result)
                self.assertIn("newTherapyPage(ctx, ", result)
                with self.assertRaises(RuntimeError):
                    module.install()

if __name__ == "__main__":
    unittest.main()
