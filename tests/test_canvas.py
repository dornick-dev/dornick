"""Drawing on screen.

"Tank level 62%" is a number; a line sitting on a tank silhouette reads
at a glance. The agent writes the page itself — what is tested here is
not the drawing but the frame it is given and that frame's boundaries.
"""

from __future__ import annotations

from pathlib import Path

from dornick import canvas


def test_the_page_cannot_reach_the_network(tmp_path: Path) -> None:
    """A page written by the agent being able to send requests out would
    be a walk around the permission gate. The CSP shuts everything and
    opens only what is inline."""
    page = canvas.wrap("depo", "<p>merhaba</p>")

    assert "default-src 'none'" in page
    assert "img-src data:" in page      # embedded images allowed, remote ones not
    assert "connect-src" not in page    # not opened: no requests at all


def test_interaction_is_allowed(tmp_path: Path) -> None:
    """A clickable, animated drawing is part of what is wanted."""
    assert "script-src 'unsafe-inline'" in canvas.wrap("x", "<p>y</p>")


def test_the_body_lands_inside_the_frame() -> None:
    page = canvas.wrap("Depo 1", "<svg><rect/></svg>")
    assert "<svg><rect/></svg>" in page
    assert "<title>Depo 1</title>" in page


def test_a_title_cannot_break_out_of_the_markup() -> None:
    """The title is free text: a `</title><script>` written by the model
    must not break out of the frame."""
    page = canvas.wrap("</title><script>kotu()</script>", "<p>x</p>")
    assert "<script>kotu()" not in page
    assert "&lt;script&gt;" in page


def test_a_full_document_is_left_alone() -> None:
    """If the agent built its own frame, forcing a second frame over it
    breaks a working page."""
    own = "<!DOCTYPE html><html><body><p>kendi</p></body></html>"
    assert canvas.wrap("x", own) == own


def test_turkish_titles_become_usable_file_names() -> None:
    assert canvas.slug("Depo 1 seviyesi") == "depo-1-seviyesi"
    assert canvas.slug("Şişli Çağrı Ölçümü") == "sisli-cagri-olcumu"
    assert canvas.slug("") == "cizim"
    # A path separator must not enter the file name.
    assert "/" not in canvas.slug("a/b/c") and "\\" not in canvas.slug("a\\b")


def test_drawings_stay_inside_the_workshop(tmp_path: Path) -> None:
    path = canvas.save(tmp_path, "Depo 1", "<p>x</p>")

    assert path.parent == tmp_path / canvas.FOLDER
    assert path.name == "depo-1.html"
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_a_second_drawing_replaces_the_first(tmp_path: Path) -> None:
    """Redrawing with the same title means updating: dropping a new file
    every time turns the folder into a dump."""
    canvas.save(tmp_path, "Depo 1", "<p>ilk</p>")
    canvas.save(tmp_path, "Depo 1", "<p>ikinci</p>")

    files = list((tmp_path / canvas.FOLDER).glob("*.html"))
    assert len(files) == 1
    assert "ikinci" in files[0].read_text(encoding="utf-8")


def test_the_palette_matches_the_program(tmp_path: Path) -> None:
    """The drawing sits inside the UI, not like a foreign white page
    floating above it."""
    page = canvas.wrap("x", "<p>y</p>")
    for token in ("--cyan", "--mint", "--amber", "--rose", "--violet"):
        assert token in page
