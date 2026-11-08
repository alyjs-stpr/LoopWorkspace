#!/usr/bin/env python3
"""Install a read-only, opt-in LoKey Loop export under LoKey Settings.

Run after all UI patches in the LoopWorkspace build workflow.
Only edits Loop/Loop/Views/SettingsView.swift. No insulin delivery changes.
The generated JSON is a *reference archive*, NOT a restoreable pump state.
"""
from pathlib import Path

PATH = Path("Loop/Loop/Views/SettingsView.swift")

NAV_ANCHOR = '''                NavigationLink(destination: LoKeyReportsView(viewModel: viewModel)) {
                    Label("Glucose reports & settings PDF", systemImage: "chart.pie")
                }'''

NEW_NAV = NAV_ANCHOR + '''
                NavigationLink(destination: LoKeyLoopDataArchiveView(viewModel: viewModel)) {
                    Label("Export Loop Data Archive", systemImage: "externaldrive.badge.person.crop")
                }'''

NEW_VIEW = r'''
// MARK: - LoKey Loop: opt-in, read-only personal data archive
//
// For reference and archival purposes. NOT a pump/controller restore file.
// Deliberately excludes keychain secrets, Nightscout tokens, stored Bluetooth
// pairing state, raw pump database, and all API credentials. It cannot reactivate
// a pod or reconstruct insulin-on-board.
private struct LoKeyLoopDataArchiveView: View {
    let viewModel: SettingsViewModel

    @State private var exporting = false
    @State private var exportURL: URL?
    @State private var showingShareSheet = false
    @State private var errorText: String?
    @State private var warningText: String?

    var body: some View {
        Form {
            Section(header: Text("Save Before Uninstalling")) {
                Text("Creates a dated personal archive of your current therapy settings, up to 90 days of stored glucose readings, and existing LoKey Shadow and pod-leak notes when available.")
                Text("This is a read-only archive for reference. It cannot restore pump pairing, app databases, active insulin, or dosing state.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
                Button(action: prepareExport) {
                    Label(exporting ? "Preparing archive…" : "Prepare Data Archive", systemImage: "square.and.arrow.up")
                }
                .disabled(exporting)
                if exporting { ProgressView() }
                if let warningText = warningText {
                    Text(warningText).font(.caption).foregroundColor(.orange)
                }
                if let errorText = errorText {
                    Text(errorText).font(.caption).foregroundColor(.red)
                }
                Text("When the share sheet opens, use Save to Files. Confirm that the saved JSON file exists outside Loop before deleting the app. Keep this health-data archive private.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
            Section(header: Text("Additional History")) {
                Text("For detailed pump and insulin history, separately export Critical Event Logs under Settings → Support. You can also export the existing settings PDF under LoKey Settings → Glucose Reports.")
                    .font(.footnote)
            }
        }
        .navigationTitle("Data Archive")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showingShareSheet) {
            if let exportURL = exportURL {
                LoKeyReportShareSheet(items: [exportURL])
            }
        }
    }

    private func prepareExport() {
        exporting = true
        errorText = nil
        warningText = nil

        let end = Date()
        let start = end.addingTimeInterval(-90 * 24 * 60 * 60)
        guard let fetch = viewModel.loKeyLoadGlucose else {
            finalizeExport(glucose: [], glucoseIssue: "Glucose history loader is unavailable.")
            return
        }
        fetch(start, end) { result in
            DispatchQueue.main.async {
                switch result {
                case .success(let samples):
                    self.finalizeExport(glucose: samples, glucoseIssue: nil)
                case .failure(let error):
                    self.finalizeExport(glucose: [], glucoseIssue: "Glucose history failed: \(error.localizedDescription)")
                }
            }
        }
    }

    private func finalizeExport(glucose: [StoredGlucoseSample], glucoseIssue: String?) {
        defer { exporting = false }
        do {
            let now = Date()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let settingsData = try encoder.encode(viewModel.therapySettings())
            let currentSettings = try JSONSerialization.jsonObject(with: settingsData)

            var readings = [[String: Any]]()
            for sample in glucose {
                let value = sample.quantity.doubleValue(for: .milligramsPerDeciliter)
                guard value.isFinite else { continue }
                readings.append([
                    "date": ISO8601DateFormatter().string(from: sample.startDate),
                    "glucoseMgDl": value,
                    "displayOnly": sample.isDisplayOnly,
                    "userEntered": sample.wasUserEntered
                ])
            }

            var notes: [String: Any] = [:]
            if let events = UserDefaults.standard.array(forKey: "LoKeyLeakEventHistoryV1") {
                notes["podLeakEventHistory"] = jsonSafe(events)
            }
            notes["reportingLowerMgDl"] = UserDefaults.standard.object(forKey: "lokeyTIRLowerMGDL") as? Int ?? 65
            notes["reportingUpperMgDl"] = UserDefaults.standard.object(forKey: "lokeyTIRUpperMGDL") as? Int ?? 180

            // Capture only explicitly named, LoKey-owned Shadow JSONL files.
            // Never archive arbitrary application folders, secrets, or keychains.
            var shadowRecords: [[String: Any]] = []
            var skippedShadow: [String] = []
            let fm = FileManager.default
            if let appSupport = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first {
                let folder = appSupport.appendingPathComponent("LoKeyAdaptiveShadow", isDirectory: true)
                let files = (try? fm.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.fileSizeKey])) ?? []
                var captured = 0
                let limit = 18 * 1024 * 1024
                for file in files.sorted(by: { $0.lastPathComponent < $1.lastPathComponent })
                    where file.lastPathComponent.hasPrefix("adaptive-shadow-") && file.pathExtension == "jsonl" {
                    let data = try Data(contentsOf: file)
                    guard data.count <= 5 * 1024 * 1024, data.count + captured <= limit,
                          let text = String(data: data, encoding: .utf8)
                    else {
                        skippedShadow.append(file.lastPathComponent)
                        continue
                    }
                    captured += data.count
                    shadowRecords.append(["filename": file.lastPathComponent, "jsonl": text])
                }
            }

            let warnings = ([glucoseIssue].compactMap { $0 }) + (
                skippedShadow.isEmpty ? [] : ["Some Shadow files exceeded the archive size limit; export them separately."]
            )
            let archive: [String: Any] = [
                "format": "LoKeyLoopReferenceArchive",
                "schemaVersion": 1,
                "createdAt": ISO8601DateFormatter().string(from: now),
                "disclaimer": "Not an app backup or pump/controller restore. Never import as active IOB, settings or pump state without clinical review.",
                "currentTherapySettings": currentSettings,
                "closedLoopPreference": String(describing: viewModel.closedLoopPreference),
                "automaticDosingStrategy": String(describing: viewModel.automaticDosingStrategy),
                "pumpDisplayName": viewModel.pumpManagerSettingsViewModel.name(),
                "cgmDisplayName": viewModel.cgmManagerSettingsViewModel.name(),
                "glucoseHistoryLast90Days": readings,
                "loKeyNotes": notes,
                "adaptiveShadowFiles": shadowRecords,
                "skippedShadowFiles": skippedShadow,
                "warnings": warnings,
                "excludedSensitiveData": [
                    "Keychain credentials", "Nightscout tokens", "Pump pairing keys",
                    "Pump state databases", "Active insulin state", "Service passwords"
                ]
            ]

            guard JSONSerialization.isValidJSONObject(archive) else {
                throw NSError(domain: "LoKeyArchive", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "Archive includes unsupported values."])
            }
            let encoded = try JSONSerialization.data(withJSONObject: archive, options: [.prettyPrinted, .sortedKeys])
            let name = "LoKey-Loop-Archive-\(Int(now.timeIntervalSince1970)).json"
            let url = fm.temporaryDirectory.appendingPathComponent(name)
            try encoded.write(to: url, options: .atomic)
            exportURL = url
            warningText = warnings.isEmpty ? nil : warnings.joined(separator: "\n")
            showingShareSheet = true
        } catch {
            errorText = "Unable to create archive: \(error.localizedDescription)"
        }
    }

    private func jsonSafe(_ value: Any) -> Any {
        if let date = value as? Date {
            return ISO8601DateFormatter().string(from: date)
        }
        if let dict = value as? [String: Any] {
            return dict.mapValues { jsonSafe($0) }
        }
        if let items = value as? [Any] {
            return items.map { jsonSafe($0) }
        }
        if let text = value as? String { return text }
        if let number = value as? NSNumber { return number }
        return String(describing: value)
    }
}

'''

def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if text.count(NAV_ANCHOR) != 1:
        raise RuntimeError("Expected LoKey Settings navigation anchor exactly once; found " + str(text.count(NAV_ANCHOR)))
    if "private struct LoKeyLoopDataArchiveView" in text:
        raise RuntimeError("Archive view already installed")
    text = text.replace(NAV_ANCHOR, NEW_NAV, 1)
    anchor = "private struct LoKeyAdaptiveShadowSettingsView: View {"
    if text.count(anchor) != 1:
        raise RuntimeError("Expected Shadow view anchor exactly once; found " + str(text.count(anchor)))
    text = text.replace(anchor, NEW_VIEW + anchor, 1)
    PATH.write_text(text, encoding="utf-8")
    print("PASS: added manual LoKey reference archive export without dosing changes")

if __name__ == "__main__":
    main()
