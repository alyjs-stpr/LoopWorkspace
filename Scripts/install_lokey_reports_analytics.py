#!/usr/bin/env python3
"""Install the LoKey appointment reports and pod usage ledger after existing UI patches.

Read-only data access: DoseStore, GlucoseStore, existing Omnipod HUD metadata.
Writes only local user-initiated pod ledger entries and exported PDF files.
Never interacts with pump delivery commands, CGM communications or Loop algorithms.
"""
from pathlib import Path

SETTINGS = Path("Loop/Loop/Views/SettingsView.swift")
MODEL = Path("Loop/Loop/View Models/SettingsViewModel.swift")
STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")

def replace_once(text, before, after, label):
    count = text.count(before)
    if count != 1:
        raise RuntimeError(f"{label}: expected one installation anchor; found {count}")
    return text.replace(before, after, 1)

def install():
    model = MODEL.read_text()
    old = '    var loKeyLoadSettingsHistory: ((Date, Date, @escaping (Swift.Result<[StoredSettings], Error>) -> Void) -> Void)?'
    new = old + '''
    // Read-only sources for clinical reporting. Not dosing APIs.
    var loKeyLoadDoses: ((Date, Date, @escaping (Swift.Result<[DoseEntry], Error>) -> Void) -> Void)?
    var loKeyCurrentPodSnapshot: (() -> [String: Any])?
'''
    model = replace_once(model, old, new, "SettingsViewModel report sources")
    MODEL.write_text(model)

    status = STATUS.read_text()
    anchor = '        viewModel.loKeyLoadSettingsHistory = { [weak self] start, end, completion in'
    extra = '''        viewModel.loKeyLoadDoses = { [weak self] start, end, completion in
            guard let self = self else {
                completion(.failure(NSError(domain: "LoKeyReports", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Insulin history source unavailable"])))
                return
            }
            self.deviceManager.doseStore.getNormalizedDoseEntries(start: start, end: end) { result in
                switch result {
                case .success(let doses): completion(.success(doses))
                case .failure(let error): completion(.failure(error))
                }
            }
        }
        viewModel.loKeyCurrentPodSnapshot = { [weak self] in
            self?.deviceManager.pumpManagerHUDProvider?.hudViewRawState ?? [:]
        }
'''
    status = replace_once(status, anchor, extra + anchor, "Settings host report sources")
    # The normal dashboard is visited far more often than Pod History.
    # Capture newly observed pod activations here without controlling the pump.
    refresh_anchor = '    private func loKeyRefreshHeader() {'
    capture = '''    private func loKeyRefreshHeader() {
        // Purely historical bookkeeping, independent from Loop's insulin algorithm.
        let podStart = deviceManager.pumpManagerHUDProvider?.hudViewRawState["podActivatedAt"] as? Date
        LoKeyPodLedger.reconcile(podActivatedAt: podStart)'''
    status = replace_once(status, refresh_anchor, capture, "Dashboard pod activation ledger")
    STATUS.write_text(status)

    settings = SETTINGS.read_text()
    original = '''                NavigationLink(destination: LoKeyReportsView(viewModel: viewModel)) {
                    Label("Glucose reports & settings PDF", systemImage: "chart.pie")
                }'''
    replacement = '''                NavigationLink(destination: LoKeyReportsHubView(viewModel: viewModel)) {
                    Label("Reports & Analytics", systemImage: "chart.bar.xaxis")
                }'''
    settings = replace_once(settings, original, replacement, "LoKey Reports & Analytics navigation")
    if "private struct LoKeyReportsHubView: View {" in settings:
        raise RuntimeError("Reports & Analytics is already installed")
    if "import UIKit" not in settings:
        settings = "import UIKit\n" + settings
    SETTINGS.write_text(settings + SWIFT_SOURCE)
    print("PASS: installed reports hub, daily insulin history, pod ledger and clinician PDF; no dosing changes")

