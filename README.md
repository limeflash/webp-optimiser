# webp-optimiser

Convert and optimise images to **WebP** — as a [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin *and* a standalone Python CLI.

Point it at images or a whole project folder and it produces optimised `.webp`
files, reports the size savings, and keeps your originals safe.

- **Smart compression** — PNG → lossless, animated GIF → animated lossy, everything else → lossy (quality 80).
- **Safe by default** — writes `.webp` into a separate `./webp-optimised/` folder, originals untouched.
- **Archiving** — `--archive` zips your originals as a backup before converting.
- **Flexible** — `--replace` / `--in-place`, custom quality, recursion control, dry-run.
- Supports **PNG, JPG/JPEG, GIF, TIFF, BMP**. Only dependency: [Pillow](https://python-pillow.org/).

---

## Use it with Claude Code

This repo is a Claude Code **plugin marketplace**. Add it and install the plugin:

```text
/plugin marketplace add limeflash/webp-optimiser
/plugin install webp-optimiser@webp-optimiser
```

Then just talk to Claude:

> "optimise these images to webp"
> "go through ./public and convert all the images to webp, keep a backup"

The `optimise` skill triggers automatically when you share images or ask to
shrink/convert/optimise them.

---

## Use it standalone (no Claude required)

The converter is a plain Python script with zero Claude coupling.

```bash
pip install Pillow

python plugins/webp-optimiser/skills/optimise/scripts/optimise.py ./assets
```

### Examples

```bash
# Convert a folder into ./webp-optimised/ (originals untouched)
python optimise.py ./assets

# Specific files into a chosen output folder, with an originals backup zip
python optimise.py logo.png banner.jpg -o ./dist/webp --archive

# Optimise a project in place and delete originals (backup kept in the zip)
python optimise.py ./public --in-place --replace --archive

# Force lossy quality 90
python optimise.py ./img -q 90 --mode lossy

# Preview without writing anything
python optimise.py ./img --dry-run
```

### Options

| Flag | Description |
| --- | --- |
| `paths…` | One or more image files and/or directories. |
| `-o, --output-dir DIR` | Output folder for `.webp` (default `./webp-optimised`). |
| `-q, --quality 0-100` | Lossy quality (default `80`). |
| `--mode {smart,lossy,lossless}` | Compression mode (default `smart`). |
| `--method 0-6` | WebP compression effort (default `6`; lower = faster, larger). |
| `--in-place` | Write `.webp` next to each source. |
| `--replace` | Delete the original after a successful, size-reducing conversion (implies `--in-place`). |
| `--archive` | Zip all originals into the output folder before converting. |
| `--no-recursive` | Don't descend into subfolders (recursion is on by default). |
| `--formats png,jpg,…` | Restrict which input extensions are processed. |
| `--dry-run` | Show what would happen, write nothing. |
| `--auto-install` | `pip install Pillow` automatically if it's missing. |

> Safety: in `--replace` mode, if the WebP would be **larger** than the source,
> the original is kept and the conversion is skipped.

---

## Requirements

- Python 3.8+
- Pillow (`pip install Pillow` or `pip install -r requirements.txt`)

## License

[MIT](LICENSE) © limeflash
