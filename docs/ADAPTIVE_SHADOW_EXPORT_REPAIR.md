# LoKey Loop Adaptive Shadow · Save to Files export repair

## Symptom
Settings → LoKey Settings → Adaptive Shadow → Export Shadow Records opens a nearly empty iOS share panel (often showing only the LoKey icon and Close button). The Shadow Dashboard may still display recorded cycles.

## Suspected cause and fix
The Build 33 UI passed multiple app-private `.jsonl` file URLs directly to a generic `UIActivityViewController`. File-extension handling and share previews are not reliable for this export on every iOS version.

This branch replaces **only** the Shadow export UI with a SwiftUI `fileExporter` and a `FileDocument` using the standard JSON content type. The user sees the native Save to Files picker. The code prepares one `LoKey-Adaptive-Shadow-YYYYMMDD-HHMMSS.json` file containing:

- `format: "LoKeyAdaptiveShadowExport"`
- `schemaVersion: 1`
- `exportedAt`, `sourceFileCount`, `sourceBytes`
- `files[]` entries with original `filename`, `byteCount`, and **unaltered UTF-8 `jsonl` content**

The output format is a wrapper for transport, not a clinical report or dosing input. An Adaptive importer must later unpack the `jsonl` strings and validate their record schema. No data is uploaded automatically.

## Safety / data-loss boundaries
- **Read-only**. No mutation of the original local Shadow JSONL files or recording preference.
- No insulin dosing, pump connection, therapy settings, glucose predictions, or data collection changes.
- If a source file is unreadable, not a regular file, missing, or exceeds the bounded size limit (64 MB combined), export **fails with a visible error** rather than silently producing a partial copy.
- Original records are preserved even after user cancellation or a failed export.
- Existing recorder retention is unchanged (**14 days**); export does not recover expired records. Verify the saved copy in Files before reinstalling or deleting the LoKey Loop app.
- The exported file contains private health information. Save and share only intentionally.

## End-user steps (after a new verified build is installed)
1. LoKey Loop → Settings → LoKey Settings → Adaptive Shadow.
2. Select **Export Shadow Records to Files**.
3. Choose **On My iPhone** or **iCloud Drive** in the file picker and Save.
4. Open Files and confirm a `LoKey-Adaptive-Shadow-*.json` file exists and has nonzero size.
5. Upload the file to ChatGPT or import it to a future read-only Adaptive importer. Do not delete the source app until verification.

## Validation
- `python3 -m unittest discover -s Scripts/tests -p test_lokey_shadow_files_export.py -v`
- All production and iOS simulator build workflows run the same targeted installer immediately after the existing Build 33 Shadow dashboard patch.
- The existing unsigned simulator compile remains the gate before merging.
- **Device-level test required:** on the iPhone with recorded data, confirm Files chooser appears, saved JSON contents are readable, and the Shadow dashboard still shows its original records.
