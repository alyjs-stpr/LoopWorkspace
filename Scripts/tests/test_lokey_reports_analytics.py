"""Source-only tests for LoKey clinical reporting installer; no app builds or devices."""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "install_lokey_reports_analytics.py"

spec = importlib.util.spec_from_file_location("lokey_reports", SCRIPT)
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)


class LoKeyReportsInstallerTests(unittest.TestCase):
    def test_source_guards_and_report_sections(self):
        swift = reports.SWIFT_SOURCE
        self.assertIn("LoKeyReportsHubView", swift)
        self.assertIn("LoKeyInsulinHistoryView", swift)
        self.assertIn("LoKeyPodUsageView", swift)
        self.assertIn("LoKeyClinicalReportView", swift)
        self.assertIn("LoKeyClinicalPDF", swift)
        self.assertIn("UIGraphicsPDFRenderer", swift)
        self.assertIn("Ambulatory Glucose Profile", swift)
        self.assertIn("dose.automatic == true", swift)
        self.assertIn("dose.wasProgrammedByPumpUI", swift)
        self.assertIn("dose.manuallyEntered", swift)
        self.assertIn("No pump delivery entries available", swift)
        self.assertIn("Pod reservoir: 50+ U (not an exact reading)", swift)
        self.assertNotIn("enactBolus(", swift)
        self.assertNotIn("suspendDelivery(", swift)
        self.assertNotIn("deactivatePod(", swift)
        self.assertNotIn("setTempBasal(", swift)

    def test_installer_edits_only_expected_sources_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            settings = root / "SettingsView.swift"
            model = root / "SettingsViewModel.swift"
            status = root / "StatusTableViewController.swift"
            settings.write_text("""
private struct LoKeySettingsView: View {
    var body: some View {
                NavigationLink(destination: LoKeyReportsView(viewModel: viewModel)) {
                    Label("Glucose reports & settings PDF", systemImage: "chart.pie")
                }
    }
}
""")
            model.write_text("    var loKeyLoadSettingsHistory: ((Date, Date, @escaping (Swift.Result<[StoredSettings], Error>) -> Void) -> Void)?")
            status.write_text("        viewModel.loKeyLoadSettingsHistory = { [weak self] start, end, completion in\n")
            with mock.patch.object(reports, "SETTINGS", settings), \
                 mock.patch.object(reports, "MODEL", model), \
                 mock.patch.object(reports, "STATUS", status):
                reports.install()
                s = settings.read_text()
                m = model.read_text()
                st = status.read_text()
                self.assertEqual(s.count("private struct LoKeyReportsHubView: View"), 1)
                self.assertEqual(s.count('Label("Reports & Analytics"'), 1)
                self.assertIn("loKeyLoadDoses", m)
                self.assertIn("loKeyCurrentPodSnapshot", m)
                self.assertIn("getNormalizedDoseEntries", st)
                self.assertIn("pumpManagerHUDProvider?.hudViewRawState", st)
                with self.assertRaises(RuntimeError):
                    reports.install()

if __name__ == "__main__":
    unittest.main()
