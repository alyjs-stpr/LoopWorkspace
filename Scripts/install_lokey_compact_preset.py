#!/usr/bin/env python3
"""LoKey-only compact preset status cell.

This installs a presentation-only replacement for Loop's oversized native
schedule-override row. It intentionally retains the native override lifecycle,
tap-to-edit behavior, pump safety status priority, and all therapy settings.
Runs after the other LoKey display installers; aborts on changed source anchors.
"""
from pathlib import Path

STATUS = Path("Loop/Loop/View Controllers/StatusTableViewController.swift")

CELL = r'''    // Compact active-target summary. The original status-row lifecycle and
    // didSelectRowAt override editor are unchanged.
    private final class LoKeyPresetCompactCell: UITableViewCell {
        private let card = UIView()
        private let iconView = UIImageView()
        private let nameLabel = UILabel()
        private let detailLabel = UILabel()
        private let expiryContainer = UIView()
        private let expiryLabel = UILabel()

        override init(style: UITableViewCell.CellStyle, reuseIdentifier: String?) {
            super.init(style: style, reuseIdentifier: reuseIdentifier)
            installLayout()
        }

        required init?(coder: NSCoder) {
            super.init(coder: coder)
            installLayout()
        }

        private func installLayout() {
            selectionStyle = .none
            backgroundColor = .clear
            contentView.backgroundColor = .clear

            card.translatesAutoresizingMaskIntoConstraints = false
            card.isUserInteractionEnabled = false // Let native row taps edit targets.
            card.layer.cornerRadius = 14
            card.backgroundColor = UIColor { trait in
                trait.userInterfaceStyle == .dark
                    ? UIColor(red: 27.0 / 255, green: 28.0 / 255,
                              blue: 47.0 / 255, alpha: 1)
                    : UIColor.secondarySystemGroupedBackground
            }

            iconView.image = UIImage(systemName: "scope")
            iconView.tintColor = UIColor(red: 173.0 / 255, green: 107.0 / 255,
                                        blue: 252.0 / 255, alpha: 1)
            iconView.contentMode = .scaleAspectFit
            iconView.translatesAutoresizingMaskIntoConstraints = false
            NSLayoutConstraint.activate([
                iconView.widthAnchor.constraint(equalToConstant: 19),
                iconView.heightAnchor.constraint(equalToConstant: 19)
            ])

            nameLabel.font = UIFontMetrics(forTextStyle: .subheadline)
                .scaledFont(for: .systemFont(ofSize: 14, weight: .semibold))
            nameLabel.adjustsFontForContentSizeCategory = true
            nameLabel.textColor = .label
            nameLabel.lineBreakMode = .byTruncatingTail
            nameLabel.numberOfLines = 1

            detailLabel.font = UIFontMetrics(forTextStyle: .caption2)
                .scaledFont(for: .systemFont(ofSize: 11, weight: .regular))
            detailLabel.adjustsFontForContentSizeCategory = true
            detailLabel.textColor = .secondaryLabel
            detailLabel.numberOfLines = 1
            detailLabel.lineBreakMode = .byTruncatingTail

            expiryContainer.translatesAutoresizingMaskIntoConstraints = false
            expiryContainer.backgroundColor = UIColor { trait in
                trait.userInterfaceStyle == .dark
                    ? UIColor(red: 48.0 / 255, green: 36.0 / 255,
                              blue: 67.0 / 255, alpha: 1)
                    : UIColor.systemPurple.withAlphaComponent(0.10)
            }
            expiryContainer.layer.cornerRadius = 10

            expiryLabel.translatesAutoresizingMaskIntoConstraints = false
            expiryLabel.font = UIFontMetrics(forTextStyle: .caption1)
                .scaledFont(for: .systemFont(ofSize: 12, weight: .medium))
            expiryLabel.adjustsFontForContentSizeCategory = true
            expiryLabel.adjustsFontSizeToFitWidth = true
            expiryLabel.minimumScaleFactor = 0.8
            expiryLabel.textColor = UIColor { trait in
                trait.userInterfaceStyle == .dark
                    ? UIColor(red: 213.0 / 255, green: 181.0 / 255,
                              blue: 1, alpha: 1)
                    : UIColor.systemPurple
            }
            expiryLabel.numberOfLines = 1
            expiryContainer.addSubview(expiryLabel)
            NSLayoutConstraint.activate([
                expiryLabel.leadingAnchor.constraint(equalTo: expiryContainer.leadingAnchor, constant: 10),
                expiryLabel.trailingAnchor.constraint(equalTo: expiryContainer.trailingAnchor, constant: -10),
                expiryLabel.topAnchor.constraint(equalTo: expiryContainer.topAnchor, constant: 7),
                expiryLabel.bottomAnchor.constraint(equalTo: expiryContainer.bottomAnchor, constant: -7),
                expiryContainer.widthAnchor.constraint(lessThanOrEqualToConstant: 165)
            ])
            expiryContainer.setContentCompressionResistancePriority(.required, for: .horizontal)

            let labels = UIStackView(arrangedSubviews: [nameLabel, detailLabel])
            labels.axis = .vertical
            labels.alignment = .leading
            labels.spacing = 2
            labels.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

            let row = UIStackView(arrangedSubviews: [iconView, labels, expiryContainer])
            row.translatesAutoresizingMaskIntoConstraints = false
            row.axis = .horizontal
            row.alignment = .center
            row.spacing = 9
            contentView.addSubview(card)
            card.addSubview(row)
            NSLayoutConstraint.activate([
                card.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 14),
                card.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -14),
                card.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 4),
                card.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -4),
                card.heightAnchor.constraint(greaterThanOrEqualToConstant: 54),
                row.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 12),
                row.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -12),
                row.topAnchor.constraint(equalTo: card.topAnchor, constant: 8),
                row.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -8)
            ])
            isAccessibilityElement = true
            accessibilityTraits.insert(.button)
        }

        func configure(title: String, active: Bool, when: String?) {
            nameLabel.text = title
            detailLabel.text = active
                ? NSLocalizedString("Active glucose target", comment: "Active LoKey target description")
                : NSLocalizedString("Scheduled glucose target", comment: "Future LoKey target description")
            expiryLabel.text = when
            expiryContainer.isHidden = when == nil
            accessibilityLabel = [title, detailLabel.text, when]
                .compactMap { $0 }.joined(separator: ", ")
            accessibilityHint = NSLocalizedString("Opens target details when available", comment: "Preset row action")
        }
    }

'''

