import Foundation

/// Experimental target-selection policy, not a pump dosing algorithm.
/// This package is deliberately independent of Loop's insulin-delivery path.
/// It accepts snapshots, produces auditable *hypothetical* target decisions,
/// and cannot request a bolus, temp basal, or change to Loop settings.
public enum LoKeyAdaptive {
    public struct TargetRange: Codable, Equatable, Sendable {
        public let lowMgDl: Double
        public let highMgDl: Double

        public init(lowMgDl: Double, highMgDl: Double) {
            self.lowMgDl = lowMgDl
            self.highMgDl = highMgDl
        }

        public var isValid: Bool {
            lowMgDl.isFinite && highMgDl.isFinite
                && lowMgDl >= 55 && highMgDl <= 250 && lowMgDl <= highMgDl
        }
    }

    public struct Reading: Codable, Equatable, Sendable {
        public let timestamp: Date
        public let glucoseMgDl: Double

        public init(timestamp: Date, glucoseMgDl: Double) {
            self.timestamp = timestamp
            self.glucoseMgDl = glucoseMgDl
        }
    }

    public enum DeliveryCertainty: String, Codable, Sendable {
        case confirmed
        case uncertain
        case pumpDisconnected
    }

    public struct Snapshot: Codable, Sendable {
        public let observedAt: Date
        public let parkModeActive: Bool
        public let automaticDosingEnabled: Bool
        public let target: TargetRange
        public let latestGlucose: Reading?
        public let loopCompletedAt: Date?
        /// Loop's own predictions; do not create glucose predictions here.
        public let predictedGlucose: [Reading]
        /// An observed value from Loop's existing DoseStore, never reset on switching modes.
        public let recordedIOBUnits: Double?
        public let insulinHistoryReconciled: Bool
        public let deliveryCertainty: DeliveryCertainty

        public init(
            observedAt: Date,
            parkModeActive: Bool,
            automaticDosingEnabled: Bool,
            target: TargetRange,
            latestGlucose: Reading?,
            loopCompletedAt: Date?,
            predictedGlucose: [Reading],
            recordedIOBUnits: Double?,
            insulinHistoryReconciled: Bool,
            deliveryCertainty: DeliveryCertainty
        ) {
            self.observedAt = observedAt
            self.parkModeActive = parkModeActive
            self.automaticDosingEnabled = automaticDosingEnabled
            self.target = target
            self.latestGlucose = latestGlucose
            self.loopCompletedAt = loopCompletedAt
            self.predictedGlucose = predictedGlucose
            self.recordedIOBUnits = recordedIOBUnits
            self.insulinHistoryReconciled = insulinHistoryReconciled
            self.deliveryCertainty = deliveryCertainty
        }
    }

    public enum TargetBias: String, Codable, Sendable {
        case center
        case towardUpperBound
        case towardLowerBound
        case unavailable
    }

    public enum Blocker: String, Codable, Sendable {
        case inactiveParkMode
        case automaticDosingOff
        case invalidTarget
        case staleOrMissingCGM
        case staleOrMissingLoop
        case insulinHistoryUnreconciled
        case uncertainDelivery
        case missingOrInvalidIOB
        case insufficientForecast
        case invalidForecast
    }

    public struct Evaluation: Codable, Sendable {
        public let observedAt: Date
        public let bias: TargetBias
        /// Hypothetical target only. This is NEVER written to Loop settings.
        public let shadowTargetMgDl: Double?
        public let blocker: Blocker?
        public let firstPredictedOutOfRangeMinutes: Double?
        public let predictionMinimumMgDl: Double?
        public let predictionMaximumMgDl: Double?
        public let recordedIOBUnits: Double?

        public var eligible: Bool { blocker == nil }
    }

    public struct Controller {
        public init() {}

