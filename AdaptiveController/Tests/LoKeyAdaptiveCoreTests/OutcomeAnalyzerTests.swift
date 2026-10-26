import Foundation
import XCTest
@testable import LoKeyAdaptiveCore

final class OutcomeAnalyzerTests: XCTestCase {
    let anchor = Date(timeIntervalSince1970: 1_700_000_000)
    let policy = LoKeyAdaptive.Controller()

    func cycle(offsetMinutes: Int, glucose: Double, predictions: [(Int, Double)]) -> LoKeyAdaptive.RecordedCycle {
        let t = anchor.addingTimeInterval(TimeInterval(offsetMinutes * 60))
        let snapshot = LoKeyAdaptive.Snapshot(
            observedAt: t,
            parkModeActive: true,
            automaticDosingEnabled: true,
            target: .init(lowMgDl: 120, highMgDl: 150),
            latestGlucose: .init(timestamp: t, glucoseMgDl: glucose),
            loopCompletedAt: t,
            predictedGlucose: predictions.map {
                .init(timestamp: t.addingTimeInterval(TimeInterval($0.0 * 60)), glucoseMgDl: $0.1)
            },
            recordedIOBUnits: 1.5,
            insulinHistoryReconciled: true,
            deliveryCertainty: .confirmed
        )
        return .init(snapshot: snapshot, evaluation: policy.evaluate(snapshot))
    }

    func testMeasuresActualErrorWithoutAttributingToShadow() {
        let original = cycle(offsetMinutes: 0, glucose: 130,
                             predictions: [(0,130), (10,140), (30,150), (60,160)])
        let actual30 = cycle(offsetMinutes: 30, glucose: 142, predictions: [])
        let actual60 = cycle(offsetMinutes: 60, glucose: 155, predictions: [])
        let report = LoKeyAdaptive.OutcomeAnalyzer().analyze([actual60, original, actual30])
        XCTAssertEqual(report.cycleCount, 3)
        let thirty = report.outcomes.first { $0.sourceTimestamp == anchor && $0.horizonMinutes == 30 }
        XCTAssertEqual(thirty?.predictedMgDl, 150)
        XCTAssertEqual(thirty?.observedMgDl, 142)
        XCTAssertEqual(thirty?.errorMgDl, -8)
        let sixty = report.outcomes.first { $0.sourceTimestamp == anchor && $0.horizonMinutes == 60 }
        XCTAssertEqual(sixty?.absoluteErrorMgDl, 5)
        XCTAssertEqual(report.meanAbsoluteError(horizonMinutes: 30), 8)
    }

    func testNeverInventsMissingOutcomes() {
        let original = cycle(offsetMinutes: 0, glucose: 130, predictions: [(30,145),(60,140)])
        let later = cycle(offsetMinutes: 80, glucose: 138, predictions: [])
        XCTAssertTrue(LoKeyAdaptive.OutcomeAnalyzer().analyze([original, later]).outcomes.isEmpty)
    }

    func testCannotCompareAlternativeDosesWithObservedOutcome() {
        let source = cycle(offsetMinutes: 0, glucose: 130, predictions: [(30,162)])
        let actual = cycle(offsetMinutes: 30, glucose: 150, predictions: [])
        let report = LoKeyAdaptive.OutcomeAnalyzer().analyze([source, actual])
        XCTAssertEqual(report.outcomes.count, 1)
        XCTAssertEqual(report.outcomes[0].sourceBias, .unavailable)
        // Only normal Loop's forecast-vs-observed error exists here; the
        // alternative target's delivered-insulin outcome cannot be observed.
        XCTAssertEqual(report.outcomes[0].absoluteErrorMgDl, 12)
    }
}
