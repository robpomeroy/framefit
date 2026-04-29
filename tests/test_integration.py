import sys
from pathlib import Path

import piexif
import pytest
from PIL import Image

from framefit import main, process_image


def test_process_image_converts_png_and_deletes_original(make_image):
    source = make_image("sample.png", size=(3000, 2000), mode="RGB")

    ok = process_image(source, 2000, 1200)

    output = source.with_suffix(".jpg")
    assert ok is True
    assert output.exists()
    assert not source.exists()
    with Image.open(output) as result:
        assert result.format == "JPEG"
        assert result.width <= 2000
        assert result.height <= 1200


def test_process_image_updates_jpg_in_place(make_image):
    source = make_image("sample.jpg", size=(2500, 1600), mode="RGB")

    ok = process_image(source, 2000, 1200)

    assert ok is True
    assert source.exists()
    with Image.open(source) as result:
        assert result.format == "JPEG"
        assert result.width <= 2000
        assert result.height <= 1200


@pytest.mark.parametrize("name", ["sample.jpeg", "sample.JPG"])
def test_process_image_updates_jpeg_variants_in_place(make_image, name):
    source = make_image(name, size=(2500, 1600), mode="RGB")

    ok = process_image(source, 2000, 1200)

    assert ok is True
    assert source.exists()
    lowercase_variant = source.with_suffix(".jpg")
    if lowercase_variant.exists():
        assert lowercase_variant.samefile(source)
    else:
        assert source.suffix.lower() in {".jpeg", ".jpg"}
    with Image.open(source) as result:
        assert result.format == "JPEG"
        assert result.width <= 2000
        assert result.height <= 1200


def test_process_image_handles_rgba_input(make_image):
    source = make_image("alpha.png", size=(900, 900),
                        mode="RGBA", color=(1, 2, 3, 120))

    ok = process_image(source, 2000, 1200)

    output = source.with_suffix(".jpg")
    assert ok is True
    with Image.open(output) as result:
        assert result.mode == "RGB"


def test_process_image_dry_run_no_write_no_delete(make_image):
    source = make_image("dryrun.png", size=(1200, 800), mode="RGB")

    ok = process_image(source, 2000, 1200, dry_run=True)

    output = source.with_suffix(".jpg")
    assert ok is True
    assert source.exists()
    assert not output.exists()


def test_process_image_skips_jpeg_when_already_correct_size(make_image):
    source = make_image("already_ok.jpeg", size=(1600, 1200), mode="RGB")
    original_bytes = source.read_bytes()

    ok = process_image(source, 2000, 1200)

    assert ok is True
    assert source.exists()
    assert source.read_bytes() == original_bytes


def test_process_image_updates_exif_when_size_already_matches(make_exif_jpeg):
    source = make_exif_jpeg(name="needs_orientation_fix.jpg",
                            size=(1600, 1200))

    with Image.open(source) as before:
        before_exif = piexif.load(before.info.get("exif"))
    assert before_exif["0th"][piexif.ImageIFD.Orientation] == 6

    ok = process_image(source, 2000, 1200)

    assert ok is True
    with Image.open(source) as after:
        after_exif_bytes = after.info.get("exif")
    assert after_exif_bytes is not None
    after_exif = piexif.load(after_exif_bytes)
    orientation = after_exif.get("0th", {}).get(piexif.ImageIFD.Orientation)
    assert orientation in (None, 1)


def test_process_image_fails_cleanly_on_corrupt_file(tmp_path: Path):
    source = tmp_path / "broken.png"
    source.write_bytes(b"not-an-image")

    ok = process_image(source, 2000, 1200)

    assert ok is False
    assert source.exists()
    assert not source.with_suffix(".jpg").exists()


def test_process_image_preserves_exif_and_resets_orientation(make_exif_jpeg):
    source = make_exif_jpeg()

    ok = process_image(source, 2000, 1200)

    assert ok is True
    with Image.open(source) as result:
        exif_bytes = result.info.get("exif")
    assert exif_bytes is not None
    exif_dict = piexif.load(exif_bytes)
    orientation = exif_dict.get("0th", {}).get(piexif.ImageIFD.Orientation)
    assert orientation in (None, 1)


def test_main_exits_for_invalid_directory(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["framefit.py", "Z:/__this_path_should_not_exist__"],
    )

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_exits_for_invalid_dimensions(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["framefit.py", str(tmp_path), "--width", "0"],
    )

    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_main_dry_run_does_not_modify_files(monkeypatch, make_image):
    source = make_image("main_dry.PNG", size=(1024, 768), mode="RGB")

    monkeypatch.setattr(
        sys,
        "argv",
        ["framefit.py", str(source.parent), "--dry-run"],
    )

    main()

    assert source.exists()
    assert not source.with_suffix(".jpg").exists()


def test_main_does_not_traverse_symlink_directories(monkeypatch,
                                                    tmp_path: Path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    inside_png = root / "inside.png"
    outside_png = outside / "outside.png"
    Image.new("RGB", (300, 200), (20, 30, 40)).save(inside_png, format="PNG")
    Image.new("RGB", (300, 200), (90, 60, 30)).save(outside_png, format="PNG")

    symlink_dir = root / "linked_outside"
    try:
        symlink_dir.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlink directories is not permitted here")

    monkeypatch.setattr(sys, "argv", ["framefit.py", str(root)])
    main()

    assert not inside_png.exists()
    assert inside_png.with_suffix(".jpg").exists()

    # If symlinked directories were traversed, this file would be converted.
    assert outside_png.exists()
    assert not outside_png.with_suffix(".jpg").exists()
