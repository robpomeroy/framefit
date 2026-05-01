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
    - Saves the output as <original_name>.jpg next to the original file or
      replaces it, if a JPEG.
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
import os
import sys
import tempfile
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


def _build_argument_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
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
    return parser


def _build_save_kwargs(exif_bytes: bytes | None) -> dict[str, object]:
    """Build JPEG save arguments, including EXIF bytes when present."""
    save_kwargs: dict[str, object] = {
        "format": "JPEG",
        "progressive": False,
        "quality": 95,
        "optimize": False,
    }
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes
    return save_kwargs


def _calculate_new_size(
    orig_w: int, orig_h: int, target_w: int, target_h: int
) -> tuple[int, int]:
    """
    Return (new_width, new_height) scaled proportionally so the image fits
    within target_w x target_h.  Both upscaling and downscaling are applied.
    """
    scale = min(target_w / orig_w, target_h / orig_h)
    new_w = max(1, min(target_w, round(orig_w * scale)))
    new_h = max(1, min(target_h, round(orig_h * scale)))
    return new_w, new_h


def _is_path_within_root(file_path: Path, root_resolved: Path) -> bool:
    """Return True when file_path resolves inside root_resolved."""
    try:
        file_path.resolve().relative_to(root_resolved)
    except ValueError:
        return False
    return True


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


def _log_dry_run(
    source_path: Path,
    output_path: Path,
    same_output_file: bool,
    new_w: int,
    new_h: int,
) -> None:
    """Log the actions that would be performed in dry-run mode."""
    if not same_output_file:
        logger.info(
            "[DRY RUN] Would convert: %s  ->  %s  (%dx%d) and "
            "delete original",
            source_path.name,
            output_path.name,
            new_w,
            new_h,
        )
        return

    logger.info(
        "[DRY RUN] Would update in-place: %s  (%dx%d)",
        source_path.name,
        new_w,
        new_h,
    )


def _orientation_needs_update(raw_exif: bytes | None) -> bool:
    """Return True when EXIF orientation exists and is not already 1."""
    if not raw_exif:
        return False
    try:
        original_exif = piexif.load(raw_exif)
        original_orientation = original_exif.get("0th", {}).get(
            piexif.ImageIFD.Orientation
        )
        return original_orientation not in (None, 1)
    except Exception:
        return False


def _process_tree(
    root: Path,
    root_resolved: Path,
    width: int,
    height: int,
    dry_run: bool,
) -> tuple[int, int]:
    """Process all eligible files under root and return counters."""
    processed = 0
    skipped = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current_dir = Path(dirpath)
        skipped += _prune_symlink_dirs(current_dir, dirnames)

        for filename in sorted(filenames):
            file_path = current_dir / filename
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            if not _is_path_within_root(file_path, root_resolved):
                logger.warning(
                    "Skipping %s: symlink resolves outside root directory.",
                    file_path,
                )
                skipped += 1
                continue

            if process_image(file_path, width, height, dry_run):
                processed += 1
            else:
                skipped += 1

    return processed, skipped


def _prune_symlink_dirs(current_dir: Path, dirnames: list[str]) -> int:
    """Remove symlink directories from traversal and return skip count."""
    symlink_dirs = [d for d in dirnames if (current_dir / d).is_symlink()]
    for symlink_dir in symlink_dirs:
        logger.warning(
            "Skipping symlink directory: %s",
            current_dir / symlink_dir,
        )
    dirnames[:] = [d for d in dirnames if d not in symlink_dirs]
    return len(symlink_dirs)


