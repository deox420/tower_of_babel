*confusion of tongues, by design*

```
███████╗████████╗██████╗ ██╗██████╗
██╔════╝╚══██╔══╝██╔══██╗██║██╔══██╗
███████╗   ██║   ██████╔╝██║██████╔╝
╚════██║   ██║   ██╔══██╗██║██╔═══╝
███████║   ██║   ██║  ██║██║██║
╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝
```

# STRIP - metadata laundry

## 1 - What this is

STRIP removes declared metadata from common file formats: EXIF / XMP
/ IPTC in images, properties and revision residue in Office
documents, /Info dictionaries and XMP streams in PDFs, ID3 / APE
tags in MP3s. It runs locally, never touches the network, never
phones home, and never modifies the original file unless you point
the output back at it explicitly.

The tool ships as an action: drop in a file, see what was in it,
write the laundered copy out, return to the menu. There is no
"session". Memory is released when the operation ends.

STRIP is the simplest hammer in the tower. It does one thing and
it does it loudly: every field it removes is named in the
before/after diff so you can see what would have leaked if you had
shared the file as-is.

## 2 - What it protects

| Surface | Protection |
|---|---|
| EXIF (camera make, lens, GPS, timestamp, serial) in JPEG | Removed entirely. |
| XMP packets embedded in JPEG, PNG, PDF | Stripped from container. |
| IPTC blocks (caption, byline, location) in JPEG | Removed. |
| Photoshop image resources (APP13) in JPEG | Removed. |
| Adobe APP14 segment (authoring software hint) in JPEG | Removed in aggressive mode. |
| Comment markers (COM, FFFE) in JPEG | Removed. |
| Thumbnails embedded inside EXIF | Removed with the EXIF block. |
| PNG textual chunks (tEXt, iTXt, zTXt) | Removed. |
| PNG timestamp chunk (tIME) | Removed. |
| PNG eXIf chunk | Removed. |
| PNG ICC profile chunk (iCCP) | Removed in aggressive mode. |
| PDF /Info dictionary (Author, Title, Producer, Creator, CreationDate, ModDate) | Cleared. |
| PDF XMP /Metadata stream | Removed. |
| PDF /ID array (file identifier pair) | Replaced with a fresh random pair. |
| DOCX core properties (creator, lastModifiedBy, revision history) | Replaced with empty stubs. |
| DOCX extended properties (Application, Company, AppVersion) | Replaced with empty stubs. |
| DOCX custom properties | Removed entirely. |
| DOCX rsid (revision-save IDs that can fingerprint editing sessions) | Removed in aggressive mode. |
| DOCX trackChanges and revision marks | Removed in aggressive mode. |
| MP3 ID3v2 tag (artist, album, comment, lyrics, attached pictures) | Removed. |
| MP3 ID3v1 trailer | Removed. |
| MP3 APEv2 tag (header and footer) | Removed. |
| Filename (optional) | Replaceable with a deterministic hash of the laundered content via `--hash-rename`. |
| Originals in batch mode | Never modified. The input directory is read-only; outputs go to a directory you pick. |

## 3 - What this does NOT protect

| Risk | Why it survives |
|---|---|
| Sensor-pattern noise (PRNU) in JPEG/PNG pixel data | Lives in the pixels, not the metadata. A forensic match to your camera body remains possible. |
| Printer steganography (yellow-dot tracking) in scans | The marks are part of the image content. STRIP would not recognise them. |
| Codec quirks (encoder fingerprints, quantisation tables) | Re-encoding to defeat these changes the visual output; STRIP refuses to silently re-encode. |
| Office "track changes" residue in obscure XML namespaces | The aggressive pass scrubs the common ones. Third-party plugins can leave traces in their own namespaces; STRIP runs a normalisation pass but does not guarantee 100%. |
| PDFs with encrypted dictionaries you cannot open | STRIP refuses to guess the password and refuses to ship a half-stripped output. |
| PDFs that embed JavaScript, attachments, or named destinations referencing personal paths | Out of scope. Use a hardening tool before STRIP if you need this gone. |
| Audio fingerprints (acoustic ID, watermarks) in MP3 frames | Frame data is left intact so the file plays. |
| File-system metadata (mtime, ACLs, xattrs, NTFS streams) | STRIP normalises mtime on its own outputs but cannot affect files at rest elsewhere on your disk. |
| Filename leaks elsewhere on disk | `--hash-rename` renames the output. Anything that already references the old name is your problem. |
| The fact that you ran STRIP | Process listings, shell history, antivirus telemetry, and the existence of `babel` on disk are all observable. STRIP cannot launder itself. |
| Endpoint compromise | If something on your machine reads files before STRIP processes them, STRIP cannot help. |
| The receiving party screenshotting or re-uploading the laundered file | Out of scope for any metadata tool. |

