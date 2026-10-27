#!/usr/bin/env python3
"""Ensure the read-only native Loop shadow path uses the tested Swift core source."""
from pathlib import Path

native = Path("Loop/Loop/Managers/DeviceDataManager.swift").read_text()
for name in ("Controller.swift", "OutcomeAnalyzer.swift"):
    source = Path("AdaptiveController/Sources/LoKeyAdaptiveCore", name).read_text()
    if source.startswith("import Foundation\n"):
        source = source[len("import Foundation\n"):].lstrip("\n")
    source = source.rstrip()
    if source not in native:
        raise SystemExit(f"ERROR: {name} differs between tested Swift package and iOS app. Never merge.")
    print(f"PASS: {name} matches iOS shadow copy.")

prefix = native.split("// Native background-capable, READ-ONLY shadow recorder.", 1)
if len(prefix) != 2:
    raise SystemExit("ERROR: Missing native shadow recorder.")
recorder = prefix[1]
for forbidden in ("enactBolus(", "enactTempBasal(", "deliverBolus(", "setTempBasal(", "mutateSettings("):
    if forbidden in recorder:
        raise SystemExit(f"ERROR: shadow recorder calls a dosing API: {forbidden}")
print("PASS: No dosing API in shadow recorder.")
