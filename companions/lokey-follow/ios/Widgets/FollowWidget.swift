import SwiftUI
import WidgetKit

struct FollowEntry: TimelineEntry { let date: Date; let snapshot: Snapshot? }
struct FollowProvider: TimelineProvider {
    func placeholder(in context: Context) -> FollowEntry { FollowEntry(date:.now,snapshot:nil) }
    func getSnapshot(in context: Context, completion: @escaping (FollowEntry) -> Void) { completion(FollowEntry(date:.now,snapshot:ConnectionStore.cached())) }
    func getTimeline(in context: Context, completion: @escaping (Timeline<FollowEntry>) -> Void) {
        Task {
            let c=ConnectionStore.read()
            var s: Snapshot?=nil
            if let c { s=(try? await NightscoutClient.fetch(c)) ?? ConnectionStore.cached(); if ConnectionStore.read() != c { s=nil } }
            let now=Date()
            var dates=[now]
            // Explicit expiry entries avoid keeping fresh IOB/forecasts visible until the next network reload.
            for time in [s?.latest?.date,s?.iob?.date,s?.loopDate,s?.forecast.first?.date].compactMap({ $0 }) {
                let expiry=time.addingTimeInterval(601); if expiry > now { dates.append(expiry) }
            }
            let entries=Set(dates).sorted().map { FollowEntry(date:$0,snapshot:s) }
            completion(Timeline(entries:entries,policy:.after(now.addingTimeInterval(900))))
        }
    }
}
struct FollowWidgetView: View {
    let entry: FollowEntry
    @Environment(\.widgetFamily) private var family
    var body: some View {
        let s=entry.snapshot
        let fresh=Snapshot.fresh(s?.latest?.date,now:entry.date)
        VStack(alignment:.leading,spacing:4) {
            if family == .systemSmall || family == .systemMedium { Text("LoKey Follow").font(.caption).foregroundStyle(FollowTheme.purple) }
            Text("\(s?.glucoseText ?? "—") \(fresh ? s?.arrow ?? "" : "")").font(.system(size:family == .accessoryCircular ? 22 : 38,weight:.bold,design:.rounded)).foregroundStyle(FollowTheme.purple).minimumScaleFactor(0.5).lineLimit(1)
            Text(fresh ? "mg/dL · snapshot" : "STALE / NO DATA").font(.caption2)
            if family != .accessoryCircular {
                Text("IOB \(s?.iobText(now:entry.date) ?? "—")").font(.subheadline).foregroundStyle(FollowTheme.green)
                if let time=s?.latest?.date { Text("Reading \(time.formatted(date:.abbreviated,time:.shortened))").font(.caption2) }
                if family == .systemMedium, fresh, let d=s?.delta { Text(String(format:"%+.0f mg/dL in %.1f min",d.value,d.minutes)).font(.caption) }
            } else if let time=s?.latest?.date { Text(time,style:.time).font(.system(size:8)) }
        }.privacySensitive().containerBackground(FollowTheme.card,for:.widget).widgetURL(URL(string:"lokeyfollow://dashboard"))
    }
}
@main struct FollowWidget: Widget {
    let kind="net.lokey.follow.widgets"
    var body: some WidgetConfiguration {
        StaticConfiguration(kind:kind,provider:FollowProvider()) { FollowWidgetView(entry:$0) }
            .configurationDisplayName("LoKey Follow").description("Glucose, change and Loop IOB with source timestamps.")
            .supportedFamilies([.systemSmall,.systemMedium,.accessoryRectangular,.accessoryCircular])
    }
}
