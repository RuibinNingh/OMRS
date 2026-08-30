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


def test_markdown_table_becomes_a_structured_export_block():
    blocks = exporting._text_to_blocks(
        "unused",
        "| 选项 | 离子方程式 | 化学方程式 |\n"
        "| --- | --- | --- |\n"
        "| A | $H^+ + OH^-$ | $CH_3COOH + NaOH$ |",
    )

    assert blocks == [{
        "t": "table",
        "headers": ["选项", "离子方程式", "化学方程式"],
        "rows": [["A", "$H^+ + OH^-$", "$CH_3COOH + NaOH$"]],
    }]


def test_multiline_display_math_stays_one_export_text_block():
    source = r"""前文
$$
\begin{cases}
f(-1) < 0 \\
f(2) < 0
\end{cases}
$$
后文"""
    blocks = exporting._text_to_blocks("unused", source)

    assert blocks == [
        {"t": "txt", "text": "前文"},
        {
            "t": "txt",
            "text": r"""$$
\begin{cases}
f(-1) < 0 \\
f(2) < 0
\end{cases}
$$""",
        },
        {"t": "txt", "text": "后文"},
    ]


def test_export_data_keeps_a4_question_gap_line_count():
    data = exporting._build_export_data(
        "unused",
        "EXP-test",
        [{"uid": "q-1", "question": "题目", "answer": "", "subject": "数学"}],
        False,
        question_gap_lines=3,
    )

    assert data["meta"]["question_gap_lines"] == 3
    assert exporting._normalize_question_gap_lines("99") == 20
    assert exporting._normalize_question_gap_lines("bad") == 0


def test_a4_export_embeds_formula_boundary_continuation_layout():
    html = exporting._build_html(
        {
            "meta": {"a4_two_columns": True},
            "questions": [],
            "feedback": [],
            "answers": [],
        },
        "a4",
    )

    assert "function formulaBreakOffsets" in html
    assert "function splitFormulaText" in html
    assert "function placeText" in html
    assert "function placeContentBlock" in html
    assert "function placeQuestion" not in html
    assert "question-group" not in html
    assert "QUESTION_SLACK" not in html
    assert "mount.replaceChildren()" in html
    assert "await document.fonts.ready" in html
    assert "KaTeX 字体是在 run() 创建数学节点后才会被浏览器请求" in html
    assert 'window.addEventListener(\"beforeprint\"' not in html
    assert 'window.matchMedia(\"print\")' not in html
    assert "node.getBoundingClientRect().bottom - col.getBoundingClientRect().top" in html
    assert "pages.push(page); mount.appendChild(page);" in html