#!/usr/bin/env python3
"""Read-only, fail-closed LoKey dark glucose/IOB Home Screen widget installer.

Apply after all existing LoKey UI/widget patches. Only presentation and
read-only extension context are changed; Loop's controller, dose store,
CGM drivers and pump code are untouched. Any upstream drift aborts first.
"""
from pathlib import Path

ROOT = Path("Loop")
FILES = {
    "context": ROOT / "Common/Models/StatusExtensionContext.swift",
    "extension": ROOT / "Loop/Managers/ExtensionDataManager.swift",
    "entry": ROOT / "Loop Widget Extension/Timeline/StatusWidgetTimelimeEntry.swift",
    "provider": ROOT / "Loop Widget Extension/Timeline/StatusWidgetTimelineProvider.swift",
    "widget": ROOT / "Loop Widget Extension/Widgets/SystemStatusWidget.swift",
}

def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, got {count}")
    return source.replace(old, new, 1)

def context_transform(source: str) -> str:
    source = once(source,
        "    var carbsOnBoard: Double?\n",
        "    var carbsOnBoard: Double?\n    var insulinOnBoard: Double? // read-only display cache; optional for older snapshots\n",
        "status context declaration")
    source = once(source,
        '        carbsOnBoard = rawValue["carbsOnBoard"] as? Double\n',
        '        carbsOnBoard = rawValue["carbsOnBoard"] as? Double\n        insulinOnBoard = rawValue["insulinOnBoard"] as? Double\n',
        "status context decode")
    return once(source,
        '        raw["carbsOnBoard"] = carbsOnBoard\n',
        '        raw["carbsOnBoard"] = carbsOnBoard\n        raw["insulinOnBoard"] = insulinOnBoard\n',
        "status context encode")

def extension_transform(source: str) -> str:
    return once(source,
        "            context.carbsOnBoard = state.carbsOnBoard?.quantity.doubleValue(for: .gram())\n",
        "            context.carbsOnBoard = state.carbsOnBoard?.quantity.doubleValue(for: .gram())\n"
        "            // Display the controller's already-calculated IOB; never recalculate or dose.\n"
        "            context.insulinOnBoard = state.insulinOnBoard?.value\n",
        "status producer")

def entry_transform(source: str) -> str:
    source = once(source, "struct StatusWidgetTimelimeEntry: TimelineEntry {",
        """// Historical samples are read from the existing glucose cache only.
struct LoKeyWidgetGlucosePoint: Identifiable {
    let id: Int
    let date: Date
    let glucose: Double
    let segment: Int
}

struct StatusWidgetTimelimeEntry: TimelineEntry {""", "widget entry declaration")
    return once(source,
        "    let eventualGlucose: GlucoseContext?\n",
        "    let eventualGlucose: GlucoseContext?\n"
        "    let insulinOnBoard: Double?\n"
        "    let carbsOnBoard: Double?\n"
        "    let glucoseHistory: [LoKeyWidgetGlucosePoint]\n",
        "widget entry fields")

def provider_transform(source: str) -> str:
    # Build 17/19 widget reliability patches must already be present.
    if "private final class EntryCompletion" not in source or "asyncAfter(deadline: .now() + 4)" not in source:
        raise RuntimeError("Widget timeout protection missing; refusing to replace provider")
    if source.count("eventualGlucose: nil,") != 2:
        raise RuntimeError("Expected placeholder and unavailable fallbacks")
    source = source.replace("eventualGlucose: nil,",
        "eventualGlucose: nil, insulinOnBoard: nil, carbsOnBoard: nil, glucoseHistory: [],")
    source = once(source,
        "        let startDate = Date(timeIntervalSinceNow: -.minutes(45))",
        "        let startDate = Date(timeIntervalSinceNow: -.hours(3))",
        "widget glucose history window")
    source = once(source, "            let currentGlucose = finalGlucose.last",
        """            // The chart is historical only, segmented across missing CGM samples.
            // Never connect a purple line across a dropout.
            var glucoseHistory: [LoKeyWidgetGlucosePoint] = []
            var segment = 0
            var previousDate: Date?
            for sample in finalGlucose.sorted(by: { $0.startDate < $1.startDate }) {
                if let previousDate, sample.startDate.timeIntervalSince(previousDate) > 7 * 60 {
                    segment += 1
                }
                glucoseHistory.append(LoKeyWidgetGlucosePoint(
                    id: glucoseHistory.count,
                    date: sample.startDate,
                    glucose: sample.quantity.doubleValue(for: unit),
                    segment: segment
                ))
                previousDate = sample.startDate
            }
            let currentGlucose = finalGlucose.last""", "widget chart history")
    return once(source,
        "                eventualGlucose: eventualGlucose,\n",
        "                eventualGlucose: eventualGlucose,\n"
        "                insulinOnBoard: context.insulinOnBoard,\n"
        "                carbsOnBoard: context.carbsOnBoard,\n"
        "                glucoseHistory: glucoseHistory,\n",
        "widget read-only metrics")

