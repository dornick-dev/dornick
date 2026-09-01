"""Ekrana çizme.

"Depo seviyesi %62" bir sayı; depo silueti üzerinde duran bir çizgi bir
bakışta okunuyor. Sayfayı ajan kendi yazıyor — burada test edilen şey
çizimin kendisi değil, ona verilen çerçeve ve o çerçevenin sınırları.
"""

from __future__ import annotations

from pathlib import Path

from dornick import canvas


def test_the_page_cannot_reach_the_network(tmp_path: Path) -> None:
    """Ajanın yazdığı bir sayfanın dışarıya istek atabilmesi, izin
    kapısının etrafından dolaşmak olurdu. CSP her şeyi kapatıp yalnızca
    satır içi olanı açıyor."""
    page = canvas.wrap("depo", "<p>merhaba</p>")

    assert "default-src 'none'" in page
    assert "img-src data:" in page      # gömülü görsel olur, uzak görsel olmaz
    assert "connect-src" not in page    # açılmıyor: hiç istek yok


def test_interaction_is_allowed(tmp_path: Path) -> None:
    """Tıklanabilir, canlanan bir çizim istenen şeyin bir parçası."""
    assert "script-src 'unsafe-inline'" in canvas.wrap("x", "<p>y</p>")


def test_the_body_lands_inside_the_frame() -> None:
    page = canvas.wrap("Depo 1", "<svg><rect/></svg>")
    assert "<svg><rect/></svg>" in page
    assert "<title>Depo 1</title>" in page


def test_a_title_cannot_break_out_of_the_markup() -> None:
    """Başlık serbest metin: modelin yazdığı bir `</title><script>` ile
    çerçeveden çıkılmamalı."""
    page = canvas.wrap("</title><script>kotu()</script>", "<p>x</p>")
    assert "<script>kotu()" not in page
    assert "&lt;script&gt;" in page


def test_a_full_document_is_left_alone() -> None:
    """Ajan kendi çerçevesini kurduysa üstüne ikinci bir çerçeve geçirmek
    çalışan bir sayfayı bozar."""
    own = "<!DOCTYPE html><html><body><p>kendi</p></body></html>"
    assert canvas.wrap("x", own) == own


def test_turkish_titles_become_usable_file_names() -> None:
    assert canvas.slug("Depo 1 seviyesi") == "depo-1-seviyesi"
    assert canvas.slug("Şişli Çağrı Ölçümü") == "sisli-cagri-olcumu"
    assert canvas.slug("") == "cizim"
    # Yol ayracı dosya adına girmemeli.
    assert "/" not in canvas.slug("a/b/c") and "\\" not in canvas.slug("a\\b")


def test_drawings_stay_inside_the_workshop(tmp_path: Path) -> None:
    path = canvas.save(tmp_path, "Depo 1", "<p>x</p>")

    assert path.parent == tmp_path / canvas.FOLDER
    assert path.name == "depo-1.html"
    assert path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_a_second_drawing_replaces_the_first(tmp_path: Path) -> None:
    """Aynı başlıkla yeniden çizmek güncelleme demek: her seferinde yeni
    bir dosya bırakmak klasörü çöplüğe çeviriyor."""
    canvas.save(tmp_path, "Depo 1", "<p>ilk</p>")
    canvas.save(tmp_path, "Depo 1", "<p>ikinci</p>")

    files = list((tmp_path / canvas.FOLDER).glob("*.html"))
    assert len(files) == 1
    assert "ikinci" in files[0].read_text(encoding="utf-8")


def test_the_palette_matches_the_program(tmp_path: Path) -> None:
    """Çizim arayüzün içinde duruyor, üstünde yüzen yabancı bir beyaz
    sayfa gibi değil."""
    page = canvas.wrap("x", "<p>y</p>")
    for token in ("--cyan", "--mint", "--amber", "--rose", "--violet"):
        assert token in page
