import io
import zipfile

from omrs import analytics
from omrs import exporting


def test_review_export_without_images_stays_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(
        analytics,
        "build_review_markdown",
        lambda vault: (b"# review", "OMRS-review.md"),
    )

    payload, filename, content_type = analytics.build_review_export(str(tmp_path), False)

    assert payload == b"# review"
    assert filename == "OMRS-review.md"
    assert content_type == "text/markdown; charset=utf-8"


def test_review_export_with_images_packages_only_referenced_files(monkeypatch, tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"png-data")
    second.write_bytes(b"jpg-data")
    paths = {first.name: str(first), second.name: str(second)}

    monkeypatch.setattr(
        analytics,
        "build_review_markdown",
        lambda vault: (b"# review", "OMRS-review.md"),
    )
    monkeypatch.setattr(
        analytics,
        "get_analytics",
        lambda vault: {
            "items": [
                {"images": [first.name, first.name, "missing.gif"]},
                {"images": [second.name]},
            ]
        },
    )
    monkeypatch.setattr(exporting, "_find_image", lambda vault, name: paths.get(name))

    payload, filename, content_type = analytics.build_review_export(str(tmp_path), True)

    assert filename.endswith("-含图片.zip")
    assert content_type == "application/zip"
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == [
            "OMRS-review.md",
            "images/first.png",
            "images/second.jpg",
        ]
        assert archive.read("images/first.png") == b"png-data"
        assert archive.read("images/second.jpg") == b"jpg-data"
