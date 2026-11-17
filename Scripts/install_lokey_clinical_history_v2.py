#!/usr/bin/env python3
"""Upgrade LoKey clinical reports with HealthKit history and correct basal groupings.

Only edits read-only display/report paths after the existing LoKey UI installers.
Does not change pump, Loop dosing, HealthKit writer or widget logic.
"""
from pathlib import Path
SETTINGS = Path("Loop/Loop/Views/SettingsView.swift")
STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")

def replace_one(source, before, after, label):
    n = source.count(before)
    if n != 1:
        raise RuntimeError(f"{label}: expected one exact anchor, found {n}")
    return source.replace(before, after, 1)

GENERATE = r'''    private func generate() {
        guard !preparing else { return }
        preparing = true
        errorMessage = nil
        let end = Date()
        let start = Calendar.current.date(byAdding: .day, value: -(days - 1),
                    to: Calendar.current.startOfDay(for: end))!
        let reportName = String(patientName.prefix(80))
        let currentSettings = viewModel.therapySettings()
        LoKeyClinicV2History.load(viewModel: viewModel, start: start, end: end) { data in
            DispatchQueue.global(qos: .utility).async {
                do {
                    let url = try LoKeyClinicalPDFV2.make(data: data,
                        pods: LoKeyPodLedger.read(), start: start, end: end,
                        settings: currentSettings, patientName: reportName)
                    DispatchQueue.main.async {
                        self.exportURL = url
                        self.preparing = false
                        self.showShare = true
                    }
                } catch {
                    DispatchQueue.main.async {
                        self.preparing = false
                        self.errorMessage = "Could not generate clinical PDF: " + error.localizedDescription
                    }
                }
            }
        }
    }'''

