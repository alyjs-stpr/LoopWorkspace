"""No-build regression checks for LoKey Glooko-style PDF and October HealthKit history."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

history = module("history", "install_lokey_clinical_history_v2.py")
pdf = module("pdf_v2", "install_lokey_clinical_pdf_v2.py")

class ClinicalV2Tests(unittest.TestCase):
    def test_health_history_does_not_touch_insulin_control(self):
        src = history.HELPERS + history.GENERATE + pdf.PDF
        self.assertIn("HKHealthStore", src)
        self.assertIn("HKSampleQuery", src)
        self.assertIn("HasLoopKitOrigin", src)
        self.assertIn("com.loopkit.InsulinKit.MetadataKeyAutomaticallyIssued", src)
        self.assertIn("HKMetadataKeySyncIdentifier", src)
        self.assertIn("StoredGlucoseSample(sample: item)", src)
        self.assertIn("other-pump", src.lower())
        for forbidden in ["enactBolus(", "setTempBasal(", "deactivatePod(", "suspendDelivery("]:
            self.assertNotIn(forbidden, src)

    def test_report_has_glooko_familiar_daily_sections(self):
        src = pdf.PDF
        self.assertIn("Daily Overview", src)
        self.assertIn("GLUCOSE  (mg/dL)  •  24-HOUR TRACE", src)
        self.assertIn("CARBS", src)
        self.assertIn("BOLUSES", src)
        self.assertIn("BASAL RATE", src)
        self.assertIn("AMBULATORY GLUCOSE PROFILE", src)
        self.assertIn("TIME IN GLUCOSE RANGES", src)
        self.assertIn("for day in days", src)
        self.assertIn("Automated boluses:", src)
        self.assertIn("Total Daily Basal:", src)
        self.assertIn("basal + auto bolus", src)

    def test_report_is_explicit_about_gaps_and_sources(self):
        src = history.HELPERS + pdf.PDF
        self.assertIn("Missing days are not zero doses", src)
        self.assertIn("No CGM samples available for this day", src)
        self.assertIn("No Loop insulin records available", src)
        self.assertIn("requestAuthorization(toShare: [], read: types)", src)
        self.assertIn("Daily Overview", src)
        self.assertIn("not included in LoKey totals", src)

    def test_source_installers_fail_closed_and_only_style_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = root / "SettingsView.swift"
            status = root / "StatusTableViewController.swift"
            settings.write_text('''
private struct LoKeyInsulinHistoryView: View {
    func demo() {
        doseLine("Basal", daily.basal)
    }
}

private struct LoKeyClinicalReportView: View {
    var body: some View {
        Text("Clinical-style PDF with AGP percentiles, glucose distribution, daily delivered insulin, automated vs user-initiated boluses, recorded pod changes, and current therapy settings.")
    }
    private func generate() {
        let old = 1
    }
}

private enum LoKeyClinicalPDF {
}
''')
            status.write_text('''
todayTile("BASAL", value: todayBasalValue
todayTile("BOLUSES", value: todayBolusValue
self.loKeyDailyBasal = String(format: "%.2f U", basalUnits)
self.loKeyDailyBolus = String(format: "%.2f U", bolusUnits)
note.text = "Pump-delivered entries shown above; unverified manual logs excluded from totals. In-progress delivery may be estimated."
''')
            with mock.patch.object(history,"SETTINGS",settings),\
                 mock.patch.object(history,"STATUS",status),\
                 mock.patch.object(pdf,"PATH",settings):
                history.install()
                pdf.install()
                content = settings.read_text()
                self.assertEqual(content.count("private enum LoKeyClinicalPDFV2 {"), 1)
                self.assertEqual(content.count("private enum LoKeyClinicV2History {"), 1)
                self.assertIn("LoKeyClinicalPDFV2.make(", content)
                self.assertIn('Total basal (basal + Loop auto)', content)
                self.assertIn("TOTAL BASAL*", status.read_text())
                self.assertIn("basalUnits + automaticBolusUnits",status.read_text())
                self.assertIn("initiatedBolusUnits + unclassifiedBolusUnits",status.read_text())
                with self.assertRaises(RuntimeError):
                    pdf.install()

if __name__ == "__main__":
    unittest.main()
