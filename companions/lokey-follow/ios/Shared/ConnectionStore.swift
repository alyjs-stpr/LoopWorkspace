import Foundation
import Security

struct Connection: Codable, Equatable { let url: URL; let token: String }
enum ConnectionStore {
    private static var query: [String: Any] {
        // A single Keychain access group is shared by the app and extension.
        // Xcode resolves the team's prefix in each target's Info.plist.
        var q: [String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:"net.lokey.follow.connection", kSecAttrAccount as String:"readable"]
        if let group=Bundle.main.object(forInfoDictionaryKey:"FollowKeychainGroup") as? String { q[kSecAttrAccessGroup as String]=group }
        return q
    }
    static func read() -> Connection? {
        var q=query; q[kSecReturnData as String]=true; q[kSecMatchLimit as String]=kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q,&result)==errSecSuccess, let data=result as? Data else { return nil }
        return try? JSONDecoder().decode(Connection.self,from:data)
    }
    static func save(_ c: Connection) throws {
        _ = try NightscoutParser.validateURL(c.url.absoluteString)
        guard !c.token.isEmpty, !c.token.contains("\n"), !c.token.contains("\r") else { throw ParseError.invalidURL }
        let data=try JSONEncoder().encode(c)
        let attributes: [String:Any]=[kSecValueData as String:data,kSecAttrAccessible as String:kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status=SecItemUpdate(query as CFDictionary,attributes as CFDictionary)
        if status == errSecItemNotFound { var q=query; attributes.forEach { q[$0.key]=$0.value }; guard SecItemAdd(q as CFDictionary,nil)==errSecSuccess else { throw ParseError.invalidResponse } }
        else if status != errSecSuccess { throw ParseError.invalidResponse }
        clearCache()
    }
    static func disconnect() { SecItemDelete(query as CFDictionary); clearCache() }
    private static var cacheURL: URL? { FileManager.default.containerURL(forSecurityApplicationGroupIdentifier:"group.net.lokey.follow")?.appendingPathComponent("snapshot.json") }
    static func cache(_ snapshot: Snapshot, for c: Connection) {
        guard read()==c, let url=cacheURL, let data=try? JSONEncoder().encode(snapshot) else { return }
        try? data.write(to:url,options:[.atomic,.completeFileProtectionUntilFirstUserAuthentication])
    }
    static func cached() -> Snapshot? { guard let url=cacheURL, let data=try? Data(contentsOf:url) else { return nil }; return try? JSONDecoder().decode(Snapshot.self,from:data) }
    static func clearCache() { if let url=cacheURL { try? FileManager.default.removeItem(at:url) } }
}
final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}
enum NightscoutClient {
    static func fetch(_ c: Connection) async throws -> Snapshot {
        let now=Date()
        let session=URLSession(configuration:.ephemeral,delegate:NoRedirectDelegate(),delegateQueue:nil)
        defer { session.finishTasksAndInvalidate() }
        func get(_ path: String, _ items: [URLQueryItem]) async throws -> Data {
            var components=URLComponents(url:c.url,resolvingAgainstBaseURL:false)!
            components.path += path; components.queryItems=items
            var request=URLRequest(url:components.url!,timeoutInterval:15)
            request.setValue(c.token,forHTTPHeaderField:"API-SECRET"); request.setValue("application/json",forHTTPHeaderField:"Accept")
            let (data,response)=try await session.data(for:request)
            guard (response as? HTTPURLResponse)?.statusCode==200, data.count<4_000_000 else { throw ParseError.invalidResponse }; return data
        }
        let f=ISO8601DateFormatter()
        async let entries=get("/api/v1/entries/sgv.json",[.init(name:"count",value:"1000"),.init(name:"find[date][$gte]",value:String(Int(now.addingTimeInterval(-86400).timeIntervalSince1970*1000)))])
        async let statuses=get("/api/v1/devicestatus.json",[.init(name:"count",value:"100")])
        async let doses=get("/api/v1/treatments.json",[.init(name:"count",value:"1000"),.init(name:"find[created_at][$gte]",value:f.string(from:now.addingTimeInterval(-21600)))])
        let snapshot=try await NightscoutParser.parse(entries:entries,statuses:statuses,treatments:doses,now:now)
        ConnectionStore.cache(snapshot,for:c); return snapshot
    }
}
