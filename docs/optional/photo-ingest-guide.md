# Photo Ingest Guide

**Use multimodal AI to analyze your photography sessions — selecting the best shots, suggesting edits, and improving your composition.**

> This is an extension of the [Obsidian Memory for AI](README.md) system. It builds on the existing `sources/` layer and the Ingest operation to add a specialized workflow for photographs.

---

## The idea

You take dozens of photos per session. Many are variations of the same shot — different exposures, slightly different compositions, one with eyes open and one without. Selecting the best, figuring out how to develop them, and identifying patterns in your technique takes time.

Multimodal AI models (Claude, GPT-4o, Gemini) can see your photos and give you a second opinion: which shot is sharpest, whether the exposure needs correction, how the composition could improve. Combined with EXIF metadata, the AI can also identify systematic patterns — are you consistently underexposing? Shooting too wide open?

This guide shows how to integrate that analysis into your Obsidian vault as a repeatable workflow.

## What you get

For each photography session, you get a Markdown report (`analysis.md`) with:

- **Best-of-group selection**: For burst/similar shots, the AI picks the best and explains why
- **Editing recommendations**: Specific adjustments for your photo editor (exposure ±, contrast, highlights, shadows, clarity, temperature, crop suggestions)
- **Composition notes**: What works, what could improve, alternative framings
- **Session patterns**: Recurring tendencies across the session (systematic underexposure, tilted horizons, etc.)

## Requirements

