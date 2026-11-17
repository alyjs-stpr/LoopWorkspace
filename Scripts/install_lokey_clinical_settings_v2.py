#!/usr/bin/env python3
"""Install formatted clinician-facing therapy schedules + dated historical changes.

Read-only LoKey SettingsStore snapshots. No insulin-dose or controller mutation.
Must run AFTER install_lokey_clinical_pdf_v2.py in both build routes.
"""
from pathlib import Path
VIEW = Path("Loop/Loop/Views/SettingsView.swift")

HELPER = r'''

// MARK: - LoKey: readable therapy settings, recorded history, no dosing changes
private extension LoKeyClinicalPDFV2 {
    struct ClinicalSettingsSnapshot {
        let label: String
        let icr: CarbRatioSchedule?
        let isf: InsulinSensitivitySchedule?
        let basal: BasalRateSchedule?
        let target: GlucoseRangeSchedule?
        let preMeal: ClosedRange<HKQuantity>?
        let workout: ClosedRange<HKQuantity>?
        let suspend: GlucoseThreshold?
        let maxBolus: Double?
        let maxBasal: Double?
        let insulinModel: String
    }

    static func clock(_ seconds: TimeInterval) -> String {
        let mins = Int(max(0, seconds) / 60) % 1440
        let hour = mins / 60
        let displayHour = hour % 12 == 0 ? 12 : hour % 12
        return String(format: "%d:%02d %@", displayHour, mins % 60,
                      hour >= 12 ? "PM" : "AM")
    }

    static func describeRange(_ value: ClosedRange<HKQuantity>?) -> String {
        guard let value else { return "Not configured" }
        return String(format: "%.0f–%.0f mg/dL",
            value.lowerBound.doubleValue(for: .milligramsPerDeciliter),
            value.upperBound.doubleValue(for: .milligramsPerDeciliter))
    }

    static func fromCurrent(_ t: TherapySettings) -> ClinicalSettingsSnapshot {
        ClinicalSettingsSnapshot(label: "CURRENT SETTINGS (AT PDF EXPORT)",
            icr: t.carbRatioSchedule, isf: t.insulinSensitivitySchedule,
            basal: t.basalRateSchedule, target: t.glucoseTargetRangeSchedule,
            preMeal: t.correctionRangeOverrides?.preMeal,
            workout: t.correctionRangeOverrides?.workout,
            suspend: t.suspendThreshold,
            maxBolus: t.maximumBolus, maxBasal: t.maximumBasalRatePerHour,
            insulinModel: t.defaultRapidActingModel?.rawValue ?? "Not recorded")
    }

    static func fromSaved(_ t: StoredSettings, label: String) -> ClinicalSettingsSnapshot {
        ClinicalSettingsSnapshot(label: label,
            icr: t.carbRatioSchedule, isf: t.insulinSensitivitySchedule,
            basal: t.basalRateSchedule, target: t.glucoseTargetRangeSchedule,
            preMeal: t.preMealTargetRange, workout: t.workoutTargetRange,
            suspend: t.suspendThreshold,
            maxBolus: t.maximumBolus, maxBasal: t.maximumBasalRatePerHour,
            insulinModel: t.defaultRapidActingModel.map { String(describing: $0) }
                ?? "Not recorded")
    }

    static func newTherapyPage(_ ctx: UIGraphicsPDFRendererContext,
                               _ name: String, _ range: String,
                               _ page: inout Int, _ y: inout CGFloat) {
        page += 1
        ctx.beginPage()
        header(name, range: range, page: page)
        y = 132
    }

    static func settingsRows(_ ctx: UIGraphicsPDFRendererContext,
                             _ title: String, rows: [(String, String)],
                             range: String, page: inout Int, y: inout CGFloat) {
        if y > 678 {
            newTherapyPage(ctx, "Therapy Settings (continued)", range, &page, &y)
        }
        text(title.uppercased(), x: 38, y: y, w: 535, h: 22,
             size: 10, bold: true, color: violet)
        y += 23
        let values = rows.isEmpty ? [("Unavailable", "No stored schedule")] : rows
        for (left, right) in values {
            if y > 695 {
                newTherapyPage(ctx, "Therapy Settings (continued)", range, &page, &y)
                text(title.uppercased() + " (CONTINUED)", x:38, y:y,
                     w:535, size:10, bold:true, color:violet)
                y += 23
            }
            fill(CGRect(x: 38, y: y, width: 536, height: 21),
                 color: UIColor(white: 0.972, alpha: 1))
            text(left, x: 45, y: y+2, w: 155, h: 17, size: 9, color: gray)
            text(right, x: 203, y: y+2, w: 360, h: 17, size: 9, bold: true)
            y += 23
        }
        y += 13
    }

    static func printSnapshot(_ snapshot: ClinicalSettingsSnapshot,
                              ctx: UIGraphicsPDFRendererContext, range: String,
                              page: inout Int, y: inout CGFloat) {
        newTherapyPage(ctx, "Insulin Therapy Settings", range, &page, &y)
        text(snapshot.label, x: 38, y: y, w: 536, h: 22,
             size: 11, bold: true, color: navy)
        y += 21
        text("Programmed schedule values; not a record of actual insulin delivered.",
             x: 38, y: y, w: 536, size: 9, color: gray)
        y += 27

        let icr: [(String,String)] = snapshot.icr?.items.map {
            (clock($0.startTime), String(format:"1 U per %.2f g", $0.value))
        } ?? []
        let icrZone = snapshot.icr?.timeZone.identifier ?? "Unknown"
        settingsRows(ctx, "Insulin-to-carb ratio (ICR)  •  " + icrZone,
                     rows:icr, range:range, page:&page, y:&y)

        let isf: [(String,String)] = snapshot.isf?.items.map { item in
            let unit = snapshot.isf!.unit
            let converted = HKQuantity(unit:unit, doubleValue:item.value)
                .doubleValue(for:.milligramsPerDeciliter)
            return (clock(item.startTime), String(format:"%.1f mg/dL per U",converted))
        } ?? []
        let isfZone = snapshot.isf?.timeZone.identifier ?? "Unknown"
        settingsRows(ctx, "Insulin sensitivity (ISF)  •  " + isfZone,
                     rows:isf, range:range, page:&page, y:&y)

        let basal: [(String,String)] = snapshot.basal?.items.map {
            (clock($0.startTime), String(format:"%.3f U/hour",$0.value))
        } ?? []
        let basalZone = snapshot.basal?.timeZone.identifier ?? "Unknown"
        settingsRows(ctx, "Programmed basal schedule  •  " + basalZone,
                     rows:basal, range:range, page:&page, y:&y)

        let targets: [(String,String)] = snapshot.target?.items.map { item in
            let unit = snapshot.target!.unit
            let low = HKQuantity(unit:unit, doubleValue:item.value.minValue)
                .doubleValue(for:.milligramsPerDeciliter)
            let high = HKQuantity(unit:unit, doubleValue:item.value.maxValue)
                .doubleValue(for:.milligramsPerDeciliter)
            return (clock(item.startTime), String(format:"%.0f–%.0f mg/dL",low,high))
        } ?? []
        let targetZone = snapshot.target?.timeZone.identifier ?? "Unknown"
        settingsRows(ctx, "Glucose target schedule  •  " + targetZone,
                     rows:targets, range:range, page:&page, y:&y)

        let threshold = snapshot.suspend.map {
            String(format:"%.0f mg/dL", $0.quantity.doubleValue(for:.milligramsPerDeciliter))
        } ?? "Not configured"
        settingsRows(ctx, "Limits, overrides & insulin model", rows: [
            ("Pre-meal target",describeRange(snapshot.preMeal)),
            ("Workout target",describeRange(snapshot.workout)),
            ("Suspend threshold",threshold),
            ("Maximum bolus", snapshot.maxBolus.map {
                String(format:"%.2f U",$0) } ?? "Not recorded"),
            ("Maximum basal rate", snapshot.maxBasal.map {
                String(format:"%.2f U/hour",$0) } ?? "Not recorded"),
            ("Insulin action model",snapshot.insulinModel)
        ],range:range,page:&page,y:&y)
    }

    static func changesBetween(_ previous: StoredSettings,
                               _ next: StoredSettings) -> [String] {
        var changed: [String] = []
        if previous.carbRatioSchedule != next.carbRatioSchedule { changed.append("ICR") }
        if previous.insulinSensitivitySchedule != next.insulinSensitivitySchedule { changed.append("ISF") }
        if previous.basalRateSchedule != next.basalRateSchedule { changed.append("Basal schedule") }
        if previous.glucoseTargetRangeSchedule != next.glucoseTargetRangeSchedule { changed.append("Targets") }
        if previous.preMealTargetRange != next.preMealTargetRange ||
           previous.workoutTargetRange != next.workoutTargetRange {
            changed.append("Target overrides")
        }
        if previous.maximumBolus != next.maximumBolus ||
           previous.maximumBasalRatePerHour != next.maximumBasalRatePerHour ||
           previous.suspendThreshold != next.suspendThreshold {
            changed.append("Limits / suspend")
        }
        if previous.dosingEnabled != next.dosingEnabled ||
           previous.automaticDosingStrategy != next.automaticDosingStrategy {
            changed.append("Dosing mode")
        }
        return changed
    }

    static func renderTherapySettings(ctx: UIGraphicsPDFRendererContext,
                                      current: TherapySettings,
                                      saved: [StoredSettings],
                                      start: Date, end: Date,
                                      range: String, page: inout Int) {
        var y: CGFloat = 132
        printSnapshot(fromCurrent(current), ctx:ctx, range:range,
                      page:&page, y:&y)

        let ordered = saved.filter { $0.date <= end }.sorted { $0.date < $1.date }
        let dateFormatter = DateFormatter()
        dateFormatter.dateStyle = .medium
        dateFormatter.timeStyle = .short

        // Never present current settings as if they were active in October.
        if let baseline = ordered.last(where: { $0.date <= start }) {
            let label = "LAST RECORDED BEFORE REPORT: " +
                dateFormatter.string(from:baseline.date)
            printSnapshot(fromSaved(baseline,label:label),
                          ctx:ctx,range:range,page:&page,y:&y)
        }

        let changes = ordered.filter { $0.date >= start && $0.date <= end }
        newTherapyPage(ctx, "Recorded Settings History", range, &page, &y)
        text("Based only on saved Loop SettingsStore records.",x:38,y:y,w:536,
             size:10,bold:true)
        y += 24
        text("No saved record means settings are unknown, not unchanged.",
             x:38,y:y,w:536,size:9,color:gray)
        y += 28
        if changes.isEmpty {
            settingsRows(ctx,"Changes during selected period",
                rows:[("No snapshots", "No settings changes could be verified")],
                range:range,page:&page,y:&y)
        } else {
            var prior = ordered.last(where: { $0.date < start })
            var changeRows: [(String,String)] = []
            for item in changes {
                let differences = prior.map { changesBetween($0,item) } ??
                    ["First snapshot in period"]
                if !differences.isEmpty {
                    changeRows.append((dateFormatter.string(from:item.date),
                                       differences.joined(separator:", ")))
                }
                prior = item
            }
            settingsRows(ctx,"Documented settings changes",
                         rows:changeRows.isEmpty ? [
                             ("No changes","No ICR, ISF, basal or target changes recorded")
                         ] : changeRows,
                         range:range,page:&page,y:&y)
        }

        if let latest = ordered.last(where: { $0.date >= start }) {
            let label = "LAST SAVED DURING REPORT: " +
                dateFormatter.string(from:latest.date)
            printSnapshot(fromSaved(latest,label:label),
                          ctx:ctx,range:range,page:&page,y:&y)
        } else {
            settingsRows(ctx,"Historical therapy settings",
                         rows:[("Unavailable","No new settings snapshots saved during this range")],
                         range:range,page:&page,y:&y)
        }
    }
}
'''

