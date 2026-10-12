import Foundation
import CoreFoundation

public struct Point: Codable, Equatable, Identifiable {
    public let date: Date
    public let value: Double
    public var id: Date { date }
    public init(date: Date, value: Double) { self.date = date; self.value = value }
}
public struct Treatment: Codable, Identifiable {
    public let date: Date
    public let insulin: Double?
    public let rate: Double?
    public let duration: Double
    public let suspended: Bool
    public var id: String { "\(date.timeIntervalSince1970):\(insulin ?? -1):\(rate ?? -1)" }
}
public struct Snapshot: Codable {
    public let glucose: [Point]
    public let direction: String
    public let loopDate: Date?
    public let iob: Point?
    public let forecast: [Point]
    public let treatments: [Treatment]
    public let failure: String?
    public let fetchedAt: Date
    public var latest: Point? { glucose.last }
    public static func fresh(_ date: Date?, now: Date) -> Bool {
        guard let date else { return false }; return (-60...600).contains(now.timeIntervalSince(date))
    }
    public var delta: (value: Double, minutes: Double)? {
        guard glucose.count >= 2 else { return nil }
        let a = glucose[glucose.count - 2], b = glucose[glucose.count - 1]
        let minutes = b.date.timeIntervalSince(a.date) / 60
        return (2...10).contains(minutes) ? (b.value-a.value, minutes) : nil
    }
    public func prediction(now: Date) -> [Point] {
        guard Self.fresh(loopDate, now: now), Self.fresh(forecast.first?.date, now: now), failure == nil else { return [] }; return forecast
    }
    public func activeTemp(now: Date) -> Treatment? {
        guard Self.fresh(loopDate, now: now), let last = treatments.last(where: { $0.rate != nil && $0.date <= now }),
              last.duration > 0, now < last.date.addingTimeInterval(last.duration * 60) else { return nil }; return last
    }
    public func iobText(now: Date) -> String {
        guard let iob, Self.fresh(iob.date, now: now) else { return "—" }; return String(format: "%.2f U", iob.value)
    }
    public var glucoseText: String { latest.map { String(Int($0.value.rounded())) } ?? "—" }
    public var arrow: String {
        ["DoubleUp":"⇈", "SingleUp":"↑", "FortyFiveUp":"↗", "Flat":"→", "FortyFiveDown":"↘", "SingleDown":"↓", "DoubleDown":"⇊"][direction] ?? ""
    }
}
public enum ParseError: Error { case invalidURL, invalidResponse }
public enum NightscoutParser {
    public static func validateURL(_ raw: String) throws -> URL {
        guard let c = URLComponents(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)), c.scheme == "https", let host=c.host, !host.isEmpty,
              c.user == nil, c.password == nil, c.query == nil, c.fragment == nil,
              let url = c.url else { throw ParseError.invalidURL }
        return URL(string: url.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")))!
    }
    public static func timestamp(_ raw: Any?) -> Date? {
        if let n = raw as? NSNumber, n.doubleValue > 1_000_000_000_000 { return Date(timeIntervalSince1970: n.doubleValue / 1000) }
        guard let s = raw as? String else { return nil }
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date=f.date(from:s) { return date }; f.formatOptions = [.withInternetDateTime]; return f.date(from:s)
    }
    static func number(_ j: [String: Any], _ key: String) -> Double? {
        guard let n = j[key] as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(), n.doubleValue.isFinite else { return nil }; return n.doubleValue
    }
    public static func parse(entries: Data, statuses: Data, treatments: Data, now: Date) throws -> Snapshot {
        func rows(_ data: Data) throws -> [[String: Any]] {
            guard let rows=try JSONSerialization.jsonObject(with:data) as? [[String:Any]] else { throw ParseError.invalidResponse }; return rows
        }
        let entryRows=try rows(entries)
        var seenDates=Set<Date>()
        let glucose=entryRows.compactMap { j -> Point? in
            guard let value=number(j,"sgv"), (20...600).contains(value), let date=timestamp(j["date"]) ?? timestamp(j["dateString"]),
                  date <= now.addingTimeInterval(60), date >= now.addingTimeInterval(-86400), seenDates.insert(date).inserted else { return nil }; return Point(date:date,value:value)
        }.sorted { $0.date < $1.date }
        let direction=entryRows.first { (timestamp($0["date"]) ?? timestamp($0["dateString"])) == glucose.last?.date }?["direction"] as? String ?? ""
        let loop=try rows(statuses).compactMap { $0["loop"] as? [String:Any] }.filter { j in
            guard let date=timestamp(j["timestamp"]) else { return false }; return date <= now.addingTimeInterval(60)
        }.max { timestamp($0["timestamp"])! < timestamp($1["timestamp"])! }
        let loopDate=timestamp(loop?["timestamp"])
        let iob=(loop?["iob"] as? [String:Any]).flatMap { j -> Point? in
            guard let date=timestamp(j["timestamp"]), let value=number(j,"iob") else { return nil }; return Point(date:date,value:value)
        }
        var forecast=[Point]()
        if let predicted=loop?["predicted"] as? [String:Any], let start=timestamp(predicted["startDate"]), let values=predicted["values"] as? [Any] {
            forecast=values.prefix(145).enumerated().compactMap { index,raw in
                guard let value=number(["v":raw],"v"), value > 0 else { return nil }; return Point(date:start.addingTimeInterval(Double(index)*300),value:value)
            }
        }
        var seen=Set<String>()
        let doses=try rows(treatments).compactMap { j -> Treatment? in
            guard let date=timestamp(j["timestamp"]) ?? timestamp(j["created_at"]), date <= now.addingTimeInterval(60), date >= now.addingTimeInterval(-21600) else { return nil }
            let type=j["eventType"] as? String ?? ""
            let insulin=["Correction Bolus","Meal Bolus","Bolus","Combo Bolus"].contains(type) ? number(j,"insulin").flatMap { $0 >= 0 ? $0 : nil } : nil
            let rate=type == "Temp Basal" && (j["temp"] as? String ?? "absolute") == "absolute" ? (number(j,"absolute") ?? number(j,"rate")).flatMap { $0 >= 0 ? $0 : nil } : nil
            guard insulin != nil || rate != nil else { return nil }
            let duration=number(j,"duration") ?? 0
            let sync=j["syncIdentifier"] as? String ?? ""
            let id=sync.isEmpty ? "\(date):\(type):\(insulin ?? -1):\(rate ?? -1):\(duration)" : sync
            guard seen.insert(id).inserted else { return nil }
            return Treatment(date:date,insulin:insulin,rate:rate,duration:duration,suspended:j["reason"] as? String == "suspend")
        }.sorted { $0.date < $1.date }
        let failure=(loop?["failureReason"] as? String).flatMap { $0.isEmpty ? nil : $0 }
        return Snapshot(glucose:glucose,direction:direction,loopDate:loopDate,iob:iob,forecast:forecast,treatments:doses,failure:failure,fetchedAt:now)
    }
}