## 4 - CLI flags

```
babel strip <path>            # single file: shows diff, writes <path>.stripped
babel strip -o <out> <path>   # explicit output path
babel strip -i <path>         # in-place; overwrites the input
babel strip <dir> --batch     # process a directory; writes results to <dir>.stripped/
babel strip ... --aggressive  # also strip ICC profiles, rsids, software-version hints
babel strip ... --hash-rename # rename output to <sha256_of_output>.<ext>
babel strip ... --quiet       # suppress the diff; still prints summary
babel strip ... --json        # emit the diff as JSON (one record per file)
babel strip ... --dry-run     # show what would be removed, do not write
babel strip --setup           # diagnostic: which formats are supported here
```

`--batch` and `-i` are mutually exclusive. `-o` and `--batch` are
mutually exclusive (use the directory output path instead). `-o`
with a directory path errors; use the explicit file path.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | all files processed cleanly |
| 1 | at least one file had unsupported format; others may have succeeded |
| 2 | invocation error (bad flags, missing input) |
| 3 | I/O error (permission, disk full) |
| 4 | encrypted PDF or otherwise locked input |

## 5 - In-app commands and keys

STRIP's chrome screen is a simple two-pane view: file picker on the
left, before/after diff on the right.

| Key | Effect |
|---|---|
| `Enter` on a file | run STRIP, render the diff |
| `a` | toggle aggressive mode |
| `h` | toggle hash-rename |
| `w` | write the laundered copy (asks for confirmation) |
| `Esc` | leave STRIP, return to the menu |
| `q` | quit the suite (`Ctrl+C` and `Ctrl+Q` also work) |

Batch mode in the TUI is opened with `b`; it asks for an input
directory and an output directory, then runs the same pipeline file
by file with a real progress bar (bytes processed per second is
real, not animated).

## 6 - Worked walkthrough

```
$ babel strip ~/Downloads/IMG_4517.jpg
                                 STRIP / 1 file
+----------------------------------------------------------+
|  field                          before          after    |
|--------------------------------|---------------|---------|
|  EXIF.Make                      Apple           -        |
|  EXIF.Model                     iPhone 14 Pro   -        |
|  EXIF.GPSLatitude               41.385064       -        |
|  EXIF.GPSLongitude              2.173404        -        |
|  EXIF.DateTimeOriginal          2026:03:21 ...  -        |
|  EXIF.LensModel                 iPhone 14 ...   -        |
|  EXIF.SerialNumber              FJ3L2HQF1Q      -        |
|  IPTC.Caption                   (...)           -        |
|  XMP.CreatorTool                Adobe Lightro.. -        |
+----------------------------------------------------------+
  9 fields removed.  size before 3.84 MB  ->  after 3.80 MB
  written to /home/u/Downloads/IMG_4517.stripped.jpg
```

In batch mode the same diff prints once per file, separated by a
single ruled line. The progress bar at the bottom reflects bytes
done across the whole batch.

## 7 - Architecture

STRIP is an action tool (MASTER.md 4.4): no slot, no background
work, no lingering state. The Textual screen mounts inside
`babel.shell.Chrome`'s content slot. The same core functions back
the CLI.

