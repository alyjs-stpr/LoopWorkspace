#!/usr/bin/env python3
"""Port Trio's read-only atomic App Group snapshot + WidgetCenter reload pattern to LoKey Loop.

Runs after install_lokey_trio_widget.py. Changes only the Loop app's
extension-data publisher and the Home Screen widget timeline provider.
No CGM drivers, pump controllers, dose calculation, or dosing actions touched.
"""
from pathlib import Path

ROOT = Path("Loop")
PRODUCER = ROOT / "Loop/Managers/ExtensionDataManager.swift"
PROVIDER = ROOT / "Loop Widget Extension/Timeline/StatusWidgetTimelineProvider.swift"
SNAPSHOT_NAME = "LoKeyLoopWidgetSnapshot.v1.json"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    occurrences = source.count(old)
    if occurrences != 1:
        raise RuntimeError(f"{label}: expected one anchor; found {occurrences}")
    return source.replace(old, new, 1)


PUBLISHER = """
    // Adapted from the read-only Trio widget's atomic App Group snapshot
    // pattern. Use observed glucose only; never calculate or request insulin.
    private func publishLoKeyWidgetSnapshot() {
        let store = deviceManager.glucoseStore
        let latest = store.latestGlucose
        let start = Date(timeIntervalSinceNow: -3 * 60 * 60)
        store.getGlucoseSamples(start: start) { result in
            let samples: [StoredGlucoseSample]
            switch result {
            case .success(let stored): samples = stored
            case .failure: samples = []
            }
            var points: [[String: Double]] = samples
                .sorted { $0.startDate < $1.startDate }
                .suffix(72)
                .map { [
                    "time": $0.startDate.timeIntervalSince1970,
                    "mgdl": $0.quantity.doubleValue(for: .milligramsPerDeciliter)
                ] }
            if points.isEmpty, let latest = latest {
                points = [[
                    "time": latest.startDate.timeIntervalSince1970,
                    "mgdl": latest.quantity.doubleValue(for: .milligramsPerDeciliter)
                ]]
            }
            let latestAllowed = Date().addingTimeInterval(120).timeIntervalSince1970
            points = points.filter { point in
                guard let time = point["time"], let glucose = point["mgdl"] else { return false }
                return time.isFinite && glucose.isFinite && glucose > 0 && time <= latestAllowed
            }
            guard !points.isEmpty,
                  let directory = FileManager.default.containerURL(
                      forSecurityApplicationGroupIdentifier: Bundle.main.appGroupSuiteName),
                  let payload = try? JSONSerialization.data(withJSONObject: [
                      "savedAt": Date().timeIntervalSince1970,
                      "points": points
                  ]) else { return }
            do {
                try payload.write(
                    to: directory.appendingPathComponent("LoKeyLoopWidgetSnapshot.v1.json"),
                    options: .atomic
                )
                // Best effort. iOS controls when the Home Screen actually redraws.
                WidgetCenter.shared.reloadTimelines(ofKind: "SystemStatusWidget")
            } catch {
                // A widget cache failure must never affect Loop's insulin delivery.
            }
        }
    }

"""


def producer_transform(source: str) -> str:
    source = replace_once(source, "import UIKit\n", "import UIKit\nimport WidgetKit\n",
                          "widget refresh import")
    source = replace_once(
        source,
        "                ExtensionDataManager.context = context\n",
        "                ExtensionDataManager.context = context\n"
        "                self.publishLoKeyWidgetSnapshot()\n",
        "snapshot publication after existing status update")
    return replace_once(source, "    private func createIntentsContext(",
                        PUBLISHER + "    private func createIntentsContext(",
                        "read-only snapshot publisher insertion")


