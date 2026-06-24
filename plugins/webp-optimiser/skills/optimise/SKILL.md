---
name: optimise
description: >-
  Convert and optimise images to WebP to shrink file size. Use whenever the user
  shares image files (PNG, JPG, JPEG, GIF, TIFF, BMP) and asks to optimise,
  compress, shrink, or convert them — or asks to "go through a project/folder and
  optimise images" or convert images to WebP. Writes .webp into a separate output
  folder with smart lossy/lossless compression and can archive the originals.
---

# WebP Optimiser

Convert images to optimised WebP using the bundled, self-contained Python script.
Use this skill when the user wants to shrink, compress, optimise, or convert
images to WebP — including sweeping a whole project folder for images.

## How to run it

The converter lives next to this skill. Invoke it with Python, passing the target
files and/or folders. Reference it via the plugin root environment variable so the
path is correct after installation:

- **bash / zsh:**
  ```bash
  python "$CLAUDE_PLUGIN_ROOT/skills/optimise/scripts/optimise.py" <paths…> [options]
  ```
- **PowerShell (Windows):**
  ```powershell
  python "$env:CLAUDE_PLUGIN_ROOT/skills/optimise/scripts/optimise.py" <paths…> [options]
  ```

If `python` is not found, try `python3`. The script only needs **Pillow**; if it
reports Pillow is missing, run `python -m pip install Pillow` (or add `--auto-install`).

## Default behaviour (recommended)

Unless the user asks otherwise, use the safe defaults: write `.webp` into a separate
`./webp-optimised/` folder (mirroring the source tree), leave originals untouched,
and create a zip backup of the originals.

```bash
python "$CLAUDE_PLUGIN_ROOT/skills/optimise/scripts/optimise.py" <paths…> --mode smart -o ./webp-optimised --archive
```

Smart mode = PNG → lossless WebP, animated GIF → animated lossy WebP, everything
else → lossy quality 80.

## Adjust to the request

- "replace the originals" / "optimise in place" → add `--replace` (it auto-keeps an
  original when the WebP would be larger). Always combine with `--archive` for safety.
- "put them next to the originals" → add `--in-place`.
- "higher/lower quality", "lossless", "lossy" → use `-q <0-100>` and/or
  `--mode {smart,lossy,lossless}`.
- "only this folder, not subfolders" → add `--no-recursive`.
- "just show me what it would do" → add `--dry-run`.
- Restrict input types with `--formats png,jpg` if asked.

## After running

Report the per-file and total size savings the script prints (e.g.
`saved 3.4 MB, 78%`). If files failed, surface which ones and why. If the user ran
with `--replace`, mention the originals backup zip location.
