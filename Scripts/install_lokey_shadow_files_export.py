#!/usr/bin/env python3
"""Replace only the broken Adaptive Shadow share-sheet export with Save to Files.

Install after LoKeyBuild33ShadowDashboard.patch, before code signing.
Read-only: edits only Loop/Loop/Views/SettingsView.swift. No insulin, pump,
CGM, prediction, recorder, retention, or delivery code is changed.
Fail closed if expected preexisting view structure is different.
"""
from pathlib import Path

SOURCE = Path("Loop/Loop/Views/SettingsView.swift")
START = "private struct LoKeyAdaptiveShadowSettingsView: View {"
END = "private struct LoKeyShadowDashboardView: View {"
NEEDED = (
    'Button("Export Shadow Records") { exportShadowRecords() }',
    "LoKeyReportShareSheet(items: exportFiles)",
    'appendingPathComponent("LoKeyAdaptiveShadow", isDirectory: true)',
)

REPLACEMENT = r'''
// MARK: - LoKey Adaptive Shadow: user-initiated read-only export
//
// Do not hand app-private .jsonl URLs directly to UIActivityViewController:
// iOS can display an empty share panel for this uncommon extension.
// fileExporter uses the system document picker, producing one standard JSON file.
private struct LoKeyAdaptiveShadowSettingsView: View {
    @AppStorage("LoKeyAdaptiveShadowEnabledV1") private var shadowEnabled = false
    @State private var preparingExport = false
    @State private var exportDocument: LoKeyShadowExportDocument?
    @State private var exportName = "LoKey-Adaptive-Shadow"
    @State private var showingExporter = false
    @State private var exportMessage: String?
    @State private var exportFailed = false

    var body: some View {
        Form {
            Section(header: Text("Recording")) {
                Toggle("Record live shadow decisions", isOn: $shadowEnabled)
                Text("Observation only. Normal Loop remains the only insulin controller. Recording continues during ordinary Loop use when enabled.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }

            Section(header: Text("Collected Data")) {
                NavigationLink(destination: LoKeyShadowDashboardView()) {
                    Label("View Dashboard", systemImage: "chart.xyaxis.line")
                }
                Button(action: exportShadowRecords) {
                    Label(preparingExport ? "Preparing export…" : "Export Shadow Records to Files",
                          systemImage: "square.and.arrow.down")
                }
                .disabled(preparingExport)
                if preparingExport {
                    ProgressView("Preparing local JSON archive")
                }
                if let exportMessage {
                    Text(exportMessage)
                        .font(.footnote)
                        .foregroundColor(exportFailed ? .red : .secondary)
                }
                Text("Save the JSON file in Files or iCloud Drive, then upload it to Adaptive or share it for analysis. Your original Shadow records stay in Loop. Export is manual and includes private health information.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
        }
        .navigationTitle("Adaptive Shadow")
        .navigationBarTitleDisplayMode(.inline)
        .fileExporter(isPresented: $showingExporter,
                      document: exportDocument,
                      contentType: .json,
                      defaultFilename: exportName) { result in
            Task { @MainActor in
                switch result {
                case .success:
                    exportFailed = false
                    exportMessage = "Export saved. Verify the JSON file in Files before deleting or reinstalling Loop."
                case .failure(let error):
                    exportFailed = true
                    exportMessage = "Export was not saved: \(error.localizedDescription). Your original records are still in Loop."
                }
            }
        }
    }

    private func exportShadowRecords() {
        guard !preparingExport else { return }
        preparingExport = true
        exportMessage = nil
        exportFailed = false
        exportDocument = nil
        Task { @MainActor in
            do {
                let payload = try await Task.detached(priority: .utility) {
                    try LoKeyShadowArchiveBuilder.build()
                }.value
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyyMMdd-HHmmss"
                formatter.locale = Locale(identifier: "en_US_POSIX")
                formatter.timeZone = TimeZone(secondsFromGMT: 0)
                exportName = "LoKey-Adaptive-Shadow-" + formatter.string(from: Date())
                exportDocument = LoKeyShadowExportDocument(payload: payload)
                preparingExport = false
                showingExporter = true
            } catch {
                preparingExport = false
                exportFailed = true
                exportMessage = "Couldn't prepare the export: \(error.localizedDescription). Your original records were not changed."
            }
        }
    }
}

private struct LoKeyShadowExportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    static var writableContentTypes: [UTType] { [.json] }

    let payload: Data

    init(payload: Data) {
        self.payload = payload
    }

    init(configuration: ReadConfiguration) throws {
        guard let bytes = configuration.file.regularFileContents else {
            throw CocoaError(.fileReadCorruptFile)
        }
        payload = bytes
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: payload)
    }
}

private enum LoKeyShadowArchiveBuilder {
    enum ExportError: LocalizedError {
        case noRecords
        case notRegularFile(String)
        case invalidUTF8(String)
        case tooLarge
        case missingStorage

        var errorDescription: String? {
            switch self {
            case .noRecords:
                return "No local Shadow files were found. Check that recording is enabled and the Shadow dashboard has records."
            case .notRegularFile(let name):
                return "Shadow file is not a regular file: \(name)"
            case .invalidUTF8(let name):
                return "Shadow file cannot be read as text: \(name)"
            case .tooLarge:
                return "Shadow history exceeds the 64 MB single-export limit. No partial archive was created."
            case .missingStorage:
                return "Application Support storage is unavailable."
            }
        }
    }

    // Preserve every original JSONL line, including unrecognized future fields,
    // by storing UTF-8 contents verbatim in a standard JSON envelope.
    // No data is uploaded. If any file cannot be read, do not silently omit it.
    static func build() throws -> Data {
        let manager = FileManager.default
        guard let root = manager.urls(for: .applicationSupportDirectory,
                                      in: .userDomainMask).first else {
            throw ExportError.missingStorage
        }
        let directory = root.appendingPathComponent("LoKeyAdaptiveShadow", isDirectory: true)
        guard manager.fileExists(atPath: directory.path) else { throw ExportError.noRecords }
        let files = try manager.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey]
        ).filter {
            $0.lastPathComponent.hasPrefix("adaptive-shadow-") && $0.pathExtension == "jsonl"
        }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        guard !files.isEmpty else { throw ExportError.noRecords }

        let maxBytes = 64 * 1024 * 1024
        var totalBytes = 0
        var archives: [[String: Any]] = []
        for file in files {
            let resources = try file.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            guard resources.isRegularFile == true else {
                throw ExportError.notRegularFile(file.lastPathComponent)
            }
            let fileBytes = resources.fileSize ?? 0
            guard fileBytes >= 0 && fileBytes <= maxBytes - totalBytes else {
                throw ExportError.tooLarge
            }
            let data = try Data(contentsOf: file, options: .mappedIfSafe)
            guard data.count <= maxBytes - totalBytes else {
                throw ExportError.tooLarge
            }
            guard let originalText = String(data: data, encoding: .utf8) else {
                throw ExportError.invalidUTF8(file.lastPathComponent)
            }
            totalBytes += data.count
            archives.append([
                "filename": file.lastPathComponent,
                "byteCount": data.count,
                "jsonl": originalText
            ])
        }

        let envelope: [String: Any] = [
            "format": "LoKeyAdaptiveShadowExport",
            "schemaVersion": 1,
            "exportedAt": ISO8601DateFormatter().string(from: Date()),
            "recordStorage": "LoKey Loop / Application Support / LoKeyAdaptiveShadow",
            "sourceFileCount": archives.count,
            "sourceBytes": totalBytes,
            "files": archives,
            "notice": "Read-only historical observations. Never treat as current glucose, pump state, IOB, or an instruction to dose."
        ]
        // Serialization failures must be visible; never export a partial file.
        return try JSONSerialization.data(
            withJSONObject: envelope, options: [.prettyPrinted, .sortedKeys]
        )
    }
}

'''

def transform(source: str) -> str:
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("Shadow settings anchors were changed; refusing export patch.")
    start = source.index(START)
    end = source.index(END, start)
    existing = source[start:end]
    for anchor in NEEDED:
        if existing.count(anchor) != 1:
            raise RuntimeError(f"Expected one existing export anchor: {anchor}")
    if "private struct LoKeyShadowExportDocument" in source:
        raise RuntimeError("Shadow document exporter already installed.")
    if source.count("import SwiftUI\n") != 1:
        raise RuntimeError("Cannot locate exactly one SwiftUI import.")
    source = source[:start] + REPLACEMENT + source[end:]
    if "import UniformTypeIdentifiers\n" not in source:
        source = source.replace("import SwiftUI\n",
                                "import SwiftUI\nimport UniformTypeIdentifiers\n", 1)
    return source

def install() -> None:
    before = SOURCE.read_text(encoding="utf-8")
    after = transform(before)
    SOURCE.write_text(after, encoding="utf-8")
    print("PASS: Shadow export uses the native Save to Files JSON document picker; original JSONL data untouched.")

if __name__ == "__main__":
    install()
