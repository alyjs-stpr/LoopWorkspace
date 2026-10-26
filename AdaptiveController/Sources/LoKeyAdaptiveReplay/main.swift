import Foundation
import LoKeyAdaptiveCore

// Exported files from LoKey are line-delimited RecordedCycle objects.
// This utility also accepts legacy raw Snapshot lines for compatibility.
// Never connects to Loop, HealthKit, or a pump.
//
// swift run --package-path AdaptiveController lokey-adaptive-replay < export.jsonl
// swift run --package-path AdaptiveController lokey-adaptive-replay --outcomes < export.jsonl
let decoder = JSONDecoder()
let encoder = JSONEncoder()
decoder.dateDecodingStrategy = .iso8601
decoder.nonConformingFloatDecodingStrategy = .convertFromString(
    positiveInfinity: "Infinity", negativeInfinity: "-Infinity", nan: "NaN"
)
encoder.dateEncodingStrategy = .iso8601
encoder.nonConformingFloatEncodingStrategy = .convertToString(
    positiveInfinity: "Infinity", negativeInfinity: "-Infinity", nan: "NaN"
)
encoder.outputFormatting = [.sortedKeys]
let engine = LoKeyAdaptive.Controller()
let reportMode = CommandLine.arguments.contains("--outcomes")
var cycles: [LoKeyAdaptive.RecordedCycle] = []

while let line = readLine() {
    guard !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
    do {
        let data = Data(line.utf8)
        let cycle: LoKeyAdaptive.RecordedCycle
        if let imported = try? decoder.decode(LoKeyAdaptive.RecordedCycle.self, from: data) {
            cycle = imported
        } else {
            let snapshot = try decoder.decode(LoKeyAdaptive.Snapshot.self, from: data)
            cycle = .init(snapshot: snapshot, evaluation: engine.evaluate(snapshot))
        }

        if reportMode {
            cycles.append(cycle)
        } else {
            // Evaluate again with the current policy to compare against the
            // policy version embedded in the recorded snapshot.
            let result = engine.evaluate(cycle.snapshot)
            let evaluated = try encoder.encode(result)
            if let json = String(data: evaluated, encoding: .utf8) { print(json) }
        }
    } catch {
        fputs("Invalid shadow record: \(error)\n", stderr)
        exit(2)
    }
}
if reportMode {
    let report = LoKeyAdaptive.OutcomeAnalyzer().analyze(cycles)
    do {
        let data = try encoder.encode(report)
        if let json = String(data: data, encoding: .utf8) { print(json) }
    } catch {
        fputs("Unable to encode outcome report: \(error)\n", stderr)
        exit(2)
    }
}
