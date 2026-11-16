"""Static, fail-closed validation for the Trio-style LoKey widget snapshot bridge."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "install_lokey_widget_snapshot_bridge.py"
spec = importlib.util.spec_from_file_location("lokey_widget_snapshot", SOURCE)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SnapshotBridgeTests(unittest.TestCase):
    def test_producer_adds_only_observation_and_refresh(self):
        original = (
            "import HealthKit\nimport UIKit\nimport LoopKit\n"
            "                ExtensionDataManager.context = context\n"
            "    private func createIntentsContext("
        )
        updated = installer.producer_transform(original)
        self.assertIn("WidgetCenter.shared.reloadTimelines(ofKind: \"SystemStatusWidget\")", updated)
        self.assertIn("options: .atomic", updated)
        self.assertIn("getGlucoseSamples(start: start)", updated)
        self.assertIn(installer.SNAPSHOT_NAME, updated)
        self.assertNotIn("enactBolus", updated)
        self.assertNotIn("enactTempBasal", updated)
        self.assertNotIn("recommendBolus", updated)

    def test_widget_timeline_uses_shared_snapshot_before_expensive_cache(self):
        original = (
            "private final class EntryCompletion\n"
            "struct LoKeyWidgetGlucosePoint\n"
            "    func placeholder(in context: Context)\n"
            "    func getSnapshot(in context: Context, completion: @escaping (StatusWidgetTimelimeEntry) -> ()) {\n"
            "    func getTimeline(in context: Context, completion: @escaping (Timeline<StatusWidgetTimelimeEntry>) -> ()) {\n"
        )
        updated = installer.provider_transform(original)
        self.assertIn("readLoKeySharedEntry(at: now)", updated)
        self.assertIn("readLoKeySharedEntry(at: Date())", updated)
        self.assertIn("glucoseFetchedAt: Date(timeIntervalSince1970: savedAt)", updated)
        self.assertIn("contextUpdatedAt: context?.createdAt ?? .distantPast", updated)
        self.assertIn("TimeInterval(offset * 60)", updated)
        self.assertIn("glucoseHistory: history", updated)
        self.assertNotIn("enactBolus", updated)

    def test_fails_closed_on_source_drift(self):
        with self.assertRaises(RuntimeError):
            installer.producer_transform("unknown")
        with self.assertRaises(RuntimeError):
            installer.provider_transform("unknown")
        with self.assertRaises(RuntimeError):
            installer.producer_transform("import UIKit\n")

if __name__ == "__main__":
    unittest.main()
