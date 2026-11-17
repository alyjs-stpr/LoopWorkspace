"""LoKey widget-matched interior theme: source-only, no app compile/build."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import tempfile

SCRIPT = Path(__file__).resolve().parents[1] / "install_lokey_widget_theme.py"
SPEC = importlib.util.spec_from_file_location("lokey_widget_theme", SCRIPT)
theme = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(theme)

PURPLE = "UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)"
STATUS_FIXTURE = '''
import UIKit
private extension RefreshContext {
}
final class StatusTableViewController {
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
    }
    private func loKeyInstallPages() {
        header.backgroundColor = .systemGroupedBackground
        tabs.selectedSegmentTintColor = UIColor(red: 0.46, green: 0.19, blue: 0.79, alpha: 1)
        tabs.setTitleTextAttributes([.foregroundColor: UIColor.white], for: .selected)
        brand.textColor = UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)
    }
    private func loKeyRefreshHeader() {
    }
    private final class LoKeyGlucoseCard: UITableViewCell {
        let a = UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)
        let b = UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)
        let c = UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)
        stack.backgroundColor = .secondarySystemGroupedBackground
        stack.backgroundColor = .secondarySystemGroupedBackground
        group.backgroundColor = .tertiarySystemGroupedBackground
        amount.textColor = LoKeyWidgetPalette.violet
    }
    override func viewDidLoad() {
    }
}
'''

SETTINGS_FIXTURE = '''
private struct LoKeySettingsView: View {
    let viewModel: SettingsViewModel
    var body: some View {
        Form {
            Section(header: Text("Adaptive Shadow")) {
            }
        }
        .navigationTitle("LoKey Settings")
    }
}

private struct LoKeyNextView: View {
}
'''

class ThemeInstallerTests(unittest.TestCase):
    def test_palette_and_layout_excludes_control_code(self):
        source = theme.PALETTE
        self.assertIn("#0E0F1F", source)
        self.assertIn("#AD6BFC", source)
        self.assertIn("UIUserInterfaceStyle", source)
        self.assertIn("systemOrange", source)
        self.assertNotIn("enactBolus(", source)
        self.assertNotIn("suspendDelivery(", source)
        self.assertNotIn("setTempBasal(", source)

    def test_status_transform_is_bounded_and_idempotent(self):
        out = theme.status_transform(STATUS_FIXTURE)
        self.assertIn("LoKeyWidgetPalette.background", out)
        self.assertIn("LoKeyWidgetPalette.applyWindowStyle(view.window)", out)
        self.assertIn("LoKeyWidgetPalette.card", out)
        self.assertIn("LoKeyWidgetPalette.violet", out)
        self.assertIn("LoKeyWidgetPalette.insulin", out)
        self.assertIn("LoKeyWidgetPalette.selectedText", out)
        self.assertNotIn(PURPLE, out)
        with self.assertRaises(RuntimeError):
            theme.status_transform(out)

    def test_settings_toggle_is_reversible(self):
        out = theme.settings_transform(SETTINGS_FIXTURE)
        self.assertIn('Toggle("Match Widget Dark Theme"', out)
        self.assertIn('enabled ? .dark : .unspecified', out)
        self.assertIn(".tint(Color(red: 0.68, green: 0.42, blue: 0.99))", out)
        with self.assertRaises(RuntimeError):
            theme.settings_transform(out)

    def test_atomic_install_only_changes_expected_source_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            status = root / "Status.swift"
            settings = root / "Settings.swift"
            status.write_text(STATUS_FIXTURE)
            settings.write_text(SETTINGS_FIXTURE)
            with mock.patch.object(theme,"STATUS",status),mock.patch.object(theme,"SETTINGS",settings):
                theme.install()
                self.assertIn("LoKeyWidgetPalette.card", status.read_text())
                self.assertIn("Match Widget Dark Theme", settings.read_text())
                with self.assertRaises(RuntimeError):
                    theme.install()

if __name__ == "__main__":
    unittest.main()
