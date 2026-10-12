import SwiftUI
import Charts
import WidgetKit

@main struct LoKeyFollowApp: App { var body: some Scene { WindowGroup { DashboardView().preferredColorScheme(.dark) } } }
@MainActor final class DashboardModel: ObservableObject {
    @Published var snapshot=ConnectionStore.cached()
    @Published var message="Connect your private Nightscout site to begin."
    private var loading=false
    func refresh() async {
        guard !loading, let c=ConnectionStore.read() else { return }
        loading=true; defer { loading=false }
        do {
            let s=try await NightscoutClient.fetch(c)
            guard !Task.isCancelled, ConnectionStore.read()==c else { return }
            snapshot=s; message="Last sync \(s.fetchedAt.formatted(date:.omitted,time:.shortened))"; WidgetCenter.shared.reloadAllTimelines()
        } catch { if !Task.isCancelled { message="Unable to refresh. Check your connection or readable token. Saved readings may be shown." } }
    }
    func reset() { snapshot=nil; message="Connection changed; refresh to verify."; WidgetCenter.shared.reloadAllTimelines() }
}
struct DashboardView: View {
    @StateObject private var model=DashboardModel()
    @Environment(\.scenePhase) private var scenePhase
    @State private var screen=0
    @State private var settings=false
    @AppStorage("showGraph") private var showGraph=true
    @AppStorage("showInsulin") private var showInsulin=true
    @AppStorage("keepAwake") private var keepAwake=true
    var body: some View {
        NavigationStack {
            TimelineView(.periodic(from:.now,by:30)) { context in
                ScrollView {
                    VStack(alignment:.leading,spacing:18) {
                        Picker("Screen",selection:$screen) { Text("Dashboard").tag(0); Text("Display").tag(1); Text("Widgets").tag(2) }.pickerStyle(.segmented)
                        if screen==2 { widgets } else { dashboard(now:context.date) }
                        Text(model.message).font(.caption).foregroundStyle(.secondary)
                        Button("Refresh") { Task { await model.refresh() } }.buttonStyle(.borderedProminent).tint(FollowTheme.purple)
                    }.padding(20).frame(maxWidth:900)
                }.frame(maxWidth:.infinity).background(FollowTheme.background)
            }
            .navigationTitle("LoKey Follow").navigationBarTitleDisplayMode(.inline)
            .toolbar { Button("Connection",systemImage:"gearshape") { settings=true } }
            .sheet(isPresented:$settings) { ConnectionView { model.reset(); Task { await model.refresh() } } }
            .task(id:scenePhase) {
                updateAwake()
                guard scenePhase == .active else { return }
                while !Task.isCancelled { await model.refresh(); do { try await Task.sleep(for:.seconds(60)) } catch { break } }
            }
            .onChange(of:screen) { _,_ in updateAwake() }
            .onChange(of:keepAwake) { _,_ in updateAwake() }
            .onDisappear { UIApplication.shared.isIdleTimerDisabled=false }
        }
    }
    private func updateAwake() { UIApplication.shared.isIdleTimerDisabled = screen==1 && keepAwake && scenePhase == .active }
    private func time(_ date: Date?) -> String { date?.formatted(date:.omitted,time:.shortened) ?? "—" }
    private func metric(_ label: String, _ value: String, color: Color, detail: String = "") -> some View {
        VStack(alignment:.leading,spacing:6) {
            Text(label).font(.subheadline).foregroundStyle(.secondary)
            Text(value).font(.system(size:screen==1 ? 38 : 30,weight:.semibold,design:.rounded)).foregroundStyle(color).minimumScaleFactor(0.5)
            if !detail.isEmpty { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }.frame(maxWidth:.infinity,alignment:.leading).padding(18).background(FollowTheme.card,in:RoundedRectangle(cornerRadius:22))
    }
    @ViewBuilder private func dashboard(now: Date) -> some View {
        let s=model.snapshot
        let fresh=Snapshot.fresh(s?.latest?.date,now:now)
        Text("\(fresh ? "Glucose reading" : "STALE / NO DATA · reading") \(time(s?.latest?.date))").font(.subheadline).foregroundStyle(fresh ? Color.secondary : Color.orange)
        HStack(alignment:.lastTextBaseline) {
            Text(s?.glucoseText ?? "—").font(.system(size:screen==1 ? 120 : 84,weight:.bold,design:.rounded)).minimumScaleFactor(0.4)
            Text(s?.arrow ?? "").font(.system(size:40))
            Text("mg/dL").font(.subheadline).foregroundStyle(.secondary)
        }.foregroundStyle(FollowTheme.purple)
        let delta=fresh ? s?.delta : nil
        metric("Glucose change",delta.map { String(format:"%+.0f mg/dL in %.1f min",$0.value,$0.minutes) } ?? "—",color:FollowTheme.purple,
               detail:delta.map { String(format:"%+.2f mg/dL/min",$0.value/$0.minutes) } ?? "Needs two recent readings 2–10 minutes apart.")
        metric("Insulin on board · from Loop",s?.iobText(now:now) ?? "—",color:FollowTheme.green,detail:"IOB timestamp \(time(s?.iob?.date))")
        let temp=s?.activeTemp(now:now)
        metric("Active temp basal",temp.map { $0.suspended ? "Suspended · 0 U/hr" : String(format:"%.2f U/hr",$0.rate ?? 0) } ?? "—",color:FollowTheme.green,detail:"Scheduled basal is not inferred.")
        if showGraph, let s {
            Text("Glucose & Loop prediction").font(.headline).foregroundStyle(FollowTheme.purple)
            GlucoseChart(snapshot:s,now:now).frame(height:screen==1 ? 260 : 200)
            let prediction=s.prediction(now:now).filter { $0.date >= now }
            if let last=prediction.last { Text("Eventually \(Int(last.value.rounded())) mg/dL · \(time(last.date))\nPredicted low \(Int((prediction.map(\.value).min() ?? last.value).rounded())) mg/dL").font(.subheadline) }
            else { Text("No current Loop prediction").font(.subheadline).foregroundStyle(.secondary) }
        }
        Text("Loop update \(time(s?.loopDate))\(Snapshot.fresh(s?.loopDate,now:now) ? "" : " · STALE")\(s?.failure == nil ? "" : " · Loop reported an error")").font(.caption).foregroundStyle(.secondary)
        if screen==0 && showInsulin {
            Text("Insulin history · last 6 hours").font(.headline).foregroundStyle(FollowTheme.green)
            if s?.treatments.isEmpty != false { Text("No uploaded treatments available.").foregroundStyle(.secondary) }
            ForEach(Array((s?.treatments ?? []).suffix(20).reversed())) { dose in
                HStack { Text(time(dose.date)); Spacer(); Text(dose.insulin.map { String(format:"Bolus %.2f U",$0) } ?? (dose.duration <= 0 ? "Temp basal cancelled" : dose.suspended ? "Suspend" : String(format:"Temp %.2f U/hr · %.0f min",dose.rate ?? 0,dose.duration))) }.font(.subheadline).foregroundStyle(FollowTheme.green)
            }
        }
    }
    private var widgets: some View {
        VStack(alignment:.leading,spacing:18) {
            metric("Your home screen", "Glucose · Dashboard",color:FollowTheme.purple,detail:"Hold the home screen → Edit → Add Widget → LoKey Follow. Choose small or medium. Lock-screen editing also offers circular and rectangular widgets.")
            Text("Widgets show source timestamps. iOS controls refresh timing; tap to open Follow for a fresh check.")
            Toggle("Show glucose graph",isOn:$showGraph)
            Toggle("Show insulin history",isOn:$showInsulin)
            Toggle("Keep screen awake in Display mode",isOn:$keepAwake)
        }.tint(FollowTheme.green)
    }
}
struct GlucoseChart: View {
    let snapshot: Snapshot
    let now: Date
    var body: some View {
        let history=snapshot.glucose.filter { $0.date >= now.addingTimeInterval(-10800) }
        let forecast=snapshot.prediction(now:now).filter { $0.date >= now.addingTimeInterval(-300) }
        Chart {
            RectangleMark(yStart:.value("Lower",70),yEnd:.value("Upper",180)).foregroundStyle(FollowTheme.purple.opacity(0.10))
            ForEach(history) { p in PointMark(x:.value("Time",p.date),y:.value("Glucose",p.value)).foregroundStyle(FollowTheme.purple).symbolSize(18) }
            ForEach(forecast) { p in LineMark(x:.value("Time",p.date),y:.value("Forecast",p.value)).foregroundStyle(FollowTheme.purple).lineStyle(StrokeStyle(lineWidth:2,dash:[5,5])) }
        }.chartXAxis { AxisMarks(values:.automatic(desiredCount:4)) { AxisValueLabel(format:.dateTime.hour().minute()); AxisGridLine() } }
    }
}
struct ConnectionView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var url=ConnectionStore.read()?.url.absoluteString ?? ""
    @State private var token=""
    @State private var error=""
    let changed: () -> Void
    var body: some View {
        NavigationStack {
            Form {
                Section("Private Nightscout") {
                    TextField("HTTPS base URL",text:$url).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("This device's readable token",text:$token).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Use a separate readable token for each phone. Keep the administrator secret in Nightscout and Loop.").font(.caption)
                }
                if !error.isEmpty { Text(error).foregroundStyle(.orange) }
                Button("Save connection") {
                    do { try ConnectionStore.save(Connection(url:NightscoutParser.validateURL(url),token:token.trimmingCharacters(in:.whitespacesAndNewlines))); changed(); dismiss() }
                    catch { self.error="Enter a valid HTTPS URL and readable token; check Keychain/App Group signing if saving fails." }
                }
                Button("Disconnect",role:.destructive) { ConnectionStore.disconnect(); changed(); dismiss() }
            }.navigationTitle("Nightscout").toolbar { Button("Cancel") { dismiss() } }
        }
    }
}