WIDGET = r'''//
//  SystemStatusWidget.swift — LoKey dark Glucose & IOB
//  Display-only customization. No widget shortcuts or insulin commands.
//

import Charts
import LoopUI
import SwiftUI
import WidgetKit

@available(iOS 16.1, *)
struct SystemStatusWidgetEntryView: View {
    @Environment(\.widgetFamily) private var widgetFamily

    let entry: StatusWidgetTimelineProvider.Entry

    private let night = Color(red: 0.055, green: 0.06, blue: 0.12)
    private let purple = Color(red: 0.68, green: 0.42, blue: 0.99)
    private let secondary = Color(red: 0.66, green: 0.68, blue: 0.77)

    private var graphRange: ClosedRange<Double> {
        let values = entry.glucoseHistory.map(\.glucose)
        guard let low = values.min(), let high = values.max() else { return 60...200 }
        let minimum = max(40, low - 25)
        return minimum...max(minimum + 25, high + 25)
    }

    private var glucoseIsUnavailable: Bool {
        entry.currentGlucose == nil || entry.glucoseIsStale || entry.glucoseStatusIsStale
    }

    private var iobString: String {
        guard !entry.contextIsStale, let iob = entry.insulinOnBoard, iob.isFinite else {
            return "--"
        }
        return String(format: "%.2f U", iob)
    }

    private var eventualString: String {
        guard !entry.contextIsStale, !glucoseIsUnavailable,
              let value = entry.eventualGlucose else { return "--" }
        return String(format: "%.0f", value.quantity.doubleValue(for: value.unit))
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 8) {
                LoopCircleView(entry: entry)
                    .frame(width: 36, height: 36)
                GlucoseView(entry: entry)
                Spacer(minLength: 6)
                VStack(alignment: .trailing, spacing: 1) {
                    Text("IOB").font(.system(size: 10, weight: .semibold))
                        .foregroundColor(secondary)
                    Text(iobString)
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .minimumScaleFactor(0.75)
                        .lineLimit(1)
                }
            }
            if widgetFamily == .systemMedium {
                if entry.glucoseHistory.count > 1 {
                    Chart(entry.glucoseHistory) { point in
                        LineMark(
                            x: .value("Time", point.date),
                            y: .value("Glucose", point.glucose),
                            series: .value("Connected data", point.segment)
                        )
                        .foregroundStyle(purple)
                        .lineStyle(StrokeStyle(lineWidth: 2.5, lineCap: .round))
                        .interpolationMethod(.linear)
                    }
                    .chartLegend(.hidden)
                    .chartYAxis(.hidden)
                    .chartXAxis(.hidden)
                    .chartYScale(domain: graphRange)
                    .chartXScale(domain: entry.date.addingTimeInterval(-3 * 60 * 60)...entry.date)
                    .frame(height: 57)
                    .opacity(glucoseIsUnavailable ? 0.5 : 1)
                } else {
                    Text("No recent glucose history")
                        .font(.caption2)
                        .foregroundColor(secondary)
                        .frame(height: 57, alignment: .center)
                        .frame(maxWidth: .infinity)
                }
                HStack(spacing: 8) {
                    Text("3H GLUCOSE").foregroundColor(secondary)
                    Spacer(minLength: 1)
                    Text("EVENTUAL " + eventualString).foregroundColor(.white)
                    if let cob = entry.carbsOnBoard, !entry.contextIsStale, cob.isFinite {
                        Text(String(format: "COB %.0f g", cob)).foregroundColor(secondary)
                    }
                }
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            } else {
                HStack {
                    Text("EVENTUAL " + eventualString)
                    Spacer(minLength: 4)
                    Text("3H graph on medium widget")
                }
                .font(.system(size: 10))
                .foregroundColor(secondary)
            }

            if let warning = entry.pumpHighlight {
                Text("PUMP: " + warning.localizedMessage)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.orange)
                    .lineLimit(1)
            } else if glucoseIsUnavailable {
                Text("CGM DATA STALE — open LoKey")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.orange)
            } else if entry.contextIsStale {
                Text("LOOP DATA STALE — open LoKey")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.orange)
            } else if let last = entry.currentGlucose?.startDate {
                (Text("CGM updated ") + Text(last, style: .relative))
                    .font(.system(size: 10))
                    .foregroundColor(secondary)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .foregroundColor(.white)
        .environment(\.colorScheme, .dark)
        .privacySensitive()
    }

    @ViewBuilder
    var body: some View {
        if #available(iOSApplicationExtension 17.0, *) {
            content.containerBackground(for: .widget) { night }
        } else {
            content.background(night)
        }
    }
}

@available(iOS 16.1, *)
struct SystemStatusWidget: Widget {
    let kind: String = "SystemStatusWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: StatusWidgetTimelineProvider()) { entry in
            SystemStatusWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("LoKey Glucose & IOB")
        .description("Dark glucose history, IOB, eventual glucose and stale-data status.")
        .supportedFamilies([.systemSmall, .systemMedium])
        .contentMarginsDisabledIfAvailable()
    }
}
'''

def widget_transform(source: str) -> str:
    start = "//\n//  SystemStatusWidget.swift"
    if not source.startswith(start) or source.count("struct SystemStatusWidgetEntryView") != 1:
        raise RuntimeError("Existing widget source changed; refusing full display replacement")
    if "SystemActionLink(to: .bolus)" not in source:
        raise RuntimeError("Existing widget quick-action anchors changed")
    return WIDGET

def install() -> None:
    transforms = {
        "context": context_transform,
        "extension": extension_transform,
        "entry": entry_transform,
        "provider": provider_transform,
        "widget": widget_transform,
    }
    originals = {key: path.read_text(encoding="utf-8") for key, path in FILES.items()}
    transformed = {key: transforms[key](originals[key]) for key in FILES}
    # No partial writes: verify every anchor before touching a file.
    for key, path in FILES.items():
        path.write_text(transformed[key], encoding="utf-8")
    print("PASS: LoKey dark purple glucose-history widget + display-only cached IOB")

if __name__ == "__main__":
    install()
