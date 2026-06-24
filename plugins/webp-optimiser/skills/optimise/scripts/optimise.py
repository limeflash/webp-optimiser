#!/usr/bin/env python3
"""webp-optimiser — convert and optimise images to WebP.

A small, dependency-light CLI (only requires Pillow) that converts images
(PNG, JPG, JPEG, GIF, TIFF, BMP) to optimised WebP. It is deliberately free of
any Claude-specific coupling so it can be used as a standalone tool too.

Smart mode (default):
  * PNG            -> lossless WebP
  * animated GIF   -> animated lossy WebP
  * everything else-> lossy WebP (quality 80)

By default, .webp files are written into a separate output folder
(./webp-optimised) mirroring the input tree, and the originals are left
untouched. Use --archive to zip the originals as a backup, --in-place to write
next to the sources, or --replace to delete originals after a successful,
size-reducing conversion.

Examples:
  python optimise.py ./assets
  python optimise.py logo.png banner.jpg
  python optimise.py ./src -o ./dist/webp --archive
  python optimise.py ./public --in-place --replace --archive
  python optimise.py ./img -q 90 --mode lossy
"""

from __future__ import annotations

import argparse
import datetime
import sys
import zipfile
from pathlib import Path

DEFAULT_FORMATS = ["png", "jpg", "jpeg", "gif", "tiff", "tif", "bmp"]
DEFAULT_OUTPUT_DIR = "webp-optimised"
HIGH_BIT_MODES = ("I", "I;16", "I;16B", "I;16L", "F")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def fmt_delta(pct: float) -> str:
    """Describe a size change percentage in plain words."""
    if pct >= 0:
        return f"{pct:.0f}% smaller"
    return f"{-pct:.0f}% larger"


def human_size(num: int) -> str:
    """Format a byte count as a human-readable string."""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def require_pillow(auto_install: bool):
    """Import Pillow, optionally auto-installing it, else exit with guidance."""
    try:
        from PIL import Image  # noqa: F401

        return
    except ImportError:
        pass

    if auto_install:
        import subprocess

        print("Pillow not found — installing (pip install Pillow)...", flush=True)
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
            from PIL import Image  # noqa: F401

            return
        except Exception as exc:  # pragma: no cover - install failure path
            print(f"error: automatic install failed: {exc}", file=sys.stderr)

    print(
        "error: this tool requires Pillow.\n"
        "       install it with:  python -m pip install Pillow\n"
        "       or re-run with --auto-install",
        file=sys.stderr,
    )
    sys.exit(2)


def collect_images(paths, formats, recursive):
    """Expand the given paths into a list of (image_path, base_dir) tuples.

    base_dir is the root used to compute the mirrored output path. For a file
    argument the base is the file's parent; for a directory it is the directory.
    Duplicate physical files (resolved) are only listed once.
    """
    exts = {f".{f.lower().lstrip('.')}" for f in formats}
    found = []
    seen = set()

    def add(img_path: Path, base: Path):
        try:
            key = img_path.resolve()
        except OSError:
            key = img_path.absolute()
        if key in seen:
            return
        seen.add(key)
        found.append((img_path, base))

    for raw in paths:
        p = Path(raw)
        if not p.exists():
            print(f"warning: path not found, skipping: {p}", file=sys.stderr)
            continue
        if p.is_file():
            if p.suffix.lower() in exts:
                add(p, p.parent)
            else:
                print(f"warning: not a supported image, skipping: {p}", file=sys.stderr)
        else:
            globber = p.rglob("*") if recursive else p.glob("*")
            for child in sorted(globber):
                if child.is_file() and child.suffix.lower() in exts:
                    add(child, p)

    return found


def rel_to_base(path: Path, base: Path) -> Path:
    """Path of `path` relative to `base`, using the lexical path first.

    Lexical first keeps the mirrored sub-directory layout even for symlinks
    (where resolve() could point outside base). Falls back to the bare name.
    """
    try:
        return path.relative_to(base)
    except ValueError:
        try:
            return path.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            return Path(path.name)


def output_path_for(img_path: Path, base: Path, output_dir: Path, in_place: bool) -> Path:
    """Compute the (pre-collision) .webp destination for an image."""
    if in_place:
        return img_path.with_suffix(".webp")
    return (output_dir / rel_to_base(img_path, base)).with_suffix(".webp")