        public func evaluate(_ snapshot: Snapshot) -> Evaluation {
            func blocked(_ reason: Blocker) -> Evaluation {
                Evaluation(
                    observedAt: snapshot.observedAt,
                    bias: .unavailable,
                    shadowTargetMgDl: nil,
                    blocker: reason,
                    firstPredictedOutOfRangeMinutes: nil,
                    predictionMinimumMgDl: nil,
                    predictionMaximumMgDl: nil,
                    recordedIOBUnits: snapshot.recordedIOBUnits
                )
            }

            guard snapshot.parkModeActive else { return blocked(.inactiveParkMode) }
            guard snapshot.automaticDosingEnabled else { return blocked(.automaticDosingOff) }
            guard snapshot.target.isValid else { return blocked(.invalidTarget) }
            guard let glucose = snapshot.latestGlucose,
                  glucose.glucoseMgDl.isFinite,
                  (35...600).contains(glucose.glucoseMgDl),
                  snapshot.observedAt.timeIntervalSince(glucose.timestamp) >= -60,
                  snapshot.observedAt.timeIntervalSince(glucose.timestamp) <= 10 * 60
            else { return blocked(.staleOrMissingCGM) }

            guard let lastLoop = snapshot.loopCompletedAt,
                  snapshot.observedAt.timeIntervalSince(lastLoop) >= -60,
                  snapshot.observedAt.timeIntervalSince(lastLoop) <= 10 * 60
            else { return blocked(.staleOrMissingLoop) }

            guard snapshot.insulinHistoryReconciled else { return blocked(.insulinHistoryUnreconciled) }
            guard snapshot.deliveryCertainty == .confirmed else { return blocked(.uncertainDelivery) }
            guard let iob = snapshot.recordedIOBUnits,
                  iob.isFinite, iob >= 0 else { return blocked(.missingOrInvalidIOB) }

            // Only examine the next hour. Missing predictions cannot be treated
            // as evidence that glucose is safely within the requested range.
            let forecast = snapshot.predictedGlucose
                .filter { $0.timestamp >= snapshot.observedAt
                            && $0.timestamp <= snapshot.observedAt.addingTimeInterval(60 * 60) }
                .sorted { $0.timestamp < $1.timestamp }

            guard forecast.count >= 2,
                  let first = forecast.first, let last = forecast.last,
                  first.timestamp.timeIntervalSince(snapshot.observedAt) <= 15 * 60,
                  last.timestamp.timeIntervalSince(snapshot.observedAt) >= 30 * 60
            else { return blocked(.insufficientForecast) }

            guard forecast.allSatisfy({
                $0.glucoseMgDl.isFinite && (35...600).contains($0.glucoseMgDl)
            }), zip(forecast, forecast.dropFirst()).allSatisfy({ pair in
                pair.0.timestamp < pair.1.timestamp &&
                pair.1.timestamp.timeIntervalSince(pair.0.timestamp) <= 15 * 60
            }) else { return blocked(.invalidForecast) }

            let values = forecast.map(\.glucoseMgDl)
            let minGlucose = min(glucose.glucoseMgDl, values.min()!)
            let maxGlucose = max(glucose.glucoseMgDl, values.max()!)
            let firstExit = forecast.first {
                $0.glucoseMgDl < snapshot.target.lowMgDl
                    || $0.glucoseMgDl > snapshot.target.highMgDl
            }
            let firstExitMinutes = firstExit.map {
                $0.timestamp.timeIntervalSince(snapshot.observedAt) / 60
            }

            // Experimental preference ordering: predicted lows always outrank
            // predicted highs. No insulin amount is calculated or authorized.
            let bias: TargetBias
            let shadowTarget: Double
            if minGlucose < snapshot.target.lowMgDl {
                bias = .towardUpperBound
                shadowTarget = snapshot.target.highMgDl
            } else if maxGlucose > snapshot.target.highMgDl {
                bias = .towardLowerBound
                shadowTarget = snapshot.target.lowMgDl
            } else {
                bias = .center
                shadowTarget = (snapshot.target.lowMgDl + snapshot.target.highMgDl) / 2
            }

            return Evaluation(
                observedAt: snapshot.observedAt,
                bias: bias,
                shadowTargetMgDl: shadowTarget,
                blocker: nil,
                firstPredictedOutOfRangeMinutes: firstExitMinutes,
                predictionMinimumMgDl: minGlucose,
                predictionMaximumMgDl: maxGlucose,
                recordedIOBUnits: iob
            )
        }
    }

    /// Pure state representation for testing ownership and handoffs. It does not
    /// change Loop's actual owner or make any insulin delivery request.
    public enum Owner: String, Codable, Sendable {
        case normalLoop
        case experimentalPark
    }

    public struct HandoffState: Codable, Sendable {
        public private(set) var owner: Owner
        public var pendingPumpCommand: Bool
        public var doseHistoryReconciled: Bool

        public init(
            owner: Owner = .normalLoop,
            pendingPumpCommand: Bool = false,
            doseHistoryReconciled: Bool = true
        ) {
            self.owner = owner
            self.pendingPumpCommand = pendingPumpCommand
            self.doseHistoryReconciled = doseHistoryReconciled
        }

        public var mayIssueAnotherCommand: Bool {
            !pendingPumpCommand && doseHistoryReconciled
        }

        @discardableResult
        public mutating func requestParkControl() -> Bool {
            guard mayIssueAnotherCommand else { return false }
            owner = .experimentalPark
            return true
        }

        /// Returning to normal is always allowed, but pending/unreconciled
        /// delivery still blocks *new* commands in this model.
        public mutating func returnToNormalLoop() {
            owner = .normalLoop
        }
    }
}