def _save_image_to_temp(
    img: Image.Image,
    final_path: Path,
    save_kwargs: dict[str, object],
) -> Path:
    """Save image data to a temporary sibling file and return its path."""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{final_path.stem}.",
        suffix=final_path.suffix,
        dir=final_path.parent,
    )
    os.close(fd)

    temp_path = Path(tmp_name)
    try:
        img.save(temp_path, **save_kwargs)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _validate_cli_args(args: argparse.Namespace) -> Path:
    """Validate CLI arguments and return resolved root path."""
    root = Path(args.path)
    if not root.is_dir():
        logger.error("'%s' is not a valid directory.", args.path)
        sys.exit(1)

    if args.width <= 0 or args.height <= 0:
        logger.error("--width and --height must be positive integers.")
        sys.exit(1)

    return root.resolve()


# ---------------------------------------------------------------------------
# Image processing and file handling
# ---------------------------------------------------------------------------


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
    is_jpeg_input = source_path.suffix.lower() in {".jpg", ".jpeg"}
    output_path = source_path if is_jpeg_input else source_path.with_suffix(
        ".jpg")
    same_output_file = source_path.resolve() == output_path.resolve()
    final_path = source_path if same_output_file else output_path
    temp_output_path: Path | None = None

    try:
        with Image.open(source_path) as img:
            is_progressive = bool(img.info.get(
                "progressive") or img.info.get("progression"))
            raw_exif = img.info.get("exif")
            orientation_needs_update = (
                is_jpeg_input and _orientation_needs_update(raw_exif)
            )

            # Physically apply any EXIF rotation before we do anything else.
            img = ImageOps.exif_transpose(img)

            exif_bytes = _load_exif_bytes(img)

            orig_w, orig_h = img.size
            new_w, new_h = _calculate_new_size(
                orig_w, orig_h, target_w, target_h)

            should_skip_conversion = (
                is_jpeg_input
                and not is_progressive
                and not orientation_needs_update
                and (new_w, new_h) == (orig_w, orig_h)
            )

            if should_skip_conversion:
                logger.info(
                    "Skipping: %s already matches target size and is a "
                    "non-progressive JPEG.",
                    source_path.name,
                )
                return True

            if dry_run:
                _log_dry_run(
                    source_path,
                    output_path,
                    same_output_file,
                    new_w,
                    new_h,
                )
                return True

            img = img.resize(
                (new_w, new_h),
                resample=Image.Resampling.LANCZOS,
            )

            # JPEG requires RGB; convert from RGBA, palette, grayscale, etc.
            if img.mode != "RGB":
                img = img.convert("RGB")

            save_kwargs = _build_save_kwargs(exif_bytes)

            # Always write to a temp file first, then atomically replace
            # the destination to avoid leaving partially-written JPEGs.
            temp_output_path = _save_image_to_temp(
                img,
                final_path,
                save_kwargs,
            )

        if temp_output_path is not None:
            os.replace(temp_output_path, final_path)
            temp_output_path = None

        # Delete original only when it differs from the output file.
        # On Windows, Path.resolve() normalises case, so .JPG and .jpg
        # pointing to the same file will compare equal.
        if not same_output_file:
            source_path.unlink()
            logger.info("Converted: %s  ->  %s  (%dx%d)", source_path.name,
                        output_path.name, new_w, new_h)
        else:
            logger.info("Updated:   %s  (%dx%d)",
                        source_path.name, new_w, new_h)

        return True

    except Exception as exc:
        if temp_output_path is not None:
            temp_output_path.unlink(missing_ok=True)
        logger.error("Failed to process %s: %s", source_path, exc)
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    root = Path(args.path)
    root_resolved = _validate_cli_args(args)
    logger.info("Scanning: %s", root_resolved)
    logger.info("Target resolution: %d x %d", args.width, args.height)
    if args.dry_run:
        logger.info(
            "Dry-run mode enabled: no files will be created or deleted."
        )

    processed, skipped = _process_tree(
        root,
        root_resolved,
        args.width,
        args.height,
        args.dry_run,
    )

    logger.info(
        "Done. Processed: %d  |  Errors/skipped: %d", processed, skipped
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Interrupted by user. Exiting gracefully.")
        sys.exit(130)