def plan_outputs(images, output_dir: Path, in_place: bool):
    """Assign a unique .webp destination to every image.

    Two different sources can map to the same default name (e.g. a.png + a.jpg
    -> a.webp, or same-named files from different folders). To avoid silently
    overwriting one with another — and, under --replace, deleting both originals
    while keeping only one result — colliding destinations get a -1, -2, ...
    suffix. Returns (plan, had_collisions) where plan is a list of
    (img_path, base, dest).
    """
    used = set()
    plan = []
    collisions = False
    for img_path, base in images:
        dest = output_path_for(img_path, base, output_dir, in_place)
        cand = dest
        n = 1
        while str(cand).casefold() in used:
            collisions = True
            cand = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
            n += 1
        used.add(str(cand).casefold())
        plan.append((img_path, base, cand))
    return plan, collisions


def is_animated(img) -> bool:
    return getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1


def normalise_mode(img):
    """Return an image in a mode WebP can encode (L, RGB, RGBA)."""
    if img.mode in ("RGB", "RGBA", "L"):
        return img
    if img.mode == "P":
        return img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode == "LA":
        return img.convert("RGBA")
    if img.mode in ("CMYK", "YCbCr", "HSV"):
        return img.convert("RGB")
    if img.mode in HIGH_BIT_MODES:
        return img.convert("L")  # high bit-depth -> 8-bit (warned in save_static)
    return img.convert("RGBA")


def save_static(img, dest: Path, lossless: bool, quality: int, method: int):
    from PIL import ImageOps

    img = ImageOps.exif_transpose(img)  # bake in EXIF orientation; WebP drops EXIF
    if lossless and img.mode in HIGH_BIT_MODES:
        print(f"  note: {dest.name}: {img.mode} reduced to 8-bit "
              f"(WebP has no high-bit-depth lossless)", file=sys.stderr)
    img = normalise_mode(img)
    params = {"format": "WEBP", "method": method}
    if lossless:
        params.update(lossless=True, quality=100)
    else:
        params.update(quality=quality)
    img.save(dest, **params)


def save_animated(img, dest: Path, lossless: bool, quality: int, method: int):
    frames = []
    durations = []
    n = getattr(img, "n_frames", 1)
    for i in range(n):
        img.seek(i)  # Pillow composites partial frames + disposal on seek
        frames.append(img.convert("RGBA"))
        durations.append(img.info.get("duration", 100))
    loop = img.info.get("loop", 0)
    params = {
        "format": "WEBP",
        "method": method,
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "loop": loop,
    }
    if lossless:
        params["lossless"] = True
    else:
        params["quality"] = quality
    frames[0].save(dest, **params)


def choose_lossless(img_path: Path, mode: str) -> bool:
    if mode == "lossless":
        return True
    if mode == "lossy":
        return False
    # smart: PNG -> lossless, everything else (incl. GIF) -> lossy
    return img_path.suffix.lower() == ".png"