SWIFT_SOURCE = r'''

// MARK: - LoKey clinical reporting and pod usage: read-only pump history

private struct LoKeyDoseTotals {
    var basal = 0.0
    var automated = 0.0
    var initiated = 0.0
    var unclassified = 0.0
    var logged = 0.0
    var count = 0

    var bolus: Double { automated + initiated + unclassified }
    var delivered: Double { basal + bolus }

    mutating func add(_ dose: DoseEntry, from start: Date, to end: Date) {
        guard dose.endDate >= start && dose.startDate <= end else { return }
        let value = dose.trimmed(from: start, to: end).unitsInDeliverableIncrements
        guard value.isFinite, value >= 0 else { return }
        switch dose.type {
        case .basal, .tempBasal:
            basal += value
            count += 1
        case .bolus:
            if dose.manuallyEntered {
                logged += value
            } else if dose.automatic == true {
                automated += value
                count += 1
            } else if dose.automatic == false || dose.wasProgrammedByPumpUI {
                initiated += value
                count += 1
            } else {
                unclassified += value
                count += 1
            }
        case .suspend, .resume: break
        }
    }

    static func sum(_ doses: [DoseEntry], from start: Date, to end: Date) -> LoKeyDoseTotals {
        var result = LoKeyDoseTotals()
        for dose in doses { result.add(dose, from: start, to: end) }
        return result
    }
}

struct LoKeyPodRecord: Codable, Identifiable {
    var id: String
    var activatedAt: Date
    var endedAt: Date?
    var endInferred: Bool
    var fillUnits: Double?
    var changeReason: String

    var wearHours: Double? {
        guard let end = endedAt else { return nil }
        return max(0, end.timeIntervalSince(activatedAt) / 3600)
    }
}

enum LoKeyPodLedger {
    static let key = "LoKeyPodUsageLedgerV1"
    static let pendingFillKey = "LoKeyNextPodPlannedFillV1"
    static let reasons = ["Unrecorded", "Routine", "Suspected leak", "Pod failure", "Empty reservoir", "Adhesion / site", "Other"]

    static func read() -> [LoKeyPodRecord] {
        guard let data = UserDefaults.standard.data(forKey: key),
              let records = try? JSONDecoder().decode([LoKeyPodRecord].self, from: data)
        else { return [] }
        return records
    }

    static func store(_ entries: [LoKeyPodRecord]) {
        guard let data = try? JSONEncoder().encode(Array(entries.suffix(200))) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    @discardableResult static func reconcile(podActivatedAt: Date?) -> [LoKeyPodRecord] {
        var records = read()
        guard let start = podActivatedAt, start <= Date().addingTimeInterval(300) else { return records }
        let identifier = String(Int(start.timeIntervalSince1970))
        guard !records.contains(where: { $0.id == identifier }) else { return records }
        for index in records.indices where records[index].endedAt == nil &&
            records[index].activatedAt < start {
            records[index].endedAt = start
            records[index].endInferred = true
        }
        let planned = UserDefaults.standard.object(forKey: pendingFillKey) as? Double
        let acceptedFill = planned.flatMap { (85...200).contains($0) ? $0 : nil }
        records.append(LoKeyPodRecord(id: identifier, activatedAt: start,
            endedAt: nil, endInferred: false, fillUnits: acceptedFill, changeReason: "Unrecorded"))
        if acceptedFill != nil {
            UserDefaults.standard.removeObject(forKey: pendingFillKey)
        }
        store(records)
        return records
    }
}

private struct LoKeyReportsHubView: View {
    @ObservedObject var viewModel: SettingsViewModel

    var body: some View {
        Form {
            Section(header: Text("Appointment Report")) {
                NavigationLink(destination: LoKeyClinicalReportView(viewModel: viewModel)) {
                    Label("Endocrinologist PDF", systemImage: "doc.richtext")
                }
                Text("AGP-style glucose profile, CGM statistics, daily insulin breakdown, pod history and current therapy settings.")
                    .font(.footnote).foregroundColor(.secondary)
            }
            Section(header: Text("Explore My History")) {
                NavigationLink(destination: LoKeyInsulinHistoryView(viewModel: viewModel)) {
                    Label("Daily Insulin History", systemImage: "chart.bar")
                }
                NavigationLink(destination: LoKeyPodUsageView(viewModel: viewModel)) {
                    Label("Pod Fill & Change History", systemImage: "calendar.badge.clock")
                }
                NavigationLink(destination: LoKeyReportsView(viewModel: viewModel)) {
                    Label("Glucose and Loop Target Reports", systemImage: "waveform.path.ecg")
                }
            }
            Section {
                Text("Reporting never changes pump settings, insulin delivery, or glucose alerts. Missing data is labeled rather than estimated as zero.")
                    .font(.footnote).foregroundColor(.secondary)
            }
        }
        .navigationTitle("Reports & Analytics")
    }
}

// Supports Loop's minimum iOS 15.1 target; SwiftUI LabeledContent requires iOS 16.
private struct LoKeyMetricLine: View {
    let title: String
    let value: String
    init(_ title: String, value: String) {
        self.title = title
        self.value = value
    }
    var body: some View {
        HStack {
            Text(title).font(.subheadline)
            Spacer(minLength: 8)
            Text(value).font(.subheadline).monospacedDigit()
        }
    }
}

private struct LoKeyInsulinHistoryView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var selectedDays = 14
    @State private var doses: [DoseEntry]?
    @State private var errorMessage: String?
    private let calendar = Calendar.current

    var body: some View {
        List {
            Section {
                Picker("History period", selection: $selectedDays) {
                    Text("7 days").tag(7)
                    Text("14 days").tag(14)
                    Text("30 days").tag(30)
                    Text("90 days").tag(90)
                }
                .onChange(of: selectedDays) { _ in reload() }
            }
            if let errorMessage {
                Text(errorMessage).foregroundColor(.red)
            } else if let doses {
                if doses.isEmpty {
                    Text("No insulin history was returned. This does not mean zero insulin was delivered.")
                        .foregroundColor(.secondary)
                } else {
                    Section(header: Text("Recorded Insulin by Day")) {
                        ForEach(0..<selectedDays, id: \.self) { offset in
                            let start = calendar.date(byAdding: .day, value: -offset,
                                to: calendar.startOfDay(for: Date()))!
                            let end = min(Date(), calendar.date(byAdding: .day, value: 1, to: start)!)
                            let daily = LoKeyDoseTotals.sum(doses, from: start, to: end)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(start, style: .date).font(.headline)
                                if daily.count == 0 {
                                    Text("No confirmed delivery entries in available history")
                                        .foregroundColor(.secondary).font(.caption)
                                } else {
                                    HStack {
                                        Text("Delivered total")
                                        Spacer()
                                        Text(String(format: "%.2f U", daily.delivered)).bold()
                                    }
                                    doseLine("Basal", daily.basal)
                                    doseLine("Automatic boluses", daily.automated)
                                    doseLine("You initiated", daily.initiated)
                                    doseLine("Origin unknown", daily.unclassified)
                                    if daily.logged > 0 { doseLine("Logged, not verified", daily.logged) }
                                }
                            }
                            .padding(.vertical, 5)
                        }
                    }
                }
            } else {
                ProgressView("Loading insulin delivery history…")
            }
            Section {
                Text("Pump delivery is not the same as insulin absorption when a pod leaks. Logged manual injections are not added to pump-delivered totals.")
                    .font(.footnote).foregroundColor(.secondary)
            }
        }
        .navigationTitle("Insulin History")
        .onAppear(perform: reload)
    }

    private func doseLine(_ label: String, _ amount: Double) -> some View {
        HStack {
            Text(label).foregroundColor(.secondary).font(.subheadline)
            Spacer()
            Text(String(format: "%.2f U", amount)).monospacedDigit().font(.subheadline)
        }
    }

    private func reload() {
        doses = nil
        errorMessage = nil
        guard let load = viewModel.loKeyLoadDoses else {
            errorMessage = "Insulin delivery history is unavailable in this build."
            return
        }
        let start = calendar.date(byAdding: .day, value: -(selectedDays - 1),
            to: calendar.startOfDay(for: Date()))!
        load(start, Date()) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let entries): doses = entries
                case .failure(let error): errorMessage = error.localizedDescription
                }
            }
        }
    }
}

private struct LoKeyPodUsageView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var pods: [LoKeyPodRecord] = []
    @State private var doses: [DoseEntry]?
    @State private var doseError: String?
    @State private var fillUnits = 110.0
    @State private var nextFillUnits = 110.0
    @State private var nextFillSaved = false
    @State private var changeReason = "Unrecorded"
    @State private var snapshot: [String: Any] = [:]
    private let setupEstimate = 3.1

    var body: some View {
        List {
            Section(header: Text("Before Activating Your Next Pod")) {
                Stepper(value: $nextFillUnits, in: 85...200, step: 1) {
                    Text("Planned insulin fill: \(Int(nextFillUnits)) U")
                }
                Button("Save Planned Fill for Next Pod") {
                    UserDefaults.standard.set(nextFillUnits, forKey: LoKeyPodLedger.pendingFillKey)
                    nextFillSaved = true
                }
                if nextFillSaved {
                    Text("Saved. This amount will be linked to the next newly detected pod activation.")
                        .font(.caption).foregroundColor(.secondary)
                }
                Text("Use the normal Loop/Omnipod pairing procedure. This screen does not send any pump command.")
                    .font(.caption).foregroundColor(.secondary)
            }
            Section(header: Text("Current Pod")) {
                if let current = pods.first(where: { $0.endedAt == nil }) {
                    HStack {
                        Text("Activated")
                        Spacer()
                        Text(current.activatedAt, style: .date)
                    }
                    if let fill = current.fillUnits {
                        LoKeyMetricLine("Recorded fill", value: String(format: "%.0f U", fill))
                    } else {
                        Text("No fill amount recorded yet").foregroundColor(.secondary)
                    }
                    Stepper(value: $fillUnits, in: 85...200, step: 1) {
                        Text("Insulin put in pod: \(Int(fillUnits)) U")
                    }
                    Button("Save Fill Amount") { saveFill(id: current.id) }
                    if let delivered = totalForPod(current) {
                        LoKeyMetricLine("Pump-reported delivery", value: String(format: "%.1f U", delivered))
                        if let filled = current.fillUnits {
                            LoKeyMetricLine("Estimated unused insulin",
                                value: String(format: "%.1f U", max(0, filled - setupEstimate - delivered)))
                        }
                    }
                    if let raw = snapshot["reservoirLevel"] as? Double {
                        Text(raw > 50 ? "Pod reservoir: 50+ U (not an exact reading)" :
                            String(format: "Pod reservoir: %.1f U (hardware reported)", raw))
                            .font(.footnote).foregroundColor(.secondary)
                    }
                    Picker("Reason for change", selection: $changeReason) {
                        ForEach(LoKeyPodLedger.reasons, id: \.self) { Text($0).tag($0) }
                    }
                    Button("Record Pod Removal") { finishPod(id: current.id) }
                    Text("Record removal only when the pod is actually removed. This does not deactivate, pair, or change any pod.")
                        .font(.caption).foregroundColor(.secondary)
                } else {
                    Text("No current pod activation found. Open this page after the next pod is activated.")
                        .foregroundColor(.secondary)
                }
            }
            Section(header: Text("Pod Usage Averages")) {
                let completed = pods.filter { $0.endedAt != nil }
                let completedHours = completed.compactMap(\.wearHours)
                if completedHours.isEmpty {
                    Text("Averages will appear after pod removals have been recorded.")
                        .foregroundColor(.secondary)
                } else {
                    let averageHours = completedHours.reduce(0, +) / Double(completedHours.count)
                    LoKeyMetricLine("Average pod wear time", value: String(format: "%.1f h (%.2f days)",
                        averageHours, averageHours / 24))
                    let confirmed = completed.compactMap { pod -> Double? in totalForPod(pod) }
                    if !confirmed.isEmpty {
                        LoKeyMetricLine("Average pump-reported insulin per pod",
                            value: String(format: "%.1f U", confirmed.reduce(0, +) / Double(confirmed.count)))
                    } else {
                        Text("Insulin-per-pod average unavailable until delivery history is recorded.")
                            .font(.caption).foregroundColor(.secondary)
                    }
                    let estimatedUnused = completed.compactMap { pod -> Double? in
                        guard let fill = pod.fillUnits, let used = totalForPod(pod) else { return nil }
                        return max(0, fill - setupEstimate - used)
                    }
                    if !estimatedUnused.isEmpty {
                        LoKeyMetricLine("Average estimated unused insulin",
                            value: String(format: "%.1f U", estimatedUnused.reduce(0, +) / Double(estimatedUnused.count)))
                    }
                    let leaking = completed.filter { $0.changeReason == "Suspected leak" }
                    let leakHours = leaking.compactMap(\.wearHours)
                    if !leakHours.isEmpty {
                        LoKeyMetricLine("Average wear until suspected leak",
                            value: String(format: "%.1f h", leakHours.reduce(0, +) / Double(leakHours.count)))
                    }
                    Text("Averages use only recorded completed pods. Unknown fill volumes and missing delivery data are excluded from their respective insulin averages.")
                        .font(.caption).foregroundColor(.secondary)
                }
            }
            Section(header: Text("Pod Usage History")) {
                ForEach(pods.sorted(by: { $0.activatedAt > $1.activatedAt })) { pod in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack {
                            Text(pod.activatedAt, style: .date).font(.headline)
                            Spacer()
                            Text(pod.changeReason).font(.caption).foregroundColor(.secondary)
                        }
                        Menu {
                            ForEach(LoKeyPodLedger.reasons, id: \.self) { reason in
                                Button(reason) { updateReason(id: pod.id, reason: reason) }
                            }
                        } label: {
                            Label("Edit change reason", systemImage: "square.and.pencil")
                                .font(.caption)
                        }
                        if let hours = pod.wearHours {
                            Text(String(format: "Worn %.1f hours%@", hours,
                                pod.endInferred ? " (end inferred from next activation)" : ""))
                                .font(.subheadline)
                        } else {
                            Text("Currently active / end not recorded").font(.subheadline)
                        }
                        if let fill = pod.fillUnits {
                            Text(String(format: "Filled %.0f U", fill)).font(.subheadline)
                        } else {
                            Text("Fill amount unknown").font(.subheadline).foregroundColor(.secondary)
                        }
                        if let total = totalForPod(pod) {
                            Text(String(format: "Pump-reported delivery %.1f U", total)).font(.subheadline)
                        } else {
                            Text("Delivery history unavailable").font(.subheadline).foregroundColor(.secondary)
                        }
                    }.padding(.vertical, 4)
                }
                if pods.isEmpty {
                    Text("Pod history begins when this feature first sees a pod activation. Earlier changes cannot be reconstructed reliably from the current pod status.")
                        .foregroundColor(.secondary)
                }
            }
            if let doseError {
                Text("Dose history error: " + doseError).foregroundColor(.red).font(.caption)
            }
            Section {
                Text("Above 50 U, Omnipod provides only a 50+ reservoir reading. The remaining amount calculated from your entered fill and recorded delivery is an estimate, not a sensor reading or a safe automatic fill recommendation. Setup insulin is estimated at 3.1 U.")
                    .font(.footnote).foregroundColor(.secondary)
            }
        }
        .navigationTitle("Pod Fill & History")
        .onAppear(perform: reload)
    }

    private func totalForPod(_ pod: LoKeyPodRecord) -> Double? {
        guard let doses, !doses.isEmpty else { return nil }
        let cutoff = pod.endedAt ?? Date()
        let summary = LoKeyDoseTotals.sum(doses, from: pod.activatedAt, to: cutoff)
        return summary.count > 0 ? summary.delivered : nil
    }

    private func saveFill(id: String) {
        guard (85...200).contains(fillUnits) else { return }
        var copy = pods
        guard let index = copy.firstIndex(where: { $0.id == id }) else { return }
        copy[index].fillUnits = fillUnits
        LoKeyPodLedger.store(copy)
        pods = copy
    }

    private func updateReason(id: String, reason: String) {
        var copy = pods
        guard let index = copy.firstIndex(where: { $0.id == id }),
              LoKeyPodLedger.reasons.contains(reason) else { return }
        copy[index].changeReason = reason
        LoKeyPodLedger.store(copy)
        pods = copy
    }

    private func finishPod(id: String) {
        var copy = pods
        guard let index = copy.firstIndex(where: { $0.id == id }) else { return }
        copy[index].endedAt = Date()
        copy[index].endInferred = false
        copy[index].changeReason = changeReason
        LoKeyPodLedger.store(copy)
        pods = copy
    }

    private func reload() {
        if let pending = UserDefaults.standard.object(forKey: LoKeyPodLedger.pendingFillKey) as? Double,
           (85...200).contains(pending) {
            nextFillUnits = pending
            nextFillSaved = true
        }
        snapshot = viewModel.loKeyCurrentPodSnapshot?() ?? [:]
        let started = snapshot["podActivatedAt"] as? Date
        pods = LoKeyPodLedger.reconcile(podActivatedAt: started)
        if let current = pods.first(where: { $0.endedAt == nil }), let fill = current.fillUnits {
            fillUnits = fill
        }
        doses = nil
        doseError = nil
        guard let load = viewModel.loKeyLoadDoses else {
            doseError = "Insulin history source unavailable"
            return
        }
        let oldest = pods.map(\.activatedAt).min() ?? Date().addingTimeInterval(-90*86400)
        let start = max(oldest, Date().addingTimeInterval(-90*86400))
        load(start, Date()) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let entries): doses = entries
                case .failure(let error): doseError = error.localizedDescription
                }
            }
        }
    }
}

private struct LoKeyClinicalReportView: View {
    @ObservedObject var viewModel: SettingsViewModel
    @State private var days = 14
    @State private var preparing = false
    @State private var exportURL: URL?
    @State private var showShare = false
    @State private var errorMessage: String?
    @AppStorage("LoKeyClinicalReportPatientNameV1") private var patientName = ""

    var body: some View {
        Form {
            Section(header: Text("Endocrinologist Report")) {
                Picker("Report period", selection: $days) {
                    Text("7 days").tag(7)
                    Text("14 days").tag(14)
                    Text("30 days").tag(30)
                    Text("90 days").tag(90)
                }.pickerStyle(.menu)
                TextField("Patient name (optional)", text: $patientName)
                    .textContentType(.name)
                Text("Clinical-style PDF with AGP percentiles, glucose distribution, daily delivered insulin, automated vs user-initiated boluses, recorded pod changes, and current therapy settings.")
                    .font(.footnote).foregroundColor(.secondary)
                Button(preparing ? "Preparing report…" : "Generate PDF") { generate() }
                    .disabled(preparing)
                if preparing { ProgressView("Preparing report locally…") }
                if let errorMessage { Text(errorMessage).foregroundColor(.red).font(.footnote) }
            }
            Section {
                Text("Uses available on-device records. Missing data and uncertain pod history are explicitly labeled. Report generation is local, read-only and never changes insulin delivery. Verify the PDF before sharing it with your endocrinologist.")
                    .font(.footnote).foregroundColor(.secondary)
            }
        }
        .navigationTitle("Endocrinologist PDF")
        .sheet(isPresented: $showShare) {
            if let exportURL { LoKeyReportShareSheet(items: [exportURL]) }
        }
    }

    private func generate() {
        guard let glucoseLoader = viewModel.loKeyLoadGlucose,
              let doseLoader = viewModel.loKeyLoadDoses else {
            errorMessage = "A required history source is unavailable."
            return
        }
        preparing = true
        errorMessage = nil
        let end = Date()
        let start = Calendar.current.date(byAdding: .day, value: -(days - 1),
                    to: Calendar.current.startOfDay(for: end))!
        let reportName = String(patientName.prefix(80))
        glucoseLoader(start, end) { glucoseResult in
            doseLoader(start, end) { doseResult in
                switch (glucoseResult, doseResult) {
                case (.success(let glucose), .success(let doses)):
                    let pods = LoKeyPodLedger.read()
                    let snapshot = viewModel.therapySettings()
                    DispatchQueue.global(qos: .utility).async {
                        do {
                            let url = try LoKeyClinicalPDF.make(glucose: glucose, doses: doses,
                                pods: pods, start: start, end: end, settings: snapshot,
                                patientName: reportName)
                            DispatchQueue.main.async {
                                self.exportURL = url
                                self.preparing = false
                                self.showShare = true
                            }
                        } catch {
                            DispatchQueue.main.async {
                                self.errorMessage = "PDF generation failed: " + error.localizedDescription
                                self.preparing = false
                            }
                        }
                    }
                case (.failure(let error), _), (_, .failure(let error)):
                    DispatchQueue.main.async {
                        self.errorMessage = "Could not read report data: " + error.localizedDescription
                        self.preparing = false
                    }
                }
            }
        }
    }
}

private enum LoKeyClinicalPDF {
    private static let accent = UIColor(red: 0.44, green: 0.20, blue: 0.78, alpha: 1)
    private static let ink = UIColor(white: 0.16, alpha: 1)
    private static let gray = UIColor(white: 0.40, alpha: 1)
    private static let W: CGFloat = 612
    private static let H: CGFloat = 792

    private static func draw(_ value: String, x: CGFloat, y: CGFloat,
                             w: CGFloat, h: CGFloat = 21, size: CGFloat = 10,
                             bold: Bool = false, color: UIColor = ink) {
        let attrs: [NSAttributedString.Key: Any] = [
            .font: bold ? UIFont.boldSystemFont(ofSize: size) : UIFont.systemFont(ofSize: size),
            .foregroundColor: color,
        ]
        (value as NSString).draw(in: CGRect(x: x, y: y, width: w, height: h), withAttributes: attrs)
    }

    private static func separator(_ y: CGFloat) {
        let path = UIBezierPath()
        path.move(to: CGPoint(x: 37, y: y))
        path.addLine(to: CGPoint(x: 575, y: y))
        UIColor(white: 0.86, alpha: 1).setStroke()
        path.lineWidth = 0.7
        path.stroke()
    }

    private static func header(_ title: String, range: String, page: Int) {
        draw("LoKey T1D", x: 38, y: 25, w: 280, size: 23, bold: true, color: accent)
        draw("CLINICAL REPORT", x: 425, y: 33, w: 150, size: 10, bold: true, color: gray)
        separator(60)
        draw(title, x: 38, y: 76, w: 530, size: 18, bold: true)
        draw(range, x: 38, y: 105, w: 530, size: 10, color: gray)
        separator(742)
        draw("Generated by LoKey Loop • Read-only historical report", x: 38, y: 751, w: 450, size: 9, color: gray)
        draw("Page \(page)", x: 520, y: 751, w: 55, size: 9, color: gray)
    }

    private static func pct(_ values: [Double], _ p: Double) -> Double {
        guard !values.isEmpty else { return 0 }
        let s = values.sorted()
        let index = Double(s.count - 1) * p
        let lo = Int(floor(index)), hi = Int(ceil(index))
        let fraction = index - Double(lo)
        return s[lo] + (s[hi] - s[lo]) * fraction
    }

    private static func yPoint(_ glucose: Double, rect: CGRect) -> CGFloat {
        let clamped = min(350, max(40, glucose))
        return rect.maxY - CGFloat((clamped - 40) / 310) * rect.height
    }

    private static func agp(_ readings: [(Date, Double)], rect: CGRect) {
        let grid = UIBezierPath(rect: rect)
        UIColor(white: 0.94, alpha: 1).setStroke()
        grid.lineWidth = 1
        grid.stroke()
        let inRange = CGRect(x: rect.minX, y: yPoint(180, rect: rect),
                             width: rect.width, height: yPoint(70, rect: rect) - yPoint(180, rect: rect))
        UIColor(red: 0.90, green: 0.97, blue: 0.92, alpha: 1).setFill()
        UIBezierPath(rect: inRange).fill()
        for mark in [70.0, 180.0, 250.0] {
            let y = yPoint(mark, rect: rect)
            let path = UIBezierPath()
            path.move(to: CGPoint(x: rect.minX, y: y))
            path.addLine(to: CGPoint(x: rect.maxX, y: y))
            UIColor(white: 0.82, alpha: 1).setStroke()
            path.lineWidth = 0.6
            path.stroke()
        }
        let hours = (0..<24).map { hour in
            readings.filter { Calendar.current.component(.hour, from: $0.0) == hour }.map { $0.1 }
        }
        let x: (Int) -> CGFloat = { rect.minX + (CGFloat($0) + 0.5) * rect.width / 24 }
        for i in 0..<23 where hours[i].count >= 4 && hours[i+1].count >= 4 {
            let band = UIBezierPath()
            band.move(to: CGPoint(x: x(i), y: yPoint(pct(hours[i], 0.25), rect: rect)))
            band.addLine(to: CGPoint(x: x(i+1), y: yPoint(pct(hours[i+1], 0.25), rect: rect)))
            band.addLine(to: CGPoint(x: x(i+1), y: yPoint(pct(hours[i+1], 0.75), rect: rect)))
            band.addLine(to: CGPoint(x: x(i), y: yPoint(pct(hours[i], 0.75), rect: rect)))
            band.close()
            accent.withAlphaComponent(0.2).setFill()
            band.fill()
            let line = UIBezierPath()
            line.move(to: CGPoint(x: x(i), y: yPoint(pct(hours[i], 0.5), rect: rect)))
            line.addLine(to: CGPoint(x: x(i+1), y: yPoint(pct(hours[i+1], 0.5), rect: rect)))
            accent.setStroke()
            line.lineWidth = 2.0
            line.stroke()
        }
        draw("12 AM", x: rect.minX, y: rect.maxY+4, w: 60, size: 9, color: gray)
        draw("6 AM", x: rect.minX + rect.width*0.25-15, y: rect.maxY+4, w: 60, size: 9, color: gray)
        draw("NOON", x: rect.midX-15, y: rect.maxY+4, w: 60, size: 9, color: gray)
        draw("6 PM", x: rect.minX + rect.width*0.75-15, y: rect.maxY+4, w: 60, size: 9, color: gray)
    }

    static func make(glucose: [StoredGlucoseSample], doses: [DoseEntry],
                     pods: [LoKeyPodRecord], start: Date, end: Date,
                     settings: TherapySettings, patientName: String) throws -> URL {
        let fmt = DateFormatter()
        fmt.dateStyle = .medium
        let baseRange = fmt.string(from: start) + " – " + fmt.string(from: end)
        let normalizedName = patientName.trimmingCharacters(in: .whitespacesAndNewlines)
        let range = normalizedName.isEmpty ? baseRange : "Patient: " + normalizedName + "  |  " + baseRange
        // Match the existing LoKey TIR report: exclude display-only and manual
        // readings, credit each real sensor measurement for at most five minutes.
        // Duplicate timestamps and CGM gaps never fabricate monitoring time.
        let raw = glucose.compactMap { sample -> (Date, Double)? in
            let value = sample.quantity.doubleValue(for: .milligramsPerDeciliter)
            guard sample.startDate >= start && sample.startDate <= end,
                  !sample.isDisplayOnly && !sample.wasUserEntered,
                  value.isFinite && value > 0 && value < 1000 else { return nil }
            return (sample.startDate, value)
        }.sorted(by: { $0.0 < $1.0 })
        let measured: [(value: Double, seconds: Double)] = raw.enumerated().compactMap { index, item in
            let cappedEnd = min(item.0.addingTimeInterval(300), end)
            let nextDate = index + 1 < raw.count ? min(raw[index + 1].0, cappedEnd) : cappedEnd
            let seconds = max(0, nextDate.timeIntervalSince(item.0))
            guard seconds > 0 else { return nil }
            return (value: item.1, seconds: seconds)
        }
        let observedSeconds = measured.reduce(0.0) { $0 + $1.seconds }
        let mean = observedSeconds > 0
            ? measured.reduce(0.0) { $0 + $1.value * $1.seconds } / observedSeconds : 0.0
        let deviation = observedSeconds > 0
            ? sqrt(measured.reduce(0.0) {
                $0 + ($1.value - mean) * ($1.value - mean) * $1.seconds
              } / observedSeconds) : 0.0
        let coverage = min(1.0, observedSeconds / max(1.0, end.timeIntervalSince(start)))
        func share(_ check: (Double) -> Bool) -> Double {
            guard observedSeconds > 0 else { return 0 }
            return measured.filter { check($0.value) }.reduce(0.0) {
                $0 + $1.seconds
            } / observedSeconds
        }
        let tir = share { $0 >= 70 && $0 <= 180 }
        let veryLow = share { $0 < 54 }
        let lowOnly = share { $0 >= 54 && $0 < 70 }
        let highOnly = share { $0 > 180 && $0 <= 250 }
        let veryHigh = share { $0 > 250 }
        let totals = LoKeyDoseTotals.sum(doses, from: start, to: end)
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: W, height: H))
        let settingsData = try JSONEncoder().encode(settings)
        let json = String(data: settingsData, encoding: .utf8) ?? "{}"
        let pretty: String
        if let object = try? JSONSerialization.jsonObject(with: settingsData),
           let data = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            pretty = text
        } else { pretty = json }
        let data = renderer.pdfData { ctx in
            ctx.beginPage()
            header("Glucose & Insulin Summary", range: range, page: 1)
            draw("CGM Summary", x: 38, y: 141, w: 500, size: 13, bold: true)
            if measured.isEmpty {
                draw("CGM readings unavailable for this period — no glucose statistics calculated.",
                     x: 38, y: 170, w: 530, size: 10, color: gray)
            } else {
                draw(String(format: "Average glucose  %.0f mg/dL", mean),
                     x: 38, y: 171, w: 260, size: 12, bold: true)
                draw(String(format: "Time 70–180  %.1f%%", tir*100),
                     x: 305, y: 171, w: 240, size: 12, bold: true)
                if coverage >= 0.70 && end.timeIntervalSince(start) >= 12 * 86400 {
                    draw(String(format: "GMI  %.1f%%", 3.31 + 0.02392 * mean),
                         x: 38, y: 199, w: 260, size: 11)
                } else {
                    draw("GMI omitted (limited period or CGM coverage)",
                         x: 38, y: 199, w: 265, size: 9, color: gray)
                }
                draw(String(format: "CV  %.1f%%", mean > 0 ? deviation / mean * 100 : 0),
                     x: 305, y: 199, w: 240, size: 11)
                draw(String(format: "CGM data coverage (approx.)  %.1f%%", coverage*100),
                     x: 38, y: 225, w: 450, size: 10)
            }
            draw("Ambulatory Glucose Profile (AGP-style)", x: 38, y: 270, w: 530, size: 13, bold: true)
            agp(raw, rect: CGRect(x: 60, y: 307, width: 490, height: 142))
            draw("Hourly median (purple) and interquartile band. Gaps mean inadequate samples.",
                 x: 60, y: 473, w: 500, size: 9, color: gray)
            draw(String(format: "Very low <54: %.1f%%    Low 54–69: %.1f%%    Range 70–180: %.1f%%",
                 veryLow*100, lowOnly*100, tir*100),
                 x: 38, y: 502, w: 530, size: 10, bold: true)
            draw(String(format: "High 181–250: %.1f%%    Very high >250: %.1f%%",
                 highOnly*100, veryHigh*100),
                 x: 38, y: 520, w: 530, size: 10)
            separator(543)
            draw("Recorded Insulin", x: 38, y: 562, w: 510, size: 13, bold: true)
            if totals.count == 0 {
                draw("No pump delivery entries available. Insulin total is unknown, not zero.",
                     x: 38, y: 588, w: 530, size: 10, color: gray)
            } else {
                let elapsed = max(1, end.timeIntervalSince(start) / 86400)
                draw(String(format: "Average daily pump delivery: %.2f U/day", totals.delivered/elapsed),
                     x: 38, y: 590, w: 490, size: 12, bold: true)
                draw(String(format: "Basal %.2f U   Auto bolus %.2f U   Initiated %.2f U   Unknown %.2f U",
                     totals.basal, totals.automated, totals.initiated, totals.unclassified),
                     x: 38, y: 620, w: 540, size: 10)
            }
            draw("Statistics use available CGM samples, not Dexcom's proprietary interpolation. "
                 + "Coverage is approximate. Pump-reported delivery may not equal insulin "
                 + "absorbed during a leaking pod.",
                 x: 38, y: 677, w: 530, h: 54, size: 9, color: gray)

            ctx.beginPage()
            header("Daily Insulin & Pod Usage", range: range, page: 2)
            draw("Date", x: 39, y: 142, w: 112, size: 10, bold: true)
            draw("Basal", x: 165, y: 142, w: 75, size: 10, bold: true)
            draw("Auto", x: 243, y: 142, w: 75, size: 10, bold: true)
            draw("You", x: 320, y: 142, w: 75, size: 10, bold: true)
            draw("Unknown", x: 394, y: 142, w: 78, size: 10, bold: true)
            draw("Total", x: 493, y: 142, w: 70, size: 10, bold: true)
            separator(164)
            let first = Calendar.current.startOfDay(for: start)
            let count = min(90, Calendar.current.dateComponents([.day], from: first, to: end).day! + 1)
            let shown = min(count, 18)
            for offset in 0..<shown {
                guard let day = Calendar.current.date(byAdding: .day, value: offset, to: first),
                      let next = Calendar.current.date(byAdding: .day, value: 1, to: day) else { continue }
                let summary = LoKeyDoseTotals.sum(doses, from: day, to: min(next, end))
                let y = CGFloat(173 + offset*21)
                draw(fmt.string(from: day), x: 39, y: y, w: 122, size: 9)
                if summary.count == 0 {
                    draw("No data", x: 164, y: y, w: 230, size: 9, color: gray)
                } else {
                    draw(String(format: "%.1f", summary.basal), x: 165, y: y, w: 65, size: 9)
                    draw(String(format: "%.1f", summary.automated), x: 243, y: y, w: 65, size: 9)
                    draw(String(format: "%.1f", summary.initiated), x: 320, y: y, w: 65, size: 9)
                    draw(String(format: "%.1f", summary.unclassified), x: 394, y: y, w: 65, size: 9)
                    draw(String(format: "%.1f", summary.delivered), x: 493, y: y, w: 67, size: 9, bold: true)
                }
            }
            if count > shown {
                draw("Daily history continues on the following page(s).",
                     x: 39, y: 555, w: 525, size: 9, color: gray)
            }
            separator(568)
            draw("Pod Changes", x: 39, y: 579, w: 520, size: 13, bold: true)
            let relevant = pods.filter { $0.activatedAt <= end &&
                ($0.endedAt ?? end) >= start }.sorted(by: { $0.activatedAt > $1.activatedAt })
            if relevant.isEmpty {
                draw("No pod change records yet. Tracking begins after the feature is installed.",
                     x: 39, y: 605, w: 520, size: 9, color: gray)
            } else {
                let completed = relevant.filter { $0.endedAt != nil }
                let hours = completed.compactMap(\.wearHours)
                if !hours.isEmpty {
                    draw(String(format: "Completed pods: %d   Average wear: %.1f hours",
                        hours.count, hours.reduce(0,+) / Double(hours.count)),
                        x: 39, y: 591, w: 530, size: 9, bold: true)
                }
                for (index, pod) in relevant.prefix(4).enumerated() {
                    let y = CGFloat(604 + index*27)
                    let duration = pod.wearHours.map { String(format: "%.1f h", $0) } ?? "active"
                    let filled = pod.fillUnits.map { String(format: "%.0f U", $0) } ?? "unknown"
                    draw(fmt.string(from: pod.activatedAt) + "  |  " + duration +
                        "  |  fill " + filled + "  |  " + pod.changeReason,
                        x: 40, y: y, w: 530, size: 9)
                }
            }

            var page = 3
            var nextOffset = shown
            while nextOffset < count {
                ctx.beginPage()
                header("Daily Insulin (continued)", range: range, page: page)
                draw("Date", x: 39, y: 144, w: 122, size: 10, bold: true)
                draw("Basal", x: 165, y: 144, w: 65, size: 10, bold: true)
                draw("Auto", x: 243, y: 144, w: 65, size: 10, bold: true)
                draw("You", x: 320, y: 144, w: 65, size: 10, bold: true)
                draw("Unknown", x: 394, y: 144, w: 70, size: 10, bold: true)
                draw("Total", x: 493, y: 144, w: 70, size: 10, bold: true)
                separator(164)
                let lastOffset = min(nextOffset + 23, count)
                for offset in nextOffset..<lastOffset {
                    guard let day = Calendar.current.date(byAdding: .day, value: offset, to: first),
                          let next = Calendar.current.date(byAdding: .day, value: 1, to: day) else { continue }
                    let daily = LoKeyDoseTotals.sum(doses, from: day, to: min(next, end))
                    let y = CGFloat(174 + (offset - nextOffset)*22)
                    draw(fmt.string(from: day), x: 39, y: y, w: 122, size: 9)
                    if daily.count == 0 {
                        draw("No data", x: 164, y: y, w: 200, size: 9, color: gray)
                    } else {
                        draw(String(format: "%.1f", daily.basal), x: 165, y: y, w: 65, size: 9)
                        draw(String(format: "%.1f", daily.automated), x: 243, y: y, w: 65, size: 9)
                        draw(String(format: "%.1f", daily.initiated), x: 320, y: y, w: 65, size: 9)
                        draw(String(format: "%.1f", daily.unclassified), x: 394, y: y, w: 65, size: 9)
                        draw(String(format: "%.1f", daily.delivered), x: 493, y: y, w: 67, size: 9, bold: true)
                    }
                }
                nextOffset = lastOffset
                page += 1
            }

            let settingsLines = pretty.components(separatedBy: "\n")
            var position = 0
            while position < settingsLines.count {
                ctx.beginPage()
                header("Current Therapy Settings (JSON detail)", range: range, page: page)
                draw("Snapshot at export time; not a reconstruction of historical settings.",
                     x: 38, y: 135, w: 530, size: 10, color: gray)
                var y: CGFloat = 166
                while position < settingsLines.count && y < 721 {
                    let line = settingsLines[position]
                    // Wrap long JSON strings to keep content inside page margins.
                    let chunks = stride(from: 0, to: line.count, by: 89).map { idx -> String in
                        let a = line.index(line.startIndex, offsetBy: idx)
                        let b = line.index(a, offsetBy: min(89, line.count-idx))
                        return String(line[a..<b])
                    }
                    let pieces = chunks.isEmpty ? [""] : chunks
                    if y + CGFloat(pieces.count)*12 > 721 { break }
                    for piece in pieces {
                        draw(piece, x: 39, y: y, w: 535, h: 12, size: 8, color: ink)
                        y += 12
                    }
                    position += 1
                }
                page += 1
            }
        }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("LoKey-Clinical-Report-" + String(Int(Date().timeIntervalSince1970)) + ".pdf")
        try data.write(to: url, options: .atomic)
        return url
    }
}
'''

if __name__ == "__main__":
    install()
