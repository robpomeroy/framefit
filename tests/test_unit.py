import piexif
from PIL import Image

from framefit import _load_exif_bytes, calculate_new_size


def test_calculate_new_size_landscape_to_frame():
    new_w, new_h = calculate_new_size(4000, 3000, 2000, 1200)
    assert (new_w, new_h) == (1600, 1200)


def test_calculate_new_size_portrait_to_frame():
    new_w, new_h = calculate_new_size(3000, 4000, 2000, 1200)
    assert (new_w, new_h) == (900, 1200)


def test_calculate_new_size_upscales_small_image():
    new_w, new_h = calculate_new_size(400, 300, 2000, 1200)
    assert (new_w, new_h) == (1600, 1200)


def test_calculate_new_size_exact_match():
    new_w, new_h = calculate_new_size(2000, 1200, 2000, 1200)
    assert (new_w, new_h) == (2000, 1200)


def test_load_exif_bytes_none_when_missing():
    img = Image.new("RGB", (64, 64), (255, 0, 0))
    assert _load_exif_bytes(img) is None


def test_load_exif_bytes_resets_orientation_to_1():
    img = Image.new("RGB", (64, 64), (100, 50, 20))
    exif_bytes = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}})
    img.info["exif"] = exif_bytes

    out = _load_exif_bytes(img)

    assert out is not None
    out_dict = piexif.load(out)
    assert out_dict["0th"][piexif.ImageIFD.Orientation] == 1


def test_load_exif_bytes_none_when_corrupt():
    img = Image.new("RGB", (64, 64), (10, 10, 10))
    img.info["exif"] = b"bad-exif-data"
    assert _load_exif_bytes(img) is None
