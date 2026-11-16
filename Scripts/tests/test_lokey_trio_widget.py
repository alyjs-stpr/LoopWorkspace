"""Pure, local tests for the LoKey read-only dark widget installer."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "install_lokey_trio_widget.py"
spec = importlib.util.spec_from_file_location("lokey_trio_widget", SCRIPT)
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class DarkWidgetTests(unittest.TestCase):
    def test_context_is_additive_and_optional(self):
        source = ('    var carbsOnBoard: Double?\n'
                  '        carbsOnBoard = rawValue["carbsOnBoard"] as? Double\n'
                  '        raw["carbsOnBoard"] = carbsOnBoard\n')
        patched = installer.context_transform(source)
        self.assertIn('raw["insulinOnBoard"] = insulinOnBoard', patched)
        self.assertIn('insulinOnBoard = rawValue["insulinOnBoard"] as? Double', patched)
        self.assertIn("var insulinOnBoard: Double?", patched)

    def test_observed_iob_not_recalculated(self):
        before = "            context.carbsOnBoard = state.carbsOnBoard?.quantity.doubleValue(for: .gram())\n"
        after = installer.extension_transform(before)
        self.assertIn('context.insulinOnBoard = state.insulinOnBoard?.value', after)
        self.assertNotIn("enactBolus", after)
        self.assertNotIn("insulinOnBoard(at:", after)

    def test_provider_keeps_timeout_fallback_and_gaps(self):
        before = ('private final class EntryCompletion\n'
                  'asyncAfter(deadline: .now() + 4)\n'
                  'eventualGlucose: nil,\n'
                  'eventualGlucose: nil,\n'
                  '        let startDate = Date(timeIntervalSinceNow: -.minutes(45))\n'
                  '            let currentGlucose = finalGlucose.last\n'
                  '                eventualGlucose: eventualGlucose,\n')
        after = installer.provider_transform(before)
        self.assertEqual(after.count("glucoseHistory: []"), 2)
        self.assertIn("glucoseHistory: glucoseHistory", after)
        self.assertIn("sample.startDate.timeIntervalSince(previousDate) > 7 * 60", after)
        self.assertIn("asyncAfter(deadline: .now() + 4)", after)

    def test_widget_has_data_not_dosing_shortcuts(self):
        source = ('//\n//  SystemStatusWidget.swift\n'
                  'struct SystemStatusWidgetEntryView { SystemActionLink(to: .bolus) }')
        after = installer.widget_transform(source)
        self.assertIn("Chart(entry.glucoseHistory)", after)
        self.assertIn('Text("IOB")', after)
        self.assertIn("glucoseIsUnavailable", after)
        self.assertNotIn("SystemActionLink", after)
        self.assertNotIn("enactBolus", after)
        self.assertNotIn("enactTempBasal", after)

    def test_fail_closed_on_changed_source(self):
        with self.assertRaises(RuntimeError):
            installer.provider_transform("unknown widget")
        with self.assertRaises(RuntimeError):
            installer.widget_transform("some other widget")

if __name__ == "__main__":
    unittest.main()
