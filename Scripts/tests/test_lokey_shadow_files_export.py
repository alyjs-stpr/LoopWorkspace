"""Guard the targeted Adaptive Shadow export rewrite against accidental scope drift."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Scripts" / "install_lokey_shadow_files_export.py"
spec = importlib.util.spec_from_file_location("shadow_export", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def original_fixture():
    return (
        "import SwiftUI\nimport Foundation\n"
        "private struct LoKeySettingsView: View {}\n"
        + module.START + "\n"
        '                Button("Export Shadow Records") { exportShadowRecords() }\n'
        "                LoKeyReportShareSheet(items: exportFiles)\n"
        '                let directory = root.appendingPathComponent("LoKeyAdaptiveShadow", isDirectory: true)\n'
        "}\n\n"
        + module.END + "\n"
        "private let unchangedPumpLogic = true\n"
    )


class ShadowExportSourceTests(unittest.TestCase):
    def test_replaces_only_shadow_settings_section(self):
        before = original_fixture()
        after = module.transform(before)
        self.assertIn("import UniformTypeIdentifiers", after)
        self.assertIn("private struct LoKeyShadowExportDocument: FileDocument", after)
        self.assertIn(".fileExporter(isPresented: $showingExporter,", after)
        self.assertIn('contentType: .json', after)
        self.assertIn('format": "LoKeyAdaptiveShadowExport"', after)
        self.assertIn('original Shadow records stay in Loop', after)
        self.assertIn("private let unchangedPumpLogic = true", after)
        self.assertNotIn("LoKeyReportShareSheet(items: exportFiles)", after)
        self.assertNotIn('Button("Export Shadow Records") { exportShadowRecords() }', after)
        self.assertEqual(after.count("private struct LoKeyAdaptiveShadowSettingsView"), 1)
        self.assertEqual(after.count("private struct LoKeyShadowDashboardView"), 1)

    def test_refuses_second_application(self):
        after = module.transform(original_fixture())
        with self.assertRaises(RuntimeError):
            module.transform(after)

    def test_refuses_changed_historical_export_behavior(self):
        altered = original_fixture().replace(
            "LoKeyReportShareSheet(items: exportFiles)", "MissingShareSheet()"
        )
        with self.assertRaises(RuntimeError):
            module.transform(altered)

    def test_is_only_a_settings_view_installer(self):
        self.assertEqual(module.SOURCE, Path("Loop/Loop/Views/SettingsView.swift"))
        self.assertNotIn("PumpManager", module.REPLACEMENT)
        self.assertNotIn("deliverBolus", module.REPLACEMENT)
        self.assertIn('sourceFileCount', module.REPLACEMENT)
        self.assertIn('jsonl": originalText', module.REPLACEMENT)
        self.assertIn("throw ExportError.tooLarge", module.REPLACEMENT)
        self.assertIn("Export was not saved:", module.REPLACEMENT)


if __name__ == "__main__":
    unittest.main()
