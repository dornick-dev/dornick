"""Arayüz varlıkları üzerinde yapısal kontroller.

Tarayıcı olmadan çalışan ucuz testler. Buradaki her kontrol, gerçekten
yaşanmış ve sessizce geçmiş bir hataya karşılık geliyor: kırık CSS değeri
görünmez bir bozulma, gizlenmeyen bir katman ise tüm arayüzü kilitliyor.
"""

from __future__ import annotations

import re
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
                     "chrome.js", "listen.js", "camera.js", "drop.js")
    )
    used = set(re.findall(r'\$\("([\w-]+)"\)', scripts))
    used |= set(re.findall(r'getElementById\("([\w-]+)"\)', scripts))

    assert used, "betikte hiç kimlik kullanımı bulunamadı — desen bayatlamış olabilir"
    missing = sorted(i for i in used if f'id="{i}"' not in HTML)
    assert not missing, f"işaretlemede yok: {', '.join(missing)}"


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
           "chrome.js", "speech.js", "listen.js", "camera.js", "drop.js")


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
    cercevede gecerli, sayfanin kendisinde degil."""
    for name in SCRIPTS:
        if name == "viewer.js":
            continue
        assert "srcdoc" not in (STATIC / name).read_text(encoding="utf-8"), name
    assert VIEWER_JS.count("srcdoc") == 1


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


def test_everything_that_floats_shares_one_column() -> None:
    """Sohbet, yazma satırı, önizleme ve ekler aynı sütunda.

    Ayrı ayrı konumlandırıldıklarında biri diğerinin üstüne biniyordu:
    kamera önizlemesi cevabın üzerine oturmuştu ve "hiçbir şey olmuyor"
    gibi görünüyordu.
    """
    for selector in (".stream", ".entry", ".lens", ".drops", ".shot"):
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
    assert re.search(r"shaped\(url\)\.catch\(\(\) => plain\(url\)\)", SPEECH_JS)


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


def test_the_thinking_line_shows_it_is_still_going() -> None:
    """Sabit bir "düşünüyor" satırı uzun bir turda donmuş gibi duruyor.

    İki katman var: geçen süre (since) ilerliyor ve düşünme kelimesi (mull)
    birkaç saniyede bir dönüyor — "Düşünüyor", "Tartıyor"… Kelime modelden
    gelmiyor, sabit listeden seçiliyor; sıfır maliyetli canlılık.
    """
    assert "function since(started)" in APP_JS
    assert re.search(r"mull\(\) \+ since\(", APP_JS)
    # Kelime listesi "Düşünüyor" ile başlıyor: tur başında tanıdık olan
    # görünsün, oyun sonra gelsin.
    assert re.search(r'const MULL = \["Düşünüyor"', APP_JS)
    assert re.search(r'"\d+ adım"|steps \+ " adım"', APP_JS)


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


def test_intermediate_narration_folds_into_the_strip_regardless_of_length() -> None:
    """Çok konuşan yerel modeller her adımda paragraflarca "düşünce" yazınca
    uzunluk-tabanlı kural (140+ ise cevap say) sohbeti sayfalarca "NEO"
    bloğuna boğuyordu — kullanıcı ne yukarıyı ne aşağıyı takip edebiliyordu.

    Yeni kural konuma göre: araçtan ÖNCE gelen metin — uzun olsa bile — ara
    adımdır ve katlanan şeridin İÇİNE girer. foldNarration artık uzunluğa
    bakmaz.
    """
    body = re.search(r"function foldNarration\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert body, "foldNarration() bulunamadı — desen bayatlamış olabilir"

    inner = body.group(1)
    # Uzunluk eşiği kalktı: her ara-anlatım şeride katlanıyor.
    assert "NARRATION" not in inner
    assert "work.body.append(note)" in inner
    # Katlanan son anlatım güvenlik ağı için tutuluyor.
    assert "lastNarr = text" in inner


def test_a_tool_ended_turn_still_shows_an_answer() -> None:
    """Her ara-anlatım katlandığından, tur bir araçla biterse (model son
    sözünü söyleyip ardından mind_memory çağırırsa) ekranda hiç cevap
    kalmayabilir. Güvenlik ağı: sealLine son anlatımı cevaba yükseltir.
    """
    seal = re.search(r"function sealLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert seal, "sealLine() bulunamadı"
    inner = seal.group(1)
    assert "!answerKept && lastNarr" in inner
    # Tam boy cevap kaldıysa güvenlik ağı devreye girmemeli.
    fin = re.search(r"function finishAgentLine\(\) \{(.*?)\n\}", APP_JS, re.S)
    assert fin and "answerKept = true" in fin.group(1)


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
