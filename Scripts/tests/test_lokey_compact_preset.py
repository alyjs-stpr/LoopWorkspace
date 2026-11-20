"""Source-only guards for the compact preset status row."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "install_lokey_compact_preset.py"
spec = importlib.util.spec_from_file_location("lokey_compact_preset", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

NATIVE = """
    private class AlertPermissionsDisabledWarningCell: UITableViewCell {
    }
    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
                case .scheduleOverrideEnabled(let override):
                    let cell = getTitleSubtitleCell()
                    return cell
                case .enactingBolus:
                    return existingBolusCell
                case .bolusing(let dose):
                    cancelBolus()
    }
    override func tableView(_ tableView: UITableView, heightForRowAt indexPath: IndexPath) -> CGFloat {
    }
    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        editOverride()
    }
"""

class CompactPresetTests(unittest.TestCase):
    def test_only_preset_row_changes(self):
        revised = module.transform(NATIVE)
        self.assertIn("private final class LoKeyPresetCompactCell", revised)
        self.assertIn("Active glucose target", revised)
        self.assertIn("case .bolusing(let dose):\n                    cancelBolus()", revised)
        self.assertIn("editOverride()", revised)
        self.assertIn("case .enactingBolus:\n                    return existingBolusCell", revised)
        self.assertNotIn("let cell = getTitleSubtitleCell()", revised)
        self.assertIn("override.activeInterval.end", revised)
        self.assertIn("override.startDate", revised)
        self.assertIn("case .indefinite:", revised)
        self.assertIn("accessibilityLabel =", revised)
        self.assertIn("card.isUserInteractionEnabled = false", revised)

    def test_fails_closed_when_native_row_changes(self):
        with self.assertRaises(RuntimeError):
            module.transform(NATIVE.replace("case .scheduleOverrideEnabled(let override):", "case .changed:"))
        with self.assertRaises(RuntimeError):
            module.transform(NATIVE.replace("case .enactingBolus:", "case .changed:"))

    def test_rejects_double_install(self):
        with self.assertRaises(RuntimeError):
            module.transform(module.transform(NATIVE))

    def test_no_therapy_mutations_in_installer(self):
        source = PATH.read_text(encoding="utf-8")
        self.assertNotIn("enactBolus(", source)
        self.assertNotIn("cancelBolus()", source)
        self.assertNotIn("settings.scheduleOverride =", source)
        self.assertNotIn("pumpManager.resumeDelivery", source)

if __name__ == "__main__":
    unittest.main()