# --------------------------------------------------------------------------- #
# Archiving
# --------------------------------------------------------------------------- #
def archive_originals(images, output_dir: Path) -> Path:
    """Zip every original into the output folder, with collision-free arcnames."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = output_dir / f"_originals-backup-{stamp}.zip"
    used = set()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for img_path, base in images:
                arc = rel_to_base(img_path, base).as_posix()
                key = arc.casefold()
                n = 1
                while key in used:  # never let one backup entry shadow another
                    p = Path(arc)
                    arc = p.with_name(f"{p.stem}-{n}{p.suffix}").as_posix()
                    key = arc.casefold()
                    n += 1
                used.add(key)
                zf.write(img_path, arc)
    except Exception:
        try:
            zip_path.unlink()  # don't leave a half-written backup behind
        except OSError:
            pass
        raise
    return zip_path


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimise.py",
        description="Convert and optimise images to WebP.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python optimise.py ./assets\n"
            "  python optimise.py logo.png banner.jpg -o ./dist/webp --archive\n"
            "  python optimise.py ./public --in-place --replace --archive\n"
        ),
    )
    parser.add_argument("paths", nargs="+", help="image files and/or directories to process")
    parser.add_argument(
        "-o", "--output-dir", default=DEFAULT_OUTPUT_DIR,
        help=f"output folder for .webp files (default: ./{DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-q", "--quality", type=int, default=80,
        help="WebP quality for lossy encoding, 0-100 (default: 80)",
    )
    parser.add_argument(
        "--mode", choices=("smart", "lossy", "lossless"), default="smart",
        help="compression mode (default: smart — PNG lossless, others lossy)",
    )
    parser.add_argument(
        "--method", type=int, default=6,
        help="WebP compression effort 0-6, higher = smaller but slower (default: 6)",
    )
    parser.add_argument(
        "--in-place", action="store_true",
        help="write .webp next to each source instead of into the output folder",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="delete the original after a successful, size-reducing conversion (implies --in-place)",
    )
    parser.add_argument(
        "--archive", action="store_true",
        help="zip all originals into the output folder before converting (backup)",
    )
    parser.add_argument(
        "--no-recursive", dest="recursive", action="store_false",
        help="do not descend into subdirectories (recursion is on by default)",
    )
    parser.add_argument(
        "--formats", default=",".join(DEFAULT_FORMATS),
        help="comma-separated input extensions (default: %(default)s)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    parser.add_argument("--auto-install", action="store_true", help="pip install Pillow if it is missing")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not 0 <= args.quality <= 100:
        print("error: --quality must be between 0 and 100", file=sys.stderr)
        return 2
    if not 0 <= args.method <= 6:
        print("error: --method must be between 0 and 6", file=sys.stderr)
        return 2

    in_place = args.in_place or args.replace
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    output_dir = Path(args.output_dir)

    images = collect_images(args.paths, formats, args.recursive)
    if not images:
        print("No supported images found.")
        return 0

    plan, collisions = plan_outputs(images, output_dir, in_place)
    if collisions:
        print("note: some images would share an output name; the later ones were "
              "renamed (-1, -2, …) so nothing is overwritten.", file=sys.stderr)

    print(f"Found {len(images)} image(s). Mode: {args.mode}"
          + ("" if in_place else f"  ->  {output_dir}")
          + (" [dry-run]" if args.dry_run else ""))

    # Dry run never imports Pillow and never writes (no archive, no convert).
    if args.dry_run:
        for img_path, _base, dest in plan:
            print(f"  would convert {img_path}  ->  {dest}")
        print("-" * 48)
        print(f"Dry run: {len(plan)} image(s) would be processed.")
        return 0

    require_pillow(args.auto_install)
    from PIL import Image, UnidentifiedImageError

    # Archive originals up front (so a later --replace can't lose data).
    if args.archive:
        zip_path = archive_originals(images, output_dir)
        print(f"Archived {len(images)} original(s) -> {zip_path}")

    total_in = 0
    total_out = 0
    converted = 0
    skipped = 0
    failed = 0
    replace_errors = 0

    for img_path, _base, dest in plan:
        try:
            orig_size = img_path.stat().st_size
        except OSError:
            orig_size = 0

        # Never write onto / delete the source itself.
        try:
            same = img_path.resolve() == dest.resolve()
        except OSError:
            same = False
        if same:
            print(f"  {img_path.name}: source is already the target — skipped")
            skipped += 1
            continue

        try:
            with Image.open(img_path) as img:
                lossless = choose_lossless(img_path, args.mode)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if is_animated(img):
                    save_animated(img, dest, lossless, args.quality, args.method)
                else:
                    save_static(img, dest, lossless, args.quality, args.method)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            print(f"  FAILED  {img_path}: {exc}", file=sys.stderr)
            failed += 1
            continue

        new_size = dest.stat().st_size
        total_in += orig_size
        total_out += new_size
        converted += 1
        pct = (1 - new_size / orig_size) * 100 if orig_size else 0.0

        if new_size >= orig_size and orig_size:
            if args.replace:
                # Don't destroy a smaller original for a larger webp.
                try:
                    dest.unlink()
                except OSError:
                    pass
                print(f"  {img_path.name}: {human_size(orig_size)} -> "
                      f"{human_size(new_size)} ({fmt_delta(pct)}) — kept original, skipped")
                converted -= 1
                total_out -= new_size
                total_in -= orig_size
                skipped += 1
                continue
            print(f"  {img_path.name}: {human_size(orig_size)} -> "
                  f"{human_size(new_size)} ({fmt_delta(pct)})  (no gain — original is smaller)")
            continue

        print(f"  {img_path.name}: {human_size(orig_size)} -> "
              f"{human_size(new_size)} ({fmt_delta(pct)})")

        if args.replace:
            try:
                img_path.unlink()
            except OSError as exc:
                print(f"    note: could not remove original {img_path}: {exc}", file=sys.stderr)
                replace_errors += 1

    # Summary
    print("-" * 48)
    saved = total_in - total_out
    overall = (saved / total_in * 100) if total_in else 0.0
    print(f"Converted {converted} image(s)"
          + (f", skipped {skipped}" if skipped else "")
          + (f", {failed} failed" if failed else "")
          + (f", {replace_errors} original(s) not removed" if replace_errors else "")
          + ".")
    if converted:
        print(f"Total: {human_size(total_in)} -> {human_size(total_out)}  "
              f"(saved {human_size(saved)}, {overall:.0f}%)")
    return 1 if (failed or replace_errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
