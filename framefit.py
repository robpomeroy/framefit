"""
framefit.py — Resize and convert photos for a digital photo frame.

Usage:
    python framefit.py <path> [--width WIDTH] [--height HEIGHT]
    [--dry-run]

Arguments:
    path            Root directory containing photos to process (searched
                    recursively).
    --width         Target frame width in pixels (default: 2000).
    --height        Target frame height in pixels (default: 1200).
    --dry-run       Show what would happen without creating/deleting files.

Behaviour:
    - Recursively scans <path> for images with supported extensions.
    - Resizes each image proportionally so it fits within the target resolution
      (both upscaling and downscaling are applied as needed).
    - Converts the result to a non-progressive JPEG (quality 95).
    - Preserves EXIF metadata where available; resets the orientation tag to 1
      after applying any rotation via exif_transpose.
    - Saves the output as <original_name>.jpg next to the original file.
    - Deletes the original file after successful conversion (except when the
      original is already a .jpg/.jpeg, in which case it is overwritten
      in-place).
    - In dry-run mode, reports intended actions without writing or deleting.
    - Skips and logs any file that cannot be processed; processing continues.

Setup (one-time):
    python -m venv venv
    venv\\Scripts\\activate
    pip install -r requirements.txt
"""

import argparse
import logging
import sys
from pathlib import Path

import piexif
from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".gif", ".tiff", ".tif",
    ".png", ".bmp", ".webp",
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging() -> logging.Logger:
    """Configure and return a module-level console logger."""
    logger = logging.getLogger("framefit")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s",
                              datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    return logger


logger = setup_logging()

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def calculate_new_size(
    orig_w: int, orig_h: int, target_w: int, target_h: int
) -> tuple[int, int]:
    """
    Return (new_width, new_height) scaled proportionally so the image fits
    within target_w x target_h.  Both upscaling and downscaling are applied.
    """
    scale = min(target_w / orig_w, target_h / orig_h)
    return round(orig_w * scale), round(orig_h * scale)


def _load_exif_bytes(img: Image.Image) -> bytes | None:
    """
    Extract EXIF bytes from a PIL image, reset the orientation tag to 1
    (since exif_transpose has already physically applied any rotation),
    and return the updated bytes.  Returns None if no valid EXIF is found.
    """
    try:
        raw = img.info.get("exif")
        if not raw:
            return None
        exif_dict = piexif.load(raw)
        # Reset orientation so viewers don't rotate the already-corrected
        # image.
        ifd = exif_dict.get("0th", {})
        if piexif.ImageIFD.Orientation in ifd:
            ifd[piexif.ImageIFD.Orientation] = 1
        return piexif.dump(exif_dict)
    except Exception:
        return None


def process_image(
    source_path: Path,
    target_w: int,
    target_h: int,
    dry_run: bool = False,
) -> bool:
    """
    Resize, convert, and save a single image as a non-progressive JPEG.

    Returns True on success, False on failure.
    """
    output_path = source_path.with_suffix(".jpg")

    try:
        with Image.open(source_path) as img:
            # Physically apply any EXIF rotation before we do anything else.
            img = ImageOps.exif_transpose(img)

            exif_bytes = _load_exif_bytes(img)

            orig_w, orig_h = img.size
            new_w, new_h = calculate_new_size(
                orig_w, orig_h, target_w, target_h)

            if dry_run:
                if source_path.resolve() != output_path.resolve():
                    logger.info(
                        "[DRY RUN] Would convert: %s  ->  %s  (%dx%d) and "
                        "delete original",
                        source_path.name,
                        output_path.name,
                        new_w,
                        new_h,
                    )
                else:
                    logger.info(
                        "[DRY RUN] Would update in-place: %s  (%dx%d)",
                        source_path.name,
                        new_w,
                        new_h,
                    )
                return True

            img = img.resize((new_w, new_h), Image.LANCZOS)

            # JPEG requires RGB; convert from RGBA, palette, grayscale, etc.
            if img.mode != "RGB":
                img = img.convert("RGB")

            save_kwargs: dict[str, object] = {
                "format": "JPEG",
                "progressive": False,
                "quality": 95,
                "optimize": False,
            }
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes

            img.save(output_path, **save_kwargs)

        # Delete original only when it differs from the output file.
        # On Windows, Path.resolve() normalises case, so .JPG and .jpg
        # pointing to the same file will compare equal.
        if source_path.resolve() != output_path.resolve():
            source_path.unlink()
            logger.info("Converted: %s  →  %s  (%dx%d)", source_path.name,
                        output_path.name, new_w, new_h)
        else:
            logger.info("Updated:   %s  (%dx%d)",
                        source_path.name, new_w, new_h)

        return True

    except Exception as exc:
        logger.error("Failed to process %s: %s", source_path, exc)
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resize and convert photos for a digital photo frame."
    )
    parser.add_argument(
        "path",
        help="Root directory containing photos to process.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=2000,
        metavar="PIXELS",
        help="Target frame width in pixels (default: 2000).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1200,
        metavar="PIXELS",
        help="Target frame height in pixels (default: 1200).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without creating/deleting files.",
    )
    args = parser.parse_args()

    root = Path(args.path)
    if not root.is_dir():
        logger.error("'%s' is not a valid directory.", args.path)
        sys.exit(1)

    if args.width <= 0 or args.height <= 0:
        logger.error("--width and --height must be positive integers.")
        sys.exit(1)

    root_resolved = root.resolve()
    logger.info("Scanning: %s", root_resolved)
    logger.info("Target resolution: %d x %d", args.width, args.height)
    if args.dry_run:
        logger.info(
            "Dry-run mode enabled: no files will be created or deleted."
        )

    processed = 0
    skipped = 0

    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        # Guard against symlinks that resolve to a path outside the root
        # directory (path traversal via symlink).
        try:
            file_path.resolve().relative_to(root_resolved)
        except ValueError:
            logger.warning(
                "Skipping %s: symlink resolves outside root directory.",
                file_path,
            )
            skipped += 1
            continue

        if process_image(file_path, args.width, args.height, args.dry_run):
            processed += 1
        else:
            skipped += 1

    logger.info(
        "Done. Processed: %d  |  Errors/skipped: %d", processed, skipped
    )


if __name__ == "__main__":
    main()
