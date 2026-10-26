import Foundation
import XCTest
@testable import LoKeyAdaptiveCore

final class ControllerTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_700_000_000)
    private let engine = LoKeyAdaptive.Controller()

    private func forecast(_ numbers: [Double]) -> [LoKeyAdaptive.Reading] {
        let minutes: [Double] = [0, 5, 10, 20, 30, 45, 60]
        return zip(minutes, numbers).map {
            LoKeyAdaptive.Reading(
                timestamp: now.addingTimeInterval($0.0 * 60),
                glucoseMgDl: $0.1
            )
        }
    }

    private func snapshot(
        park: Bool = true,
        automatic: Bool = true,
        lower: Double = 120,
        upper: Double = 150,
        glucose: Double? = 135,
        glucoseTime: Date? = nil,
        loopTime: Date? = nil,
        points: [LoKeyAdaptive.Reading]? = nil,
        iob: Double? = 2.5,
        historyReconciled: Bool = true,
        delivery: LoKeyAdaptive.DeliveryCertainty = .confirmed
    ) -> LoKeyAdaptive.Snapshot {
        LoKeyAdaptive.Snapshot(
            observedAt: now,
            parkModeActive: park,
            automaticDosingEnabled: automatic,
            target: .init(lowMgDl: lower, highMgDl: upper),
            latestGlucose: glucose.map {
                .init(timestamp: glucoseTime ?? now, glucoseMgDl: $0)
            },
            loopCompletedAt: loopTime ?? now,
            predictedGlucose: points ?? forecast([135, 136, 137, 138, 138, 140, 141]),
            recordedIOBUnits: iob,
            insulinHistoryReconciled: historyReconciled,
            deliveryCertainty: delivery
        )
    }

    func testStableForecastKeepsTargetCentered() {
        let decision = engine.evaluate(snapshot())
        XCTAssertTrue(decision.eligible)
        XCTAssertEqual(decision.bias, .center)
        XCTAssertEqual(decision.shadowTargetMgDl, 135)
        XCTAssertNil(decision.firstPredictedOutOfRangeMinutes)
        XCTAssertEqual(decision.recordedIOBUnits, 2.5)
    }

    func testPredictedRiseProducesLowerBoundShadowPreference() {
        let decision = engine.evaluate(snapshot(points: forecast([135, 139, 145, 154, 160, 165, 168])))
        XCTAssertTrue(decision.eligible)
        XCTAssertEqual(decision.bias, .towardLowerBound)
        XCTAssertEqual(decision.shadowTargetMgDl, 120)
        XCTAssertEqual(decision.firstPredictedOutOfRangeMinutes, 20)
    }

    func testPredictedLowTakesPrecedence() {
        let decision = engine.evaluate(snapshot(points: forecast([135, 131, 126, 119, 109, 104, 99])))
        XCTAssertTrue(decision.eligible)
        XCTAssertEqual(decision.bias, .towardUpperBound)
        XCTAssertEqual(decision.shadowTargetMgDl, 150)
    }

    func testLowRiskTakesPriorityOverSimultaneousHighRisk() {
        let decision = engine.evaluate(snapshot(points: forecast([135, 159, 163, 119, 114, 135, 142])))
        XCTAssertEqual(decision.bias, .towardUpperBound)
        XCTAssertEqual(decision.shadowTargetMgDl, 150)
        XCTAssertEqual(decision.firstPredictedOutOfRangeMinutes, 5)
    }

    func testStaleCGMFailsClosed() {
        let d = engine.evaluate(snapshot(glucoseTime: now.addingTimeInterval(-11 * 60)))
        XCTAssertEqual(d.blocker, .staleOrMissingCGM)
        XCTAssertNil(d.shadowTargetMgDl)
    }

    func testFutureGlucoseFailsClosed() {
        let d = engine.evaluate(snapshot(glucoseTime: now.addingTimeInterval(2 * 60)))
        XCTAssertEqual(d.blocker, .staleOrMissingCGM)
    }

    func testStaleLoopPredictionFailsClosed() {
        let d = engine.evaluate(snapshot(loopTime: now.addingTimeInterval(-11 * 60)))
        XCTAssertEqual(d.blocker, .staleOrMissingLoop)
    }

    func testIOBMustBeKnownAndFinite() {
        XCTAssertEqual(engine.evaluate(snapshot(iob: nil)).blocker, .missingOrInvalidIOB)
        XCTAssertEqual(engine.evaluate(snapshot(iob: -0.1)).blocker, .missingOrInvalidIOB)
        XCTAssertEqual(engine.evaluate(snapshot(iob: .nan)).blocker, .missingOrInvalidIOB)
    }

    func testDeliveryUncertaintyBlocksAdaptiveDecision() {
        XCTAssertEqual(
            engine.evaluate(snapshot(delivery: .uncertain)).blocker,
            .uncertainDelivery
        )
        XCTAssertEqual(
            engine.evaluate(snapshot(delivery: .pumpDisconnected)).blocker,
            .uncertainDelivery
        )
    }

    func testUnreconciledHistoryBlocksAdaptiveDecision() {
        XCTAssertEqual(
            engine.evaluate(snapshot(historyReconciled: false)).blocker,
            .insulinHistoryUnreconciled
        )
    }

    func testInactiveOrDisabledModeBlocksAdaptiveDecision() {
        XCTAssertEqual(engine.evaluate(snapshot(park: false)).blocker, .inactiveParkMode)
        XCTAssertEqual(engine.evaluate(snapshot(automatic: false)).blocker, .automaticDosingOff)
    }

    func testInvalidTargetIsRejected() {
        XCTAssertEqual(
            engine.evaluate(snapshot(lower: 151, upper: 150)).blocker,
            .invalidTarget
        )
        XCTAssertEqual(
            engine.evaluate(snapshot(lower: .nan)).blocker,
            .invalidTarget
        )
    }

    func testShortForecastIsNotAssumedSafe() {
        let short = forecast([130, 131, 132])
        let d = engine.evaluate(snapshot(points: short))
        XCTAssertEqual(d.blocker, .insufficientForecast)
        XCTAssertNil(d.shadowTargetMgDl)
    }

    func testCorruptForecastIsRejected() {
        let corrupt = forecast([135, 136, 138, .infinity, 140, 143, 147])
        XCTAssertEqual(engine.evaluate(snapshot(points: corrupt)).blocker, .invalidForecast)
    }

    func testGapInForecastIsRejected() {
        let gap = [
            LoKeyAdaptive.Reading(timestamp: now, glucoseMgDl: 135),
            LoKeyAdaptive.Reading(timestamp: now.addingTimeInterval(31 * 60), glucoseMgDl: 145),
            LoKeyAdaptive.Reading(timestamp: now.addingTimeInterval(60 * 60), glucoseMgDl: 151)
        ]
        XCTAssertEqual(engine.evaluate(snapshot(points: gap)).blocker, .invalidForecast)
    }

    func testPendingPumpCommandPreventsSwitchToPark() {
        var state = LoKeyAdaptive.HandoffState(pendingPumpCommand: true)
        XCTAssertFalse(state.requestParkControl())
        XCTAssertEqual(state.owner, .normalLoop)
        XCTAssertFalse(state.mayIssueAnotherCommand)
    }

    func testUnreconciledHistoryPreventsSwitchToPark() {
        var state = LoKeyAdaptive.HandoffState(doseHistoryReconciled: false)
        XCTAssertFalse(state.requestParkControl())
        XCTAssertEqual(state.owner, .normalLoop)
        XCTAssertFalse(state.mayIssueAnotherCommand)
    }

    func testReturnToNormalNeverClearsPendingDelivery() {
        var state = LoKeyAdaptive.HandoffState()
        XCTAssertTrue(state.requestParkControl())
        state.pendingPumpCommand = true
        state.returnToNormalLoop()
        XCTAssertEqual(state.owner, .normalLoop)
        XCTAssertTrue(state.pendingPumpCommand)
        XCTAssertFalse(state.mayIssueAnotherCommand)
    }

    func testReturnToNormalDoesNotImplyDoseHistoryReconciled() {
        var state = LoKeyAdaptive.HandoffState()
        XCTAssertTrue(state.requestParkControl())
        state.doseHistoryReconciled = false
        state.returnToNormalLoop()
        XCTAssertFalse(state.mayIssueAnotherCommand)
    }

    func testCodableSnapshotAndEvaluationForReplay() throws {
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()
        encoder.dateEncodingStrategy = .iso8601
        decoder.dateDecodingStrategy = .iso8601
        let original = snapshot()
        let received = try decoder.decode(
            LoKeyAdaptive.Snapshot.self, from: encoder.encode(original)
        )
        let decision = engine.evaluate(received)
        XCTAssertTrue(decision.eligible)
        let roundTripped = try decoder.decode(
            LoKeyAdaptive.Evaluation.self, from: encoder.encode(decision)
        )
        XCTAssertEqual(roundTripped.bias, .center)
        XCTAssertNil(roundTripped.blocker)
    }
}
