import Foundation

extension LoKeyAdaptive {
    /// Auditable record of a completed Loop cycle. A shadow recommendation is
    /// never an actual dose or a directly observable counterfactual result.
    public struct RecordedCycle: Codable, Sendable {
        public let schemaVersion: Int
        public let snapshot: Snapshot
        public let evaluation: Evaluation

        public init(snapshot: Snapshot, evaluation: Evaluation) {
            schemaVersion = 1
            self.snapshot = snapshot
            self.evaluation = evaluation
        }
    }

    public struct ForecastOutcome: Codable, Sendable {
        public let sourceTimestamp: Date
        public let horizonMinutes: Int
        public let predictedMgDl: Double
        public let observedMgDl: Double
        public let errorMgDl: Double
        public let absoluteErrorMgDl: Double
        public let sourceBias: TargetBias
        public let sourceWasEligible: Bool
    }

    public struct Report: Codable, Sendable {
        public let cycleCount: Int
        public let eligibleCount: Int
        public let blockedCount: Int
        public let outcomes: [ForecastOutcome]

        public func meanAbsoluteError(horizonMinutes: Int) -> Double? {
            let selected = outcomes.filter { $0.horizonMinutes == horizonMinutes }
            guard !selected.isEmpty else { return nil }
            return selected.map(\.absoluteErrorMgDl).reduce(0, +) / Double(selected.count)
        }
    }

    public struct OutcomeAnalyzer {
        public init() {}

        public func analyze(_ cycles: [RecordedCycle]) -> Report {
            let sorted = cycles.sorted { $0.snapshot.observedAt < $1.snapshot.observedAt }
            // Later CGM readings are actual outcomes from *normal Loop's* delivery,
            // not outcomes of the alternative shadow policy.
            let glucose = sorted.compactMap(\.snapshot.latestGlucose)
                .filter { $0.glucoseMgDl.isFinite && (35...600).contains($0.glucoseMgDl) }
            var outcomes: [ForecastOutcome] = []

            for cycle in sorted {
                let source = cycle.snapshot
                for horizon in [30, 60, 120, 180] {
                    let dueAt = source.observedAt.addingTimeInterval(TimeInterval(horizon * 60))
                    guard let predicted = source.predictedGlucose
                        .filter({ $0.glucoseMgDl.isFinite && abs($0.timestamp.timeIntervalSince(dueAt)) <= 4 * 60 })
                        .min(by: { abs($0.timestamp.timeIntervalSince(dueAt)) < abs($1.timestamp.timeIntervalSince(dueAt)) }),
                          let actual = glucose
                        .filter({ abs($0.timestamp.timeIntervalSince(dueAt)) <= 4 * 60 && $0.timestamp > source.observedAt })
                        .min(by: { abs($0.timestamp.timeIntervalSince(dueAt)) < abs($1.timestamp.timeIntervalSince(dueAt)) })
                    else { continue }
                    let error = actual.glucoseMgDl - predicted.glucoseMgDl
                    outcomes.append(ForecastOutcome(
                        sourceTimestamp: source.observedAt,
                        horizonMinutes: horizon,
                        predictedMgDl: predicted.glucoseMgDl,
                        observedMgDl: actual.glucoseMgDl,
                        errorMgDl: error,
                        absoluteErrorMgDl: abs(error),
                        sourceBias: cycle.evaluation.bias,
                        sourceWasEligible: cycle.evaluation.eligible
                    ))
                }
            }
            return Report(
                cycleCount: sorted.count,
                eligibleCount: sorted.filter(\.evaluation.eligible).count,
                blockedCount: sorted.filter { !$0.evaluation.eligible }.count,
                outcomes: outcomes
            )
        }
    }
}
