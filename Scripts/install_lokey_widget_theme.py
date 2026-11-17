#!/usr/bin/env python3
"""Apply the LoKey widget's night/violet/insulin-green palette to native app UI.

Run LAST, after chart/UI/Shadow/Reports installers. The theme is cosmetic:
it cannot alter the Loop algorithm, pump state, CGM data or PDF exports.
LoKey Settings contains a reversible, persisted switch. Safety status remains
system green/orange/red to preserve urgency and familiar semantics.
"""
from pathlib import Path

STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")
SETTINGS = Path("Loop/Loop/Views/SettingsView.swift")
KEY = "LoKeyWidgetMatchingThemeV1"

PALETTE = r'''// MARK: - LoKey display-only widget-matched night palette
// Matches SystemStatusWidget: #0E0F1F background, #AD6BFC glucose.
// Native pump warnings deliberately keep systemOrange / systemRed.
private enum LoKeyWidgetPalette {
    private static func adaptive(_ night: UIColor, _ day: UIColor) -> UIColor {
        UIColor { traits in
            traits.userInterfaceStyle == .dark ? night : day
        }
    }

    static let background = adaptive(
        UIColor(red: 0.055, green: 0.060, blue: 0.120, alpha: 1),
        .systemGroupedBackground
    )
    static let card = adaptive(
        UIColor(red: 0.105, green: 0.110, blue: 0.185, alpha: 1),
        .secondarySystemGroupedBackground
    )
    static let raised = adaptive(
        UIColor(red: 0.148, green: 0.152, blue: 0.240, alpha: 1),
        .tertiarySystemGroupedBackground
    )
    static let control = adaptive(
        UIColor(red: 0.175, green: 0.160, blue: 0.270, alpha: 1),
        UIColor(red: 0.94, green: 0.91, blue: 0.99, alpha: 1)
    )
    static let violet = adaptive(
        UIColor(red: 0.680, green: 0.420, blue: 0.990, alpha: 1),
        UIColor(red: 0.430, green: 0.180, blue: 0.790, alpha: 1)
    )
    static let insulin = adaptive(
        UIColor(red: 0.3451, green: 1.0, blue: 0.2471, alpha: 1),
        UIColor(red: 0.0863, green: 0.69, blue: 0.12, alpha: 1)
    )
    static let selectedText = adaptive(.black, .white)
    static let secondaryText = adaptive(
        UIColor(red: 0.66, green: 0.68, blue: 0.77, alpha: 1),
        .secondaryLabel
    )

    static func applyWindowStyle(_ window: UIWindow?) {
        guard let window else { return }
        let on = UserDefaults.standard.object(forKey: "LoKeyWidgetMatchingThemeV1") as? Bool ?? true
        let target: UIUserInterfaceStyle = on ? .dark : .unspecified
        if window.overrideUserInterfaceStyle != target {
            window.overrideUserInterfaceStyle = target
        }
    }
}

'''

def once(s: str, old: str, new: str, label: str) -> str:
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one exact UI anchor, found {count}")
    return s.replace(old, new, 1)