| Requirement | Why | Alternative |
|-------------|-----|-------------|
| Camera shooting RAW+JPEG or RAW+HEIF | JPEGs/HEIFs for AI analysis, RAWs for editing | JPEG-only works too (no RAW editing later) |
| macOS with `sips` | Generate thumbnails and convert HEIF→JPEG | ImageMagick, Pillow (+pillow-heif), or any resize tool |
| Python 3 + Pillow | Extract EXIF metadata from JPEGs | `exiftool` CLI works too |
| macOS `mdls` (for HEIF) | Extract EXIF from HEIF/HIF files (Pillow can't natively) | `exiftool` as universal alternative |
| Multimodal AI | Visual analysis of photographs | Claude (via Claude Code, Copilot CLI), GPT-4o, Gemini |

### Supported formats

The prep script handles:
- **JPEG** (`.jpg`, `.jpeg`) — standard output, EXIF via Pillow
- **HEIF/HEIC** (`.hif`, `.heif`, `.heic`) — Fuji X100VI and modern iPhones. EXIF extracted via macOS `mdls`, thumbnails converted to JPEG via `sips -s format jpeg`

> **Why HEIF?** Some cameras (notably Fuji X100VI) output `.HIF` instead of JPEG when configured for HEIF. These files are smaller at equivalent quality but require conversion for AI analysis since most AI APIs don't accept HEIF natively.

### Why thumbnails — and why 800px?

A 40MP photo from a modern camera is 10-20MB. Sending dozens to an AI burns context and money. But **thumbnail size matters more than you'd think** — not just for cost, but for API stability.

**The problem with 1600px thumbnails:**
- Each 1600px JPEG thumbnail is ~300-700KB
- When base64-encoded for API transmission, that's ~400-930KB per image
- Multimodal AI models process images as "vision tokens" — a 1600px image costs ~1500-3000 tokens
- Loading 6-8 images per batch = ~12,000-24,000 tokens *just for images*
- After several batches, accumulated context causes API errors: rate limits, payload size exceeded, degraded image rendering (some images processed at minimum resolution)

**800px is the sweet spot:**
- ~60% fewer vision tokens per image
- Still large enough to assess composition, exposure, focus, and fine detail
- Allows comfortable batches of 4 images without API pressure
- Dramatically reduces the risk of mid-session API failures

On macOS, `sips` handles both JPEG and HEIF:
```bash
# JPEG → thumbnail
sips -Z 800 input.jpg --out output.jpg

# HEIF → JPEG thumbnail
sips -s format jpeg -Z 800 input.hif --out output.jpg
```

## Setup

### 1. Create the folder structure

```
your-vault/
└── sources/
    └── photos/
        ├── README.md        ← Documentation
        ├── .gitignore       ← Exclude heavy files from git
        └── prep.py          ← Preparation script
```

### 2. Configure `.gitignore`

Photos are too large for git. Only version the reports and documentation:

```gitignore
# Photo files (heavy, not versioned)
*.RAF
*.raf
*.JPG
*.jpg
*.JPEG
*.jpeg
*.CR3
*.cr3
*.ARW
*.arw
*.DNG
*.dng
*.HEIC
*.heic
*.HIF
*.hif
*.HEIF
*.heif

# Thumbnails and temp data
.thumbnails/
.session-data.json
```

### 3. Install the preparation script

The `prep.py` script handles the tedious parts:
1. Scans a session folder for JPEG + HEIF/HIF files
2. Extracts EXIF metadata — Pillow for JPEGs, macOS `mdls` for HEIF/HIF
3. Generates 800px JPEG thumbnails using `sips` (macOS) into a `.thumbnails/` subfolder
4. Groups photos by temporal proximity (shots within 10 seconds = same group)
5. Outputs a `.session-data.json` manifest

<details>
<summary>Full prep.py script (click to expand)</summary>

```python
#!/usr/bin/env python3
"""
prep.py — Photo session preparation for AI analysis.

Scans a photo session folder, extracts EXIF metadata from JPEGs
and HEIF/HIF files, generates thumbnails via macOS sips, groups
similar shots by timestamp proximity, and outputs a JSON manifest
for AI consumption.

Usage:
    python3 prep.py <session_folder>
    python3 prep.py                     # auto-detects most recent session
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

THUMBNAIL_SIZE = 800  # long edge in pixels — 800px is optimal for AI vision triage
GROUP_THRESHOLD_SECONDS = 10  # photos within this interval = same group
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".hif", ".heif", ".heic"}
SCRIPT_DIR = Path(__file__).parent


def find_session_folder(base_dir):
    """Find the most recent session folder (YYYY-MM-DD pattern)."""
    sessions = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
        reverse=True,
    )
    return sessions[0] if sessions else None


def extract_exif_mdls(file_path):
    """Extract EXIF metadata using macOS mdls (works with HEIF/HIF)."""
    fields = {
        "kMDItemContentCreationDate": "datetime",
        "kMDItemFNumber": "aperture",
        "kMDItemISOSpeed": "iso",
        "kMDItemExposureTimeSeconds": "shutter_speed_raw",
        "kMDItemFocalLength": "focal_length",
        "kMDItemAcquisitionMake": "camera_make",
        "kMDItemAcquisitionModel": "camera_model",
        "kMDItemWhiteBalance": "white_balance_raw",
    }
    try:
        cmd = ["mdls"] + [arg for f in fields for arg in ("-name", f)] + [str(file_path)]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        result = {}
        for line in out.strip().splitlines():
            parts = line.split("=", 1)
            if len(parts) != 2:
                continue
            key = parts[0].strip()
            val = parts[1].strip().strip('"')
            if val == "(null)" or not val:
                continue
            mapped = fields.get(key)
            if not mapped:
                continue
            if mapped == "datetime":
                try:
                    dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S %z")
                    result["datetime"] = dt.isoformat()
                except ValueError:
                    result["datetime"] = val
            elif mapped == "shutter_speed_raw":
                exp = float(val)
                if exp < 1:
                    denom = round(1 / exp)
                    result["shutter_speed"] = f"1/{denom}"
                else:
                    result["shutter_speed"] = f"{exp}s"
            elif mapped == "white_balance_raw":
                result["white_balance"] = "Auto" if val == "0" else "Manual"
            elif mapped in ("aperture", "focal_length"):
                result[mapped] = round(float(val), 1)
            elif mapped == "iso":
                result[mapped] = int(float(val))
            else:
                result[mapped] = val

        # Dimensions via sips (fast)
        dim_out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(file_path)],
            capture_output=True, text=True, check=True,
        ).stdout
        for dline in dim_out.splitlines():
            if "pixelWidth" in dline:
                result["width"] = int(dline.split(":")[-1].strip())
            elif "pixelHeight" in dline:
                result["height"] = int(dline.split(":")[-1].strip())

        return result
    except Exception as e:
        return {"error": str(e)}


def extract_exif(file_path):
    """Extract relevant EXIF fields from a photo file."""
    # For HEIF/HIF files, use macOS mdls
    if file_path.suffix.lower() in {".hif", ".heif", ".heic"}:
        return extract_exif_mdls(file_path)

    # For JPEGs, use Pillow
    try:
        img = Image.open(file_path)
        exif_data = img._getexif()
        if not exif_data:
            return {}

        tagged = {TAGS.get(k, k): v for k, v in exif_data.items()}
        result = {}

        # Date/time
        for field in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            if field in tagged:
                try:
                    result["datetime"] = datetime.strptime(
                        str(tagged[field]), "%Y:%m:%d %H:%M:%S"
                    ).isoformat()
                except (ValueError, TypeError):
                    pass
                break

        # Exposure
        if "ExposureTime" in tagged:
            et = tagged["ExposureTime"]
            if hasattr(et, "numerator"):
                result["shutter_speed"] = f"{et.numerator}/{et.denominator}"
            else:
                result["shutter_speed"] = str(et)

        if "FNumber" in tagged:
            fn = tagged["FNumber"]
            if hasattr(fn, "numerator") and fn.denominator:
                result["aperture"] = round(fn.numerator / fn.denominator, 1)
            else:
                result["aperture"] = float(fn)

        if "ISOSpeedRatings" in tagged:
            iso = tagged["ISOSpeedRatings"]
            result["iso"] = iso if isinstance(iso, int) else iso[0]

        if "FocalLength" in tagged:
            fl = tagged["FocalLength"]
            if hasattr(fl, "numerator") and fl.denominator:
                result["focal_length"] = round(fl.numerator / fl.denominator, 1)
            else:
                result["focal_length"] = float(fl)

        if "ExposureBiasValue" in tagged:
            eb = tagged["ExposureBiasValue"]
            if hasattr(eb, "numerator") and eb.denominator:
                result["exposure_comp"] = round(eb.numerator / eb.denominator, 2)
            else:
                result["exposure_comp"] = float(eb)

        if "WhiteBalance" in tagged:
            result["white_balance"] = "Auto" if tagged["WhiteBalance"] == 0 else "Manual"

        if "Make" in tagged:
            result["camera_make"] = str(tagged["Make"]).strip()
        if "Model" in tagged:
            result["camera_model"] = str(tagged["Model"]).strip()

        result["width"] = img.width
        result["height"] = img.height
        img.close()
        return result

    except Exception as e:
        return {"error": str(e)}


def generate_thumbnail(photo_path, output_dir):
    """Generate a JPEG thumbnail using macOS sips. Works with JPEG, HEIF, HIF."""
    output_dir.mkdir(exist_ok=True)
    # Always output as .jpg for universal compatibility
    output_name = photo_path.stem.lower() + ".jpg"
    output_path = output_dir / output_name

    try:
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", str(THUMBNAIL_SIZE),
             str(photo_path), "--out", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  Warning: sips failed for {photo_path.name}: {e.stderr.decode()}")
        return None


def group_by_timestamp(photos):
    """Group photos by temporal proximity (burst/similar shot detection)."""
    if not photos:
        return []

    timed = [p for p in photos if p.get("exif", {}).get("datetime")]
    untimed = [p for p in photos if not p.get("exif", {}).get("datetime")]
    timed.sort(key=lambda p: p["exif"]["datetime"])

    groups = []
    current_group = []

    for photo in timed:
        if not current_group:
            current_group.append(photo)
            continue

        prev_time = datetime.fromisoformat(current_group[-1]["exif"]["datetime"])
        curr_time = datetime.fromisoformat(photo["exif"]["datetime"])
        delta = (curr_time - prev_time).total_seconds()

        if delta <= GROUP_THRESHOLD_SECONDS:
            current_group.append(photo)
        else:
            groups.append(current_group)
            current_group = [photo]

    if current_group:
        groups.append(current_group)

    for photo in untimed:
        groups.append([photo])

    return groups


def main():
    if len(sys.argv) > 1:
        session_dir = Path(sys.argv[1])
    else:
        session_dir = find_session_folder(SCRIPT_DIR)
        if not session_dir:
            print("No session folders found. Usage: python3 prep.py <session_folder>")
            sys.exit(1)
        print(f"Auto-detected session: {session_dir.name}")

    if not session_dir.is_dir():
        print(f"Error: {session_dir} is not a directory")
        sys.exit(1)

    # Find photo files (JPEG + HEIF/HIF)
    photos_found = sorted([
        f for f in session_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith(".")
    ])

    if not photos_found:
        print(f"No photo files found in {session_dir}")
        sys.exit(1)

    print(f"Found {len(photos_found)} photo files in {session_dir.name}")
    rafs = [f for f in session_dir.iterdir() if f.suffix.lower() == ".raf"]
    print(f"Found {len(rafs)} RAF files")

    thumbnail_dir = session_dir / ".thumbnails"
    photos = []

    for photo_file in photos_found:
        print(f"  Processing {photo_file.name}...", end=" ")
        exif = extract_exif(photo_file)
        thumb = generate_thumbnail(photo_file, thumbnail_dir)
        photo_data = {
            "filename": photo_file.name,
            "path": str(photo_file),
            "exif": exif,
            "has_raw": any(
                (session_dir / photo_file.stem).with_suffix(ext).exists()
                for ext in [".RAF", ".raf", ".CR3", ".cr3", ".ARW", ".arw", ".DNG", ".dng"]
            ),
            "thumbnail": str(thumb) if thumb else None,
            "size_bytes": photo_file.stat().st_size,
        }
        photos.append(photo_data)
        print("OK")

    groups = group_by_timestamp(photos)

    manifest = {
        "session_date": session_dir.name,
        "session_path": str(session_dir),
        "total_photos": len(photos_found),
        "total_raws": len(rafs),
        "total_groups": len(groups),
        "groups": [
            {"group_id": i + 1, "count": len(group), "photos": group}
            for i, group in enumerate(groups)
        ],
        "prepared_at": datetime.now().isoformat(),
    }

    manifest_path = session_dir / ".session-data.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Session prepared:")
    print(f"   Photos: {len(photos_found)} ({len(rafs)} with RAW)")
    print(f"   Groups: {len(groups)}")
    print(f"   Thumbnails: {thumbnail_dir}")
    print(f"   Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
```

</details>

**Adapting for non-macOS:** Replace the `sips` call in `generate_thumbnail()` with ImageMagick (`convert input.jpg -resize 800x800 output.jpg`) or Pillow's `Image.thumbnail()`. For HEIF files without macOS, install `pillow-heif` (`pip install pillow-heif`) to let Pillow read them, and use `exiftool` for EXIF extraction instead of `mdls`.

**Adapting for other cameras:** The script detects RAW files by extension. Edit the extension list in `.gitignore` and the `has_raw` check in the script for your camera's format (`.CR3` for Canon, `.ARW` for Sony, `.NEF` for Nikon, `.ORF` for Olympus/OM System).

### 4. Add triggers to your AI configuration

If you're using the [trigger system](guide.md), add:

**In `triggers.md`:**
```markdown
| /ingest photos, foto, fotos, sesión fotográfica | `sources/photos/README.md` | ingest |
```

**In the writing triggers:**
```markdown
| Fotos nuevas en `sources/photos/` o `/ingest photos` | Ejecutar prep.py, analizar thumbnails, generar analysis.md | Automático |
```

### 5. Document the photo ingest in your schema

Add a "Photo Ingest" subsection under the Ingest operation in your `schema.md`:

```markdown
### Photo Ingest (extension)

Trigger: `/ingest photos` or `/ingest photos YYYY-MM-DD`

Flow:
1. Run `python3 sources/photos/prep.py <session_folder>`
2. Read `.session-data.json` for structure
3. Analyze thumbnails in batches of 4 (max — see "API stability" below)
4. Generate `analysis.md` alongside the photos
5. Log: `## [date] ingest | Photo session YYYY-MM-DD (location)`
```

---

## The workflow

### Step 1: Copy your photos

After a photography session, copy the files from your SD card to a dated folder:

```bash
mkdir -p sources/photos/2026-04-15
cp /Volumes/SD_CARD/DCIM/100FUJI/*.{RAF,JPG} sources/photos/2026-04-15/
```

### Step 2: Tell the AI to ingest

In your AI session (Claude Code, Copilot CLI, or any multimodal tool):

```
/ingest photos
```

Or for a specific session:
```
/ingest photos 2026-04-15
```

### Step 3: The AI processes

The AI will:
1. **Run prep.py** → creates thumbnails + extracts EXIF + groups photos
2. **Read the manifest** → understands session structure (groups, metadata)
3. **Analyze visually** → looks at thumbnails in batches of 4 (max per turn)
4. **Generate the report** → creates `analysis.md` alongside your photos

> **Note:** The folder date may differ from actual shooting dates — it's typically the SD card transfer date. The AI will identify temporal blocks from EXIF timestamps automatically.

### Step 4: Review and edit

Open `analysis.md` in Obsidian. It lives alongside your photos:

```
sources/photos/2026-04-15/
├── DSCF0001.RAF
├── DSCF0001.JPG
├── ...
└── analysis.md    ← Your report ✨
```

Use the recommendations to:
- Delete the inferior shots from each group
- Apply the suggested Photomator/editor adjustments
- Consider the composition feedback for future shoots

---

## Report format

The `analysis.md` follows this structure:

```markdown
---
title: "Photo analysis — 2026-04-15"
date: 2026-04-15
source_type: photo-session
camera: Fuji X100VI
total_photos: 34
keepers: 18
strong_keepers: 6
processed: true
tags:
  - photography/analysis
---

# Analysis — 2026-04-15

## Session summary
- Total photos: 34 (34 RAF+JPEG pairs)
- Time range: 10:15 – 14:30
- Shooting blocks: 2 (morning outdoor, afternoon interior)
- Conditions: Overcast, ISO 400-1600 range, mostly f/2.0-4.0
- Groups detected: 12

## Rating system
- **Strong keeper** — Portfolio-worthy. Outstanding composition, light, or subject.
- **Keep** — Good photo worth editing. Solid but not exceptional.
- **Marginal** — Context/documentary value only. May keep for completeness.
- **Discard** — Technically flawed (blur, bad exposure) or redundant duplicate.

## Group 1: Street scene with bicycle
| # | File | Aperture | Speed | ISO | Rating |
|---|------|----------|-------|-----|--------|
| 1 | DSCF0001.JPG | f/2.0 | 1/125 | 400 | ★★★ Strong keeper |
| 2 | DSCF0002.JPG | f/2.0 | 1/125 | 400 | Discard (redundant) |

### Recommendation: DSCF0001.JPG
**Why it's the best:** Sharper focus on the bicycle, better timing with the pedestrian in the background creating depth.

### Suggested edits (Photomator)
- Exposure: +0.3 EV
- Highlights: -20
- Shadows: +10
- White Balance: no change
- Saturation: +5
- Sharpening: +15
- Vignette: -10

### Composition notes
- Good use of leading lines from the street
- Consider a tighter crop (3:2 → 16:9) eliminating the distracting element on the right

## Strong keepers (summary)
| File | Subject | Key quality |
|------|---------|-------------|
| DSCF0001.JPG | Street with bicycle | Perfect timing, leading lines |
| DSCF0015.JPG | Cathedral interior | Extraordinary light, scale |
| ... | ... | ... |

## Session patterns
- Tendency to underexpose by ~0.3 EV (consistent across groups)
- Strong eye for geometric composition
- Consider experimenting with f/4-5.6 for more depth of field in street scenes
```

---

## Adapting for your setup

### Different cameras

| Camera brand | RAW extension | Output format | Notes |
|-------------|---------------|---------------|-------|
| Fujifilm | `.RAF` | JPEG or HEIF (`.HIF`) | Film simulations in EXIF (need `exiftool`). X100VI defaults to HIF when HEIF enabled. |
| Canon | `.CR3` (R-series), `.CR2` (older) | JPEG | — |
| Sony | `.ARW` | JPEG or HEIF | A7 IV+ supports HEIF |
| Nikon | `.NEF` / `.NRW` | JPEG or HEIF | Z-series supports HEIF |
| OM System/Olympus | `.ORF` | JPEG | — |
| Panasonic | `.RW2` | JPEG | — |
| Leica | `.DNG` | JPEG | — |
| iPhone/iPad | — | HEIC (`.heic`) | Default format since iOS 11 |

Update `.gitignore` and the `has_raw` extension list in `prep.py`.

### Different editors

The report references **Photomator** by default. Adapt the editing section of your AI's mode configuration to reference your editor:

| Editor | Adjustment terminology |
|--------|----------------------|
| Photomator | Exposure, Contrast, Highlights, Shadows, Clarity, Temperature |
| Lightroom | Exposure, Contrast, Highlights, Shadows, Texture/Clarity, Temp |
| Capture One | Exposure, Contrast, High Dynamic Range, Shadow Recovery, Clarity, Kelvin |
| darktable | Exposure, Contrast (via tone curve), Highlight reconstruction, Shadows, Local contrast, Temperature |
| RawTherapee | Exposure compensation, Contrast (L curve), Highlight recovery, Shadow/highlight, Sharpening, White balance |

### Different AI tools

The core workflow requires a multimodal AI that can:
1. Execute shell commands (to run `prep.py`)
2. View images (to analyze thumbnails)
3. Write files (to generate `analysis.md`)

| Tool | Runs scripts | Views images | Writes files |
|------|-------------|-------------|-------------|
| Claude Code (CLI) | ✅ | ✅ | ✅ |
| GitHub Copilot CLI | ✅ | ✅ | ✅ |
| Claude Desktop | ✅ (with MCP) | ✅ | ✅ (with MCP) |
| Cursor | ✅ | ✅ | ✅ |
| ChatGPT + Code Interpreter | ✅ | ✅ | ✅ |
| Gemini 2.0 | ✅ (with extensions) | ✅ | ✅ (with extensions) |

For tools that can't run scripts, run `prep.py` manually first, then paste the manifest content into the conversation and attach the thumbnails.

### Non-macOS thumbnail generation

Replace the `sips` call with one of these:

**ImageMagick:**
```bash
convert input.jpg -resize 800x800 output.jpg
```

**Pillow (cross-platform Python):**
```python
from PIL import Image
img = Image.open("input.jpg")
img.thumbnail((800, 800))
img.save("output.jpg", quality=85)
```

**Pillow + pillow-heif (for HEIF on any platform):**
```python
import pillow_heif
pillow_heif.register_heif_opener()
from PIL import Image
img = Image.open("input.hif")
img.thumbnail((800, 800))
img.save("output.jpg", quality=85)
```

**FFmpeg:**
```bash
ffmpeg -i input.jpg -vf "scale='min(800,iw)':'min(800,ih)':force_original_aspect_ratio=decrease" output.jpg
```

**EXIF from HEIF without macOS `mdls`:**
```bash
# exiftool works universally for all formats
exiftool -json -DateTimeOriginal -FNumber -ISO -ExposureTime -FocalLength -Make -Model input.hif
```

---

## API stability and token management

This section exists because we learned these lessons the hard way. Multimodal AI APIs have hard limits on image processing that aren't obvious until you hit them mid-session.

### The core problem

Each image sent to a multimodal AI is converted to "vision tokens." The cost scales with resolution:

| Thumbnail size | Approx. tokens per image | 4-image batch | 8-image batch |
|---------------|-------------------------|---------------|---------------|
| 1600px | 1,500–3,000 | 6,000–12,000 | 12,000–24,000 |
| 800px | 600–1,200 | 2,400–4,800 | 4,800–9,600 |

These vision tokens compete with the text context window. After several batches, the accumulated conversation (prior image descriptions, analysis text, EXIF data) plus new image tokens can exceed API limits.

### Symptoms of token overflow

- **Inconsistent image rendering:** Some images in a batch are processed at minimum resolution (appear "tiny" or lack detail in the AI's description)
- **API rate errors:** 429 (Too Many Requests), 413 (Payload Too Large)
- **Degraded analysis quality:** The AI's descriptions become vague or generic for later images in a batch
- **Session crashes:** The API returns 500 errors or the session hangs

### Prevention rules

1. **Thumbnails at 800px, not 1600px.** This is the single most impactful change. 800px preserves enough detail for composition, exposure, and focus assessment while using ~60% fewer tokens.

2. **4 images per batch, maximum.** Not 6, not 8. Four images at 800px stays comfortably under per-turn token limits.

3. **If any image renders poorly, re-view it individually.** Don't skip it — view it alone in the next turn. The AI needs to see every photo at adequate resolution to make valid comparisons.

4. **Keep inter-batch text concise.** Reference previous photos by filename (e.g., "DSCF1090"), don't re-describe them. The AI has them in context already.

5. **For sessions with 50+ photos**, consider a two-pass approach:
   - **Pass 1 (triage):** Quick scan at 4 per batch, marking obvious discards and potential keepers
   - **Pass 2 (detailed):** Only load keepers/ambiguous shots for detailed comparison and edit recommendations

---

## Limitations

- **AI can't read RAW files directly.** It needs JPEG or HEIF previews. If you shoot RAW-only, you'll need to generate JPEGs first (your camera software can batch-export).
- **HEIF/HIF requires macOS tools.** On macOS, `sips` and `mdls` handle HEIF natively. On Linux/Windows, install `pillow-heif` and `exiftool` as alternatives.
- **Batch size is critical.** Sending more than 4 thumbnails per turn causes API instability — degraded rendering, errors, or hallucinated descriptions. This was tested empirically with 800px and 1600px thumbnails across Claude and Copilot CLI.
- **Technical precision has limits.** The AI can identify obviously soft focus but won't measure MTF charts. For pixel-level sharpness evaluation, zoom into specific areas and ask about them individually.
- **Style is subjective.** The AI gives technically grounded opinions, but "best photo" involves taste. Use its analysis as input, not as a verdict.
- **Context window limits.** Even with 800px thumbnails, sessions of 50+ photos benefit from the two-pass approach described above.
- **EXIF depth varies.** Pillow extracts standard EXIF fields. macOS `mdls` extracts most but misses exposure compensation. For camera-specific data (Fuji film simulations, Canon Picture Styles), install `exiftool` for richer metadata.
- **Folder date ≠ shoot date.** The session folder is typically named by transfer date, not shooting date. Photos from a multi-day trip may all land in one folder. The prep script handles this by grouping on EXIF timestamps, not folder names.

---

## Future ideas

- **Automatic IPTC tagging** — have the AI suggest keywords and descriptions for each photo
- **Portfolio curation** — across sessions, identify your strongest images for a portfolio
- **Progress tracking** — compare analysis reports over time to see technique improvement
- **Lightroom/Photomator preset generation** — translate repeated adjustments into saved presets
- **GPS/location integration** — if your camera has GPS, enrich reports with location context

---

*Built as an extension of the [Obsidian Memory for AI](README.md) system. April 2026. Updated with lessons from real-world HEIF sessions and API stability testing.*