READER = """
    // Trio-style synchronous shared snapshot: avoid blocking WidgetKit's
    // Home Screen timeline on Core Data, which may be slow after app suspension.
    // Missing snapshots still fall through to Loop's existing async provider.
    private func readLoKeySharedEntry(at date: Date) -> StatusWidgetTimelimeEntry? {
        guard let directory = FileManager.default.containerURL(
                  forSecurityApplicationGroupIdentifier: Bundle.main.appGroupSuiteName),
              let data = try? Data(contentsOf: directory.appendingPathComponent(
                  "LoKeyLoopWidgetSnapshot.v1.json")),
              let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rows = payload["points"] as? [[String: Double]],
              let savedAt = payload["savedAt"] as? Double, savedAt.isFinite
        else { return nil }

        let now = date.timeIntervalSince1970
        let sorted = rows.compactMap { row -> (Date, Double)? in
            guard let timestamp = row["time"], let glucose = row["mgdl"],
                  timestamp.isFinite, glucose.isFinite, glucose > 0,
                  timestamp <= now + 120, timestamp >= now - 4 * 60 * 60
            else { return nil }
            return (Date(timeIntervalSince1970: timestamp), glucose)
        }.sorted { $0.0 < $1.0 }
        guard let last = sorted.last else { return nil }

        var segment = 0
        var previous: Date?
        let history: [LoKeyWidgetGlucosePoint] = sorted.enumerated().map { index, sample in
            if let previous = previous, sample.0.timeIntervalSince(previous) > 7 * 60 {
                segment += 1
            }
            previous = sample.0
            return LoKeyWidgetGlucosePoint(id: index, date: sample.0,
                                          glucose: sample.1, segment: segment)
        }
        let glucose = GlucoseContext(value: last.1, unit: .milligramsPerDeciliter,
                                     startDate: last.0)
        var delta: HKQuantity?
        if sorted.count >= 2 {
            let earlier = sorted[sorted.count - 2]
            if last.0.timeIntervalSince(earlier.0) > 0,
               last.0.timeIntervalSince(earlier.0) < 6 * 60 {
                delta = HKQuantity(unit: .milligramsPerDeciliter,
                                   doubleValue: last.1 - earlier.1)
            }
        }
        let context = defaults?.statusExtensionContext
        return StatusWidgetTimelimeEntry(
            date: date,
            contextUpdatedAt: context?.createdAt ?? .distantPast,
            lastLoopCompleted: context?.lastLoopCompleted,
            closeLoop: context?.isClosedLoop ?? false,
            currentGlucose: glucose,
            glucoseFetchedAt: Date(timeIntervalSince1970: savedAt),
            delta: delta,
            unit: .milligramsPerDeciliter,
            sensor: context?.glucoseDisplay,
            pumpHighlight: context?.pumpStatusHighlightContext,
            netBasal: context?.netBasal,
            eventualGlucose: context?.predictedGlucose?.samples.last,
            insulinOnBoard: context?.insulinOnBoard,
            carbsOnBoard: context?.carbsOnBoard,
            glucoseHistory: history,
            preMealPresetAllowed: context?.preMealPresetAllowed ?? false,
            preMealPresetActive: context?.preMealPresetActive ?? false,
            customPresetActive: context?.customPresetActive ?? false
        )
    }

"""


def provider_transform(source: str) -> str:
    if "LoKeyWidgetGlucosePoint" not in source or "private final class EntryCompletion" not in source:
        raise RuntimeError("LoKey display widget and timeout guard must be installed first")
    source = replace_once(source, "    func placeholder(in context: Context)",
                          READER + "    func placeholder(in context: Context)",
                          "shared snapshot reader insertion")
    source = replace_once(
        source,
        "    func getSnapshot(in context: Context, completion: @escaping (StatusWidgetTimelimeEntry) -> ()) {\n",
        "    func getSnapshot(in context: Context, completion: @escaping (StatusWidgetTimelimeEntry) -> ()) {\n"
        "        if let entry = readLoKeySharedEntry(at: Date()) {\n"
        "            completion(entry)\n"
        "            return\n"
        "        }\n",
        "snapshot preview fast path")
    source = replace_once(
        source,
        "    func getTimeline(in context: Context, completion: @escaping (Timeline<StatusWidgetTimelimeEntry>) -> ()) {\n",
        "    func getTimeline(in context: Context, completion: @escaping (Timeline<StatusWidgetTimelimeEntry>) -> ()) {\n"
        "        let now = Date()\n"
        "        if let first = readLoKeySharedEntry(at: now) {\n"
        "            // Reuse the observed snapshot while letting stale flags advance.\n"
        "            let entries = [0, 5, 10, 15, 20].map { offset -> StatusWidgetTimelimeEntry in\n"
        "                var entry = first\n"
        "                entry.date = now.addingTimeInterval(TimeInterval(offset * 60))\n"
        "                return entry\n"
        "            }\n"
        "            completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(5 * 60))))\n"
        "            return\n"
        "        }\n",
        "Home Screen synchronous timeline fast path")
    return source


def install() -> None:
    original_producer = PRODUCER.read_text(encoding="utf-8")
    original_provider = PROVIDER.read_text(encoding="utf-8")
    updated_producer = producer_transform(original_producer)
    updated_provider = provider_transform(original_provider)
    # Fail closed: both outputs validated before any writes.
    PRODUCER.write_text(updated_producer, encoding="utf-8")
    PROVIDER.write_text(updated_provider, encoding="utf-8")
    print("PASS: Trio-style read-only App Group widget snapshots and refresh hints")


if __name__ == "__main__":
    install()