def status_transform(source: str) -> str:
    if "private enum LoKeyWidgetPalette" in source:
        raise RuntimeError("LoKey widget matching theme already installed")
    source = once(source, "private extension RefreshContext {",
                  PALETTE + "private extension RefreshContext {", "palette source location")
    source = once(source,
        "        header.backgroundColor = .systemGroupedBackground",
        "        header.backgroundColor = LoKeyWidgetPalette.background\n"
        "        tableView.backgroundColor = LoKeyWidgetPalette.background",
        "LoKey header/table night background")
    source = once(source,
        "    private func loKeyRefreshHeader() {",
        "    private func loKeyRefreshHeader() {\n"
        "        LoKeyWidgetPalette.applyWindowStyle(view.window)",
        "refresh window appearance")
    source = once(source,
        "        super.viewWillAppear(animated)",
        "        super.viewWillAppear(animated)\n"
        "        LoKeyWidgetPalette.applyWindowStyle(view.window)",
        "first app presentation appearance")
    source = once(source,
        "        tabs.selectedSegmentTintColor = UIColor(red: 0.46, green: 0.19, blue: 0.79, alpha: 1)",
        "        tabs.selectedSegmentTintColor = LoKeyWidgetPalette.violet",
        "violet segmented control")
    source = once(source,
        "        tabs.setTitleTextAttributes([.foregroundColor: UIColor.white], for: .selected)",
        "        tabs.setTitleTextAttributes([.foregroundColor: LoKeyWidgetPalette.selectedText], for: .selected)",
        "legible selected segment text")
    original_violet = "UIColor(red: 0.43, green: 0.18, blue: 0.79, alpha: 1)"
    total = source.count(original_violet)
    if total < 4 or total > 18:
        raise RuntimeError(f"Expected LoKey-only brand accents, found {total}; review before styling")
    source = source.replace(original_violet, "LoKeyWidgetPalette.violet")
    start = source.find("    private final class LoKeyGlucoseCard: UITableViewCell {")
    end = source.find("    override func viewDidLoad()", start)
    if start < 0 or end < start:
        raise RuntimeError("LoKey native card scope changed; refusing global style replacement")
    cards = source[start:end]
    # Within LoKey custom UI only, never change native safety or treatment views.
    if cards.count("stack.backgroundColor = .secondarySystemGroupedBackground") < 2:
        raise RuntimeError("LoKey cards unexpectedly lost native card backgrounds")
    cards = cards.replace("stack.backgroundColor = .secondarySystemGroupedBackground",
                          "stack.backgroundColor = LoKeyWidgetPalette.card")
    cards = cards.replace("content.backgroundColor = .secondarySystemGroupedBackground",
                          "content.backgroundColor = LoKeyWidgetPalette.card")
    cards = cards.replace("pumpButton.backgroundColor = .secondarySystemGroupedBackground",
                          "pumpButton.backgroundColor = LoKeyWidgetPalette.card")
    cards = cards.replace("group.backgroundColor = .tertiarySystemGroupedBackground",
                          "group.backgroundColor = LoKeyWidgetPalette.raised")
    cards = cards.replace("group.backgroundColor = .secondarySystemGroupedBackground",
                          "group.backgroundColor = LoKeyWidgetPalette.card")
    cards = cards.replace("button.backgroundColor = UIColor(red: 0.94, green: 0.91, blue: 0.99, alpha: 1)",
                          "button.backgroundColor = LoKeyWidgetPalette.control")
    # Purple is glucose; all insulin quantities and IOB are green.
    cards = cards.replace("iobValue.textColor = .systemGreen",
                          "iobValue.textColor = LoKeyWidgetPalette.insulin")
    cards = cards.replace("iobUnit.textColor = .systemGreen",
                          "iobUnit.textColor = LoKeyWidgetPalette.insulin")
    cards = cards.replace("insulin.textColor = LoKeyWidgetPalette.violet",
                          "insulin.textColor = LoKeyWidgetPalette.insulin")
    cards = cards.replace("amount.textColor = LoKeyWidgetPalette.violet",
                          "amount.textColor = LoKeyWidgetPalette.insulin")
    cards = cards.replace("button.tintColor = LoKeyWidgetPalette.violet",
                          "button.tintColor = LoKeyWidgetPalette.violet")
    cards = cards.replace("heading.textColor = .secondaryLabel",
                          "heading.textColor = LoKeyWidgetPalette.secondaryText")
    source = source[:start] + cards + source[end:]
    # The later daily-insulin tiles sit within the same native card scope; keep
    # the 'basal' accent green rather than warning orange.
    source = source.replace('todayTile("BASAL", value: todayBasalValue, tint: .systemOrange)',
                            'todayTile("BASAL", value: todayBasalValue, tint: LoKeyWidgetPalette.insulin)')
    return source

def settings_transform(source: str) -> str:
    root_start = source.find("private struct LoKeySettingsView: View {")
    if root_start < 0:
        raise RuntimeError("Missing LoKey Settings root")
    following = source.find("\nprivate struct ", root_start + 22)
    if following < root_start:
        raise RuntimeError("Could not isolate LoKey Settings")
    root = source[root_start:following]
    if '@AppStorage("LoKeyWidgetMatchingThemeV1")' in root:
        raise RuntimeError("LoKey Settings theme already installed")
    root = once(root, "    let viewModel: SettingsViewModel",
                '    let viewModel: SettingsViewModel\n'
                '    @AppStorage("LoKeyWidgetMatchingThemeV1") private var widgetThemeEnabled = true',
                "persistent theme preference")
    root = once(root, '            Section(header: Text("Adaptive Shadow")) {',
        '''            Section(header: Text("Appearance")) {
                Toggle("Match Widget Dark Theme", isOn: $widgetThemeEnabled)
                    .onChange(of: widgetThemeEnabled) { enabled in
                        // Only changes presentation style. Never writes Loop settings.
                        for case let scene as UIWindowScene in UIApplication.shared.connectedScenes {
                            for window in scene.windows where window.isKeyWindow {
                                window.overrideUserInterfaceStyle = enabled ? .dark : .unspecified
                            }
                        }
                    }
                Text("Midnight navy surfaces, violet glucose and green insulin — like the Home Screen widget. Turn this off to follow the iPhone appearance setting.")
                    .font(.footnote).foregroundColor(.secondary)
            }
            Section(header: Text("Adaptive Shadow")) {''',
        "appearance section")
    root = once(root, '        .navigationTitle("LoKey Settings")',
        '        .navigationTitle("LoKey Settings")\n'
        '        .tint(Color(red: 0.68, green: 0.42, blue: 0.99))',
        "violet settings controls")
    return source[:root_start] + root + source[following:]

def install() -> None:
    original_status = STATUS.read_text(encoding="utf-8")
    original_settings = SETTINGS.read_text(encoding="utf-8")
    # Validate BOTH transformations before writing either file.
    new_status = status_transform(original_status)
    new_settings = settings_transform(original_settings)
    STATUS.write_text(new_status, encoding="utf-8")
    SETTINGS.write_text(new_settings, encoding="utf-8")
    print("PASS: LoKey interior matched to widget palette; dosing and alerts unchanged")

if __name__ == "__main__":
    install()
