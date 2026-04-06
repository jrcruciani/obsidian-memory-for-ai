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
| Camera shooting RAW+JPEG | JPEGs for AI analysis, RAWs for editing | JPEG-only works too (no RAW editing later) |
| macOS with `sips` | Generate thumbnails from full-res images | ImageMagick, Pillow, or any resize tool |
| Python 3 + Pillow | Extract EXIF metadata from JPEGs | `exiftool` CLI works too |
| Multimodal AI | Visual analysis of photographs | Claude (via Claude Code, Copilot CLI), GPT-4o, Gemini |

### Why thumbnails?

A 40MP JPEG from a modern camera is 10-15MB. Sending dozens of these to an AI burns context and money. Resizing to 1600px on the long edge (~300KB) preserves enough detail for composition and exposure analysis while being practical for batch processing.

On macOS, `sips` is built-in and handles this efficiently:
```bash
sips -Z 1600 input.jpg --out output.jpg
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

# Thumbnails and temp data
.thumbnails/
.session-data.json
```

### 3. Install the preparation script

The `prep.py` script handles the tedious parts:
1. Scans a session folder for JPEG files
2. Extracts EXIF metadata (aperture, shutter speed, ISO, datetime) using Pillow
3. Generates thumbnails using `sips` (macOS) into a `.thumbnails/` subfolder
4. Groups photos by temporal proximity (shots within 10 seconds = same group)
5. Outputs a `.session-data.json` manifest

<details>
<summary>Full prep.py script (click to expand)</summary>

```python
#!/usr/bin/env python3
"""
prep.py — Photo session preparation for AI analysis.

Scans a photo session folder, extracts EXIF metadata from JPEGs,
generates thumbnails via macOS sips, groups similar shots by
timestamp proximity, and outputs a JSON manifest for AI consumption.

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

THUMBNAIL_SIZE = 1600  # long edge in pixels
GROUP_THRESHOLD_SECONDS = 10  # photos within this interval = same group
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}
SCRIPT_DIR = Path(__file__).parent


def find_session_folder(base_dir):
    """Find the most recent session folder (YYYY-MM-DD pattern)."""
    sessions = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
        reverse=True,
    )
    return sessions[0] if sessions else None


def extract_exif(jpeg_path):
    """Extract relevant EXIF fields from a JPEG file."""
    try:
        img = Image.open(jpeg_path)
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


def generate_thumbnail(jpeg_path, output_dir):
    """Generate a thumbnail using macOS sips."""
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / jpeg_path.name.lower()

    try:
        subprocess.run(
            ["sips", "-Z", str(THUMBNAIL_SIZE), str(jpeg_path), "--out", str(output_path)],
            capture_output=True, check=True,
        )
        return output_path
    except subprocess.CalledProcessError:
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

    jpegs = sorted([
        f for f in session_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith(".")
    ])

    if not jpegs:
        print(f"No JPEG files found in {session_dir}")
        sys.exit(1)

    print(f"Found {len(jpegs)} JPEG files in {session_dir.name}")
    rafs = [f for f in session_dir.iterdir() if f.suffix.lower() == ".raf"]
    print(f"Found {len(rafs)} RAF files")

    thumbnail_dir = session_dir / ".thumbnails"
    photos = []

    for jpeg in jpegs:
        print(f"  Processing {jpeg.name}...", end=" ")
        exif = extract_exif(jpeg)
        thumb = generate_thumbnail(jpeg, thumbnail_dir)
        photo_data = {
            "filename": jpeg.name,
            "path": str(jpeg),
            "exif": exif,
            "has_raw": any(
                (session_dir / jpeg.stem).with_suffix(ext).exists()
                for ext in [".RAF", ".raf", ".CR3", ".cr3", ".ARW", ".arw", ".DNG", ".dng"]
            ),
            "thumbnail": str(thumb) if thumb else None,
            "size_bytes": jpeg.stat().st_size,
        }
        photos.append(photo_data)
        print("OK")

    groups = group_by_timestamp(photos)

    manifest = {
        "session_date": session_dir.name,
        "session_path": str(session_dir),
        "total_jpegs": len(jpegs),
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
    print(f"   Photos: {len(jpegs)} ({len(rafs)} with RAW)")
    print(f"   Groups: {len(groups)}")
    print(f"   Thumbnails: {thumbnail_dir}")
    print(f"   Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
```