HELPERS = r'''
// MARK: - LoKey clinician history V2: local and Apple Health, never treatment data
private struct LoKeyClinicV2Data {
    let glucose: [StoredGlucoseSample]
    let doses: [DoseEntry]
    let carbs: [StoredCarbEntry]
    let externalInsulin: [HKQuantitySample]
    let notes: [String]
    let nativeGlucoseCount: Int
    let healthGlucoseCount: Int
    let nativeDoseCount: Int
    let healthDoseCount: Int
}

private enum LoKeyClinicV2History {
    private static let insulinMetadata = "com.loopkit.InsulinKit.MetadataKeyAutomaticallyIssued"
    private static let manualMetadata = "com.loopkit.InsulinKit.MetadataKeyManuallyEntered"

    // HealthKit is a read-only historical source. It is not used to calculate
    // insulin-on-board or change any active Loop pump/controller state.
    static func load(viewModel: SettingsViewModel, start: Date, end: Date,
                     completion: @escaping (LoKeyClinicV2Data) -> Void) {
        let group = DispatchGroup()
        let lock = NSLock()
        var nativeGlucose: [StoredGlucoseSample] = []
        var nativeDoses: [DoseEntry] = []
        var hkGlucose: [HKQuantitySample] = []
        var hkInsulin: [HKQuantitySample] = []
        var hkCarbs: [HKQuantitySample] = []
        var warnings: [String] = []

        if let loader = viewModel.loKeyLoadGlucose {
            group.enter()
            loader(start, end) { result in
                lock.lock()
                switch result {
                case .success(let readings): nativeGlucose = readings
                case .failure(let error): warnings.append("Local CGM history: " + error.localizedDescription)
                }
                lock.unlock()
                group.leave()
            }
        } else {
            warnings.append("Local glucose history unavailable")
        }
        if let loader = viewModel.loKeyLoadDoses {
            group.enter()
            loader(start, end) { result in
                lock.lock()
                switch result {
                case .success(let entries): nativeDoses = entries
                case .failure(let error): warnings.append("Local insulin history: " + error.localizedDescription)
                }
                lock.unlock()
                group.leave()
            }
        } else {
            warnings.append("Local insulin history unavailable")
        }

        if HKHealthStore.isHealthDataAvailable(),
           let g = HKObjectType.quantityType(forIdentifier: .bloodGlucose),
           let insulin = HKObjectType.quantityType(forIdentifier: .insulinDelivery),
           let carb = HKObjectType.quantityType(forIdentifier: .dietaryCarbohydrates) {
            let store = HKHealthStore()
            let types: Set<HKObjectType> = [g, insulin, carb]
            group.enter()
            store.requestAuthorization(toShare: [], read: types) { _, permissionError in
                if let permissionError {
                    lock.lock()
                    warnings.append("Apple Health permission: " + permissionError.localizedDescription)
                    lock.unlock()
                }
                // A successful HealthKit authorization call does not confirm
                // permission to read each type. Missing data stays unknown.
                func query(_ type: HKQuantityType, assign: @escaping ([HKQuantitySample]) -> Void) {
                    group.enter()
                    let predicate = HKQuery.predicateForSamples(
                        withStart: start, end: end, options: [])
                    let request = HKSampleQuery(sampleType: type, predicate: predicate,
                                                limit: HKObjectQueryNoLimit,
                                                sortDescriptors: nil) { _, rows, error in
                        lock.lock()
                        if let error {
                            warnings.append("Apple Health " + type.identifier + ": " + error.localizedDescription)
                        }
                        assign((rows ?? []).compactMap { $0 as? HKQuantitySample })
                        lock.unlock()
                        group.leave()
                    }
                    store.execute(request)
                }
                query(g) { hkGlucose = $0 }
                query(insulin) { hkInsulin = $0 }
                query(carb) { hkCarbs = $0 }
                group.leave()
            }
        } else {
            warnings.append("Apple Health unavailable; report uses only local Loop records")
        }

        group.notify(queue: .global(qos: .utility)) {
            // Combine sensor readings from native Loop + authorized HealthKit,
            // keeping one sample per local minute (prefer sensor over copy).
            var glucoseByMinute: [Int: StoredGlucoseSample] = [:]
            for value in nativeGlucose where !value.isDisplayOnly && !value.wasUserEntered {
                let key = Int(value.startDate.timeIntervalSince1970 / 60)
                glucoseByMinute[key] = value
            }
            let healthSensor = hkGlucose.filter { item in
                let source = item.sourceRevision.source.bundleIdentifier.lowercased()
                return source.contains("dexcom") || source.contains("loop") ||
                       source.contains("twiist") || source.contains("trio") ||
                       (item.metadata?["HasLoopKitOrigin"] as? Bool == true)
            }
            for item in healthSensor {
                let value = StoredGlucoseSample(sample: item)
                guard !value.isDisplayOnly && !value.wasUserEntered else { continue }
                let key = Int(value.startDate.timeIntervalSince1970 / 60)
                let source = item.sourceRevision.source.bundleIdentifier.lowercased()
                // Direct Dexcom source wins over loop-copied duplicate.
                if glucoseByMinute[key] == nil || source.contains("dexcom") {
                    glucoseByMinute[key] = value
                }
            }

            // Insulin samples written by the LoKey Loop app preserve original basal/bolus
            // and auto-bolus metadata. Other pump brands are separate and never
            // presented as native LoKey insulin or inferred as automated.
            var mergedDoses: [String: DoseEntry] = [:]
            func key(_ dose: DoseEntry) -> String {
                if let id = dose.syncIdentifier { return "sync:" + id }
                return "time:" + String(Int(dose.startDate.timeIntervalSince1970)) +
                    ":" + String(Int(dose.endDate.timeIntervalSince1970)) +
                    ":" + String(format: "%.3f", dose.unitsInDeliverableIncrements) +
                    ":" + String(describing: dose.type)
            }
            for sample in hkInsulin {
                // Both Twiist and LoKey write HasLoopKitOrigin. Only include
                // the ACTUAL LoKey writer in LoKey totals; this is essential
                // when old Twiist and Loop usage overlap in October.
                let source = sample.sourceRevision.source
                let fromLoKey = source.name == "LoKey T1D" ||
                    source.bundleIdentifier == "com.4MC7LCXJ5W.loopkit.Loop"
                guard fromLoKey,
                      sample.metadata?["HasLoopKitOrigin"] as? Bool == true,
                      let reasonRaw = sample.metadata?[HKMetadataKeyInsulinDeliveryReason] as? Int,
                      let reason = HKInsulinDeliveryReason(rawValue: reasonRaw) else { continue }
                let quantity = sample.quantity.doubleValue(for: .internationalUnit())
                guard quantity.isFinite && quantity > 0 && quantity < 300 else { continue }
                let type: DoseType = reason == .basal ? .basal : .bolus
                let dose = DoseEntry(type: type, startDate: sample.startDate,
                    endDate: sample.endDate, value: quantity, unit: .units,
                    deliveredUnits: quantity,
                    syncIdentifier: sample.metadata?[HKMetadataKeySyncIdentifier] as? String,
                    automatic: sample.metadata?[insulinMetadata] as? Bool,
                    manuallyEntered: sample.metadata?[manualMetadata] as? Bool ?? false)
                mergedDoses[key(dose)] = dose
            }
            let archivedCount = mergedDoses.count
            for dose in nativeDoses {
                mergedDoses[key(dose)] = dose  // prefer native Loop provenance
            }
            var loggedCarbs: [String: StoredCarbEntry] = [:]
            for sample in hkCarbs {
                let grams = sample.quantity.doubleValue(for: .gram())
                guard grams.isFinite && grams > 0 && grams < 1000 else { continue }
                let entry = StoredCarbEntry(startDate: sample.startDate, quantity: sample.quantity,
                    createdByCurrentApp: false)
                let key = String(Int(sample.startDate.timeIntervalSince1970 / 60)) +
                    ":" + String(Int(grams.rounded()))
                loggedCarbs[key] = entry
            }
            let outsiders = hkInsulin.filter {
                let source = $0.sourceRevision.source
                return source.name != "LoKey T1D" &&
                    source.bundleIdentifier != "com.4MC7LCXJ5W.loopkit.Loop"
            }
            var status = warnings
            if healthSensor.isEmpty && nativeGlucose.isEmpty {
                status.append("No CGM readings were available or permitted in this period")
            }
            if archivedCount == 0 && nativeDoses.isEmpty {
                status.append("No Loop insulin records were available or permitted")
            }
            if !outsiders.isEmpty {
                status.append("Other-pump Health insulin appears separately; it is not included in LoKey totals")
            }
            completion(LoKeyClinicV2Data(
                glucose: glucoseByMinute.values.sorted { $0.startDate < $1.startDate },
                doses: mergedDoses.values.sorted { $0.startDate < $1.startDate },
                carbs: loggedCarbs.values.sorted { $0.startDate < $1.startDate },
                externalInsulin: outsiders, notes: status,
                nativeGlucoseCount: nativeGlucose.count,
                healthGlucoseCount: healthSensor.count,
                nativeDoseCount: nativeDoses.count, healthDoseCount: archivedCount))
        }
    }
}
'''

