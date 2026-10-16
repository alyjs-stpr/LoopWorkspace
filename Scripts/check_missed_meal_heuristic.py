#!/usr/bin/env python3
"""Execute the *actual* notification-only time predicate extracted from Loop Swift.

This is not an iOS test or an insulin-dosing validation. It checks the narrow
suppression condition while the unsigned hosted Loop test runner cannot bootstrap
in GitHub CI. The full LoopTests must still be run in a supported test environment.
"""
from pathlib import Path
import subprocess
import tempfile

source = Path("Loop/Loop/Managers/Missed Meal Detection/MealDetectionManager.swift")
text = source.read_text(encoding="utf-8")
start_marker = "        let recentLogWindow = TimeInterval(minutes: 75)"
end_marker = "        if mealAlreadyLogged {"
if text.count(start_marker) != 1 or text.count(end_marker) != 1:
    raise SystemExit("Missed-meal predicate changed; review and update regression coverage.")
start = text.index(start_marker)
end = text.index(end_marker, start)
predicate = text[start:end].rstrip()
# Ensure this harness executes the intended, unchanged expression and no extra code.
for expected in ("let candidateWindow", "loggedCarbStartTimes.contains", "age >= TimeInterval(minutes: 10)", "abs(loggedAt.timeIntervalSince(startTime))"):
    if expected not in predicate:
        raise SystemExit(f"Review changed predicate: missing {expected}")

swift_program = """import Foundation

func suppression(_ loggedCarbStartTimes: [Date], _ startTime: Date, _ now: Date) -> Bool {
""" + predicate + """
    return mealAlreadyLogged
}

let now = Date(timeIntervalSince1970: 1_720_000_000)
func minutesAgo(_ minutes: Double) -> Date {
    now.addingTimeInterval(-minutes * 60)
}
func check(_ title: String, _ expected: Bool, _ candidateMinutesAgo: Double, _ loggedMinutesAgo: [Double]) {
    let observed = suppression(loggedMinutesAgo.map(minutesAgo), minutesAgo(candidateMinutesAgo), now)
    guard observed == expected else {
        fatalError("\\(title): expected \\(expected) but got \\(observed)")
    }
    print("PASS: \\(title)")
}

// A previously logged dinner near the detected rise should suppress a
// misleading "missed meal" notification, without changing its glucose math.
check("Recently logged dinner", true, 25, [30])
check("No logged meals", false, 25, [])
check("Preannounced carbs 1 minute ago", false, 25, [1])
check("Unrelated carb log 85 minutes from candidate", false, 105, [20])
check("Carbs logged in future", false, 25, [-10])
check("Old meal log", false, 25, [80])
check("Close to onset but older than 75 minutes", false, 75, [76])
check("Threshold 10 minutes (inclusive)", true, 15, [10])
check("Threshold 75 minutes (inclusive)", true, 75, [75])
check("Candidate and log 45 minutes apart", true, 55, [10])
check("Candidate and log more than 45 minutes apart", false, 56, [10])
"""
with tempfile.TemporaryDirectory(prefix="lokey-notification-check-") as directory:
    temp_file = Path(directory) / "check.swift"
    temp_file.write_text(swift_program, encoding="utf-8")
    subprocess.run(["swift", str(temp_file)], check=True)
print("Source-derived notification timing checks passed. Full iOS unit tests remain unverified.")
