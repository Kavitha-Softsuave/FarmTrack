import pytest

from app.security.paths import UnsafePathError, safe_join
from app.security.phone import mask_phone, normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("+91 00000 00001", "+910000000001"),
    ("+910000000001", "+910000000001"),
    ("9000000001", "+919000000001"),
    ("09000000001", "+919000000001"),
    ("919000000001", "+919000000001"),
    ("+91-90000-00001", "+919000000001"),
    ("  +44 7700 900123 ", "+447700900123"),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "123", "+1234567890123456", "   "])
def test_normalize_phone_rejects_garbage(raw):
    assert normalize_phone(raw) is None


def test_mask_phone_keeps_country_code_and_last_four_only():
    assert mask_phone("+910000000001") == "+91******0001"
    assert "0000000" not in mask_phone("+910000000001")
    assert mask_phone("+12345") == "*" * 6


def test_safe_join_stays_inside_root(tmp_path):
    assert safe_join(tmp_path, "photos", "F001", "a.jpg") == (tmp_path / "photos" / "F001" / "a.jpg").resolve()


@pytest.mark.parametrize("parts", [("..", "secret.txt"), ("photos", "..", "..", "x"), ("/etc/passwd",), ("a\x00b",)])
def test_safe_join_rejects_escapes(tmp_path, parts):
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, *parts)


def test_safe_join_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "root"
    root.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(UnsafePathError):
        safe_join(root, "link", "file.txt")
