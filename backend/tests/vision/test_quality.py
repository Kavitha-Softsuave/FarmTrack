from __future__ import annotations

import io

import pytest
from PIL import Image, ImageEnhance

from app.domain.types import QualityIssue
from app.interfaces import PhotoQualityChecker
from app.vision.quality import PillowQualityChecker
from tests.vision.support import FRUIT_PHOTOS, LEAF_PHOTOS, blurred, jpeg, textured

checker = PillowQualityChecker()


def issues_of(data: bytes) -> list[QualityIssue]:
    return checker.check(data).issues


def test_implements_the_interface():
    assert isinstance(checker, PhotoQualityChecker)


def test_sharp_leaf_photo_is_usable():
    res = checker.check(jpeg(textured()))
    assert res.usable and res.issues == [] and res.tip_prompt_id is None
    assert (res.width, res.height) == (480, 360)
    assert res.blur_score is not None and res.blur_score > 500
    assert res.brightness is not None and 45 < res.brightness < 225


def test_blurred_photo_is_blurry_with_tip():
    res = checker.check(jpeg(blurred(textured())))
    assert not res.usable
    assert res.issues == [QualityIssue.blurry]
    assert res.tip_prompt_id == "scan_retake_blurry"
    assert res.blur_score is not None and res.blur_score < 60


def test_dark_photo_is_too_dark_and_blur_is_not_judged():
    dark = ImageEnhance.Brightness(textured()).enhance(0.15)
    res = checker.check(jpeg(dark))
    assert res.issues == [QualityIssue.too_dark]
    assert res.tip_prompt_id == "scan_retake_dark"
    assert res.brightness is not None and res.brightness < 45


def test_bright_photo_is_too_bright():
    res = checker.check(jpeg(textured(base=(250, 250, 242), noise=5.0)))
    assert res.issues == [QualityIssue.too_bright]
    assert res.tip_prompt_id == "scan_retake_dark"


def test_tiny_photo_is_too_small():
    res = checker.check(jpeg(textured((150, 150))))
    assert QualityIssue.too_small in res.issues and not res.usable
    assert res.tip_prompt_id == "scan_retake_far"
    assert (res.width, res.height) == (150, 150)


def test_short_side_of_exactly_200_is_accepted():
    assert checker.check(jpeg(textured((400, 200)))).usable
    assert QualityIssue.too_small in issues_of(jpeg(textured((400, 199))))


@pytest.mark.parametrize("colour", [(128, 128, 128), (40, 80, 200), (200, 40, 160)], ids=["grey", "blue", "magenta"])
def test_picture_without_vegetation_colours_is_no_leaf(colour):
    res = checker.check(jpeg(textured(base=colour, noise=10.0, spots=False)))
    assert res.issues == [QualityIssue.no_leaf]
    assert res.tip_prompt_id == "scan_retake_no_leaf"


@pytest.mark.parametrize("colour", [(70, 140, 60), (150, 170, 40), (120, 80, 40), (190, 160, 50)], ids=["green", "yellow-green", "brown", "yellow"])
def test_leaf_colours_are_accepted(colour):
    assert checker.check(jpeg(textured(base=colour))).usable


@pytest.mark.parametrize("data", [b"", b"not an image at all", b"\xff\xd8\xff\xe0 truncated"])
def test_undecodable_bytes_are_unreadable(data):
    res = checker.check(data)
    assert not res.usable and res.issues == [QualityIssue.unreadable]
    assert res.tip_prompt_id == "scan_retake_blurry"
    assert res.width is None and res.blur_score is None


def test_truncated_jpeg_is_unreadable():
    data = jpeg(textured())
    assert issues_of(data[: len(data) // 3]) == [QualityIssue.unreadable]


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_absurdly_large_image_is_refused():
    buf = io.BytesIO()
    Image.new("1", (12000, 10000)).save(buf, "PNG")
    assert issues_of(buf.getvalue()) == [QualityIssue.unreadable]


@pytest.mark.parametrize("mode", ["RGBA", "L", "P"])
def test_other_image_modes_are_decoded(mode):
    buf = io.BytesIO()
    textured().convert(mode).save(buf, "PNG")
    res = checker.check(buf.getvalue())
    assert QualityIssue.unreadable not in res.issues and res.width == 480


def test_several_issues_speak_the_most_fundamental_tip_first():
    res = checker.check(jpeg(textured((120, 120), base=(128, 128, 128), spots=False)))
    assert {QualityIssue.too_small, QualityIssue.no_leaf} <= set(res.issues)
    assert res.tip_prompt_id == "scan_retake_far"


def test_large_photo_is_scored_at_working_size():
    small = checker.measure(jpeg(textured((600, 450))))
    large = checker.measure(jpeg(textured((3000, 2250), seed=1)))
    assert large.width == 3000 and large.blur_score > 60 and small.blur_score > 60


def test_thresholds_are_constructor_arguments():
    strict = PillowQualityChecker(blur_below=1e9)
    assert QualityIssue.blurry in strict.check(jpeg(textured())).issues
    assert PillowQualityChecker(vegetation_min_fraction=1.01).check(jpeg(textured())).issues == [QualityIssue.no_leaf]


# ----------------------------------------------------------------------------------- the real photos of data/images/testset_v1
real_photos = pytest.mark.skipif(len(LEAF_PHOTOS) != 23, reason="photo test set not present")


@real_photos
@pytest.mark.parametrize("path", LEAF_PHOTOS, ids=lambda p: p.stem)
def test_every_real_leaf_photo_is_usable(path):
    res = checker.check(path.read_bytes())
    assert res.usable, (path.name, res.issues, res.blur_score, res.brightness)


@real_photos
@pytest.mark.parametrize("path", FRUIT_PHOTOS, ids=lambda p: p.stem)
def test_fruit_photos_are_checked_without_error(path):
    res = checker.check(path.read_bytes())
    assert QualityIssue.unreadable not in res.issues


@real_photos
@pytest.mark.parametrize("path", LEAF_PHOTOS, ids=lambda p: p.stem)
def test_artificially_degraded_real_photos_are_caught(path):
    img = Image.open(path).convert("RGB")
    assert issues_of(jpeg(blurred(img, 2.0))) == [QualityIssue.blurry]
    assert issues_of(jpeg(ImageEnhance.Brightness(img).enhance(0.2))) == [QualityIssue.too_dark]
