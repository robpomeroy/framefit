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
