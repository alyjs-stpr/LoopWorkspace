import XCTest
@testable import FollowCore
final class SnapshotTests: XCTestCase {
    let now=ISO8601DateFormatter().date(from:"2026-10-12T14:00:00Z")!
    let status=#"[{"loop":{"timestamp":"2026-10-12T14:00:00Z","iob":{"timestamp":"2026-10-12T13:59:00Z","iob":-0.35},"predicted":{"startDate":"2026-10-12T14:00:00Z","values":[142,151,160]},"enacted":{"rate":0,"duration":0}}}]"#
    func parse(_ entries: String="[]",_ statuses: String="[]",_ doses: String="[]") throws -> Snapshot { try NightscoutParser.parse(entries:Data(entries.utf8),statuses:Data(statuses.utf8),treatments:Data(doses.utf8),now:now) }
    func testActualIntervalSortingAndDeduplication() throws {
        let s=try parse(#"[{"sgv":142,"dateString":"2026-10-12T14:00:00Z","direction":"Flat"},{"sgv":134,"dateString":"2026-10-12T13:54:00Z"},{"sgv":134,"dateString":"2026-10-12T13:54:00Z"}]"#)
        XCTAssertEqual(s.glucose.count,2); XCTAssertEqual(s.delta?.value,8); XCTAssertEqual(s.delta?.minutes,6); XCTAssertEqual(s.arrow,"→")
    }
    func testGapIsNotFiveMinuteDelta() throws { XCTAssertNil(try parse(#"[{"sgv":142,"dateString":"2026-10-12T14:00:00Z"},{"sgv":134,"dateString":"2026-10-12T13:45:00Z"}]"#).delta) }
    func testNegativeIOBAndForecastExpiry() throws {
        let s=try parse("[]",status)
        XCTAssertEqual(s.iob?.value,-0.35); XCTAssertEqual(s.iobText(now:now),"-0.35 U"); XCTAssertEqual(s.forecast[1].date.timeIntervalSince(s.forecast[0].date),300)
        XCTAssertNil(s.activeTemp(now:now)); XCTAssertEqual(s.prediction(now:now).count,3); XCTAssertTrue(s.prediction(now:now.addingTimeInterval(601)).isEmpty)
    }
    func testNewestLoopDoesNotResurrectOldIOB() throws {
        let s=try parse("[]",String(status.dropLast()) + #",{"loop":{"timestamp":"2026-10-12T14:00:30Z"}}]"#)
        XCTAssertNil(s.iob); XCTAssertTrue(s.forecast.isEmpty)
    }
    func testOldIOBAndForecastWithFreshLoop() throws {
        let old=status.replacingOccurrences(of:"13:59:00",with:"13:30:00").replacingOccurrences(of:#""startDate":"2026-10-12T14:00:00Z""#,with:#""startDate":"2026-10-12T13:30:00Z""#)
        let s=try parse("[]",old); XCTAssertEqual(s.iobText(now:now),"—"); XCTAssertTrue(s.prediction(now:now).isEmpty)
    }
    func testCancellationAndDeduplication() throws {
        let first=#"{"eventType":"Temp Basal","created_at":"2026-10-12T13:50:00Z","absolute":1.25,"duration":30,"syncIdentifier":"a"}"#
        let cancel=#"{"eventType":"Temp Basal","created_at":"2026-10-12T13:59:00Z","absolute":0,"duration":0}"#
        let s=try parse("[]",status,"[\(first),\(first),\(cancel)]"); XCTAssertEqual(s.treatments.count,2); XCTAssertNil(s.activeTemp(now:now))
    }
    func testSuspendAndBolus() throws {
        let s=try parse("[]",status,#"[{"eventType":"Temp Basal","created_at":"2026-10-12T13:59:00Z","absolute":0,"duration":30,"reason":"suspend"},{"eventType":"Correction Bolus","created_at":"2026-10-12T13:58:00Z","insulin":2.5}]"#)
        XCTAssertEqual(s.activeTemp(now:now)?.rate,0); XCTAssertEqual(s.activeTemp(now:now)?.suspended,true); XCTAssertEqual(s.treatments.first?.insulin,2.5)
    }
    func testInvalidAndFutureValuesRejected() throws {
        let s=try parse(#"[{"sgv":142,"dateString":"2026-10-12T14:02:00Z"},{"sgv":null,"dateString":"2026-10-12T14:00:00Z"},{"sgv":"142","dateString":"2026-10-12T14:00:00Z"},{"sgv":true,"dateString":"2026-10-12T14:00:00Z"}]"#)
        XCTAssertTrue(s.glucose.isEmpty); XCTAssertFalse(Snapshot.fresh(now.addingTimeInterval(120),now:now))
    }
    func testURLValidation() throws {
        XCTAssertEqual(try NightscoutParser.validateURL("https://example.org/path/").absoluteString,"https://example.org/path")
        for url in ["http://example.org","https://admin:secret@example.org","https://example.org?token=a","https://example.org#token"] { XCTAssertThrowsError(try NightscoutParser.validateURL(url)) }
    }
}