def install():
    content = VIEW.read_text(encoding="utf-8")
    if "private extension LoKeyClinicalPDFV2" in content:
        raise RuntimeError("Clinical settings tables already installed")
    if content.count('header("Pod Usage & Settings",range:headedRange,page:page)') != 1:
        raise RuntimeError("Expected exactly one V2 pod/settings page")

    start = content.find("            rule(385)\n", content.find('header("Pod Usage & Settings",range:headedRange,page:page)'))
    end = content.find("        }\n        let path = FileManager.default.temporaryDirectory", start)
    if start < 0 or end < 0:
        raise RuntimeError("V2 settings JSON block changed: refusing replacement")
    replacing = '''            rule(385)
            text("THERAPY SETTINGS",x:38,y:400,w:520,size:12,bold:true)
            text("ICR, ISF, programmed basal, glucose targets, limits and recorded",
                 x:38,y:430,w:535,size:10,color:gray)
            text("historical changes continue on dedicated, readable pages.",
                 x:38,y:447,w:535,size:10,color:gray)
'''
    content = content[:start] + replacing + content[end:]
    block = '''        }
        let path = FileManager.default.temporaryDirectory'''
    if content.count(block) != 1:
        raise RuntimeError("V2 PDF renderer closure anchor changed")
    content = content.replace(block, '''            renderTherapySettings(ctx:ctx, current:settings,
                                  saved:data.savedTherapySettings,
                                  start:start, end:end,
                                  range:headedRange, page:&page)
        }
        let path = FileManager.default.temporaryDirectory''', 1)
    # Helpers live in same Swift file as the V2 PDF generator, and only read settings.
    VIEW.write_text(content + HELPER, encoding="utf-8")
    print("PASS: complete current ICR/ISF/basal/targets and dated historical settings PDF tables")

if __name__ == "__main__":
    install()
