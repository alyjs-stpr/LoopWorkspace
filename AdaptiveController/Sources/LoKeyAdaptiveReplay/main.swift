import Foundation
import LoKeyAdaptiveCore

// Pass one JSON snapshot per line on stdin. Emit a JSON evaluation per line.
// No pump SDK is linked. This tool cannot send insulin delivery commands.
// Example: swift run --package-path AdaptiveController lokey-adaptive-replay < snapshots.jsonl
let decoder = JSONDecoder()
let encoder = JSONEncoder()
decoder.dateDecodingStrategy = .iso8601
encoder.dateEncodingStrategy = .iso8601
encoder.outputFormatting = [.sortedKeys]
let engine = LoKeyAdaptive.Controller()

while let line = readLine() {
    guard !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
    do {
        let snapshot = try decoder.decode(LoKeyAdaptive.Snapshot.self, from: Data(line.utf8))
        let evaluated = engine.evaluate(snapshot)
        let encoded = try encoder.encode(evaluated)
        if let json = String(data: encoded, encoding: .utf8) { print(json) }
    } catch {
        fputs("Invalid snapshot JSON: \(error)\n", stderr)
        exit(2)
    }
}
