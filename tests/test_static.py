"""Arayüz varlıkları üzerinde yapısal kontroller.

Tarayıcı olmadan çalışan ucuz testler. Buradaki her kontrol, gerçekten
yaşanmış ve sessizce geçmiş bir hataya karşılık geliyor: kırık CSS değeri
görünmez bir bozulma, gizlenmeyen bir katman ise tüm arayüzü kilitliyor.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "neocp" / "web" / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


def test_hidden_attribute_is_forced() -> None:
    """`hidden` her zaman kazanmalı.

    `.overlay { display: grid }` gibi bir sınıf kuralı, tarayıcının hidden
    için uyguladığı display:none'ı eziyor. Onay penceresi tam olarak bunun
    yüzünden hiç kapanmadı: ekranın üstünde boş bir diyalog kaldı, altındaki
    her şey tıklanamaz oldu.
    """
    assert re.search(r"\[hidden\]\s*\{[^}]*display:\s*none\s*!important", CSS)


def test_elements_toggled_from_js_are_declared_hidden() -> None:
    for element_id in ("overlay", "stop"):
        assert re.search(rf'id="{element_id}"[^>]*\shidden', HTML), element_id


def test_no_broken_color_values() -> None:
    """Geçersiz bir renk sessizce yok sayılır; bozulma ancak gözle görülür.

    Yalnızca bildirim gövdelerine bakılıyor: seçicilerdeki `#send` gibi
    kimlikler renk değil.
    """
    for body in re.findall(r"\{([^}]*)\}", CSS):
        for value in re.findall(r"#[0-9a-zA-Z]+", body):
            digits = value[1:]
            assert len(digits) in (3, 4, 6, 8), f"geçersiz uzunluk: {value}"
            assert re.fullmatch(r"[0-9a-fA-F]+", digits), f"onaltılık olmayan: {value}"


def test_every_referenced_asset_exists() -> None:
    for name in re.findall(r'(?:href|src)="/([^"]+)"', HTML):
        assert (STATIC / name).exists(), name


def test_dialog_explains_the_action_not_just_the_tool_name() -> None:
    """"neye izin vereyim" sorusunun cevabı diyalogda yazmalı."""
    for element_id in ("approve-why", "approve-target"):
        assert f'id="{element_id}"' in HTML
    # Araçların düz Türkçe karşılıkları tanımlı olmalı.
    for tool in ("shell", "write_file", "edit_file", "list_dir", "mind_memory"):
        assert re.search(rf"\b{tool}\s*:", APP_JS), tool


def test_ids_used_by_script_exist_in_markup() -> None:
    """Betiğin aradığı her kimlik işaretlemede olmalı.

    Liste elle tutulmuyor: betikten türetiliyor. Aksi halde arayüz yeniden
    düzenlendiğinde test ya bayatlıyor ya da yanlış yerde patlıyor. Eksik bir
    kimlik sessizce null döner ve arayüz ilk etkileşimde kırılır.
    """
    scripts = APP_JS + "".join(
        (STATIC / name).read_text(encoding="utf-8") for name in ("scene.js", "settings.js", "viewer.js", "speech.js",
                     "chrome.js", "listen.js", "camera.js", "drop.js",
                     "komut.js", "gorevler.js", "degisiklik.js", "git.js")
    )
    used = set(re.findall(r'\$\("([\w-]+)"\)', scripts))
    used |= set(re.findall(r'getElementById\("([\w-]+)"\)', scripts))

    assert used, "betikte hiç kimlik kullanımı bulunamadı — desen bayatlamış olabilir"
    # Betik içinde YARATILAN kimlikler de var olmuş sayılır (settings.js
    # model-thinking/model-window gibi alanları çalışma anında kuruyor).
    created = set(re.findall(r'\.id = "([\w-]+)"', scripts))
    missing = sorted(i for i in used
                     if f'id="{i}"' not in HTML and i not in created)
    assert not missing, f"işaretlemede yok: {', '.join(missing)}"


def test_composer_has_no_camera_button() -> None:
    """Yazma satırındaki kamera Lens'le çakışıp 'açılamadı' diyordu.
    İzleme üst bardaki ikon; kare eklemek ataş / sürükle."""
    assert 'id="cam"' not in HTML
    assert 'id="cams"' in HTML
    assert '$("cam")' not in APP_JS
    assert '"/api/senses"' in APP_JS


def test_camera_toggle_lives_on_the_eyes_pane() -> None:
    """Kamera aç/kapa Mikrofon'da mikrofon yokken gizleniyordu.
    Anahtar Kameralar sekmesinin başında; artı menü orayı açar."""
    src = (STATIC / "settings.js").read_text(encoding="utf-8")
    hearing = re.search(
        r"function drawHearing\(\) \{.*?\n  async function loadCameras",
        src, re.S)
    cameras = re.search(
        r"function drawCameras\(data\) \{.*?\n  function newCameraForm",
        src, re.S)
    assert hearing and cameras, "drawHearing / drawCameras bulunamadı"
    assert "camera.enabled" not in hearing.group(0)
    assert 'set("camera"' not in hearing.group(0)
    assert "ve kamera girişi" not in hearing.group(0)
    assert "camera.enabled" in cameras.group(0)
    assert 'set("camera", "enabled"' in cameras.group(0)
    assert 'id="pane-eyes"' in HTML
    assert "async function open(tab)" in src
    assert 'openTab("eyes")' in APP_JS
    assert '["Kamera"' in APP_JS


def test_git_bar_sits_above_the_composer() -> None:
    """Claude kalıbı: repo çubuğu composer'ın üstünde, --git-h sohbeti kaydırır."""
    assert HTML.index('id="git-bar"') < HTML.index('id="composer"')
    assert re.search(r'id="git-bar"[^>]*\shidden', HTML)
    assert "--git-h" in CSS
    assert 'src="/git.js"' in HTML
    order = re.findall(r'<script src="/([\w.]+)"></script>', HTML)
    assert order.index("viewer.js") < order.index("git.js")
    assert order.index("app.js") < order.index("git.js")
    from neocp.web.server import ASSETS, STREAMED_NOTES
    assert "/git.js" in ASSETS
    assert "git" in STREAMED_NOTES
    assert "function host(" in (STATIC / "viewer.js").read_text(encoding="utf-8")
    git_js = (STATIC / "git.js").read_text(encoding="utf-8")
    assert "/api/git" in git_js
    assert "diffHunk" in git_js


# -- sahnenin halleri --------------------------------------------------

SCENE_JS = (STATIC / "scene.js").read_text(encoding="utf-8")


def test_every_scene_mode_has_a_label_and_a_simulation() -> None:
    """Kip tablosuna yeni bir hal eklenip gerisi unutulmamalı.

    Etiketi olmayan kip durum satırında ham anahtar adıyla görünür;
    canlandırması olmayan kip ise sahnede boşta duran bir isimden ibaret
    kalır. İkisi de sessizce olur.
    """
    table = re.search(r"const MODES = \{(.*?)\n  \};", SCENE_JS, re.S)
    assert table, "MODES tablosu bulunamadı — desen bayatlamış olabilir"

    modes = set(re.findall(r"(\w+):\s*\{ spin", table.group(1)))
    assert "idle" in modes and len(modes) >= 4

    labels = re.search(r"const MODE_LABEL = \{(.*?)\};", APP_JS, re.S)
    assert labels, "MODE_LABEL tablosu bulunamadı"
    named = set(re.findall(r"(\w+):", labels.group(1)))
    assert modes <= named, f"etiketi olmayan kip: {sorted(modes - named)}"

    # idle dışında her kipin sahnede bir karşılığı olmalı.
    drawn = set(re.findall(r'mode === "(\w+)"', SCENE_JS))
    assert modes - {"idle"} <= drawn, f"canlandırması olmayan kip: {sorted(modes - drawn)}"


def test_the_scene_exposes_what_the_app_calls() -> None:
    """Sahne modülü kapalı; dışarıdan yalnızca döndürdüğü yüzey görünüyor.
    Uygulamanın çağırdığı bir ad orada yoksa hata çalışma anında çıkar."""
    # Modülün kendi dönüşü en sondaki: içeride başka `return {` var
    # (düğüm nesneleri) ve ilkini yakalamak yanlış listeyi okur.
    surfaces = re.findall(r"return \{([^}]+)\};", SCENE_JS)
    assert surfaces, "sahnenin dış yüzeyi bulunamadı — desen bayatlamış olabilir"
    exported = set(re.findall(r"\w+", surfaces[-1]))
    called = set(re.findall(r"Scene\.(\w+)\(", APP_JS))

    assert called, "uygulama sahneyi hiç çağırmıyor — desen bayatlamış olabilir"
    assert called <= exported, f"sahnede yok: {sorted(called - exported)}"


def test_buttons_in_the_hud_take_clicks() -> None:
    """Üst şerit artık GERÇEK başlık çubuğu: OS çubuğu söküldü, boş alanı
    pencereyi sürüklüyor (chrome.js → api.drag). Bu yüzden şeridin kendisi
    tıklama almalı (`pointer-events: auto`); düğmelerin de tek tek alması
    eski alışkanlıktan duruyor ve zarar vermiyor.
    """
    hud_rule = re.search(r"\.hud \{[^}]*\}", CSS)
    assert hud_rule and "pointer-events: auto" in hud_rule.group(0), "desen bayatlamış olabilir"
    # Sürükleme gerçekten bağlanıyor: şerit tıklanabilir ama sürükleme yoksa
    # ölü bir yüzey olurdu.
    CHROME_JS = (STATIC / "chrome.js").read_text(encoding="utf-8")
    assert "api.drag" in CHROME_JS and "pointerdown" in CHROME_JS

    inside = re.search(r'<div class="hud">(.*?)\n</div>', HTML, re.S)
    assert inside, "üst şerit işaretlemede bulunamadı"
    hud_html = inside.group(1)

    # Kuralı kimlikten yakalayabildiğimiz gibi, sarmalayan kabın sınıfından
    # da yakalayabiliyoruz: pencere düğmeleri tek tek değil `.chrome button`
    # ile stillendi ve testin buna körlük etmesi yanlış alarm üretiyordu.
    opened = {
        selector
        for selector, body in re.findall(r"([^{}]+)\{([^}]*)\}", CSS)
        if "pointer-events: auto" in body
    }

    for tag in re.findall(r"<button[^>]*>", hud_html):
        element_id = re.search(r'id="([\w-]+)"', tag)
        if not element_id:
            continue
        name = element_id.group(1)

        # Kural üç yerden gelebiliyor: kimlik, düğmenin kendi sınıfı, ya da
        # sarmalayan kabın sınıfı. Üçüne birden bakılmazsa test yanlış alarm
        # veriyor — düğmeler tek tek değil `.icon` ile stillendi.
        names = {f"#{name}"}
        if own := re.search(r'class="([^"]+)"', tag):
            names |= {f".{cls}" for cls in own.group(1).split()}
        # Kaptan gelen kural: seritteki her sinif icin ".sinif button"
        # bicimini de aday sayiyoruz. Iceriden disariya dogru gercek bir
        # eslesme yapmak icin CSS motoru gerekirdi; bu ölçüde yeterli.
        for group in re.findall(r'class="([^"]+)"', hud_html):
            names |= {f".{cls} button" for cls in group.split()}

        assert any(part in selector for selector in opened for part in names), (
            f"#{name} tıklanamaz: hiçbir kural pointer-events'i geri açmıyor"
        )


# -- bicimlendirme -----------------------------------------------------

SCRIPTS = ("md.js", "app.js", "settings.js", "scene.js", "viewer.js",
           "chrome.js", "speech.js", "listen.js", "camera.js", "drop.js",
           "git.js")


def test_model_output_is_never_written_as_markup() -> None:
    """Metni model yaziyor — yani guvenilmeyen bir kaynak.

    Bicimlendirici HTML dizesi hic uretmiyor, dogrudan DOM dugumu kuruyor:
    `textContent` ile giren bir sey hicbir kosulda etiket olarak
    yorumlanmiyor. Tek bir `innerHTML` bu guvenceyi bozar.
    """
    for name in SCRIPTS:
        source = (STATIC / name).read_text(encoding="utf-8")
        assert "innerHTML" not in source, name
        assert "outerHTML" not in source, name
        assert "insertAdjacentHTML" not in source, name


def test_the_formatter_is_loaded_before_the_app_uses_it() -> None:
    """Betikler sirayla calisiyor; app.js acilista Markdown'a dokunuyorsa
    md.js ondan once gelmeli, yoksa sayfa ilk cevapta kirilir."""
    order = re.findall(r'<script src="/([\w.]+)"></script>', HTML)
    assert order.index("md.js") < order.index("app.js")
    # settings.js ve viewer.js dosya onizlemesinde bicimlendiriciyi cagiriyor.
    assert order.index("md.js") < order.index("settings.js")
    assert order.index("md.js") < order.index("viewer.js")


# -- goruntuleyici -----------------------------------------------------

VIEWER_JS = (STATIC / "viewer.js").read_text(encoding="utf-8")