```
tools/strip/
  __main__.py            # entry: `python -m tools.strip` aka `babel strip`
  cli.py                 # argparse, the actual flag surface
  app.py                 # Textual screens (home, picker, diff, batch)
  setup_check.py         # contributes to `babel --setup`
  pipeline.py            # orchestration: dispatch by extension, batch loop
  diff.py                # FieldRemoved dataclass + diff aggregation
  core/
    jpeg.py              # APP-segment stripper (stdlib only)
    png.py               # chunk-level stripper (stdlib only)
    pdf.py               # pypdf-backed /Info + XMP stripper
    docx.py              # zipfile + xml.etree stripper
    mp3.py               # ID3v1 / ID3v2 / APE byte-level stripper
  screens/
    home.py              # picker + recent files
    result.py            # before/after diff view
```

Per-format strippers are pure functions:

```python
def strip_jpeg(data: bytes, *, aggressive: bool) -> StripResult: ...
def strip_png(data: bytes, *, aggressive: bool) -> StripResult: ...
def strip_pdf(data: bytes, *, aggressive: bool) -> StripResult: ...
def strip_docx(data: bytes, *, aggressive: bool) -> StripResult: ...
def strip_mp3(data: bytes, *, aggressive: bool) -> StripResult: ...
```

Each returns a `StripResult(payload: bytes, removed: list[FieldRemoved])`.
The diff view consumes `removed`; the writer consumes `payload`.
No format function ever touches the filesystem. This is what makes
the pentest harness possible.

### Dependencies

- `pypdf>=4.0` (new). PDF metadata stripping needs a real parser to
  survive cross-reference tables and compressed object streams.
  Pure-Python, MIT, no transitive deps beyond stdlib.
- Everything else: stdlib (`zipfile`, `xml.etree.ElementTree`,
  `struct`, `zlib`, `secrets`).

`shared/ui/` modules consumed:

- `shared.ui.progress.RealProgressBar` (batch mode).
- `shared.ui.diff_view.DiffTable` (the before/after table).
- `shared.ui.compact.is_compact` (label collapse).

`shared/crypto/secure_mem.py` is not consumed in Phase 2: STRIP
operates on bytes that are necessarily disk-resident (you handed
it a file), so mlock would be theatre. Future "encrypt-on-output"
mode (Phase 4+) will pull it in.

## 8 - Reproducible build notes

No per-tool overrides. STRIP rides the suite's pinned build:
`SOURCE_DATE_EPOCH`, sorted PyInstaller analysis, hash-locked
`requirements.lock`. The new `pypdf` pin is added to
`requirements.txt` and locked at release-cut time.

## 9 - Threat-model worksheet (Forge output)

Forge was invoked with a THREAT MODEL classification at design
time. Framework: LINDDUN (privacy-focused STRIDE variant), picked
because STRIP's surface is "what does the file tell about its
maker" rather than "who can break it".

| LINDDUN axis | Concern | STRIP's answer |
|---|---|---|
| **L**inkability | Two files share an identifier (camera serial, DOCX rsid, /ID array) | Sections 2 cover all three; aggressive mode catches rsids. |
| **I**dentifiability | A field directly names the maker (Author, Artist, byline) | Cleared. |
| **N**on-repudiation | Signed metadata (XMP signatures) ties content to an identity | XMP block is removed, signature with it. |
| **D**etectability | The presence of a stripped-vs-fresh signature reveals tool use | The output is a normal file in its format; the *absence* of metadata is itself a signal in adversarial contexts. Documented in Section 3. |
| **D**isclosure of information | A hidden field leaks data | If you can name it in this doc, STRIP removes it. If not, it survives. |
| **U**nawareness | User doesn't know what was in the file | The diff is mandatory; `--quiet` only hides the table, the summary still names the count. |
| **N**on-compliance | Removing metadata breaks a regulated workflow | Out of scope. STRIP does what you tell it. |

This worksheet is the source of the Section 2 / Section 3 split.
When a new format is added, run the worksheet again before the
column ships.
