#!/usr/bin/env python3
"""Install print-friendly Glooko-style LoKey AGP + one-page-per-day graphs.

No report UI code may send pump commands. Source installer runs after
install_lokey_clinical_history_v2.py. It leaves the old PDF generator intact
for comparison, but the clinical export button invokes V2 only.
"""
from pathlib import Path
PATH = Path("Loop/Loop/Views/SettingsView.swift")

PDF = r'''

// MARK: - LoKey clinician PDF V2: clinical AGP, daily glucose + carb + insulin graphs
// Glooko-style organization; original LoKey layout and brand, no Glooko assets.
private enum LoKeyClinicalPDFV2 {
    private static let navy = UIColor(red: 0.13, green: 0.18, blue: 0.27, alpha: 1)
    private static let violet = UIColor(red: 0.47, green: 0.28, blue: 0.70, alpha: 1)
    private static let green = UIColor(red: 0.14, green: 0.62, blue: 0.37, alpha: 1)
    private static let cyan = UIColor(red: 0.00, green: 0.62, blue: 0.71, alpha: 1)
    private static let amber = UIColor(red: 0.93, green: 0.59, blue: 0.10, alpha: 1)
    private static let red = UIColor(red: 0.83, green: 0.24, blue: 0.30, alpha: 1)
    private static let gray = UIColor(white: 0.42, alpha: 1)
    private static let pale = UIColor(white: 0.94, alpha: 1)
    private static let width: CGFloat = 612
    private static let height: CGFloat = 792

    private static func text(_ string: String, x: CGFloat, y: CGFloat,
                             w: CGFloat, h: CGFloat = 22, size: CGFloat = 10,
                             bold: Bool = false, color: UIColor = navy) {
        let font = bold ? UIFont.boldSystemFont(ofSize: size) : UIFont.systemFont(ofSize: size)
        (string as NSString).draw(in: CGRect(x: x, y: y, width: w, height: h),
                                 withAttributes: [.font: font, .foregroundColor: color])
    }

    private static func rule(_ y: CGFloat) {
        let p = UIBezierPath()
        p.move(to: CGPoint(x: 38, y: y)); p.addLine(to: CGPoint(x: 574, y: y))
        UIColor(white: 0.85, alpha: 1).setStroke()
        p.lineWidth = 0.6
        p.stroke()
    }

    private static func fill(_ rect: CGRect, color: UIColor, radius: CGFloat = 0) {
        color.setFill()
        UIBezierPath(roundedRect: rect, cornerRadius: radius).fill()
    }

    private static func line(_ first: CGPoint, _ last: CGPoint, color: UIColor,
                             width: CGFloat = 1) {
        let path = UIBezierPath()
        path.move(to: first); path.addLine(to: last)
        color.setStroke(); path.lineWidth = width
        path.stroke()
    }

    private static func header(_ title: String, range: String, page: Int) {
        text("LoKey", x: 38, y: 18, w: 100, size: 22, bold: true, color: violet)
        text("CLINICAL DATA REPORT", x: 405, y: 26, w: 173,
             size: 9, bold: true, color: gray)
        rule(52)
        text(title, x: 38, y: 67, w: 536, size: 18, bold: true)
        text(range, x: 38, y: 93, w: 530, size: 9, color: gray)
        rule(739)
        text("LoKey / Loop + available Apple Health history   •   Not a Glooko report",
             x: 38, y: 749, w: 485, size: 8, color: gray)
        text("Page " + String(page), x: 529, y: 749, w: 45, size: 8, color: gray)
    }

    private static func metric(_ label: String, _ value: String, x: CGFloat,
                               y: CGFloat, w: CGFloat) {
        fill(CGRect(x: x, y: y, width: w, height: 60), color: pale, radius: 7)
        text(label.uppercased(), x: x + 11, y: y + 9, w: w - 18,
             size: 8, color: gray)
        text(value, x: x + 11, y: y + 26, w: w - 19,
             size: 18, bold: true, color: navy)
    }

    private static func formatDate(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "MMM d, yyyy"
        return f.string(from: date)
    }

    private static func pct(_ values: [Double], _ fraction: Double) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        let position = Double(sorted.count - 1) * fraction
        let left = Int(floor(position)), right = Int(ceil(position))
        return sorted[left] + (sorted[right] - sorted[left]) * (position - Double(left))
    }

    private struct Stats {
        let mean: Double?
        let cv: Double?
        let coverage: Double
        let fiveBands: [Double]
        let count: Int
        var tir: Double { fiveBands[2] }
    }

    private static func glucoseStats(_ samples: [StoredGlucoseSample],
                                     start: Date, end: Date) -> Stats {
        let readings = samples.filter {
            $0.startDate >= start && $0.startDate < end &&
            !$0.isDisplayOnly && !$0.wasUserEntered
        }.sorted { $0.startDate < $1.startDate }
        var bins = [Double](repeating: 0, count: 5)
        var weighted = 0.0
        var square = 0.0
        var observed = 0.0
        for (index, sample) in readings.enumerated() {
            let next = index + 1 < readings.count ? readings[index + 1].startDate : end
            let duration = max(0, min(300, min(next, end).timeIntervalSince(sample.startDate)))
            guard duration > 0 else { continue }
            let v = sample.quantity.doubleValue(for: .milligramsPerDeciliter)
            guard v.isFinite && v > 0 else { continue }
            observed += duration
            weighted += v * duration
            square += v * v * duration
            let slot = v < 54 ? 0 : v < 70 ? 1 : v <= 180 ? 2 : v <= 250 ? 3 : 4
            bins[slot] += duration
        }
        let mean = observed > 0 ? weighted / observed : nil
        let sd = observed > 0 ? sqrt(max(0, square / observed - pow(weighted / observed, 2))) : nil
        return Stats(mean: mean, cv: (mean ?? 0) > 0 ? (sd ?? 0) / (mean ?? 1) * 100 : nil,
            coverage: min(1, observed / max(1, end.timeIntervalSince(start))),
            fiveBands: bins.map { observed > 0 ? $0 / observed : 0 },
            count: readings.count)
    }

    private static func glucoseY(_ value: Double, in rect: CGRect) -> CGFloat {
        rect.maxY - CGFloat((max(40, min(350, value)) - 40) / 310) * rect.height
    }

    private static func hourX(_ date: Date, in rect: CGRect) -> CGFloat {
        let cal = Calendar.current
        let c = cal.dateComponents([.hour, .minute, .second], from: date)
        let minutes = Double(c.hour ?? 0) * 60 + Double(c.minute ?? 0) +
                      Double(c.second ?? 0) / 60
        return rect.minX + rect.width * CGFloat(minutes / 1440)
    }

    private static func graphGrid(_ rect: CGRect, withLabels: Bool = true) {
        fill(rect, color: UIColor(white: 0.985, alpha: 1), radius: 4)
        fill(CGRect(x: rect.minX, y: glucoseY(180, in: rect),
                    width: rect.width,
                    height: glucoseY(70, in: rect) - glucoseY(180, in: rect)),
             color: UIColor(red: 0.90, green: 0.96, blue: 0.92, alpha: 1))
        for level in [70.0, 180.0, 250.0, 350.0] {
            let y = glucoseY(level, in: rect)
            line(CGPoint(x: rect.minX, y: y), CGPoint(x: rect.maxX, y: y),
                 color: UIColor(white: 0.80, alpha: 1), width: 0.6)
            if withLabels {
                text(String(Int(level)), x: rect.minX - 34, y: y - 7,
                     w: 32, size: 8, color: gray)
            }
        }
        for hour in stride(from: 0, through: 24, by: 3) {
            let x = rect.minX + rect.width * CGFloat(hour) / 24
            line(CGPoint(x: x, y: rect.minY),
                 CGPoint(x: x, y: rect.maxY),
                 color: UIColor(white: 0.88, alpha: 1), width: 0.5)
            if withLabels {
                text(hour == 24 ? "12AM" : String(format: "%02d", hour),
                     x: x - 11, y: rect.maxY + 6,
                     w: 33, size: 8, color: gray)
            }
        }
    }

    private static func agp(_ readings: [StoredGlucoseSample], rect: CGRect) {
        graphGrid(rect)
        let cal = Calendar.current
        var slots = [[Double]](repeating: [], count: 96)
        for item in readings where !item.isDisplayOnly && !item.wasUserEntered {
            let h = cal.component(.hour, from: item.startDate)
            let m = cal.component(.minute, from: item.startDate)
            let index = h * 4 + m / 15
            let value = item.quantity.doubleValue(for: .milligramsPerDeciliter)
            if index >= 0 && index < 96 && value.isFinite && value > 0 {
                slots[index].append(value)
            }
        }
        func drawBand(_ low: Double, _ high: Double, shade: UIColor) {
            for index in 0..<95 where slots[index].count >= 3 && slots[index+1].count >= 3 {
                let x1 = rect.minX + rect.width * CGFloat(index) / 95
                let x2 = rect.minX + rect.width * CGFloat(index+1) / 95
                let band = UIBezierPath()
                band.move(to: CGPoint(x: x1, y: glucoseY(pct(slots[index],low), in: rect)))
                band.addLine(to: CGPoint(x: x2, y: glucoseY(pct(slots[index+1],low), in: rect)))
                band.addLine(to: CGPoint(x: x2, y: glucoseY(pct(slots[index+1],high), in: rect)))
                band.addLine(to: CGPoint(x: x1, y: glucoseY(pct(slots[index],high), in: rect)))
                band.close()
                fillPath(band, shade)
            }
        }
        drawBand(0.10, 0.90, shade: violet.withAlphaComponent(0.10))
        drawBand(0.25, 0.75, shade: violet.withAlphaComponent(0.23))
        for index in 0..<95 where slots[index].count >= 3 && slots[index+1].count >= 3 {
            let x1 = rect.minX + rect.width * CGFloat(index) / 95
            let x2 = rect.minX + rect.width * CGFloat(index+1) / 95
            line(CGPoint(x: x1,y: glucoseY(pct(slots[index],0.50), in: rect)),
                 CGPoint(x: x2,y: glucoseY(pct(slots[index+1],0.50), in: rect)),
                 color: violet, width: 1.8)
        }
    }

    private static func fillPath(_ path: UIBezierPath, _ color: UIColor) {
        color.setFill()
        path.fill()
    }

    private static func tirBar(_ stats: Stats, rect: CGRect) {
        let colors = [UIColor(red: 0.65, green: 0.06, blue: 0.15, alpha: 1),
                      red, green, amber, UIColor(red: 0.90, green: 0.70, blue: 0.16, alpha: 1)]
        var position = rect.minX
        for i in 0..<5 {
            let width = rect.width * CGFloat(stats.fiveBands[i])
            if width > 0 {
                fill(CGRect(x: position, y: rect.minY, width: width, height: rect.height), color: colors[i])
            }
            position += width
        }
    }

    private static func dayTraces(_ glucose: [StoredGlucoseSample],
                                  start: Date, end: Date, rect: CGRect) {
        graphGrid(rect)
        let values = glucose.filter { $0.startDate >= start && $0.startDate < end }
                            .sorted { $0.startDate < $1.startDate }
        var previous: StoredGlucoseSample?
        for value in values {
            let glucose = value.quantity.doubleValue(for: .milligramsPerDeciliter)
            guard glucose.isFinite && glucose > 0 else { continue }
            let point = CGPoint(x: hourX(value.startDate, in: rect),
                                y: glucoseY(glucose, in: rect))
            if let prev = previous,
               value.startDate.timeIntervalSince(prev.startDate) <= 8*60 {
                let old = prev.quantity.doubleValue(for: .milligramsPerDeciliter)
                let color = glucose < 70 ? red : glucose > 180 ? amber : green
                line(CGPoint(x: hourX(prev.startDate, in: rect),
                             y: glucoseY(old, in: rect)), point, color: color, width: 1.5)
            }
            previous = value
        }
        if values.isEmpty {
            text("No CGM samples available for this day", x: rect.minX + 18,
                 y: rect.midY-8, w: rect.width-25, size: 11, color: gray)
        }
    }

    private static func bolusTypeColor(_ dose: DoseEntry) -> UIColor {
        if dose.automatic == true { return green }
        if dose.automatic == false || dose.wasProgrammedByPumpUI { return violet }
        return amber
    }

    private static func drawDailyTracks(doses: [DoseEntry], carbs: [StoredCarbEntry],
                                        day: Date, end: Date) {
        let origin: CGFloat = 65
        let trackW: CGFloat = 485
        text("CARBS", x: 38, y: 407, w: 70, size: 9, bold: true, color: gray)
        text("BOLUSES", x: 38, y: 481, w: 70, size: 9, bold: true, color: gray)
        text("BASAL RATE", x: 38, y: 552, w: 90, size: 9, bold: true, color: gray)
        let trackRows: [CGFloat] = [430, 505, 584]
        for y in trackRows {
            fill(CGRect(x: origin, y: y, width: trackW, height: 41),
                 color: UIColor(white: 0.974, alpha: 1))
            for hour in stride(from: 0, through: 24, by: 3) {
                let x = origin + trackW * CGFloat(hour)/24
                line(CGPoint(x: x, y: y), CGPoint(x: x, y: y+41),
                     color: UIColor(white: 0.85, alpha: 1), width: 0.5)
            }
        }
        let dayCarbs = carbs.filter { $0.startDate >= day && $0.startDate < end }
        for entry in dayCarbs {
            let grams = entry.quantity.doubleValue(for: .gram())
            let x = hourX(entry.startDate, in: CGRect(x: origin,y: 0,width: trackW,height: 0))
            let h = CGFloat(min(1, grams/80.0)) * 33
            fill(CGRect(x: x-2,y: 469-h,width: 5,height: h), color: cyan, radius: 1)
        }
        let dayDoses = doses.filter { $0.startDate < end && $0.endDate >= day }
        for dose in dayDoses where dose.type == .bolus && !dose.manuallyEntered {
            let amount = dose.unitsInDeliverableIncrements
            let x = hourX(dose.startDate, in: CGRect(x:origin,y:0,width:trackW,height:0))
            let h = CGFloat(min(1,amount/10)) * 33
            fill(CGRect(x:x-2,y:544-h,width: 5,height:h),
                 color: bolusTypeColor(dose),radius: 1)
        }
        for dose in dayDoses where dose.type == .basal || dose.type == .tempBasal {
            let duration = dose.endDate.timeIntervalSince(dose.startDate)
            guard duration > 0 else { continue }
            let clippedStart = max(day, dose.startDate)
            let clippedEnd = min(end, dose.endDate)
            guard clippedEnd > clippedStart else { continue }
            // Midnight belongs at the RIGHT edge of the preceding day.
            // hourX(midnight) returns 0, so this track must use elapsed time.
            let dayLength = max(1.0, end.timeIntervalSince(day))
            let x = origin + trackW * CGFloat(clippedStart.timeIntervalSince(day)/dayLength)
            let w = max(0.8, trackW * CGFloat(clippedEnd.timeIntervalSince(clippedStart)/dayLength))
            let h = CGFloat(min(2.5,max(0,dose.unitsPerHour))/2.5)*33
            fill(CGRect(x:x,y:623-h,width:min(w,origin+trackW-x),height:h),
                 color:green.withAlphaComponent(0.75))
        }
        if dayCarbs.isEmpty {
            text("No carb entries available",x: 310,y: 448,w:230,size:9,color:gray)
        }
        if dayDoses.isEmpty {
            text("No Loop insulin records available",x:300,y:523,w:250,size:9,color:gray)
        }
        text("Cyan: carbs    Green: auto bolus / basal rate    Purple: user bolus    Orange: unknown",
             x: 65, y: 633, w: 500, size: 9, color: gray)
    }

    private static func firstDay(_ date: Date) -> Date {
        Calendar.current.startOfDay(for: date)
    }

    static func make(data: LoKeyClinicV2Data, pods: [LoKeyPodRecord],
                     start: Date, end: Date, settings: TherapySettings,
                     patientName: String) throws -> URL {
        let range = formatDate(start) + " – " + formatDate(end)
        let who = patientName.trimmingCharacters(in: .whitespacesAndNewlines)
        let headedRange = (who.isEmpty ? "" : "Patient: " + who + "  •  ") + range
        let summary = glucoseStats(data.glucose, start: start, end: end)
        let days: [Date] = {
            let count = max(1, Calendar.current.dateComponents([.day], from: firstDay(start),
                                                                 to: firstDay(end)).day! + 1)
            return (0..<min(count,90)).compactMap {
                Calendar.current.date(byAdding:.day, value:$0,to:firstDay(start))
            }
        }()
        let dosedDays = days.map { day -> LoKeyDoseTotals in
            let finish = min(end, Calendar.current.date(byAdding:.day,value:1,to:day)!)
            return LoKeyDoseTotals.sum(data.doses, from: day, to: finish)
        }
        let observedDays = dosedDays.filter { $0.count > 0 }
        let basalMean = observedDays.isEmpty ? nil :
            observedDays.reduce(0) { $0 + $1.basal + $1.automated } / Double(observedDays.count)
        let userMean = observedDays.isEmpty ? nil :
            observedDays.reduce(0) { $0 + $1.initiated } / Double(observedDays.count)
        let unknownMean = observedDays.isEmpty ? nil :
            observedDays.reduce(0) { $0 + $1.unclassified } / Double(observedDays.count)

        let pdf = UIGraphicsPDFRenderer(bounds: CGRect(x:0,y:0,width:width,height:height))
        let bytes = pdf.pdfData { ctx in
            var page = 1
            ctx.beginPage()
            header("Glucose & Insulin Summary", range: headedRange, page: page)
            let meanText = summary.mean.map { String(format:"%.0f mg/dL",$0) } ?? "No data"
            metric("Average Glucose",meanText,x:38,y:127,w:126)
            metric("Time in Range",summary.count>0 ? String(format:"%.1f%%",summary.tir*100) : "No data",x:171,y:127,w:126)
            metric("CGM Active",summary.count>0 ? String(format:"%.1f%%",summary.coverage*100) : "No data",x:304,y:127,w:126)
            let gmi = (summary.coverage>=0.70 && end.timeIntervalSince(start)>=12*86400)
                ? summary.mean.map{ String(format:"%.1f%%",3.31+0.02392*$0) } : nil
            metric("GMI",gmi ?? "Insufficient",x:437,y:127,w:137)
            text("TIME IN GLUCOSE RANGES  (mg/dL)", x:38,y:205,w:540,size:11,bold:true)
            tirBar(summary,rect:CGRect(x:38,y:234,width:536,height:19))
            text(String(format:"<54 %.1f%%  |  54–69 %.1f%%  |  70–180 %.1f%%  |  181–250 %.1f%%  |  >250 %.1f%%",
                 summary.fiveBands[0]*100,summary.fiveBands[1]*100,summary.fiveBands[2]*100,
                 summary.fiveBands[3]*100,summary.fiveBands[4]*100),
                 x:39,y:258,w:535,size:9,color:gray)
            text("AMBULATORY GLUCOSE PROFILE  •  MEDIAN / 25–75% / 10–90%",
                 x:38,y:294,w:535,size:11,bold:true)
            agp(data.glucose,rect:CGRect(x:67,y:323,width:480,height:170))
            text("Green band: 70–180 mg/dL     Violet line: median     Shading: glucose variability",
                 x:65,y:520,w:525,size:9,color:gray)
            rule(550)
            text("INSULIN FROM LOOP", x:38,y:565,w:520,size:12,bold:true)
            if let basalMean, let userMean, let unknownMean {
                metric("Total Basal / Day*",String(format:"%.1f U",basalMean),
                       x:38,y:588,w:164)
                metric("Your Boluses / Day",String(format:"%.1f U",userMean),
                       x:210,y:588,w:164)
                metric("Total Delivery / Day",String(format:"%.1f U",basalMean+userMean+unknownMean),
                       x:382,y:588,w:192)
            } else {
                text("No Loop insulin history for the selected period; cannot calculate daily delivery.",
                     x:38,y:599,w:538,size:10,color:gray)
            }
            text("*Total Basal = pump basal + Loop automated boluses. These components are",
                 x:38,y:667,w:537,size:9,color:gray)
            text("Your Boluses excludes automated and unknown-origin doses. Unknown is in total delivery.",
                 x:38,y:679,w:537,size:9,color:gray)
            text("Local Loop CGM: " + String(data.nativeGlucoseCount) +
                 "   Health CGM: " + String(data.healthGlucoseCount) +
                 "   Local Loop doses: " + String(data.nativeDoseCount) +
                 "   Archived LoopKit doses: " + String(data.healthDoseCount),
                 x:38,y:701,w:537,size:8,color:gray)
            let firstGlucose = data.glucose.first.map { formatDate($0.startDate) } ?? "Unavailable"
            let firstInsulin = data.doses.first.map { formatDate($0.startDate) } ?? "Unavailable"
            text("First CGM in range: " + firstGlucose + "    First Loop insulin in range: " + firstInsulin,
                 x:38,y:715,w:537,size:8,color:gray)

            page += 1
            ctx.beginPage()
            header("Insulin Delivery & Daily Coverage",range:headedRange,page:page)
            text("TOTAL DAILY BASAL = RECORDED BASAL + AUTOMATED BOLUSES",
                 x:38,y:130,w:536,size:11,bold:true,color:violet)
            text("Additional initiated/unknown boluses are shown separately. Missing days are not zero doses.",
                 x:38,y:153,w:536,size:9,color:gray)
            let graph = CGRect(x:73,y:198,width:473,height:260)
            fill(graph,color:UIColor(white:0.977,alpha:1))
            let dailyMax = max(10.0, dosedDays.map{ $0.delivered }.max() ?? 10)
            let barW = graph.width / CGFloat(max(1,days.count))
            for (i, totals) in dosedDays.enumerated() where totals.count>0 {
                let dayBasal = totals.basal + totals.automated
                let yours = totals.initiated
                let unknown = totals.unclassified
                let x = graph.minX + CGFloat(i)*barW + 1
                let w = max(1,barW-2)
                let basalH = graph.height * CGFloat(dayBasal/dailyMax)
                let yourH = graph.height * CGFloat(yours/dailyMax)
                let unknownH = graph.height * CGFloat(unknown/dailyMax)
                fill(CGRect(x:x,y:graph.maxY-basalH,width:w,height:basalH),color:green)
                fill(CGRect(x:x,y:graph.maxY-basalH-yourH,width:w,height:yourH),
                     color:violet)
                fill(CGRect(x:x,y:graph.maxY-basalH-yourH-unknownH,width:w,height:unknownH),
                     color:amber)
            }
            line(CGPoint(x:graph.minX,y:graph.maxY),
                 CGPoint(x:graph.maxX,y:graph.maxY),color:gray)
            text("Green: Total Basal    Violet: Your boluses    Amber: Unknown-origin boluses",
                 x:74,y:472,w:475,size:9,color:gray)
            text("Days with recorded Loop insulin: \(observedDays.count) of \(days.count)",
                 x:74,y:495,w:475,size:11,bold:true)
            let unavailable = days.filter { day in
                let next = Calendar.current.date(byAdding:.day,value:1,to:day)!
                return !data.glucose.contains { $0.startDate>=day && $0.startDate<next }
            }.count
            text("Days without CGM data: \(unavailable)",x:74,y:522,w:475,size:10)
            let otherDays = days.filter { day in
                let next = Calendar.current.date(byAdding:.day,value:1,to:day)!
                return data.externalInsulin.contains { $0.startDate>=day && $0.startDate<next }
            }.count
            if otherDays>0 {
                text("Other-pump Health insulin appears on \(otherDays) day(s), excluded from Loop totals.",
                     x:74,y:544,w:482,size:9,color:gray)
            }
            text("DATA NOTES",x:38,y:590,w:500,size:11,bold:true)
            for (i,note) in data.notes.prefix(5).enumerated() {
                text("• " + note,x:39,y:615+CGFloat(i)*19,w:530,h:17,size:9,color:gray)
            }

            for day in days {
                page += 1
                ctx.beginPage()
                let next = min(end,Calendar.current.date(byAdding:.day,value:1,to:day)!)
                let oneDay = data.glucose.filter { $0.startDate>=day && $0.startDate<next }
                let dayStats = glucoseStats(oneDay,start:day,end:next)
                let totals = LoKeyDoseTotals.sum(data.doses,from:day,to:next)
                header("Daily Overview",range:(who.isEmpty ? "" : who+"  •  ") + formatDate(day),page:page)
                let v=dayStats.mean.map{String(format:"%.0f mg/dL",$0)} ?? "No CGM"
                metric("Avg Glucose",v,x:38,y:122,w:126)
                metric("Time In Range",dayStats.count>0 ? String(format:"%.0f%%",dayStats.tir*100):"No CGM",x:171,y:122,w:126)
                metric("Total Basal*",totals.count>0 ? String(format:"%.1f U",totals.basal+totals.automated):"No data",x:304,y:122,w:126)
                metric("Your Boluses",totals.count>0 ? String(format:"%.1f U",totals.initiated):"No data",x:437,y:122,w:137)
                let dailyCoverage = String(format:"%.0f%%",dayStats.coverage*100)
                text("CGM time covered: " + dailyCoverage +
                     (dayStats.coverage < 0.70 ? "  -  PARTIAL GLUCOSE DAY" : ""),
                     x:39,y:184,w:520,size:8,
                     color: dayStats.coverage < 0.70 ? red : gray)
                text("GLUCOSE  (mg/dL)  •  24-HOUR TRACE",x:38,y:201,w:518,size:11,bold:true)
                dayTraces(oneDay,start:day,end:next,rect:CGRect(x:65,y:231,width:485,height:154))
                drawDailyTracks(doses:data.doses,carbs:data.carbs,day:day,end:next)
                rule(662)
                if totals.count > 0 {
                    text("Pump basal: " + String(format:"%.2f U",totals.basal) +
                         "   +   Automated boluses: " + String(format:"%.2f U",totals.automated) +
                         "   =   Total Daily Basal: " + String(format:"%.2f U",totals.basal+totals.automated),
                         x:38,y:671,w:535,size:10,bold:true)
                    text("Your boluses: " + String(format:"%.2f U",totals.initiated) +
                         "  |  Unknown origin: " + String(format:"%.2f U",totals.unclassified) +
                         "  |  Pump total: " + String(format:"%.2f U",totals.delivered),
                         x:38,y:692,w:535,size:9,color:gray)
                } else {
                    text("NO LOOP INSULIN HISTORY FOR THIS DAY — DO NOT INTERPRET AS ZERO DELIVERY.",
                         x:38,y:671,w:535,size:9,bold:true,color:red)
                }
                let outside = data.externalInsulin.filter { $0.startDate>=day && $0.startDate<next }
                if !outside.isEmpty {
                    text("Other-pump Health insulin present (\(outside.count) entries), excluded from Loop totals.",
                         x:38,y:718,w:535,size:8,color:gray)
                }
            }

            page += 1
            ctx.beginPage()
            header("Pod Usage & Settings",range:headedRange,page:page)
            text("RECORDED POD CHANGES",x:38,y:135,w:520,size:12,bold:true)
            let selected = pods.filter { $0.activatedAt<end &&
                ($0.endedAt ?? end)>=start }.sorted { $0.activatedAt>$1.activatedAt }
            if selected.isEmpty {
                text("No stored pod change history for this period.",x:38,y:165,w:520,size:10,color:gray)
            } else {
                for (i,pod) in selected.prefix(9).enumerated() {
                    let wear = pod.wearHours.map{String(format:"%.1f hours",$0)} ?? "active"
                    text(formatDate(pod.activatedAt) + "  •  " + wear +
                         "  •  " + pod.changeReason,
                         x:38,y:163+CGFloat(i)*22,w:535,size:9)
                }
            }
            rule(385)
            text("CURRENT THERAPY SETTINGS",x:38,y:398,w:520,size:12,bold:true)
            text("Snapshot taken at export, not a reconstruction of historical settings.",
                 x:38,y:421,w:530,size:9,color:gray)
            if let blob = try? JSONEncoder().encode(settings),
               let object = try? JSONSerialization.jsonObject(with:blob),
               let pretty = try? JSONSerialization.data(withJSONObject:object,
                                                          options:[.prettyPrinted,.sortedKeys]),
               let detail = String(data:pretty,encoding:.utf8) {
                var y: CGFloat = 444
                for lineText in detail.components(separatedBy:"\n").prefix(21) {
                    text(String(lineText.prefix(98)),x:38,y:y,w:537,h:14,size:8,color:gray)
                    y += 13
                }
                text("See current LoKey settings for full values if truncated.",
                     x:38,y:723,w:520,size:9,color:gray)
            }
        }
        let path = FileManager.default.temporaryDirectory.appendingPathComponent(
            "LoKey-Daily-Clinical-" + String(Int(Date().timeIntervalSince1970)) + ".pdf")
        try bytes.write(to:path,options:.atomic)
        return path
    }
}
'''

def install():
    content = PATH.read_text(encoding="utf-8")
    if "private enum LoKeyClinicalPDFV2 {" in content:
        raise RuntimeError("LoKey clinical PDF V2 already installed")
    if "private enum LoKeyClinicV2History {" not in content:
        raise RuntimeError("HealthKit history installer must precede PDF V2")
    if content.count("LoKeyClinicalPDFV2.make(") != 1:
        raise RuntimeError("Clinical report view not routed to V2 PDF")
    PATH.write_text(content + PDF,encoding="utf-8")
    print("PASS: Glooko-familiar AGP and individual day charts installed, read-only")

if __name__ == "__main__":
    install()