</details>

**Adapting for non-macOS:** Replace the `sips` call in `generate_thumbnail()` with ImageMagick (`convert input.jpg -resize 1600x1600 output.jpg`) or Pillow's `Image.thumbnail()`.

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
3. Analyze thumbnails in batches of 6-8
4. Generate `analysis.md` alongside the photos
5. Log: `## [date] ingest | Photo session YYYY-MM-DD`
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
3. **Analyze visually** → looks at thumbnails in batches of 6-8
4. **Generate the report** → creates `analysis.md` alongside your photos

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
processed: true
tags:
  - photography/analysis
---

# Analysis — 2026-04-15

## Session summary
- Total photos: 34 (34 RAF+JPEG pairs)
- Time range: 10:15 – 14:30
- Conditions: Overcast, ISO 400-1600 range, mostly f/2.0-4.0
- Groups detected: 12

## Group 1: Street scene with bicycle
| # | File | Aperture | Speed | ISO | Rating |
|---|------|----------|-------|-----|--------|
| 1 | DSCF0001.JPG | f/2.0 | 1/125 | 400 | ★★★ Best |
| 2 | DSCF0002.JPG | f/2.0 | 1/125 | 400 | ★★ |

### Recommendation: DSCF0001.JPG
**Why it's the best:** Sharper focus on the bicycle, better timing with the pedestrian in the background creating depth.

### Suggested edits (Photomator)
- Exposure: +0.3 EV
- Contrast: +15
- Highlights: -20
- Shadows: +10
- Clarity: +10
- Temperature: no change

### Composition notes
- Good use of leading lines from the street
- Consider a tighter crop eliminating the distracting element on the right

## Session patterns
- Tendency to underexpose by ~0.3 EV (consistent across groups)
- Strong eye for geometric composition
- Consider experimenting with f/4-5.6 for more depth of field in street scenes
```

---

## Adapting for your setup

### Different cameras

| Camera brand | RAW extension | Notes |
|-------------|---------------|-------|
| Fujifilm | `.RAF` | Film simulations in EXIF (need `exiftool` for full extraction) |
| Canon | `.CR3` (R-series), `.CR2` (older) | — |
| Sony | `.ARW` | — |
| Nikon | `.NEF` / `.NRW` | — |
| OM System/Olympus | `.ORF` | — |
| Panasonic | `.RW2` | — |
| Leica | `.DNG` | — |

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
convert input.jpg -resize 1600x1600 output.jpg
```

**Pillow (cross-platform Python):**
```python
from PIL import Image
img = Image.open("input.jpg")
img.thumbnail((1600, 1600))
img.save("output.jpg", quality=85)
```

**FFmpeg:**
```bash
ffmpeg -i input.jpg -vf "scale='min(1600,iw)':'min(1600,ih)':force_original_aspect_ratio=decrease" output.jpg
```

---

## Limitations

- **AI can't read RAW files directly.** It needs JPEG previews. If you shoot RAW-only, you'll need to generate JPEGs first (your camera software can batch-export).
- **Batch size matters.** Sending 30 photos at once degrades analysis quality. The 6-8 photo batch size is a good balance.
- **Technical precision has limits.** The AI can identify obviously soft focus but won't measure MTF charts. For pixel-level sharpness evaluation, zoom into specific areas and ask about them individually.
- **Style is subjective.** The AI gives technically grounded opinions, but "best photo" involves taste. Use its analysis as input, not as a verdict.
- **Context window limits.** Even with thumbnails, very large sessions (50+) will need multiple passes. The prep script groups them for you; the AI processes groups sequentially.
- **EXIF depth varies.** Pillow extracts standard EXIF fields. For camera-specific data (Fuji film simulations, Canon Picture Styles), install `exiftool` for richer metadata.

---

## Future ideas

- **Automatic IPTC tagging** — have the AI suggest keywords and descriptions for each photo
- **Portfolio curation** — across sessions, identify your strongest images for a portfolio
- **Progress tracking** — compare analysis reports over time to see technique improvement
- **Lightroom/Photomator preset generation** — translate repeated adjustments into saved presets
- **GPS/location integration** — if your camera has GPS, enrich reports with location context

---

*Built as an extension of the [Obsidian Memory for AI](README.md) system. April 2026.*
