from pathlib import Path

import piexif
import pytest
from PIL import Image


@pytest.fixture
def make_image(tmp_path: Path):
    """Create a simple image file and return its path."""

    def _make(
        name: str,
        size: tuple[int, int] = (400, 300),
        mode: str = "RGB",
        color=(20, 140, 220),
    ) -> Path:
        path = tmp_path / name
        img = Image.new(mode, size, color)
        ext = path.suffix.lower()
        fmt_map = {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".gif": "GIF",
            ".bmp": "BMP",
            ".tif": "TIFF",
            ".tiff": "TIFF",
            ".webp": "WEBP",
        }
        img.save(path, format=fmt_map.get(ext, "PNG"))
        return path

    return _make


@pytest.fixture
def make_exif_jpeg(tmp_path: Path):
    """Create a JPEG file with EXIF Orientation set to 6."""

    def _make(name: str = "exif_input.jpg",
              size: tuple[int, int] = (640, 480)) -> Path:
        path = tmp_path / name
        img = Image.new("RGB", size, (120, 60, 200))
        exif_dict = {
            "0th": {
                piexif.ImageIFD.Orientation: 6,
            }
        }
        exif_bytes = piexif.dump(exif_dict)
        img.save(path, format="JPEG", exif=exif_bytes)
        return path

    return _make