def _kodu(metin: str) -> str:
    """Yorumlari atilmis kaynak.

    Guvenlik testleri bir adin GECTIGI yere degil, KULLANILDIGI yere
    bakmali: "srcdoc kullanmiyoruz" diye bir yorum, "srcdoc kullaniyoruz"
    ile ayni metni tasiyor ve ham arama ikisini ayirt edemiyor.
    """
    metin = re.sub(r"/\*.*?\*/", "", metin, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", metin)


def test_the_agents_page_runs_isolated() -> None:
    """Ajanin kurdugu sayfa gercekten calissin diye cercevede gosteriliyor.

    `allow-same-origin` verilseydi o sayfa bu programin DOM'una ve `/api`
    uclarina erisebilirdi — yani ajanin yazdigi bir betik kendi izin
    kapisini atlayabilirdi. Sandbox ozniteligi hic verilmezse de cerceve
    tam yetkili acilir.
    """
    granted = re.search(r'setAttribute\("sandbox",\s*"([^"]*)"\)', VIEWER_JS)
    assert granted, "sandbox ozniteligi verilmiyor — cerceve tam yetkili acilir"

    # Yorumlarda gecen adlar sayilmasin diye yalnizca verilen degere bakiliyor.
    tokens = set(granted.group(1).split())
    assert tokens <= {"allow-scripts"}, f"fazladan yetki: {sorted(tokens)}"


def test_srcdoc_is_only_used_inside_the_isolated_frame() -> None:
    """`srcdoc` isaretlemeyi yorumlatan tek yol; yalnizca yalitilmis
    cercevede gecerli, sayfanin kendisinde degil.

    Ham metinde saymak yetmiyor: "srcdoc DEGIL, kendi origin'inde iframe"
    diye bir YORUM da eslesiyordu ve test, guvenlik ozelligi bozulmadigi
    halde kirmizi donuyordu. Sayilan sey artik ATAMA — yani `srcdoc`u
    gercekten kuran satir.
    """
    for name in SCRIPTS:
        if name == "viewer.js":
            continue
        assert "srcdoc" not in _kodu((STATIC / name).read_text(encoding="utf-8")), name

    govde = _kodu(VIEWER_JS)
    atamalar = re.findall(r"\.srcdoc\s*=", govde)
    assert len(atamalar) == 1, f"srcdoc {len(atamalar)} yerde atanmis"
    # Ve o tek atama, sandbox'li cerceveyi kuran yardimcinin icinde olmali.
    frame_govdesi = govde[govde.index("function frame("):].split("\n  }")[0]
    assert ".srcdoc" in frame_govdesi, \
        "srcdoc atamasi sandbox'li frame() disina cikmis"


def test_code_surfaces_never_render_ligatures() -> None:
    """Cascadia Code "=>"yu tek karakter "⇒" olarak birleştiriyordu.

    PHP kaynağında dizi oku yanlış karakterle görünüyordu: kaynak gösteren
    bir araçta yazılan ile görünen birebir olmalı. Kural `pre`/`code`yi
    kapsamalı ki sohbetteki bloklar da görüntüleyici de korunsun.
    """
    rule = re.search(r"([^{}]+)\{[^}]*font-variant-ligatures:\s*none", CSS)
    assert rule, "ligatür kapatma kuralı yok"
    assert re.search(r"\bpre\b", rule.group(1)) and re.search(r"\bcode\b", rule.group(1))
    # calt (bağlamsal alternatifler) da kapalı: Cascadia oku onunla kuruyor.
    assert re.search(r'"calt"\s*0', CSS)


def test_the_viewer_numbers_lines_without_polluting_selection() -> None:
    """Satır numarası CSS sayacıyla ::before'da çiziliyor: kaynaktan seçilip
    kopyalanan metne numara karışmıyor. Numara gerçek metin olsaydı 300
    satırlık bir kopyala-yapıştır 300 sayıyla gelirdi."""
    assert "paintRows" in VIEWER_JS
    before = re.search(r"\.viewer-code \.vl::before \{([^}]*)\}", CSS)
    assert before, ".vl::before kuralı yok"
    assert "counter(" in before.group(1)
    assert "user-select: none" in before.group(1)
    # Uzun satır panel içinde kayar; sar kipi kutu içinde kırar.
    assert re.search(r"\.viewer-code \{[^}]*overflow-x: auto", CSS)
    assert re.search(r"\.viewer-code\.wrap \.vl-tx \{[^}]*pre-wrap", CSS)
    # Dev dosyada düz metne düşülüyor: on binlerce düğüm kaydırmayı öldürüyor.
    cap = re.search(r"const ROW_CAP = (\d+)", VIEWER_JS)
    assert cap and int(cap.group(1)) >= 10000


def test_the_viewer_and_the_chat_offer_copy_buttons() -> None:
    """Kod tek tıkla panoya gitmeli — hem görüntüleyicide hem sohbetteki
    kod bloklarında. Düğme onay da göstermeli: tıklayıp hiçbir şey olmaması
    "çalıştı mı" belirsizliği bırakıyordu."""
    assert "navigator.clipboard.writeText" in VIEWER_JS
    assert "Kopyalandı" in VIEWER_JS

    MD_JS = (STATIC / "md.js").read_text(encoding="utf-8")
    assert "md-copy" in MD_JS
    assert "navigator.clipboard.writeText" in MD_JS
    assert re.search(r"^\.md-copy \{", CSS, re.M)


def test_media_files_are_rendered_not_announced() -> None:
    """Bir PNG açıldığında panel "İKİLİ DOSYA" yazıyordu.

    Ajan bir grafik çizdiğinde kullanıcı onu göremiyordu — sohbetin anlatıp
    gösterememesi, bu panelin var olma sebebinin ta kendisi. Görsel, ses,
    video ve PDF ham uçtan gerçekten açılıyor.
    """
    assert "function mediaKind" in VIEWER_JS
    assert "/api/raw?path=" in VIEWER_JS
    # Dört tür de tanınıyor ve her biri kendi öğesiyle çiziliyor.
    for pattern in ("png|jpe?g", r"mp3\|wav", r"mp4\|webm", r"\\.pdf\$"):
        assert re.search(pattern, VIEWER_JS), pattern
    assert re.search(r'createElement\(kind === "audio" \? "audio" : "video"\)', VIEWER_JS)
    # Sığdır ↔ 1:1 geçişi ve piksel ölçüsünün başlığa yazılması.
    assert "naturalWidth" in VIEWER_JS
    assert re.search(r"\.viewer-img \{[^}]*object-fit: contain", CSS)
    assert re.search(r"\.viewer-media\.image\.full \.viewer-img \{[^}]*max-width: none", CSS)
    # Tanınmayan ikili: mesaj kalıyor ama boyut ve eylemlerle.
    assert "function unknownBinary" in VIEWER_JS
    assert '"/api/apps/reveal"' in VIEWER_JS


def test_the_raw_endpoint_guards_the_workspace_and_the_content_type() -> None:
    """Yol istekten geliyor: `..` ile yukarı çıkmak dizin dışına çıkma
    açığının klasik yolu. Tür de uzantıdan ve KISA bir listeden veriliyor —
    tarayıcının içeriğe bakıp tür tahmin etmesi (sniffing) çalışma
    alanındaki bir metin dosyasını HTML sayıp çalıştırabilirdi."""
    SERVER = (Path(__file__).resolve().parents[1] / "src" / "neocp" / "web" / "server.py"
              ).read_text(encoding="utf-8")
    body = re.search(r"def _raw_file\(self\) -> None:(.*?)\n    def ", SERVER, re.S)
    assert body, "_raw_file bulunamadı — desen bayatlamış olabilir"

    inner = body.group(1)
    assert "Çalışma alanı dışı" in inner
    assert "root not in target.parents" in inner
    assert 'RAW_TYPES.get(target.suffix.lower(), "application/octet-stream")' in inner
    assert 'X-Content-Type-Options", "nosniff"' in inner
    # Ses/video ileri sarabilsin: menzil isteği destekleniyor.
    assert "Accept-Ranges" in inner and "Content-Range" in inner
    # Dosya belleğe toptan alınmıyor: bir video sunucuyu düşürürdü.
    assert "handle.read(min(" in inner
    # HTML servis edilmiyor: yalnız medya türleri adıyla veriliyor.
    table = re.search(r"RAW_TYPES = \{(.*?)\n\}", SERVER, re.S)
    assert table
    for kind in re.findall(r':\s*"([\w/+.-]+)"', table.group(1)):
        assert kind.split("/")[0] in ("image", "audio", "video", "application"), kind
        assert "html" not in kind


def test_php_sources_are_recognised_by_the_viewer() -> None:
    """PHP uzantı haritasında yoktu: dosya renksiz düz metin kalıyordu."""
    assert re.search(r"\bphp:\s*\"php\"", VIEWER_JS)
    HIGHLIGHT = (STATIC / "highlight.js").read_text(encoding="utf-8")
    assert re.search(r"\bphp:\s*\"clike\"", HIGHLIGHT)


# -- sohbet metni: bağlar, katlama, kaynaklar --------------------------
#
# Claude Code'daki karşılıkları: cevaptaki dosya yolu bir bağ, uzun blok
# katlanıyor, kaynak okunur bir satır. Üçü de md.js'te yaşıyor.

MD_JS_SRC = (STATIC / "md.js").read_text(encoding="utf-8")


def test_file_paths_in_the_answer_are_links() -> None:
    """`src/neocp/loop.py:42` düz metin kalıyordu: kullanıcı yolu okuyup
    paneli elle açıp satırı elle arıyordu."""
    assert "const FILE_REF" in MD_JS_SRC
    assert "function fileChip" in MD_JS_SRC
    # Görüntüleyici satır desteğiyle açılıyor.
    assert "Viewer.open(path, line)" in MD_JS_SRC
    assert "function open(path, line)" in VIEWER_JS
    assert "function gotoLine(line)" in VIEWER_JS
    # Satır ancak çizimden SONRA var: bekleyen istek render sonunda karşılanır.
    render = re.search(r"function render\(data\) \{(.*?)\n  \}", VIEWER_JS, re.S)
    assert render and "if (pendingLine) gotoLine(pendingLine)" in render.group(1)
    assert re.search(r"\.viewer-code \.vl\.hit \{", CSS)


def test_the_path_detector_does_not_fire_on_ordinary_prose() -> None:
    """Asıl zorluk yanlış pozitif: cümledeki her `bir:iki` bağ olamaz.

    Üç koruma var ve üçü de kaybolursa "Node.js hızlıdır" cümlesindeki
    "Node.js" tıklanabilir bir dosyaya dönüşür.
    """
    body = re.search(r"function fileRef\(text\) \{(.*?)\n  \}", MD_JS_SRC, re.S)
    assert body, "fileRef() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    # 1) tanınan uzantı şart (ya da açık klasör yolu)
    assert "FILE_REF" in inner and "DIR_REF" in inner
    # 2) alan adıyla başlayan şey dosya değil adrestir
    assert "HOSTISH.test(path)" in inner
    # 3) "Node.js" gibi ürün adları: ayraçsız + numarasız + büyük harf
    assert re.search(r"!sep && !hit\[1\] && /\^\[A-Z\]/\.test\(stem\)", inner)
    # URL önce geliyor: adresin içindeki ".php" dosya sanılmamalı.
    plain = re.search(r"function plain\(parent, text\) \{(.*?)\n  \}", MD_JS_SRC, re.S)
    assert plain and "BARE_URL" in plain.group(1)
    assert "sort((a, b) => a.at - b.at)" in plain.group(1)


def test_long_blocks_fold_but_stay_whole() -> None:
    """Üç yüz satırlık bir döküm cevabın gerisini ekrandan atıyordu.

    Katlama KIRPMA değil: metnin tamamı DOM'da kalmalı, yoksa seçim ve
    kopyalama da kesilirdi (kopyala düğmesi ham kaynağı taşıyor).
    """
    rows = re.search(r"const FOLD_ROWS = (\d+)", MD_JS_SRC)
    assert rows and int(rows.group(1)) >= 20

    body = re.search(r"function fold\(block, body, rows\) \{(.*?)\n  \}", MD_JS_SRC, re.S)
    assert body, "fold() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    assert "rows <= FOLD_ROWS" in inner            # kısa blok katlanmıyor
    assert "md-folded" in inner and "md-more" in inner
    # Metin kesilmiyor: yalnızca kutu alçalıyor.
    assert "slice(" not in inner and "substring(" not in inner
    fold_css = re.search(r"\.md-folded > code,(.*?)\n\}", CSS, re.S)
    assert fold_css and "max-height" in fold_css.group(1)
    assert "overflow: hidden" in fold_css.group(1)
    # Kod, liste ve tablo aynı dili konuşuyor.
    for call in (r"fold\(block, body, rows\.length\)",
                 r"fold\(wrap, block, block\.childElementCount\)",
                 r"fold\(wrap, block, body\.childElementCount\)"):
        assert re.search(call, MD_JS_SRC), call


def test_sources_are_drawn_as_readable_rows() -> None:
    """Çıplak URL göz tarafından okunmuyor, yalnızca satırı kirletiyordu.
    Kaynak artık başlık + alan adı; nereye gidileceği TIKLAMADAN ÖNCE
    okunuyor — bağların tıklanabilir olmasının şartı buydu."""
    assert "function sourceChip" in MD_JS_SRC
    assert "function domainOf" in MD_JS_SRC
    assert "function slugTitle" in MD_JS_SRC
    # Çip gerçek <a>: URL durum çubuğunda görünür, sağ tık kopyalar.
    # Yeni sekme + açan sayfaya erişimsiz sözleşmesi sürüyor.
    assert MD_JS_SRC.count('.target = "_blank"') >= 2
    assert MD_JS_SRC.count("noopener noreferrer") >= 2
    for selector in (r"^\.md-source \{", r"^\.md-source-host \{", r"^\.md-cite \{",
                     r"^\.md-sources \{"):
        assert re.search(selector, CSS, re.M), selector


def test_numbered_citations_get_a_source_list() -> None:
    """Model `[1]` yazıp altta tanımlıyor. Tanım satırı ham URL olarak
    akmamalı, `[1]` işareti bağ olmalı ve aynı adres iki kez listelenmemeli."""
    assert "const SOURCE_DEF" in MD_JS_SRC
    assert "function collectSources" in MD_JS_SRC
    # Tanımlar ÖNCE toplanıyor: tek geçişte ilk `[1]` düz metin kalırdı.
    render = re.search(r"function render\(text\) \{(.*?)\n    return out;", MD_JS_SRC, re.S)
    assert render, "render() bulunamadı"
    inner = render.group(1)
    assert inner.index("collectSources(lines)") < inner.index("while (i < lines.length)")
    assert "if (SOURCE_DEF.test(line)) { i++; continue; }" in inner
    assert "if (sources.size) out.append(sourceList())" in inner
    # Tanımsız atıf bağ olmuyor: olmayan bir kaynağa götüren bağ, bağ değil.
    cite = re.search(r"function citeHit\(text\) \{(.*?)\n  \}", MD_JS_SRC, re.S)
    assert cite and "sources.has(hit[1])" in cite.group(1)
    # Aynı adres tek satır.
    listing = re.search(r"function sourceList\(\) \{(.*?)\n  \}", MD_JS_SRC, re.S)
    assert listing and "byUrl" in listing.group(1)


def test_the_new_chat_surfaces_speak_english_too() -> None:
    """Eksik çeviri sessiz bir İngilizce-yarım arayüz demek."""
    for phrase in ("tümünü göster", "Kaynaklar", "Tıkla — görüntüleyicide aç"):
        assert phrase in MD_JS_SRC, phrase
    added = re.search(r"Dil\.ekle\(\{(.*?)\}\);", MD_JS_SRC, re.S)
    assert added, "md.js çeviri eklemiyor"
    for phrase in ("tümünü göster", "Kaynaklar", "Tıkla — görüntüleyicide aç"):
        assert phrase in added.group(1), phrase


# -- sinyal akışı ------------------------------------------------------
#
# Ağdaki hareket sahnenin asıl anlattığı şey: hatırlamak, yazmak ve
# tartmak bir uçtan diğerine yürüyen bir uyarı olarak görünüyor. Buradaki
# kontroller, o akışı sessizce görünmez yapan hataları yakalıyor.


def test_every_signal_kind_has_a_real_colour() -> None:
    """Tanımsız bir CSS değişkeni boş dizeye çözülür ve sinyal hiç çizilmez.

    Ekranda hata yok, yalnızca hiçbir şey akmıyor — gözle bakmadan
    fark edilmesi imkânsız bir bozulma.
    """
    table = re.search(r"const CURRENT = \{(.*?)\n  \};", SCENE_JS, re.S)
    assert table, "CURRENT tablosu bulunamadı — desen bayatlamış olabilir"

    tokens = re.findall(r':\s*"(\w+)"', table.group(1))
    assert tokens, "sinyal türü tanımlı değil"
    for token in tokens:
        assert re.search(rf"^\s*--{token}:", CSS, re.M), f"CSS'te yok: --{token}"


def test_the_flow_is_slow_enough_to_watch() -> None:
    """Hız buradaki tek amaca hizmet ediyor: izlenebilmek.

    Gerçek bir sinyal milisaniyelerde geçer; o değerlerde ekranda
    yalnızca bir titreme görünüyor.
    """
    signal = int(re.search(r"const SIGNAL_MS = (\d+)", SCENE_JS).group(1))
    step = int(re.search(r"const STEP_MS = (\d+)", SCENE_JS).group(1))

    assert signal >= 500, "sıçrama izlenemeyecek kadar hızlı"
    # Adım aralığı sıçramadan kısa: zincir akıyor, sıra sıra beklemiyor.
    assert step < signal


def test_signals_are_drawn_every_frame() -> None:
    """Çizim listesine eklenmeyen bir katman hiç görünmüyor."""
    paint = re.search(r"function paint\(t\) \{(.*?)\n  \}", SCENE_JS, re.S)
    assert paint and "drawSignals(t)" in paint.group(1)


def test_memory_writes_travel_instead_of_blinking() -> None:
    """Yazma da bir hareket. Yalnızca grafiği tazelemek, yeni kaydın
    nereye oturduğunu görünmez bırakıyordu."""
    assert re.search(r'case "mind_write":\s*\n\s*Scene\.load\(\(\) => Scene\.deposit', APP_JS)


# -- yerleşim ----------------------------------------------------------


def test_the_scene_is_centred_in_the_free_space() -> None:
    """Çekirdek pencerenin ortasındayken sohbetin altında kalıyordu.

    Asıl izlenecek şey arkadaki akış; onun üstünü yazının kapatmaması
    gerekiyor.
    """
    assert "core.x = view.w / 2" not in SCENE_JS
    assert "freeWidth()" in SCENE_JS


def test_the_brain_fits_the_pane_hole() -> None:
    """Beyin sağa/sola/yukarı taşıyordu; sığdırınca ortada pul kaldı.

    Tuval tam ekran, #mind yalnız hedef kutu. Halkalar başlığın altına asılır
    ve genişliği doldurur; organ payı yükseklik tavanı (kısa pane / kamera),
    dikey ortalama değil. 96 tavanı geniş paneli kısır bırakıyordu.
    """
    assert "function mindHole(" in SCENE_JS
    assert "function rForReach(" in SCENE_JS
    assert "mind-head" in SCENE_JS
    assert "RING_OUTER" in SCENE_JS
    assert "mr.height" in SCENE_JS
    assert "watch.observe(mindEl)" in SCENE_JS
    assert "pane.width / 4.9" not in SCENE_JS
    assert "byTick, 96" not in SCENE_JS
    assert "hole.top + reach" in SCENE_JS


def test_everything_that_floats_shares_one_column() -> None:
    """Sohbet, yazma satırı, önizleme ve ekler aynı sütunda.

    Ayrı ayrı konumlandırıldıklarında biri diğerinin üstüne biniyordu:
    kamera önizlemesi cevabın üzerine oturmuştu ve "hiçbir şey olmuyor"
    gibi görünüyordu. Sohbet artık `.stream-wrap` içinde; gut/aside orada.
    """
    wrap = re.search(r"^\.stream-wrap \{(.*?)\n\}", CSS, re.S | re.M)
    assert wrap and "var(--gut)" in wrap.group(1) and "var(--aside)" in wrap.group(1)
    for selector in (".entry", ".lens", ".drops", ".shot"):
        rule = re.search(rf"^{re.escape(selector)} \{{(.*?)\n\}}", CSS, re.S | re.M)
        assert rule, f"{selector} kuralı bulunamadı"
        assert "var(--gut)" in rule.group(1), selector


def test_the_column_does_not_sit_under_the_viewer() -> None:
    """Görüntüleyici de sağda; ikisi aynı yerde olunca sohbet kayboluyor."""
    assert re.search(r"body\.viewing[^{]*\{\s*--gut:", CSS)


# -- organlar ----------------------------------------------------------
#
# Ağ ajanın bildiklerini gösteriyor, organ katmanı yapabildiklerini:
# mikrofon, kameralar, hoparlör ve kendine yazdığı modüller.


def test_every_organ_kind_is_drawable() -> None:
    """Python yeni bir organ türü eklerse sahnede karşılığı olmalı.

    Karşılığı olmayan tür sessizce yedek renge düşüyor: ekranda hata yok,
    yalnızca kamera ile PLC aynı renkte görünüyor.
    """
    from neocp import organs

    table = re.search(r"const LIMB_COLOR = \{(.*?)\};", SCENE_JS, re.S)
    assert table, "LIMB_COLOR tablosu bulunamadı — desen bayatlamış olabilir"

    drawn = set(re.findall(r"(\w+):", table.group(1)))
    known = {organs.SENSE, organs.SPEECH, organs.MODULE}
    assert known <= drawn, f"sahnede karşılığı yok: {sorted(known - drawn)}"

    for token in re.findall(r':\s*"(\w+)"', table.group(1)):
        assert re.search(rf"^\s*--{token}:", CSS, re.M), f"CSS'te yok: --{token}"


def test_organs_are_drawn_every_frame() -> None:
    paint = re.search(r"function paint\(t\) \{(.*?)\n  \}", SCENE_JS, re.S)
    assert paint and "drawLimbs(t)" in paint.group(1)


def test_the_tool_to_organ_map_comes_from_the_server() -> None:
    """Arayüzde elle tutulan bir eşleme, yeni bir araç eklendiğinde
    sessizce eşleşmeden kalıyor. Hangi aracın hangi organı kullandığını
    organ listesi söylüyor."""
    assert "fetch(\"/api/organs\")" in APP_JS
    assert re.search(r"limb\.tools \|\| \[\]\)\.includes\(tool\)", APP_JS)


def test_using_an_organ_shows_what_it_is_doing() -> None:
    """Üzerine gelince okunacak bir şey olmalı: "açık" ile "kullanılıyor"
    aynı şey değil."""
    assert re.search(r"Scene\.use\(limb, summarize\(e\.input\)\)", APP_JS)
    assert "node.doing" in SCENE_JS


def test_the_device_kinds_match_between_python_and_the_page() -> None:
    """Ayarlar sayfasındaki örnek, kabul edilmeyen bir tür yazarsa
    kullanıcı "kaydet"e bastığında hata alıyor ve sebebini bilmiyor."""
    from neocp import devices

    SETTINGS_JS = (STATIC / "settings.js").read_text(encoding="utf-8")
    template = re.search(r"const DEVICE_TEMPLATE = \{(.*?)\n  \};", SETTINGS_JS, re.S)
    assert template, "DEVICE_TEMPLATE bulunamadı — desen bayatlamış olabilir"

    kind = re.search(r'kind:\s*"(\w+)"', template.group(1))
    assert kind and kind.group(1) in devices.KINDS


def test_every_settings_tab_has_a_pane_and_a_renderer() -> None:
    """Karşılığı olmayan bir sekme tıklandığında boş bir sayfa açıyor:
    hata yok, yalnızca hiçbir şey yok."""
    SETTINGS_JS = (STATIC / "settings.js").read_text(encoding="utf-8")
    tabs = set(re.findall(r'data-tab="(\w+)"', HTML))
    panes = set(re.findall(r'data-pane="(\w+)"', HTML))

    assert tabs == panes, f"eşleşmeyen: {sorted(tabs ^ panes)}"
    for name in tabs:
        assert f'id="pane-{name}"' in HTML, name
        assert f"{name}: document.getElementById" in SETTINGS_JS, name


def test_the_voice_character_reaches_the_page() -> None:
    """Karakter tarayıcıda uygulanıyor: ayara yazılıp sayfaya
    gönderilmezse hiçbir şey değişmiyor ve kaydırak sahte oluyor."""
    SPEECH_JS = (STATIC / "speech.js").read_text(encoding="utf-8")
    assert "setCharacter" in SPEECH_JS
    assert "Speech.setCharacter(s.character)" in APP_JS


def test_a_failing_character_layer_still_speaks() -> None:
    """Ses bağlamı açılmadıysa ya da çözümleme patlarsa düz çalmaya
    dönülüyor: sesin hiç çıkmaması, karaktersiz çıkmasından kötü."""
    SPEECH_JS = (STATIC / "speech.js").read_text(encoding="utf-8")
    assert re.search(r"shaped\(url, text\)\.catch\(\(\) => plain\(url, text\)\)", SPEECH_JS)


def test_the_character_layer_does_not_turn_the_voice_down() -> None:
    """Göğüs tonunu kesmek `lowshelf` ister.

    `highshelf` 160 Hz'in **üstündeki** her şeyi, yani sesin tamamını
    kısıyor. Tarayıcıda ölçüldü: highshelf ile tam karakterde ses gücü
    %57 düşüyordu (-7,4 dB); lowshelf ile düşüş -2,1 dB ve o da yalnızca
    alınan bastan geliyor. Kulakla fark edilmesi zor, sinsi bir bozulma.
    """
    SPEECH_JS = (STATIC / "speech.js").read_text(encoding="utf-8")
    shelf = re.search(r'cut\.type = "(\w+)"', SPEECH_JS)
    assert shelf and shelf.group(1) == "lowshelf"


def test_reasoning_does_not_stream_into_the_conversation() -> None:
    """Akan ham muhakeme cevabın yerini alıyordu: modelin kendi kendine
    konuştuğu cümleler ("No, let's keep it") sohbette duruyor ve okunacak
    şey sanılıyordu. Görünen şey tek bir satır; muhakeme tıklayınca
    açılıyor."""
    body = re.search(r"function think\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "think() bulunamadı — desen bayatlamış olabilir"

    inner = body.group(1)
    # Başlık kısa bir etiket (dönen düşünme kelimesi); muhakeme metni
    # yalnızca katlanmış şeritte.
    assert "workHead(mull()" in inner
    # Akarken yalnızca kuyruk çiziliyor (tam metni her parçada basmak hem
    # O(n²) hem şeridi devasa yapıyordu); tamamı closeThought'ta tek satıra
    # katlanıp tıklayınca açılıyor.
    assert "w.thought.textContent = tail" in inner
    assert "thought.slice(-" in inner


def test_the_status_line_is_modeled_not_decorative() -> None:
    """Canli sikayet (29.08): "dusunuyor, kurcalaniyor diye durmadan
    degisiyor — bunlar gercek birer meta olmali". Etiket o an GERCEKTEN
    olan seyden turetilir: akil yurutme kanali akiyorsa "Akil yurutuyor",
    cevap metni akiyorsa "Yaziyor", akmiyorsa "Dusunuyor". Suslu havuz ve
    esanlamli rotasyonu kalkti — ayni durum ayni etiket.
    """
    assert "function since(started)" in APP_JS
    assert re.search(r"mull\(\) \+ since\(", APP_JS)
    assert "const MULL" not in APP_JS, "rastgele kelime havuzu geri gelmis"
    assert 'lastDelta === "text"' in APP_JS
    assert 'lastDelta === "thinking"' in APP_JS
    # Arac fiili belirlenimci: esanlamli rotasyon yok.
    assert "pool[0]" in APP_JS and "turnSeed % pool.length" not in APP_JS


def test_being_interrupted_also_stops_the_voice() -> None:
    """Metin durup hoparlörün cümleyi bitirmeye devam etmesi, sözü
    kesilmiş ama konuşmayı sürdüren biri gibi."""
    block = re.search(r'case "interrupted":(.*?)break;', APP_JS, re.S)
    assert block and "Speech.stop()" in block.group(1)


def test_every_function_the_event_loop_calls_exists() -> None:
    """`closeAct` çağrılıyordu ama hiç tanımlı değildi.

    Her `tool_end` olayında ReferenceError atıyor ve olay işleyicisinin
    geri kalanı hiç çalışmıyordu: araç satırı kapanmıyor, görüntüleyici
    tazelenmiyor, sahnedeki organ serbest bırakılmıyordu. Tarayıcı
    konsolunda görünmeden fark edilmesi zor bir bozulma.
    """
    called = set(re.findall(r"^\s*(?:case [^\n]*?)?\b(\w+)\(", APP_JS, re.M))
    defined = set(re.findall(r"function (\w+)\(", APP_JS))
    defined |= set(re.findall(r"(?:const|let) (\w+) = (?:async )?\(", APP_JS))
    defined |= set(re.findall(r"(?:const|let) (\w+) = (?:async )?function", APP_JS))

    # Yerleşikler ve başka dosyalardaki modüller bu dosyada tanımlı değil.
    known = {
        "if", "for", "while", "switch", "catch", "return", "setTimeout", "fetch",
        "clearTimeout", "setInterval", "String", "Number", "Math", "JSON", "Object",
        "Array", "Promise", "Date", "console", "alert", "parseInt", "parseFloat",
        # Pencere üzerinde çıplak çağrılanlar.
        "addEventListener", "removeEventListener", "requestAnimationFrame",
        "getComputedStyle", "clearInterval",
    }
    # `islower()` değil `name[0].islower()`: "closeAct" içinde büyük harf
    # olduğu için `islower()` False dönüyor ve camelCase adların tamamı —
    # yani bu dosyadaki neredeyse her işlev — süzgeçten eleniyordu. Test
    # yakalaması gereken hatayı yakalamıyordu.
    missing = {
        name for name in called - defined - known
        if name[:1].islower() and not name.startswith("_")
    }
    # Modül çağrıları (Scene.load gibi) desende zaten yakalanmıyor.
    assert not missing, f"tanımsız çağrı: {sorted(missing)}"


def test_the_turn_keeps_a_single_activity_strip() -> None:
    """Şerit her metin parçasında kapanıyordu; model araç çağırıp yazıp
    yine araç çağırınca her adım yeni bir satır açıyor ve sohbet on beş
    satırlık bir merdivene dönüyordu."""
    block = re.search(r'case "assistant_delta":(.*?)break;', APP_JS, re.S)
    assert block and "closeWork()" not in block.group(1)
    # Şerit yalnızca tur bitince kapanıyor.
    seal = re.search(r"function sealLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert seal and "closeWork()" in seal.group(1)


def test_reasoning_and_narration_live_inside_the_strip() -> None:
    """Düşünme ve ara anlatım ("Verileri topluyorum.") cevap değil."""
    think = re.search(r"function think\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert think and "ensureWork()" in think.group(1)
    assert "function foldNarration()" in APP_JS


def test_the_page_clears_a_stuck_deafness_on_load() -> None:
    """Sayfa yenilenince "konuşmam bitti" haberi hiç gitmiyor ve kulak
    kapalı kalıyordu."""
    assert re.search(r'fetch\("/api/speaking".*?on: false', APP_JS, re.S)


def test_playback_always_reports_that_it_finished() -> None:
    """Ses bağlamı askıda kalırsa `onended` hiç tetiklenmiyor ve kulak
    sonsuza kadar kapalı kalıyordu."""
    SPEECH_JS = (STATIC / "speech.js").read_text(encoding="utf-8")
    assert re.search(r"setTimeout\(finish, \(buffer\.duration", SPEECH_JS)


def test_playback_tells_the_ear_which_sentence_is_playing() -> None:
    """Yankı süzgeci hoparlör metnini bilir; aksi halde barge kendi
    TTS'ini yeni istek sanır. Kullanıcı hoparlörün üstünden konuşunca
    aynı cümle tamponda kalır — baştan kurulmaz."""
    SPEECH_JS = (STATIC / "speech.js").read_text(encoding="utf-8")
    assert "play(await item.audio, item.text)" in SPEECH_JS
    assert re.search(r"JSON.stringify\(\{ on, text:", SPEECH_JS)


def test_model_text_is_always_visible_never_folded() -> None:
    """EN ÖNEMLİ KURAL. Ayrım "tur ortası mı, tur sonu mu" DEĞİL — KİM YAZDI:

        model   -> sohbette normal cevap bloğu (iki araç çağrısı arasında
                   yazılmış olsa bile)
        harness -> şeritte ya da gizli (araç adımları, iç notlar)

    Kanıtlanmış yara: kullanıcı "yarım mı kaldı?" diye sordu, neo cevabı
    yazdı, cevap ŞERİDE KATLANDI ve ekranda yalnızca "▸ HARMANLIYOR · 13 SN"
    kaldı — kullanıcı sorduğu sorunun cevabını görmek için şeridi açmak
    zorunda kaldı.
    """
    body = re.search(r"function foldNarration\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "foldNarration() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    # Metin artık şeride KOPYALANMIYOR: yalnızca mühürleniyor.
    assert "work.body.append" not in inner
    assert "finishAgentLine()" in inner
    # Güvenlik ağı yamaları da kalktı — geri getirilecek bir şey kalmadı.
    assert "lastNarr" not in APP_JS
    assert "answerKept" not in APP_JS


def test_the_live_strip_follows_the_flow() -> None:
    """Canlı düşünme/çalışma göstergesi turun tepesine çakılı kalmamalı.

    Eski hal: model biraz cevap yazıp yeniden düşünmeye geçince düşünme
    kutusu, daha önce yazılmış metnin ÜSTÜNE (şeride) düşüyordu — ekranda
    "düşünce adımı yukarıda asılı, cevap aşağıya yazıyor" görünüyordu.
    Doğrusu (Claude Code düzeni): gösterge akışla birlikte iner, yeni içerik
    her zaman göstergenin hemen altında doğar; tur kapanınca özet başlık
    turun başında katlı kalır.
    """
    assert "function dockWork" in APP_JS
    assert "function restWork" in APP_JS

    # Düşünme yeniden başlarken o ana kadarki cevap ara-anlatıma katlanır ve
    # şerit akışın sonuna iner: kronoloji bozulmaz.
    think = re.search(r"function think\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert think and "foldNarration()" in think.group(1)
    assert "dockWork(w)" in think.group(1)

    # Cevap akmaya başlarken şerit sakinleşir ve akışın sonuna iner — yeni
    # metin şeridin hemen altında yazılır.
    write = re.search(r"function write\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert write and "restWork()" in write.group(1)


def test_the_same_text_is_never_drawn_twice() -> None:
    """Model metni tek yerde yaşıyor: sohbette. Şeritte kopyası yok, tur
    sonunda "geri getirilen" bir kopya da yok — eski çift-çizim riski
    kaynağında kalktı."""
    seal = re.search(r"function sealLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert seal, "sealLine() bulunamadı"
    inner = seal.group(1)
    assert "line(\"agent\"" not in inner, "sealLine cevap KOPYASI üretmemeli"
    assert "finishAgentLine()" in inner
    # Şeridin gövdesine giren tek metin türleri: adımlar ve iç notlar.
    fin = re.search(r"function finishAgentLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert fin and "agentLine.classList.add(\"done\")" in fin.group(1)


def test_the_scene_separates_what_was_used_from_what_was_scanned() -> None:
    """Zihin bir sorguda onlarca kayda dokunuyor. Hepsini numaralayıp
    yakmak "her şeyi karıştırdı" gibi duruyordu — "modbus cihazı ekle"
    derken beş kayıt birden yanıyor ve ikisi BTC fiyatı oluyordu."""
    assert "step.used" in SCENE_JS
    assert "function order(index)" in SCENE_JS
    # Sunucu tarafı da işareti göndermeli, yoksa sahnede ayıracak bir şey yok.
    LOOP = (Path(__file__).resolve().parents[1] / "src" / "neocp" / "loop.py").read_text(
        encoding="utf-8"
    )
    assert '"used": step.node in used' in LOOP


def test_the_route_list_also_separates_used_from_scanned() -> None:
    """Sahnede ayrılıp listede ayrılmaması, düzeltmenin yarısı demekti:
    kullanıcının okuduğu yer liste."""
    body = re.search(r"function renderRoute\((.*?)\n\}", APP_JS, re.S)
    assert body, "renderRoute() bulunamadı — desen bayatlamış olabilir"

    inner = body.group(1)
    assert "step.used" in inner
    assert "glanced" in inner
    # Numara yalnızca kullanılanlarda ve kendi arasında sıralı.
    assert "used += 1" in inner


def test_deleting_a_device_refreshes_the_organs_list() -> None:
    """Ajan cihazı silince ayarlar/sahne 30 sn bekliyordu; hâlâ orada
    görünüyordu. `device_removed` organ listesini ve ayar panelini tazeler."""
    from neocp.web.server import STREAMED_NOTES

    assert "device_removed" in STREAMED_NOTES
    assert "git" in STREAMED_NOTES
    assert 'case "device_removed"' in APP_JS
    assert 'case "git"' in APP_JS
    assert "neo:devices" in APP_JS
    settings = (STATIC / "settings.js").read_text(encoding="utf-8")
    assert 'addEventListener("neo:devices"' in settings


def test_the_recall_trace_does_not_overlay_the_conversation_rail() -> None:
    """İz paneli `position:fixed; left:30px` ile sol konuşma listesinin
    üstüne biniyordu. Hedef şeridi gibi `.stream-wrap` içinde akışın
    kardeşi — overlay değil."""
    html = open("src/neocp/web/static/index.html", encoding="utf-8").read()
    wrap_i = html.find('class="stream-wrap"')
    route_i = html.find('id="route"')
    thread_i = html.find('id="thread"')
    assert 0 <= wrap_i < route_i < thread_i
    rule = re.search(r"^\.route \{(.*?)\}", CSS, re.S | re.M)
    assert rule, ".route kuralı yok"
    assert "position: fixed" not in rule.group(1)
    assert "left: 30px" not in CSS
    assert "flex: 0 0 auto" in rule.group(1)


# -- hedef paneli ------------------------------------------------------
#
# Zihindeki hedef yığını (mind_goals) sağ üstte görünür bir kontrol
# listesi: goal_push/goal_status olayları paneli sürüyor. Buradaki
# kontroller, olay-güdümlü durum makinesini sessizce koparan hataları
# yakalıyor — olayın panele bağlanmaması ekranda hata değil, yalnızca
# hiç görünmeyen bir panel demek.


def test_goal_events_drive_the_goal_panel() -> None:
    push = re.search(r'case "goal_push":(.*?)break;', APP_JS, re.S)
    assert push and "Goals.push(e.goal_id, e.text)" in push.group(1)

    status = re.search(r'case "goal_status":(.*?)break;', APP_JS, re.S)
    assert status and "Goals.status(e.goal_id, e.status)" in status.group(1)

    # Panel işaretlemede var ve varsayılan gizli: hedef yokken görünmemeli.
    assert re.search(r'id="goals"[^>]*\shidden', HTML)
    # Sayfa yenilenince olay akışı kaçmış oluyor; panel /api/state'teki
    # aktif hedeflerle tohumlanmalı — yoksa yenileme paneli sıfırlıyor.
    assert "Goals.seed(s.goals || [])" in APP_JS


def test_finished_goals_linger_struck_through_then_leave() -> None:
    """Biten hedef önce üstü çizili görünmeli (kullanıcı bittiğini OKUSUN),
    sonra sessizce listeden düşmeli. Bırakılan soluk düşer."""
    linger = re.search(r"const GOAL_LINGER = (\d+)", APP_JS)
    assert linger and int(linger.group(1)) >= 3000, "madde okunamadan siliniyor"
    assert re.search(r"items\.delete\(id\); render\(\);", APP_JS)

    assert re.search(r"\.goal-item\.done span \{[^}]*line-through", CSS)
    assert re.search(r"\.goal-item\.dropped \{[^}]*opacity", CSS)


def test_a_long_goal_list_is_clipped_with_a_count() -> None:
    """Yirmi hedefli bir koşuda panel sohbeti kaplamamalı: ilk birkaç
    madde + "…+N", gövde de kendi içinde kayar (sınırlı yükseklik)."""
    show = re.search(r"const GOAL_SHOW = (\d+)", APP_JS)
    assert show and int(show.group(1)) == 6
    assert re.search(r'"…\+" \+ \(rows\.length - GOAL_SHOW\)', APP_JS)

    body = re.search(r"^\.goals-body \{(.*?)\}", CSS, re.S | re.M)
    assert body and "max-height" in body.group(1) and "overflow-y: auto" in body.group(1)


# -- plan kipi onay döngüsü --------------------------------------------


def test_plan_mode_offers_an_apply_button_after_the_turn() -> None:
    """Plan kipinde tur bitince "Planı uygula" düğmesi belirmeli — ama
    yalnız plan kipinde: başka kipte her turun sonuna düğme koymak olmaz."""
    block = re.search(r'case "turn_end":(.*?)break;', APP_JS, re.S)
    assert block and "maybeOfferPlan()" in block.group(1)

    body = re.search(r"function maybeOfferPlan\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "maybeOfferPlan() bulunamadı — desen bayatlamış olabilir"
    assert 'mode !== "plan"' in body.group(1)
    assert re.search(r"^\.plan-apply button \{", CSS, re.M)


def test_applying_the_plan_switches_mode_before_sending() -> None:
    """Sıra önemli: önce kip değişir, sunucu kabul ederse mesaj gider.
    Ters sırada "Planı uygula." mesajı hâlâ salt okunur kapıya çarpar."""
    body = re.search(r"async function applyPlan\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "applyPlan() bulunamadı — desen bayatlamış olabilir"

    inner = body.group(1)
    assert inner.index('"/api/settings"') < inner.index('"/api/chat"')
    # Sunucu reddederse ekran gerçeğe döner ve mesaj gitmez.
    assert "answer.ok === false" in inner
    assert 't("Planı uygula.")' in inner


def test_a_stale_plan_offer_is_withdrawn() -> None:
    """Kullanıcı kendi sözünü söylerse ya da kip plandan çıkarsa bekleyen
    teklif kalkmalı — bayat bir "uygula" düğmesi yanlış planı uygular."""
    message = re.search(r'case "message":(.*?)break;', APP_JS, re.S)
    assert message and "hidePlanOffer()" in message.group(1)

    authority = re.search(r"function setAuthority\((.*?)\n\}", APP_JS, re.S)
    assert authority and 'if (next !== "plan") hidePlanOffer();' in authority.group(1)


def test_drawings_open_in_the_isolated_frame() -> None:
    """Çizim bir dosya değil bir sunum: kaynağını okumak istenen şey değil.
    Ama yalıtım kalkmamalı — ajanın yazdığı bir betik kendi izin kapısını
    atlayamaz."""
    VIEWER = (STATIC / "viewer.js").read_text(encoding="utf-8")
    assert 'PRESENTS = new Set(["draw"])' in VIEWER
    body = re.search(r"function present\(path\) \{(.*?)\n  \}", VIEWER, re.S)
    assert body and 'mode = "live"' in body.group(1)
    assert "dismissed = false" in body.group(1)


def test_viewer_left_grip_resizes_from_the_panel_edge() -> None:
    """Git/görüntüleyici sol kenarı: innerWidth - x, panel right:0 sanır.
    Beynin solunda (right: mind-w) tutunca ilk harekette sola kaçıyordu."""
    src = (STATIC / "viewer.js").read_text(encoding="utf-8")
    assert "innerWidth - e.clientX" not in src
    assert "originW + originX - e.clientX" in src
    assert "right: var(--mind-w)" in CSS


# -- maliyet çipi -------------------------------------------------------
#
# Dock'taki tahmini harcama göstergesi. Fiyat OpenRouter kataloğundan
# geliyor; bilinmezse çip token sayısına düşüyor. Buradaki kontroller,
# çipi sessizce ölü bırakan kopuşları yakalıyor.


def test_the_cost_chip_exists_and_starts_hidden() -> None:
    """İlk kullanım olayına kadar boş bir "$0" durmasın: çip gizli doğar,
    ilk usage olayında görünür."""
    assert re.search(r'id="dock-cost"[^>]*\shidden', HTML)
    body = re.search(r"function dockCost\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "dockCost() bulunamadı — desen bayatlamış olabilir"
    assert "chip.hidden = true" in body.group(1)
    assert "chip.hidden = false" in body.group(1)


def test_the_chip_falls_back_to_tokens_when_the_price_is_unknown() -> None:
    """Fiyatsız modelde (yerel sunucu, katalog dışı) dolar UYDURULMAZ:
    çip token sayısı gösterir — "12.4k tok"."""
    body = re.search(r"function dockCost\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body and 'tok"' in body.group(1)
    # Dolar yalnız fiyat varken: koşul fiyata bakmalı.
    assert re.search(r"fiyat\s*\?\s*\"≈\"", body.group(1).replace("\n", " "))


def test_an_expensive_model_turns_the_chip_amber() -> None:
    """Çıktı fiyatı $20/M üstündeyse çip amber tona döner ve title
    "premium model" der — göze batmadan, iki temada da (token --amber)."""
    eşik = re.search(r"const PREMIUM_USD_M = (\d+)", APP_JS)
    assert eşik and int(eşik.group(1)) == 20
    assert re.search(r"cikti \* 1e6 > PREMIUM_USD_M", APP_JS)
    assert "premium model" in APP_JS
    rule = re.search(r"#dock-cost\.premium \{([^}]*)\}", CSS)
    assert rule and "var(--amber)" in rule.group(1), \
        "amber sabit renkle değil temaya uyan token'la verilmeli"


def test_usage_events_feed_the_chip_and_the_snapshot_seeds_it() -> None:
    """Olay yolu iki uçlu: usage/fiyat olayları çipi sürer, sayfa
    yenilenince /api/state tohumlar — ikisinden biri kopuk olursa çip
    sessizce ölür."""
    usage = re.search(r'case "usage":(.*?)break;', APP_JS, re.S)
    assert usage and "dockCost()" in usage.group(1)
    price = re.search(r'case "fiyat":(.*?)break;', APP_JS, re.S)
    assert price and "dockCost()" in price.group(1)
    # Tohumlama loadState'te.
    assert "s.kullanim" in APP_JS and "s.fiyat" in APP_JS
    # Sunucu tarafı sözleşme gerçekten yayında: desktop._usage_yay
    # tur/oturum/fiyat alanlarını basıyor.
    DESKTOP = (Path(__file__).resolve().parents[1] / "src" / "neocp" / "desktop.py").read_text(
        encoding="utf-8")
    assert '"tur": dict(self._tur_kullanim)' in DESKTOP
    assert '"oturum": dict(self._oturum_kullanim)' in DESKTOP
    assert '"fiyat": self._fiyat' in DESKTOP


# -- model bekleme durumu (çalışma şeridinde) ---------------------------


def test_model_wait_lives_in_the_work_strip_not_the_chat() -> None:
    """Kesinti sohbete hata duvarı basmaz: "bekleme" olayı line()/alert
    yoluna değil, şeridi süren bekleme() işleyicisine gider."""
    block = re.search(r'case "bekleme":(.*?)break;', APP_JS, re.S)
    assert block and "bekleme(e)" in block.group(1)
    assert 'line("alert"' not in block.group(1)


def test_the_wait_headline_counts_down_in_place() -> None:
    """Tek canlı satır: başlık deneme sayacı + kalan saniyeyi söyler ve
    saniye ticker'ı AYNI başlığı günceller — üst üste satır yığılmaz."""
    head = re.search(r"function waitHead\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert head, "waitHead() bulunamadı — desen bayatlamış olabilir"
    inner = head.group(1)
    assert 't("Model bekleniyor")' in inner
    assert "deadline" in inner, "geri sayım son-tarihe bakmalı"
    assert 't("İş bekletiliyor — model erişilebilir olunca sürecek")' in inner

    tick = re.search(r"function tickBusy\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert tick and "paintWait()" in tick.group(1), (
        "saniye ticker'ı bekleme başlığını işletmeli — donuk 'Düşünüyor' değil")


def test_the_raw_error_hides_behind_a_click() -> None:
    """Ham hata varsayılan GİZLİ; tık ile açılan kart sınırlı yükseklikte
    ve kendi içinde kayar — sohbeti sayfalarca itmez."""
    body = re.search(r"function bekleme\(e\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "bekleme() bulunamadı — desen bayatlamış olabilir"
    assert "detail.hidden = true" in body.group(1)

    card = re.search(r"^\.wait-detay \{(.*?)\}", CSS, re.S | re.M)
    assert card and "max-height" in card.group(1) and "overflow: auto" in card.group(1)
    # Başlık uyarı tonuna döner (sönük kehribar nabız).
    assert re.search(r"^\.acts-head\.wait \{", CSS, re.M)


def test_recovery_turns_the_same_row_green() -> None:
    """Model dönünce bekleme satırı yeşile döner ("geri geldi · N deneme
    sonrası") ve başlıktaki uyarı tonu kalkar."""
    body = re.search(r"function closeWait\(e\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "closeWait() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    assert 't("Model geri geldi")' in inner
    assert 't(" deneme sonrası")' in inner
    assert 'classList.remove("wait")' in inner


def test_the_api_error_wall_never_reaches_the_chat() -> None:
    """Günlükteki api_error notu sohbete alert olarak dökülmez: geçici hata
    şeritte, ölümcül hata notice'ta. (Eski hal: ham JSON duvarı.)"""
    block = re.search(r'case "api_error":(.*?)break;', APP_JS, re.S)
    assert block is not None
    assert "line(" not in block.group(1)


# -- iç içerik: asla düz çizim ------------------------------------------
#
# İkinci savunma hattı. Birincisi sunucuda (hub `_payload` süzgeci ve
# `mind.transcript`); buradaki, o süzgeçlerden biri bir gün kaçırırsa
# kullanıcının ekranını koruyor. Üç kalıp da ekran görüntüsüyle yakalandı.


def test_internal_notes_are_never_drawn_as_user_lines() -> None:
    """Harness dürtüsü kullanıcı balonu olarak çizilmez: `cizilir` süzgeci
    hem canlı mesaj yolunda hem de geçmiş dökümünde."""
    assert "IC_NOT_KALIPLARI" in APP_JS
    assert "Planını yazdın ama uygulamadın" in APP_JS   # kanıtlanmış sızıntı
    message = re.search(r'case "message":(.*?)break;', APP_JS, re.S)
    assert message and "cizilir(e.text)" in message.group(1)
    # Geçmiş dökümü de aynı süzgeçten geçiyor (eski günlüklerde not var).
    body = re.search(r"async function loadTranscript\(id\) \{(.*?)\n\}", APP_JS, re.S)
    assert body and "cizilir(t.text)" in body.group(1)


def test_a_faked_tool_call_is_never_drawn() -> None:
    """Model çağrı XML'ini düz metin yazdığında sohbete ham XML basılmaz —
    ne akarken ne de blok kapanırken."""
    assert "SAHTE_CAGRI_KALIBI" in APP_JS
    body = re.search(r"function write\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert body and "sahteCagri(raw)" in body.group(1)
    seal = re.search(r"function finishAgentLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert seal and "sahteCagri(raw)" in seal.group(1)


# -- asılı akış imleci --------------------------------------------------


def test_the_streaming_cursor_never_hangs() -> None:
    """İmleç bir CSS kuralı: `.line.agent` `.done` almadıkça yanıp sönüyor.
    Turun bittiği HER yolda mühürsüz bloklar süpürülüyor — boşsa siliniyor,
    doluysa mühürleniyor."""
    sweep = re.search(r"function clearCursor\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert sweep, "clearCursor() bulunamadı — desen bayatlamış olabilir"
    inner = sweep.group(1)
    assert ".line.agent:not(.done)" in inner
    assert "el.remove()" in inner and 'classList.add("done")' in inner
    # Kesme de mühürlüyor: eskiden yarım blok sonsuza kadar yanıp sönüyordu.
    stop = re.search(r'case "interrupted":(.*?)break;', APP_JS, re.S)
    assert stop and "sealLine()" in stop.group(1)
    # Model hiçbir şey döndürmediğinde de (sürdürme turu) imleç temizleniyor.
    bos = re.search(r'case "empty_assistant_turn":(.*?)break;', APP_JS, re.S)
    assert bos and "clearCursor()" in bos.group(1)


def test_an_empty_block_is_never_born() -> None:
    """Asıl çözüm süpürge değil: blok GERÇEK metin gelene kadar hiç
    doğmuyor. Model araçtan sonra çoğu zaman önce boş satır akıtıyordu ve
    ekranda boş bir "NEO" bloğu saniyelerce yanıp sönüyordu."""
    body = re.search(r"function write\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert body and "if (!raw.trim()) return;" in body.group(1)
    # Metin beklenirken şerit canlı kalıyor: donuk değil, süre sayan gösterge.
    close = re.search(r"function closeAct\(e\) \{(.*?)\n\}", APP_JS, re.S)
    assert close and "mull()" in close.group(1), \
        "araç bitince başlık hemen canlı düşünme göstergesine dönmeli"


# -- düşünme gürültüsü --------------------------------------------------


def test_trivial_thinking_opens_no_row() -> None:
    """30 adımlık bir turda 30 tane "Düşündü · 1 sn" satırı, okunacak şeyi
    (adımları) gürültüde boğuyordu. Eşiğin altındaki düşünme satır AÇMAZ."""
    assert re.search(r"const THINK_MIN_S = \d+", APP_JS)
    assert re.search(r"const THINK_MIN_WORDS = \d+", APP_JS)
    body = re.search(r"function closeThought\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "closeThought() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    assert "secs < THINK_MIN_S && words < THINK_MIN_WORDS" in inner
    assert "box.remove()" in inner


def test_swallowed_thinking_is_kept_not_lost() -> None:
    """Eşik yalnızca SATIR AÇMA kuralı, saklama kuralı değil: yutulan
    düşünce de turun arşivine giriyor ve açılan satırdan okunabiliyor."""
    body = re.search(r"function closeThought\(\) \{(.*?)\n\}", APP_JS, re.S)
    inner = body.group(1)
    assert "work.thinkAll.push(full)" in inner
    assert "arsiv.join" in inner, "açılan satır turun tüm muhakemesini göstermeli"
    # Ardışık düşünme birleşiyor: kesilmiş tek muhakeme iki satır olmamalı.
    think = re.search(r"function think\(chunk\) \{(.*?)\n\}", APP_JS, re.S)
    assert think and 'contains("think")' in think.group(1)


# -- şerit başlığı: komut KOD'dur ---------------------------------------


def test_a_command_in_the_headline_is_not_shouted() -> None:
    """Bir kabuk komutu başlıkta büyük harfe çevrilerek basılıyordu:
    okunmuyor, kopyalanamıyor, komut olduğu anlaşılmıyor. Hedef kendi
    düğümünde ve büyük harfe çevrilmiyor."""
    head = re.search(r"function workHead\(label, target, tail, kod\) \{(.*?)\n\}",
                     APP_JS, re.S)
    assert head, "workHead() bulunamadı — desen bayatlamış olabilir"
    assert "head-target" in head.group(1)
    rule = re.search(r"\.acts-head \.head-target \{([^}]*)\}", CSS)
    assert rule and "text-transform: none" in rule.group(1)
    assert "var(--mono)" in rule.group(1)
    # Şerit Cursor dili: bağıran UPPERCASE HUD değil, sakin status satırı.
    band = re.search(r"^\.acts-head \{([^}]*)\}", CSS, re.M)
    assert band and "text-transform: none" in band.group(1)


def test_the_headline_trims_shell_wrappers() -> None:
    """Sarmalayıcı her komutta aynı ve yer kaplıyor; okunmaya değer olan
    içindeki asıl komut. Kırpma yalnız GÖRÜNTÜDE: tam hâl adım kartında ve
    Kopyala ile alınabiliyor."""
    body = re.search(r"function komutOzeti\(text\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "komutOzeti() bulunamadı — desen bayatlamış olabilir"
    assert "SARMALAYICILAR" in body.group(1)
    assert re.search(r"const SARMALAYICILAR\s*=", APP_JS)
    # Kart tam komutu gösteriyor (kırpılmamış) ve kopyalanabiliyor.
    card = re.search(r"function buildCard\(card\) \{(.*?)\n\}", APP_JS, re.S)
    assert card and "card-copy" in card.group(1)
    assert 'codeBlock(String(card.input.command || ""), "powershell")' in APP_JS


# -- hedef paneli: örtmez ve yönetilir ----------------------------------


def test_the_goals_panel_reserves_its_own_room() -> None:
    """Panel sohbetin ÜSTÜNE biniyordu. Artık `.stream-wrap` içinde akışın
    kardeşi — flex sütunda kendi yerini kaplar, overlay değil."""
    html = open("src/neocp/web/static/index.html", encoding="utf-8").read()
    wrap_i = html.find('class="stream-wrap"')
    goals_i = html.find('id="goals"')
    assert 0 <= wrap_i < goals_i
    assert re.search(r"const GOAL_FOLD_WIDTH = \d+", APP_JS)
    assert "neo'nun kendine yazdığı iş listesi" in APP_JS


def test_goals_can_be_finished_dropped_and_cleared() -> None:
    """Panel salt gösterim değil: her maddede işaretle/kaldır, başlıkta iki
    adımlı "tümünü temizle" — hepsi /api/goals ucuna bağlı."""
    assert '"/api/goals"' in APP_JS
    for action in ('"done"', '"drop"', '"clear"'):
        assert action in APP_JS, action
    # İki adımlı onay: ilk tık soruyor, ikincisi uyguluyor.
    assert "clearArmed" in APP_JS and 't("Emin misin?")' in APP_JS
    # Eylemler sakin dururken görünmüyor (hover/odak).
    rule = re.search(r"^\.goal-act \{([^}]*)\}", CSS, re.M)
    assert rule and "opacity: 0" in rule.group(1)
    assert ".goal-item:hover .goal-act" in CSS
    # Panelin ne olduğu title'da — metin kalabalığı yok.
    assert "iş listesi" in APP_JS and "katla/aç" in APP_JS


# -- sürdürülen oturumun sayaçları --------------------------------------


def test_a_resumed_session_refills_the_context_gauge() -> None:
    """Kapanıp açılan uygulamada çubuk sıfırdan başlıyordu. Snapshot gerçek
    doluluğu taşıyor; tahminse title'da söyleniyor."""
    assert "dockContext(Number(s.prompt_total), s.tahmin)" in APP_JS
    body = re.search(r"function dockContext\(promptTotal, tahmin\) \{(.*?)\n\}",
                     APP_JS, re.S)
    assert body and 't("Bağlam doluluğu — yaklaşık (geçmişten tahmin)")' in body.group(1)
    # Oturum sürdürülünce durum yeniden çekiliyor (döküm kadar sayaçlar da).
    reset = re.search(r'case "session_reset": \{(.*?)\n    \}', APP_JS, re.S)
    assert reset and "loadState()" in reset.group(1)


def test_a_turn_of_only_trivial_thinking_still_keeps_a_door() -> None:
    """Turun BÜTÜN düşünmesi eşiğin altında kalırsa şeritte tek bir düşünme
    satırı bile olmaz — ve arşive girecek kapı da kalmazdı. Hiçbir şey
    kaybolmuyor: tur kapanırken TEK toplu satır ekleniyor (adım başına
    değil, tur başına)."""
    body = re.search(r"function sealThinkArchive\(w\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "sealThinkArchive() bulunamadı — desen bayatlamış olabilir"
    inner = body.group(1)
    assert 'querySelector(".think")' in inner, "açık bir kapı varsa ikincisi eklenmez"
    assert "arsiv.join" in inner
    close = re.search(r"function closeWork\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert close and "sealThinkArchive(work)" in close.group(1)


def test_the_goals_panel_cannot_overlap_by_construction() -> None:
    """Yer ayırmak (max-height'tan düşmek) yetmedi — kullanıcı hâlâ örtüşme
    gördü. Artık örtüşme YAPISAL olarak imkânsız: panel akışın kardeşi,
    ikisi de aynı flex sütununda. Overlay yok, `--goals-h` hesabı yok."""
    wrap = re.search(r"^\.stream-wrap \{(.*?)\}", CSS, re.S | re.M)
    assert wrap, ".stream-wrap kuralı yok — panel yine yüzüyor olabilir"
    assert "flex-direction: column" in wrap.group(1)
    assert "position: fixed" in wrap.group(1)
    # Akış artık kendi başına konumlanmıyor: kutunun içinde kalan yeri alır.
    stream = re.search(r"^\.stream \{(.*?)\}", CSS, re.S | re.M)
    assert stream and "position: fixed" not in stream.group(1)
    assert "min-height: 0" in stream.group(1), "flex çocuğu küçültülebilmeli"
    # Panel de yüzmüyor.
    goals = re.search(r"^\.goals \{(.*?)\}", CSS, re.S | re.M)
    assert goals and "position: fixed" not in goals.group(1)


def test_the_goals_panel_starts_folded_and_remembers() -> None:
    """Panel varsayılan TEK SATIR doğuyor ("◷ 3 iş listesi"); açık doğan bir
    liste, kullanıcının istemediği bir şeyi her açılışta yüzüne dayıyordu.
    Tercih hatırlanıyor."""
    assert re.search(r"let folded = true;", APP_JS)
    assert "GOAL_FOLD_KEY" in APP_JS
    assert "localStorage.getItem(GOAL_FOLD_KEY)" in APP_JS
    remember = re.search(r"function rememberFold\(\) \{(.*?)\n  \}", APP_JS, re.S)
    assert remember and "localStorage.setItem(GOAL_FOLD_KEY" in remember.group(1)
    # Depolama yoksa (gizli sekme) patlamıyor.
    assert remember.group(1).count("catch") >= 1
    body = re.search(r"function render\(\) \{(.*?)\n  \}", APP_JS, re.S)
    assert body and 't(" iş listesi")' in body.group(1)
    assert "if (folded) return;" in body.group(1), "katlıyken gövde kurulmamalı"


def test_the_panel_explains_itself_and_accepts_user_items() -> None:
    """Kullanıcı "bu görevleri kim oluşturuyor bilmiyorum" dedi: cevap artık
    panelin kendisinde, ve liste iki taraflı — kullanıcı da ekleyebiliyor."""
    assert "GOAL_ACIKLAMA" in APP_JS
    assert "neo'nun kendine yazdığı iş listesi" in APP_JS
    assert "Sen de ekleyebilir, silebilirsin" in APP_JS
    body = re.search(r"function render\(\) \{(.*?)\n  \}", APP_JS, re.S)
    assert body and "goals-what" in body.group(1)
    assert "addRow()" in body.group(1)
    add = re.search(r"function addRow\(\) \{(.*?)\n  \}", APP_JS, re.S)
    assert add, "addRow() bulunamadı — desen bayatlamış olabilir"
    assert 'ask("add"' in add.group(1)
    assert 'ev.key === "Enter"' in add.group(1)
    # Eski oturumdan kalan madde ayırt ediliyor.
    assert "goal-eski" in APP_JS and 't("eski")' in APP_JS


# -- oturum yönetimi paneli --------------------------------------------
#
# Adlandırma, etiket ve döküm araması geçmiş panelinde yaşıyor. Uçlar
# çalışsa bile panel onları çağırmıyorsa özellik yok demektir.

HIST_JS = (STATIC / "history.js").read_text(encoding="utf-8")
SETTINGS_JS_SRC = (STATIC / "settings.js").read_text(encoding="utf-8")


def test_the_history_panel_can_name_and_tag_a_conversation() -> None:
    """Türetilen başlık konuşmanın ilk sözü; ad ise bir karar. İkisi
    ayırt edilebilmeli, yoksa kullanıcı kendi verdiği adı arar."""
    assert "function editName" in HIST_JS
    assert "function editTags" in HIST_JS
    assert '"/api/session/meta"' in HIST_JS
    # Gönderilmeyen alan sunucuda dokunulmadan kalıyor: iki ayrı çağrı.
    assert "saveMeta(s.id, { ad })" in HIST_JS
    assert "saveMeta(s.id, { etiketler })" in HIST_JS
    assert re.search(r"\.hist-title\.named \{", CSS)
    # Sınıf adı panelin kendi başlığıyla ÇAKIŞMAMALI: index.html'deki
    # "Konuşmalar" başlığı zaten `.hist-tag` taşıyor (canlıda görüldü).
    assert re.search(r"^\.hist-label \{", CSS, re.M)
    assert "hist-label" in HIST_JS and 'el("button", "hist-tag' not in HIST_JS


def test_tags_filter_the_list_and_can_be_cleared() -> None:
    """Etikete tıklamak süzgeç; ikinci tık kaldırıyor. Süzgeç açıkken
    kullanıcı bunu GÖRMELİ, yoksa 'konuşmalarım kayboldu' olur."""
    assert "tagFilter" in HIST_JS
    assert re.search(r"tagFilter = \(tagFilter === etiket\) \? \"\" : etiket", HIST_JS)
    assert re.search(r"shown\.filter\(s => \(s\.tags \|\| \[\]\)\.includes\(tagFilter\)\)", HIST_JS)
    tools = re.search(r"function drawTools\(\) \{(.*?)\n  \}", HIST_JS, re.S)
    assert tools and "tagFilter" in tools.group(1)


def test_the_search_box_can_look_inside_transcripts() -> None:
    """Aranan söz çoğu zaman başlıkta değil; 'içinde ara' aramayı
    dökümlere taşıyor. Her tuşta istek atmamalı."""
    assert "hist-deep" in HIST_JS
    assert '"/api/sessions?ara=" + encodeURIComponent(ara)' in HIST_JS
    gecikme = re.search(r"const DEEP_DELAY = (\d+)", HIST_JS)
    assert gecikme and int(gecikme.group(1)) >= 150
    plan = re.search(r"function scheduleDeep\(\) \{(.*?)\n  \}", HIST_JS, re.S)
    assert plan, "scheduleDeep() bulunamadı"
    # Kısa sorgu sunucuya hiç gitmiyor: tek harf her konuşmada geçer.
    assert "q.length < 2" in plan.group(1)
    assert "clearTimeout(deepTimer)" in plan.group(1)
    # Eşleşmeler satırın altında iz olarak duruyor.
    assert "hist-hit" in HIST_JS
    assert re.search(r"^\.hist-hit \{", CSS, re.M)


def test_the_history_panel_says_what_it_is_doing() -> None:
    """Boş/yükleniyor/aranıyor birbirinden ayrı: sessiz boş bir panel
    'bozuk mu' sorusunu doğurur."""
    for phrase in ("Yükleniyor…", "Aranıyor…", "Henüz konuşma yok", "Eşleşen konuşma yok"):
        assert phrase in HIST_JS, phrase
    added = re.search(r"Dil\.ekle\(\{(.*?)\n\}\);", HIST_JS, re.S)
    assert added, "history.js çeviri eklemiyor"
    for phrase in ("içinde ara", "Yeniden adlandır", "Etiketle", "Aranıyor…"):
        assert phrase in added.group(1), phrase


def test_the_settings_page_offers_a_fallback_model() -> None:
    """Yedek alanı yoksa özellik ayarlanamaz; alan varsa da yamaya
    yazılmazsa kaydet hiçbir şey yapmaz."""
    assert '"Yedek model"' in SETTINGS_JS_SRC
    assert 'set("model", "fallback_model", v.trim())' in SETTINGS_JS_SRC
    # Öneriler aynı katalogdan ama seçim zorunlu değil: liste vermeyen bir
    # uçta da yedek yazılabilmeli.
    assert "function fillFallback" in SETTINGS_JS_SRC
    assert 'setAttribute("list", "yedek-modeller")' in SETTINGS_JS_SRC
    added = re.search(r"Dil\.ekle\(\{(.*?)\n\}\);", SETTINGS_JS_SRC, re.S)
    assert added and "Yedek model" in added.group(1)


# -- kompozer yüzeyleri: `/` komut defteri ve `@` dosya bahsi ----------
#
# İkisi de tek bir durum makinesinde yaşıyor (komut.js). Buradaki
# kontroller o makinenin sözleşmesini tutuyor: hangi komutlar var, neye
# bağlılar, klavye hangi tuşları anlıyor ve seçilen dosya modele NASIL
# geçiyor.

KOMUT_JS = (STATIC / "komut.js").read_text(encoding="utf-8")
GOREV_JS = (STATIC / "gorevler.js").read_text(encoding="utf-8")
CHG_JS = (STATIC / "degisiklik.js").read_text(encoding="utf-8")
SERVER_SRC = (Path(__file__).resolve().parents[1]
              / "src" / "neocp" / "web" / "server.py").read_text(encoding="utf-8")


def _defter() -> list[tuple[str, str]]:
    """komut.js'teki komut defteri: [(ad, açıklama)]."""
    block = re.search(r"const DEFTER = \[(.*?)\n  \];", KOMUT_JS, re.S)
    assert block, "komut defteri bulunamadı — desen bayatlamış olabilir"
    return re.findall(r'\{\s*ad:\s*"([\w-]+)",\s*ne:\s*"([^"]+)"', block.group(1))


def test_the_command_book_covers_the_promised_commands() -> None:
    """Kayıt TEK yerde: yenisini eklemek defterde bir satır olmalı.

    Eksik bir komut sessiz bir boşluk: kullanıcı `/model` yazıyor, menü
    onu göstermiyor ve "yok galiba" diye ayar sayfasına gidiyor.
    """
    kayit = dict(_defter())
    beklenen = {"yeni", "gecmis", "model", "yetki", "gorevler", "uygulamalar",
                "artifact", "ayarlar", "sifirla", "durdur", "yardim"}
    assert beklenen <= set(kayit), f"eksik komut: {sorted(beklenen - set(kayit))}"
    # Her komut ne yaptığını TEK satırda söylüyor.
    for ad, ne in kayit.items():
        assert ne.strip() and "\n" not in ne, ad
        assert len(ne) <= 80, f"{ad}: açıklama tek satırdan uzun"


def test_every_command_runs_something_that_exists() -> None:
    """Uydurma komut yok: her satır ya var olan bir düğmeye basıyor ya da
    sunucuda gerçekten kayıtlı bir uca gidiyor."""
    block = re.search(r"const DEFTER = \[(.*?)\n  \];", KOMUT_JS, re.S)
    assert block
    for element_id in re.findall(r'kos:\s*\(\)\s*=>\s*tik\("([\w-]+)"\)', block.group(1)):
        assert f'id="{element_id}"' in HTML, element_id
    # Düğmeye bağlanmayanlar bir fonksiyona bağlı ve o fonksiyon tanımlı.
    for name in re.findall(r"kos:\s*(\w+)\s*\}", block.group(1)):
        assert re.search(rf"function {name}\(", KOMUT_JS), name
    # `/sifirla` gerçek bir sıkıştırma ucuna gidiyor.
    assert '"/api/compact"' in KOMUT_JS
    assert '"/api/compact"' in SERVER_SRC


def test_the_composer_menu_is_a_keyboard_state_machine() -> None:
    """Fare olmadan da kullanılabilmeli: ok tuşları gezer, Enter seçer,
    Escape kapatır. Enter kutuya gitmezse mesaj yanlışlıkla gönderilir."""
    tus = re.search(r"function tus\(ev\) \{(.*?)\n  \}", KOMUT_JS, re.S)
    assert tus, "tus() bulunamadı — desen bayatlamış olabilir"
    body = tus.group(1)
    for key in ("Escape", "ArrowDown", "ArrowUp", "Enter"):
        assert f'"{key}"' in body, key
    # Kompozerin kendi Enter dinleyicisi (app.js) devreye girmemeli.
    assert "stopPropagation()" in body
    # Dinleyici belgede ve YAKALAMA evresinde: app.js'in dinleyicisi
    # kompozerin üstünde ve ondan önce çalışmak gerekiyor.
    assert 'document.addEventListener("keydown", tus, true)' in KOMUT_JS
    # Kutu kapalıyken hiçbir tuşa karışmıyor.
    assert "if (!acikMi()" in body


def test_slash_only_triggers_at_the_start_of_a_line() -> None:
    """Cümle ortasındaki bir eğik çizgi (yol, kesir) menü açmamalı."""
    kalip = re.search(r"const KOMUT_KALIBI = (.+);", KOMUT_JS)
    assert kalip, "komut kalıbı bulunamadı"
    assert kalip.group(1).startswith("/(?:^|\\n)\\/"), kalip.group(1)
    dosya = re.search(r"const DOSYA_KALIBI = (.+);", KOMUT_JS)
    assert dosya and "@" in dosya.group(1)


def test_a_mentioned_file_reaches_the_model_as_a_plain_sentence() -> None:
    """`@` gizli bir enjeksiyon değil: cipte yazan yol, mesajda da yazıyor.

    Metin kullanıcının gönderdiği mesajın İÇİNDE — sonradan "ben bunu
    yazmadım" diyebileceği görünmez bir ek değil.
    """
    assert '"Kullanıcı şu dosyayı işaret etti: "' in KOMUT_JS
    # Birden çok dosya seçilebiliyor ve her biri ayrı satır.
    assert "bahis.map(" in KOMUT_JS and 'join("\\n")' in KOMUT_JS
    # app.js gönderim yolunda bunu gerçekten çağırıyor.
    assert "withContext(withFiles(withMentions(text)))" in APP_JS
    # Arama gerçek bir uca gidiyor ve o uç sunucuda kayıtlı.
    assert '"/api/files/search?q="' in KOMUT_JS
    assert '"/api/files/search"' in SERVER_SRC


def test_the_file_picker_does_not_let_a_stale_answer_win() -> None:
    """Yazarken listenin bir öncekine geri atlaması: geç dönen eski cevap.
    Jeton karşılaştırması olmadan bu her hızlı yazımda oluyor."""
    ara = re.search(r"function dosyalariAra\(\) \{(.*?)\n  \}", KOMUT_JS, re.S)
    assert ara, "dosyalariAra() bulunamadı"
    assert "++jeton" in ara.group(1)
    assert "benim !== jeton" in ara.group(1)
    assert "clearTimeout(aramaTimer)" in ara.group(1)


# -- koşan görevler paneli ---------------------------------------------


def test_the_task_panel_speaks_the_same_shape_the_server_sends() -> None:
    """Panelin okuduğu her alan sunucunun yazdığı alan olmalı.

    Bir alan adı değişince panel sessizce boş satır çiziyor: "koşuyor" ama
    süresi yok, adı yok. Sözleşme iki tarafta da yazılı olmalı.
    """
    bridge = (Path(__file__).resolve().parents[1] / "src" / "neocp"
              / "desktop.py").read_text(encoding="utf-8")
    gorevler = re.search(r"def gorevler\(self\).*?return \{\"gorevler\"", bridge, re.S)
    assert gorevler, "Bridge.gorevler() bulunamadı"
    yazilan = set(re.findall(r'"(\w+)":', gorevler.group(0)))
    for alan in ("id", "ad", "tur", "durum", "basladi", "bitti", "ozet",
                 "oturum", "durdurulabilir"):
        assert alan in yazilan, f"sunucu {alan} yazmıyor"
        assert re.search(rf"\bg\.{alan}\b", GOREV_JS), f"panel {alan} okumuyor"


def test_the_task_panel_can_stop_one_job_and_only_a_stoppable_one() -> None:
    """Kendi kopyasını panelden öldürmek uygulamayı kapatmak olurdu."""
    assert '"/api/gorevler/durdur"' in GOREV_JS
    assert '"/api/gorevler/durdur"' in SERVER_SRC
    assert "if (g.durdurulabilir)" in GOREV_JS
    bridge = (Path(__file__).resolve().parents[1] / "src" / "neocp"
              / "desktop.py").read_text(encoding="utf-8")
    assert '"durdurulabilir": (not biten) and not kendi' in bridge


def test_a_finished_background_job_knocks_on_the_conversation() -> None:
    """Panel kapalıyken biten iş kaybolmamalı: sohbete tıklanabilir satır.
    Yalnız ARKA PLAN işleri — senkron yardımcının sonucu zaten cevapta."""
    assert re.search(r"case \"child_end\":[\s\S]*?tasksDone\(e\)", APP_JS)
    bitti = re.search(r"function bitti\(ev\) \{(.*?)\n  \}", GOREV_JS, re.S)
    assert bitti, "Gorevler.bitti() bulunamadı"
    assert "if (!ev || !ev.bg) return;" in bitti.group(1)
    assert "task-note" in bitti.group(1)
    # Köprü `bg` alanını gerçekten yayıyor (_child_end içinde).
    bridge = (Path(__file__).resolve().parents[1] / "src" / "neocp"
              / "desktop.py").read_text(encoding="utf-8")
    assert "def _child_end" in bridge
    assert "bg = self._cocuk_arka_plan(cid)" in bridge
    assert '"bg": bg' in bridge


def test_a_failed_job_report_page_is_not_a_traceback_dump() -> None:
    """Rapor sayfası komutu h1 yapıp traceback basmasın — 'İş başarısız'."""
    assert "İş başarısız" in SERVER_SRC
    assert "def _rapor_kapak" in SERVER_SRC
    assert 'class="badge err"' in SERVER_SRC
    # Ham iz rapor değil.
    assert 's.startswith("Traceback ("' in SERVER_SRC


def test_the_running_time_ticks_without_asking_the_server() -> None:
    """Saniyede bir HTTP isteği atmak paneli açık tutmayı pahalı yapardı:
    satır başlangıç damgasını taşıyor, saymayı tarayıcı yapıyor."""
    assert "dataset.basladi" in GOREV_JS
    assert re.search(r"setInterval\(\(\) => \{[^}]*task-time", GOREV_JS, re.S)


def test_the_live_jobs_ledger_stays_separate_from_orchestra() -> None:
    """Bilinçli karar: orkestra ŞU ANKİ turun sahnesi, canlı koşum defteri ayrı.
    İkisi tek panele indirilirse ya sahne kalıcı olur ya defter kaybolur —
    karar kodda yazılı olsun ki sonra 'kopya panel' diye silinmesin."""
    jobs = (STATIC / "jobs.js").read_text(encoding="utf-8")
    assert "Orkestra güvertesinden AYRI" in GOREV_JS
    assert 'id="orch-deck"' in HTML
    assert 'id="tasks-panel"' not in HTML
    assert "openLive" in jobs and "Canlı" in jobs


def test_orchestra_lives_in_the_right_sidebar_not_a_left_modal() -> None:
    """Orkestra sağ sütunda; kamera yüzen pencere (right-col overflow kesmesin)."""
    assert 'id="right-col"' in HTML
    assert 'id="side-dock"' in HTML
    assert HTML.find('id="side-dock"') < HTML.find('id="orch-deck"')
    assert ".right-col" in CSS
    assert ".side-dock" in CSS
    assert "grid-auto-rows" in CSS
    assert 'id="dock-grip"' in HTML
    assert "ns-resize" in CSS
    assert "--dock-h-user" in CSS
    assert "neo-dock-h" in APP_JS
    assert "left: 18px" not in CSS.split(".orch-deck")[1][:400]
    cams = (STATIC / "cameras.js").read_text(encoding="utf-8")
    assert "cam-open" in cams
    assert 'id="cam-head"' in HTML
    assert HTML.find('id="orch-deck"') < HTML.find('id="cam-deck"')
    assert "open_camera_window" in cams
    assert "watch.html" in cams
    assert "requestFullscreen" not in cams
    assert 'id="cam-layer"' in HTML
    assert "Bilgisayar kamerası" in cams
    assert 'id="cam-deck"' in HTML and 'id="cam-live"' in HTML
    assert HTML.find('id="cam-deck"') < HTML.find('id="cam-live"')
    assert HTML.find('id="cam-live"') < HTML.find('id="cam-foot"')
    assert HTML.find('id="right-col"') < HTML.find('id="cam-deck"')
    assert "classList.add(\"cam-open\", \"cam-stage\")" not in cams
    assert "body.cam-stage #scene" not in CSS
    assert "boxes=1" in cams
    assert 'id="cam-kind"' in HTML and 'id="cam-pass"' in HTML


def test_scheduled_tasks_are_editable_and_not_chat_dumps() -> None:
    """Zamanlanmış görev: silip yeniden eklemek yok; tık → düzenle + rapor.
    Tetikleme sohbet kuyruğu değil (run_scheduled / spawn_scheduled)."""
    settings = (STATIC / "settings.js").read_text(encoding="utf-8")
    assert "function editTaskForm" in settings
    assert 'action: "update"' in settings
    assert "Raporu aç" in settings
    assert "spawn_scheduled" in (Path(__file__).resolve().parents[1]
        / "src" / "neocp" / "loop.py").read_text(encoding="utf-8")
    assert "run_scheduled" in (Path(__file__).resolve().parents[1]
        / "src" / "neocp" / "desktop.py").read_text(encoding="utf-8")
    assert "sessiz" in (Path(__file__).resolve().parents[1]
        / "src" / "neocp" / "loop.py").read_text(encoding="utf-8")


def test_main_jobs_panel_and_artifact_export_exist() -> None:
    """Ana Görevler paneli + artifact indir/yazdır yüzeyi yerinde."""
    html = HTML
    jobs = (STATIC / "jobs.js").read_text(encoding="utf-8")
    viewer = (STATIC / "viewer.js").read_text(encoding="utf-8")
    orch = (STATIC / "orchestra.js").read_text(encoding="utf-8")
    assert 'id="jobs"' in html and 'id="jobs-panel"' in html
    assert "/jobs.js" in html and "/workflow.js" in html
    assert "function renderDefForm" in jobs
    assert "function renderSettingsForm" in jobs
    assert "view === \"live\"" in jobs  # load() Canlıyı silmesin
    assert "formatRunMeter" in jobs
    assert "duration_s" in jobs and "last_tool" in jobs
    assert "fmtDuration" in jobs
    assert "renderLiveRun" in jobs and "Canlı adımlar" in jobs
    assert "refreshLive" in jobs
    assert "download=1" in (Path("src/neocp/web/server.py").read_text(encoding="utf-8"))
    assert "downloadArtifact" in viewer and "injectScrollCss" in viewer
    assert "function wait(" in orch or "wait(ev)" in orch
    assert "ch.hedef" in orch or "ev.hedef" in orch
    assert "KEEP_ACTS" in orch and "orch-ch-acts" in orch
    assert "child_wait" in APP_JS
    assert "Gorevler.tazele" in APP_JS
    assert "DOKUM_TTL_MS" in (STATIC / "gorevler.js").read_text(encoding="utf-8")
    assert "function planCard" in APP_JS
    assert "flushDeferredPlans" in APP_JS
    assert "enterPlanEdit" in APP_JS
    assert "prompt(" not in APP_JS.split("function planCard")[1].split("function maybeOfferPlan")[0]
    assert "plan-edit-area" in (STATIC / "app.css").read_text(encoding="utf-8")
    assert "_inited" in (STATIC / "scene.js").read_text(encoding="utf-8")
    # 28.08 kabuk kararı (kullanıcı, Claude Code birebir): HUD sade başlık
    # çubuğu — kümeler dağıldı. Bağlam araçları orta-sağ üstte (ctx-tools),
    # sistem ikonları kenar çubuğunun dibinde (side-foot).
    assert "ctx-tools" in HTML and "side-foot" in HTML
    assert 'id="hist-new"' in HTML   # yeni konuşma girişi sidebar'da
    assert "Araçlar" in HTML and "Bağlantılar (MCP)" in HTML
    settings = (STATIC / "settings.js").read_text(encoding="utf-8")
    assert "confirmRow" in settings and "syncSaveFoot" in settings
    assert "fillConnectorForm" in settings or "saveLabel" in settings
    assert "tool-chips" in (STATIC / "app.css").read_text(encoding="utf-8")
    hist = (STATIC / "history.js").read_text(encoding="utf-8")
    assert "statusFilter" in hist and "assignPath" in hist and "assignModel" in hist
    assert "hist-status-filters" in (STATIC / "app.css").read_text(encoding="utf-8")
    assert "--open" in (Path(__file__).resolve().parents[1]
        / "src" / "neocp" / "cli.py").read_text(encoding="utf-8")
    assert "NeoOpen" in (Path(__file__).resolve().parents[1]
        / "installer" / "neo.iss").read_text(encoding="utf-8")
    assert "function editTaskForm" in (STATIC / "settings.js").read_text(encoding="utf-8")


# -- "bu turda ne değişti" + geri al -----------------------------------


def test_the_turn_summary_reads_the_agents_own_ledger() -> None:
    """İkinci bir defter tutulmuyor: panelin gördüğü, `undo` aracının
    okuduğu defterin aynısı (tools/checkpoint.py)."""
    assert "/api/degisiklikler" in CHG_JS
    assert "checkpoint import KLASOR, Defter" in SERVER_SRC
    # Geri alma: tur (n), dosya (sira/siralar) veya path.
    assert "defter.geri_al(n)" in SERVER_SRC
    assert "geri_al_sira" in SERVER_SRC
    assert "geri_al_dosya" in SERVER_SRC
    assert "kartUndoDosya" in CHG_JS
    assert "hepsini kabul et" in CHG_JS
    assert "diff-btn keep" in APP_JS


def test_the_turn_boundary_is_a_sequence_number_not_a_clock() -> None:
    """Saniye çözünürlüğü aynı saniyedeki iki yazımı ayıramıyor."""
    assert "since=" in CHG_JS
    assert "turBasi" in CHG_JS
    assert re.search(r"case \"turn_end\":.*?chgTurnEnd\(\)", APP_JS, re.S)
    assert "chgTurnStart()" in APP_JS


def test_undoing_a_turn_asks_twice() -> None:
    """Yanlışlıkla basılan bir düğmenin turu silmesi kabul edilemez."""
    dugme = re.search(r"function geriAlDugmesi\(kayitlar, durum, onChange\) \{(.*?)\n  \}",
                      CHG_JS, re.S)
    assert dugme, "geriAlDugmesi() bulunamadı"
    body = dugme.group(1)
    assert "if (!onay)" in body and "Emin misin?" in body
    # Onay penceresi kendiliğinden kapanıyor: kurulu bir düğme unutulmasın.
    assert "setTimeout(" in body
    # Geri alınacaklar: bu turda hâlâ açık kayıtların sira listesi.
    assert "siralar:" in body


def test_the_diff_in_the_summary_is_the_same_diff_card() -> None:
    """İkinci bir diff çizici, bir gün ikisinin ayrı görünmesi demek."""
    assert "diffHunk(veri.eski, veri.yeni, 1)" in CHG_JS
    assert "function diffHunk(" in APP_JS
    assert "/api/degisiklikler/fark" in CHG_JS


# -- bütçe freni --------------------------------------------------------


def test_the_budget_cap_lives_next_to_the_number() -> None:
    """Ayar sayfasında değil: harcamanın yanında, maliyet çipinin kutusunda."""
    assert "function butceAlani()" in APP_JS
    assert '"/api/butce"' in APP_JS and '"/api/butce"' in SERVER_SRC
    # Boş = sınırsız.
    assert 'usd: ham === "" ? null : ham' in APP_JS
    # Ayar sayfasında bir bütçe alanı YOK: iki yerde duran bir sınır, bir
    # gün birbirini tutmayan iki sayı olurdu.
    assert "butce" not in SETTINGS_JS_SRC


def test_the_cost_chip_shows_the_cap_it_is_running_under() -> None:
    """'Ne kadar kaldı' sorusu kutuyu açmadan cevaplanmalı."""
    chip = re.search(r"function dockCost\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert chip, "dockCost() bulunamadı"
    assert "if (butce)" in chip.group(1)
    assert 'classList.toggle("over"' in chip.group(1)
    assert re.search(r"^#dock-cost\.over \{", CSS, re.M)


def test_every_static_script_actually_parses() -> None:
    """Sözdizimi hatası TEK bir dosyayı değil, o dosyanın tanımladığı her
    şeyi düşürüyor: ayar sayfası açılıyor ama alanların yarısı yok.

    Yaşanmış hâli: `Dil.ekle` içinde anahtar olarak `"a" + "b"` yazıldı.
    Nesne anahtarı bir ifade olamaz; dosya hiç yüklenmedi ve "Yedek model"
    alanı sessizce kayboldu. Grep tabanlı testler bunu göremiyor — gerçek
    bir ayrıştırıcı gerekiyor.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node yok — sözdizimi denetimi atlandı")

    for path in sorted(STATIC.glob("*.js")):
        done = subprocess.run([node, "--check", str(path)],
                              capture_output=True, text=True)
        assert done.returncode == 0, f"{path.name}: {done.stderr.strip()[:400]}"


# -- proje kipi (ayarlar yüzeyi) ---------------------------------------

SETTINGS_CSS = (STATIC / "settings.css").read_text(encoding="utf-8")


def test_the_settings_page_can_choose_a_project_folder() -> None:
    """Native klasör diyaloğu yok: seçici sayfanın kendi içinde ve
    `/api/gozat` ucunu kullanıyor."""
    src = (STATIC / "settings.js").read_text(encoding="utf-8")
    assert "function projectSection" in src
    assert '"/api/gozat?yol=" + encodeURIComponent(yol)' in src
    assert 'set("sandbox", "project"' in src
    # Son projeler tek tıkla geçiş.
    assert "state.sandbox.recent" in src
    assert re.search(r"^\.panel \.proj-chip \{", SETTINGS_CSS, re.M)
    assert re.search(r"^\.panel \.proj-list \{", SETTINGS_CSS, re.M)


def test_the_project_row_is_honest_about_what_changes() -> None:
    """Seçim yazma iznini genişletiyor ve bunu kullanıcı bilmeli; ama
    oturum/anı DEĞİŞMİYOR ve bu da yazılmalı — yoksa kullanıcı proje
    değiştirmeyi konuşmayı kaybetmek sanır."""
    src = (STATIC / "settings.js").read_text(encoding="utf-8")
    row = re.search(r'"Çalışılan proje",(.*?)\n    \)\);', src, re.S)
    assert row, "proje alanı bulunamadı — desen bayatlamış olabilir"
    inner = row.group(1)
    assert "ONAYDIR" in inner
    assert "ETKİLEMEZ" in inner
    # Kaydetmeden önce/sonra ayrı ayrı söyleniyor.
    for phrase in ("Kaydedince burada çalışmaya başlayacağım.",
                   "Şu an burada çalışıyorum; yazma izni bu klasörde geçerli.",
                   "Proje seçilmedi — yazma yalnızca atölyede serbest."):
        assert phrase in src, phrase
    added = re.search(r"Dil\.ekle\(\{(.*?)\n\}\);", src, re.S)
    assert added and "Çalışılan proje" in added.group(1)
    assert "Son projeler" in added.group(1)


def test_every_toolbar_button_is_translated() -> None:
    """İngilizce arayüzde Türkçe başlık kalmamalı — `title` ve `aria-label`.

    Yaşanmış hâli: dil İngilizce'yken araç çubuğunun bütün ipuçları Türkçe
    duruyordu, çünkü eşleme yalnız bazı id'ler için ve yalnız `title` için
    yazılmıştı. `aria-label` hiç çevrilmiyordu: ekran okuyucu kullanan biri
    İngilizce arayüzde Türkçe etiket duyuyordu.
    """
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    dil = (STATIC / "dil.js").read_text(encoding="utf-8")

    # index.html'de id'si ve title/aria-label'ı olan her öğe eşlenmiş olmalı.
    for nitelik in ("title", "aria-label"):
        desen = re.compile(
            r'id="([a-z0-9-]+)"[^>]*\b' + nitelik + r'="([^"]+)"', re.I)
        for eid, metin in desen.findall(html):
            if not re.search(r"[çğıöşüÇĞİÖŞÜ]", metin):
                continue        # zaten Türkçeye özgü harf yoksa atla
            assert f'"{eid}"' in dil, (
                f'index.html#{eid} {nitelik}="{metin}" için çeviri yok')

def test_explicit_file_links_in_chat_are_actionable() -> None:
    """Canli sikayet (29.08 KPSS raporu): "[PDF raporu ac](rapor.pdf)"
    olu metindi, "[ZIP arsivini indir](rapor.zip)" hic taninmiyordu.
    Acik bagda niyet belli — tur karar verir: metin/kod goruntuleyici,
    tarayicinin cizebildigi yeni sekme, gerisi dogrudan indirme.
    """
    assert "function downloadChip" in MD_JS_SRC
    assert "MEDIA_EXT" in MD_JS_SRC and "PATHISH" in MD_JS_SRC
    # zip artik uzanti listesinde: bag olu span'a dusmez.
    assert '"zip rar 7z tar gz tgz xlsx docx pptx"' in MD_JS_SRC
    # indirme yolu gercek <a> + attachment ucu.
    assert 'download=1' in MD_JS_SRC
    assert 'chip.setAttribute("download"' in MD_JS_SRC


def test_raw_endpoint_honors_the_download_flag() -> None:
    from pathlib import Path
    src = Path('src/neocp/web/server.py').read_text(encoding='utf-8')
    assert 'Content-Disposition' in src
    assert 'attachment; filename=' in src


def test_decided_plan_cards_stay_in_place_without_buttons() -> None:
    """Canli sikayet: onaylanmis plan karti, is bitince cevabin ALTINA
    dugmeleriyle yeniden dusuyordu. Karar verilmis kart akista kalir
    ve karar dugmeleri gizlenir; yalniz 'bekliyor' kart sona tasinir.
    """
    assert "function planBekliyor" in APP_JS
    assert "function planKarariUygula" in APP_JS
    assert "if (!planBekliyor(card)) continue;" in APP_JS
    # applyPlanData her durum degisiminde dugme gorunurlugunu tazeler.
    assert APP_JS.count("planKarariUygula(card)") >= 2


def test_camera_can_open_in_a_separate_window() -> None:
    """İzleme ana Neo'dan koparılabilir: ayrı OS penceresi, canlı kare."""
    watch = (STATIC / "watch.html").read_text(encoding="utf-8")
    js = (STATIC / "watch.js").read_text(encoding="utf-8")
    desk = (Path(__file__).resolve().parents[1] / "src" / "neocp" / "desktop.py"
            ).read_text(encoding="utf-8")
    from neocp.web.server import ASSETS
    assert "watch-win" in watch
    assert 'class="brand"' in watch
    assert "function aktifVar" in js
    assert "requestFullscreen" not in js
    assert "/watch.js" in ASSETS
    assert "def open_camera_window" in desk
    assert "watch.html" in desk
    assert "frameless=False" in desk
    assert "innerHTML" not in js


def test_camera_hud_is_a_power_toggle() -> None:
    """Üst kamera ikonu: kapalıyken açar, açıkken izleme sahnesini açar."""
    cams = (STATIC / "cameras.js").read_text(encoding="utf-8")
    html = HTML
    css = CSS
    assert 'action: "power"' in cams
    assert "cam-on" in cams and "cam-off" in cams
    assert 'id="cam-stop"' in html
    assert 'id="cam-deck"' in html
    assert 'id="cam-live"' in html
    assert HTML.find('id="cam-deck"') < HTML.find('id="cam-live"')
    assert "Kamera açık — tıkla: pencerede izle" in cams
    assert "function aktifVar" in cams
    assert "if (!aktifVar()) kapat()" in cams
    assert "open_camera_window" in cams
    assert "watch.html" in cams
    assert "requestFullscreen" not in cams
    assert "classList.add(\"cam-open\", \"cam-stage\")" not in cams
    assert "body.cam-stage #scene" not in css
    assert "#cams.cam-on" in css
    assert "cam-head-acts" in css and "position: fixed" in css
    assert "minmax(0, 1fr)" in css
    assert "spec.title" in cams
    assert "#mic.mute .off-line" in css
    assert 'class="icon cam-off"' in html
    assert "case \"camera\"" in APP_JS
    assert "Cameras.baglam" in APP_JS
    assert "sync_camera" in (
        Path(__file__).resolve().parents[1] / "src" / "neocp" / "desktop.py"
    ).read_text(encoding="utf-8")


def test_voice_and_hear_hud_start_off_with_slash() -> None:
    """Ses ve mikrofon HUD: kapalı çizgi + tıkla popup (kamera ile aynı dil)."""
    html = HTML
    css = CSS
    assert 'id="mute"' in html and 'id="hear"' in html
    assert 'id="mute-pop"' in html and 'id="hear-pop"' in html
    assert 'hidden' not in html.split('id="mute"', 1)[1].split(">", 1)[0]
    assert 'class="icon off"' in html.split('id="mute"', 1)[1].split(">", 1)[0]
    assert 'class="icon off"' in html.split('id="hear"', 1)[1].split(">", 1)[0]
    assert 'class="off-line"' in html.split('id="mute"', 1)[1].split("</button>", 1)[0]
    assert 'class="off-line"' in html.split('id="hear"', 1)[1].split("</button>", 1)[0]
    assert "#mute.off .off-line" in css and "#hear.off .off-line" in css
    assert "Settings.open(\"voice\")" in APP_JS
    assert "Settings.open(\"hearing\")" in APP_JS
    assert 'what: "voice"' in APP_JS and 'what: "hearing"' in APP_JS
    assert "button.hidden = !enabled" not in APP_JS
    desk = (
        Path(__file__).resolve().parents[1] / "src" / "neocp" / "desktop.py"
    ).read_text(encoding="utf-8")
    assert "def sync_hearing" in desk
    assert "def hearing_power" in desk
    assert "def voice_power" in desk


def test_connector_catalog_uses_brand_marks() -> None:
    """Popüler bağlayıcılar metin kutusu değil — GitHub/Notion vb. logosu."""
    settings = (STATIC / "settings.js").read_text(encoding="utf-8")
    css = (STATIC / "settings.css").read_text(encoding="utf-8")
    assert "CONN_MARKS" in settings and "function connMark" in settings
    assert ".conn-mark" in css
    assert "minmax(196px" in css
    for key in ("github", "notion", "linear", "sentry", "stripe",
                "playwright", "dosyalar", "bellek", "figma", "slack",
                "atlassian", "supabase", "vercel", "huggingface"):
        assert f"{key}:" in settings, key
    assert "8.205 11.385" in settings  # GitHub octocat
    assert "mcp.figma.com" in settings and "mcp.slack.com" in settings
    assert "conn-sec-title" in settings
    assert "item.circle" in settings
    assert "Özel bağlantı" in settings
    assert "connMark(ad)" not in settings
    assert "connMark(c.id)" in settings
    assert "connMarkId(server.name" in settings

