#!/usr/bin/env python3
"""Style the native LoKey bolus progress row without changing its behavior.

Only patches Loop/Views/BolusProgressTableViewCell.swift after the pinned
Loop submodule has been checked out. The original delivered/total status,
progress reporting, and UITableView.didSelectRowAt cancellation handler remain
untouched. No bolus, pump, or insulin-delivery APIs are added or changed.
Fail closed if the upstream view's anchors change.
"""
from pathlib import Path

SOURCE = Path("Loop/Loop/Views/BolusProgressTableViewCell.swift")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor, found {found}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    if "loKeyInstallBolusProgressPresentation" in source:
        raise RuntimeError("LoKey bolus progress presentation already installed")

    source = replace_once(
        source,
        "    @IBOutlet weak var progressIndicator: RingProgressView!\n",
        """    @IBOutlet weak var progressIndicator: RingProgressView!

    // Read-only presentation. The existing UITableView selection handler is
    // still the sole route to stop/cancel a bolus.
    private let loKeyTitle = UILabel()
    private let loKeyDose = UILabel()
    private let loKeyProgressBar = UIProgressView(progressViewStyle: .default)
    private let loKeyStopSurface = UIView()
    private let loKeyStopLabel = UILabel()
    private let loKeyStopSymbol = UIImageView()
    private var loKeyPresentationInstalled = false
""",
        "additional display-only views",
    )

    source = replace_once(
        source,
        """        updateColors()
    }

    override public func layoutSubviews() {""",
        """        updateColors()
        loKeyInstallBolusProgressPresentation()
        loKeyRefreshBolusProgressPresentation(animated: false)
    }

    override public func layoutSubviews() {""",
        "presentation installation after nib loading",
    )

    source = replace_once(
        source,
        """        gradient.colors = [
            UIColor.cellBackgroundColor.withAlphaComponent(0).cgColor,
            UIColor.cellBackgroundColor.cgColor
        ]
    }""",
        """        gradient.colors = [
            UIColor.cellBackgroundColor.withAlphaComponent(0).cgColor,
            UIColor.cellBackgroundColor.cgColor
        ]
        // The progress bar and stop affordance are informational views only.
        loKeyProgressBar.progressTintColor = .systemOrange
        loKeyProgressBar.trackTintColor = UIColor.secondaryLabel.withAlphaComponent(0.22)
        loKeyStopSurface.backgroundColor = UIColor.systemOrange.withAlphaComponent(0.13)
        loKeyStopSurface.layer.borderColor = UIColor.systemOrange.cgColor
        loKeyStopLabel.textColor = .systemOrange
        loKeyStopSymbol.tintColor = .systemOrange
    }""",
        "system adaptive palette",
    )

    source = replace_once(
        source,
        """        } else {
            progressLabel.text = String(format: NSLocalizedString("Bolusing %1$@", comment: "The format string for bolus in progress showing total volume. (1: total volume)"), totalUnitsString)
        }
    }

    override public func prepareForReuse() {""",
        """        } else {
            progressLabel.text = String(format: NSLocalizedString("Bolusing %1$@", comment: "The format string for bolus in progress showing total volume. (1: total volume)"), totalUnitsString)
        }
        loKeyRefreshBolusProgressPresentation(animated: true)
    }

    // Keep the original nib outlets, dose reporter and ring fully wired.
    // Hide only their duplicate visual presentation, then install a compact
    // two-line layout with an actual horizontal delivery progress bar.
    private func loKeyInstallBolusProgressPresentation() {
        guard !loKeyPresentationInstalled else { return }
        loKeyPresentationInstalled = true
        progressLabel.alpha = 0
        tapToStopLabel.alpha = 0
        progressIndicator.alpha = 0

        loKeyTitle.text = NSLocalizedString(
            "DELIVERING INSULIN", comment: "Title of the active insulin bolus progress banner")
        loKeyTitle.font = .systemFont(ofSize: 11, weight: .semibold)
        loKeyTitle.textColor = .secondaryLabel
        loKeyTitle.adjustsFontSizeToFitWidth = true
        loKeyTitle.minimumScaleFactor = 0.8

        loKeyDose.font = .monospacedDigitSystemFont(ofSize: 20, weight: .bold)
        loKeyDose.textColor = .label
        loKeyDose.adjustsFontSizeToFitWidth = true
        loKeyDose.minimumScaleFactor = 0.75
        loKeyDose.lineBreakMode = .byTruncatingTail

        loKeyProgressBar.progress = 0
        loKeyProgressBar.layer.cornerRadius = 2
        loKeyProgressBar.clipsToBounds = true

        let details = UIStackView(arrangedSubviews: [loKeyTitle, loKeyDose, loKeyProgressBar])
        details.axis = .vertical
        details.alignment = .fill
        details.distribution = .fill
        details.spacing = 4
        details.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        loKeyStopSurface.layer.cornerRadius = 13
        loKeyStopSurface.layer.borderWidth = 1
        loKeyStopSurface.isUserInteractionEnabled = false
        loKeyStopSymbol.image = UIImage(systemName: "stop.fill")
        loKeyStopSymbol.contentMode = .scaleAspectFit
        loKeyStopSymbol.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            loKeyStopSymbol.widthAnchor.constraint(equalToConstant: 15),
            loKeyStopSymbol.heightAnchor.constraint(equalToConstant: 15)
        ])
        loKeyStopLabel.text = NSLocalizedString(
            "STOP BOLUS", comment: "Visual label for the existing tap-to-stop bolus row")
        loKeyStopLabel.font = .systemFont(ofSize: 11, weight: .bold)
        loKeyStopLabel.numberOfLines = 2
        loKeyStopLabel.lineBreakMode = .byWordWrapping
        loKeyStopLabel.textAlignment = .center

        let stopContent = UIStackView(arrangedSubviews: [loKeyStopSymbol, loKeyStopLabel])
        stopContent.axis = .horizontal
        stopContent.alignment = .center
        stopContent.distribution = .fill
        stopContent.spacing = 7
        stopContent.isUserInteractionEnabled = false
        stopContent.translatesAutoresizingMaskIntoConstraints = false
        loKeyStopSurface.addSubview(stopContent)
        NSLayoutConstraint.activate([
            stopContent.centerXAnchor.constraint(equalTo: loKeyStopSurface.centerXAnchor),
            stopContent.centerYAnchor.constraint(equalTo: loKeyStopSurface.centerYAnchor),
            stopContent.leadingAnchor.constraint(greaterThanOrEqualTo: loKeyStopSurface.leadingAnchor, constant: 8),
            stopContent.trailingAnchor.constraint(lessThanOrEqualTo: loKeyStopSurface.trailingAnchor, constant: -8),
            loKeyStopSurface.widthAnchor.constraint(equalToConstant: 112),
            loKeyStopSurface.heightAnchor.constraint(greaterThanOrEqualToConstant: 46)
        ])

        let row = UIStackView(arrangedSubviews: [details, loKeyStopSurface])
        row.axis = .horizontal
        row.alignment = .center
        row.spacing = 12
        row.distribution = .fill
        row.isUserInteractionEnabled = false
        row.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(row)
        NSLayoutConstraint.activate([
            row.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 9),
            row.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -9),
            row.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 14),
            row.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -14)
        ])
        // The native row remains the touch target. This view is not a
        // button and never invokes cancelBolus itself.
        isAccessibilityElement = true
        accessibilityTraits.insert(.button)
        accessibilityHint = NSLocalizedString(
            "Double tap to stop the active bolus", comment: "Accessibility hint for active bolus status row")
        updateColors()
    }

    private func loKeyRefreshBolusProgressPresentation(animated: Bool) {
        guard loKeyPresentationInstalled, let total = totalUnits, total > 0,
              total.isFinite else { return }

        let totalQuantity = HKQuantity(unit: .internationalUnit(), doubleValue: total)
        let totalString = insulinFormatter.string(from: totalQuantity, includeUnit: false) ?? "—"
        let fraction: Double
        let description: String
        if let delivered = deliveredUnits, delivered.isFinite {
            let safeDelivered = max(0, min(total, delivered))
            let doseQuantity = HKQuantity(unit: .internationalUnit(), doubleValue: safeDelivered)
            let deliveredString = insulinFormatter.string(from: doseQuantity, includeUnit: false) ?? "—"
            loKeyDose.text = deliveredString + " / " + totalString + " U"
            fraction = safeDelivered / total
            description = deliveredString + " of " + totalString + " units delivered"
        } else {
            loKeyDose.text = totalString + " U"
            fraction = 0
            description = totalString + " units requested; delivery progress is not yet available"
        }

        loKeyProgressBar.setProgress(Float(fraction), animated: animated)
        accessibilityLabel = "Insulin bolus in progress, " + description + ". Tap to stop bolus."
    }

    override public func prepareForReuse() {""",
        "presentation-only card and value updates",
    )

    source = replace_once(
        source,
        """        progressIndicator.progress = 0
        CATransaction.flush()
        progressLabel.text = ""
    }
}""",
        """        progressIndicator.progress = 0
        loKeyProgressBar.setProgress(0, animated: false)
        loKeyDose.text = nil
        accessibilityLabel = nil
        CATransaction.flush()
        progressLabel.text = ""
    }
}""",
        "reuse safety for displayed delivery progress",
    )
    return source


def install() -> None:
    old = SOURCE.read_text(encoding="utf-8")
    new = transform(old)
    if old == new:
        raise RuntimeError("No bolus UI update applied")
    SOURCE.write_text(new, encoding="utf-8")
    print("PASS: LoKey compact bolus-progress banner installed")
    print("PASS: original dose progress/stop-tap handling unchanged")


if __name__ == "__main__":
    install()