def install():
    view = SETTINGS.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    index = view.find("private struct LoKeyClinicalReportView: View {")
    first = view.find("    private func generate() {", index)
    last = view.find("\n    }\n}\n\nprivate enum LoKeyClinicalPDF {", first)
    if index < 0 or first < 0 or last < first or view.count("private enum LoKeyClinicalPDF {") != 1:
        raise RuntimeError("Existing LoKey clinical report generator changed; refusing replacement")
    new_view = view[:first] + GENERATE + view[last+len("\n    }"):]
    new_view = replace_one(new_view,
        "private enum LoKeyClinicalPDF {",
        HELPERS + "\nprivate enum LoKeyClinicalPDF {",
        "separate historical Health reader")

    old = 'Text("Clinical-style PDF with AGP percentiles, glucose distribution, daily delivered insulin, automated vs user-initiated boluses, recorded pod changes, and current therapy settings.")'
    new = 'Text("Glooko-familiar clinical PDF with CGM AGP, daily glucose and insulin charts, carb entries, basal plus automated bolus totals, pod history and settings. Apple Health access may be requested for older readings.")'
    new_view = replace_one(new_view, old, new, "daily-graph explanation")
    new_view = replace_one(new_view,
        'doseLine("Basal", daily.basal)',
        'doseLine("Total basal (basal + Loop auto)", daily.basal + daily.automated)\n'
        '                                    doseLine("Pump basal component", daily.basal)',
        "insulin history combined basal")
    new_view = replace_one(new_view,
        'doseLine("Automatic boluses", daily.automated)',
        'doseLine("Loop automated (included in basal)", daily.automated)',
        "automated boluses visibly allocated inside basal")
    new_view = replace_one(new_view,
        'doseLine("You initiated", daily.initiated)',
        'doseLine("Your boluses", daily.initiated)',
        "user bolus explicit name")

    status = replace_one(status,
        'todayTile("BASAL", value: todayBasalValue',
        'todayTile("TOTAL BASAL*", value: todayBasalValue',
        "combined basal tile")
    status = replace_one(status,
        'todayTile("BOLUSES", value: todayBolusValue',
        'todayTile("YOUR BOLUSES", value: todayBolusValue',
        "non-automatic bolus tile")
    status = replace_one(status,
        'self.loKeyDailyBasal = String(format: "%.2f U", basalUnits)',
        'self.loKeyDailyBasal = String(format: "%.2f U", basalUnits + automaticBolusUnits)',
        "basal plus automation")
    status = replace_one(status,
        'self.loKeyDailyBolus = String(format: "%.2f U", bolusUnits)',
        'self.loKeyDailyBolus = String(format: "%.2f U", initiatedBolusUnits)',
        "user-only bolus tile without unknown-origin doses")
    status = replace_one(status,
        'note.text = "Pump-delivered entries shown above; unverified manual logs excluded from totals. In-progress delivery may be estimated."',
        'note.text = "*Total Basal = delivered pump basal + automated Loop boluses. Your Boluses = only user-initiated boluses. Origin unknown is separate; all recorded pump insulin is included once in Total Today."',
        "insulin chart explanatory footnote")

    # All source changes are validated before any writes.
    SETTINGS.write_text(new_view, encoding="utf-8")
    STATUS.write_text(status, encoding="utf-8")
    print("PASS: historical Apple Health reader and user-defined total basal grouping installed")

if __name__ == "__main__":
    install()