STATUS_CASE = r'''                case .scheduleOverrideEnabled(let override):
                    // Only restyle the native preset row. Its activation,
                    // expiry, priority, and tap-to-edit are not reimplemented.
                    let cell = tableView.dequeueReusableCell(withIdentifier: "LoKeyPresetCompactCell")
                        as? LoKeyPresetCompactCell
                        ?? LoKeyPresetCompactCell(style: .default, reuseIdentifier: "LoKeyPresetCompactCell")

                    let title: String
                    switch override.context {
                    case .preMeal:
                        title = NSLocalizedString("Pre-meal Preset", comment: "Active pre-meal target")
                    case .legacyWorkout:
                        title = NSLocalizedString("Workout Preset", comment: "Active workout target")
                    case .preset(let preset):
                        title = preset.symbol + " " + preset.name
                    case .custom:
                        title = NSLocalizedString("Custom Preset", comment: "Active custom target")
                    }
                    let active = override.isActive()
                    let when: String?
                    if active {
                        switch override.duration {
                        case .finite:
                            let time = DateFormatter.localizedString(
                                from: override.activeInterval.end,
                                dateStyle: .none, timeStyle: .short)
                            when = String(format: NSLocalizedString(
                                "Until %@", comment: "Active target expiration time"), time)
                        case .indefinite:
                            when = NSLocalizedString("Active", comment: "Indefinite target status")
                        }
                    } else {
                        let time = DateFormatter.localizedString(
                            from: override.startDate,
                            dateStyle: .none, timeStyle: .short)
                        when = String(format: NSLocalizedString(
                            "Starts %@", comment: "Scheduled target start time"), time)
                    }
                    cell.configure(title: title, active: active, when: when)
                    return cell
'''

def transform(src: str) -> str:
    marker = "    private class AlertPermissionsDisabledWarningCell: UITableViewCell {"
    if "LoKeyPresetCompactCell" in src:
        raise RuntimeError("Compact preset cell already installed")
    if src.count(marker) != 1:
        raise RuntimeError("Native status cell insertion anchor changed")
    start = "    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {"
    end = "    override func tableView(_ tableView: UITableView, heightForRowAt indexPath: IndexPath) -> CGFloat {"
    if src.count(start) != 1 or src.count(end) != 1:
        raise RuntimeError("Status row data source anchors changed")
    a = src.index(start)
    b = src.index(end, a)
    body = src[a:b]
    case = "                case .scheduleOverrideEnabled(let override):"
    next_case = "                case .enactingBolus:"
    if body.count(case) != 1 or body.count(next_case) != 1:
        raise RuntimeError("Native preset or bolus row changed; abort")
    i = body.index(case)
    j = body.index(next_case, i)
    if i >= j:
        raise RuntimeError("Invalid native status case ordering")
    body = body[:i] + STATUS_CASE + body[j:]
    src = src[:a] + body + src[b:]
    return src.replace(marker, CELL + marker, 1)

def install() -> None:
    original = STATUS.read_text(encoding="utf-8")
    revised = transform(original)
    STATUS.write_text(revised, encoding="utf-8")
    print("PASS: compact preset banner; target activation, navigation, and safety rows untouched")

if __name__ == "__main__":
    install()
