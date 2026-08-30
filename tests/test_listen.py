"""Sesli komut ve uyandırma sözü.

Model indirmesi gerektirdiği için tanımanın kendisi burada test edilmiyor;
test edilen şey **sözün nasıl anlaşıldığı**. "neon" diye bir kelime geçince
uyanan bir asistan kullanılamaz, sözü komutun içinde bırakan bir asistan da
"neo" diye bir şey aramaya başlıyor.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from neocp import listen
from neocp.config import Config


# -- uyandırma sözü ----------------------------------------------------


def test_the_wake_word_is_heard() -> None:
    assert listen.heard_wake("neo borsayı aç")


def test_case_and_punctuation_do_not_matter() -> None:
    """Tanıyıcı "Neo," ya da "neo." yazabiliyor."""
    assert listen.heard_wake("Neo, borsayı aç")
    assert listen.heard_wake("NEO! uyan")


def test_a_much_longer_word_does_not_wake_it() -> None:
    """Sözle başlayan her kelime uyandırmamalı."""
    assert not listen.heard_wake("neoklasik mimari")
    assert not listen.heard_wake("neolitik dönem")


def test_the_recogniser_splitting_the_word_still_wakes_it() -> None:
    """Asıl sorun buydu: "neo" Türkçede bir kelime değil ve tanıyıcı onu
    gerçek bir kelimeye çeviriyor. "Neo, dışarısı sıcak mı" cümlesi
    "Ne oldu dışarısı sıcak mı" diye çıkıyor ve söz hiç duyulmuyordu."""
    assert listen.heard_wake("Ne oldu dışarısı sıcak mı?")
    assert listen.heard_wake("ne o borsayı aç")
    assert listen.after_wake("Ne oldu dışarısı sıcak mı?") == "dışarısı sıcak mı?"
    assert listen.after_wake("ne o borsayı aç") == "borsayı aç"


def test_an_unrelated_sentence_does_not_wake_it() -> None:
    assert not listen.heard_wake("bugün hava çok güzel")


def test_an_empty_wake_word_never_matches() -> None:
    """Boş söz "her şey uyandırır" demek olmamalı; ayarda boş bırakmak
    uyandırmayı kapatmak demek."""
    assert not listen.heard_wake("neo uyan", wake="")
    assert not listen.heard_wake("herhangi bir şey", wake="   ")


def test_a_custom_wake_word_works() -> None:
    assert listen.heard_wake("jarvis raporu getir", wake="jarvis")
    assert not listen.heard_wake("neo raporu getir", wake="jarvis")


# -- sözden sonrası ----------------------------------------------------


def test_the_word_itself_is_stripped() -> None:
    """Sözü komuta bırakmak modelin "neo" diye bir şey aramasına yol
    açıyor."""
    assert listen.after_wake("neo borsayı aç") == "borsayı aç"


def test_punctuation_around_the_word_is_handled() -> None:
    assert listen.after_wake("Neo, borsayı aç") == "borsayı aç"


def test_words_before_the_wake_word_are_dropped_too() -> None:
    """Tanıyıcı öncesinde gürültü uydurabiliyor."""
    assert listen.after_wake("şey ııı neo raporu getir") == "raporu getir"


def test_a_sentence_without_the_word_comes_back_whole() -> None:
    assert listen.after_wake("borsayı aç") == "borsayı aç"


def test_only_the_wake_word_leaves_nothing() -> None:
    """Yalnızca "neo" denmişse gönderilecek bir komut yok."""
    assert listen.after_wake("neo") == ""


# -- ayarlar -----------------------------------------------------------


def test_the_microphone_is_off_until_asked_for(tmp_path: Path) -> None:
    """Mikrofonu kendiliğinden açan bir program kabul edilemez."""
    assert not Config.load(tmp_path).listen.enabled


def test_settings_survive_a_restart(tmp_path: Path) -> None:
    from neocp import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    settings.apply(config, {"listen": {"enabled": True, "wake": "jarvis", "size": "tiny"}})

    reloaded = Config.load(tmp_path).listen
    assert reloaded.enabled and reloaded.wake == "jarvis" and reloaded.size == "tiny"


def test_the_settings_page_knows_whether_the_package_is_installed(tmp_path: Path) -> None:
    from neocp import settings

    config = Config.load(tmp_path)
    config.ensure_dirs()
    shown = settings.snapshot(config)["listen"]

    assert shown["available"] == listen.available()
    assert shown["sizes"] == list(listen.SIZES)


def test_an_unknown_size_falls_back(tmp_path: Path) -> None:
    """Elle düzenlenmiş bir dosyadaki saçma boyut programı düşürmemeli."""
    ear = listen.Listener(listen.ListenConfig(size="devasa"))
    if not listen.available():
        pytest.skip("tanıma paketi kurulu değil")

    # Yüklemeyi gerçekten yapmak modeli indirir; yalnızca seçimi doğruluyoruz.
    assert ear.config.size not in listen.SIZES
    assert not ear.ready


# -- sürekli dinleyen kulak --------------------------------------------


def test_the_ear_needs_the_audio_package() -> None:
    """Paket yoksa sessizce vazgeçiliyor; program çalışmaya devam etmeli."""
    from neocp import ear

    silent = ear.Ear(listener=None, heard=lambda _h: None)
    if not ear.available():
        assert not silent.start()


def test_only_speech_crosses_the_threshold() -> None:
    """Sessiz bir odada saatlerce hiçbir şey olmamalı: tanıyıcı uyanmıyor,
    metin üretilmiyor, modele bir şey gitmiyor."""
    import numpy as np

    from neocp import ear

    quiet = np.random.normal(0, 0.001, 1600).astype("float32")
    speech = np.random.normal(0, 0.05, 1600).astype("float32")

    assert float(np.sqrt(np.mean(quiet * quiet))) < ear.SPEECH
    assert float(np.sqrt(np.mean(speech * speech))) > ear.SPEECH


def test_a_transcript_without_the_wake_word_is_dropped() -> None:
    """Söz geçmeyen hiçbir şey kaydedilmiyor, gösterilmiyor, modele
    gitmiyor. Sürekli açık bir mikrofonda bu şart."""
    import numpy as np

    from neocp import ear

    class Deaf:
        def transcribe_array(self, samples, rate):
            return "bugün hava çok güzel"

    caught: list = []
    silent = ear.Ear(Deaf(), caught.append, wake="neo")
    silent._settle(np.zeros(1600, dtype="float32"))

    assert caught == []


def test_the_wake_word_is_passed_on_without_itself() -> None:
    import numpy as np

    from neocp import ear

    class Hears:
        def transcribe_array(self, samples, rate):
            return "Ne oldu dışarısı sıcak mı?"

    caught: list = []
    listening = ear.Ear(Hears(), caught.append, wake="neo")
    listening._settle(np.zeros(1600, dtype="float32"))

    assert len(caught) == 1
    assert caught[0].wake
    assert caught[0].command == "dışarısı sıcak mı?"


def test_a_failing_recogniser_does_not_kill_the_ear() -> None:
    import numpy as np

    from neocp import ear

    class Boom:
        def transcribe_array(self, samples, rate):
            raise RuntimeError("model düştü")

    caught: list = []
    listening = ear.Ear(Boom(), caught.append)
    listening._settle(np.zeros(1600, dtype="float32"))   # patlamamalı

    assert caught == []


# -- gecikme -----------------------------------------------------------
#
# "Çok geç duyuyor, anlık konuşamıyorum" şikâyetinin iki sebebi vardı ve
# ikisi de burada tutuluyor.


def test_recognition_does_not_block_the_microphone() -> None:
    """Tanıma yakalama thread'inde yapılamaz.

    Ölçüm: `small` modeli işlemcide iki saniyelik bir sözü 1,58 saniyede
    çözüyor. Aynı thread'de yapılınca o süre boyunca mikrofondan hiç
    okuma yapılmıyor, aygıtın tamponu doluyor ve konuşmanın devamı
    düşüyor — bir cümle duyuluyor, hemen ardından söylenen duyulmuyordu.
    """
    import time

    from neocp import ear

    class Slow:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            time.sleep(0.4)
            return "neo dur"

    listening = ear.Ear(Slow(), lambda _h: None, wake="neo")
    listening.start()

    try:
        began = time.monotonic()
        listening._hand_over([0.0])
        # Devretme anlık olmalı: yakalama thread'i burada beklerse ses düşer.
        assert time.monotonic() - began < 0.05
    finally:
        listening.stop()


def test_a_backlog_drops_the_oldest_not_the_newest() -> None:
    """Tanıyıcı yetişemiyorsa biriken kuyruk ajanı dakikalarca geride
    bırakıyor. Geç kalmış bir cümleyi çözmek, o an söyleneni kaçırmaya
    değmez."""
    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)

    for index in range(ear.BACKLOG + 2):
        listening._hand_over(index)

    assert listening.backlog == ear.BACKLOG
    assert listening.dropped == 2
    # Kalanlar en yenileri. Kuyruk (audio, deaf, echo, captured).
    item = listening._work.get_nowait()
    assert item[0] == 2 and item[1] is False and item[2] is False
    assert isinstance(item[3], float)


def test_the_recogniser_runs_on_the_graphics_card_when_it_can() -> None:
    """İşlemcide çalışan bir tanıyıcı "geç duyuyor" şikâyetinin sebebi.

    Ölçüm (gerçek Türkçe cümle, bu makine): `small` işlemcide 1,58 sn,
    ekran kartında 0,18 sn. Kart yoksa sessizce işlemciye düşülüyor —
    yavaş çalışmak, hiç çalışmamaktan iyi.
    """
    import inspect

    source = inspect.getsource(listen.Listener._open)
    assert 'device="cuda"' in source
    assert 'device="cpu"' in source


def test_the_cuda_libraries_are_put_on_the_dll_path() -> None:
    """pip ile kurulan `nvidia-*` paketleri DLL'leri site-packages içine
    koyuyor; oradan kendiliğinden bulunmuyorlar. İkisi birden gerekiyor:
    `add_dll_directory` yalnızca arama bayrağı kullanan yüklemelerde işe
    yarıyor, ctranslate2 düz `LoadLibrary` çağırıyor.

    Whisper ve kamera analizi aynı DLL yolunu kullanıyor (`gpu.cuda_libs_on_path`).
    """
    import inspect

    from neocp import gpu

    source = inspect.getsource(gpu.cuda_libs_on_path)
    assert "add_dll_directory" in source
    assert 'os.environ["PATH"]' in source
    assert "cuda_libs_on_path" in inspect.getsource(listen._cuda_ready)


def test_the_wake_word_can_come_last() -> None:
    """"nasılsın neo?" — söz sonda.

    Önceki hal yalnızca sözden sonrasını alıyordu ve geriye hiçbir şey
    kalmıyordu: ekranda "duydum: nasılsın neo?" yazıyor, ajan hiç cevap
    vermiyordu.
    """
    assert listen.after_wake("nasılsın neo?") == "nasılsın?"
    assert listen.after_wake("kamerada ne görüyorsun neo") == "kamerada ne görüyorsun"


def test_a_question_stays_a_question() -> None:
    """Sözün ardındaki işaret cümlenin: sözle birlikte atılırsa soru
    cümlesi düz cümleye dönüyor ve sesletilirken tonlama da bozuluyor."""
    assert listen.after_wake("nasılsın neo?").endswith("?")
    assert listen.after_wake("bugün nasıl gidiyor neo!").endswith("!")


def test_only_the_name_leaves_nothing() -> None:
    """Yalnızca ad çağrıldıysa komut yok. Orada susmak duymamakla aynı
    şey — masaüstü tarafı bunu kısa bir karşılıkla cevaplıyor."""
    assert listen.after_wake("neo") == ""
    assert listen.after_wake("Neo!") == ""


def test_being_called_by_name_still_gets_an_answer() -> None:
    """Ekranda "duydum" yazıp hiçbir şey olmaması şikâyet edilen şeydi:
    yalnızca ad çağrılınca (komut boş) yine de bir karşılık geliyor."""
    import inspect

    from neocp import desktop

    source = inspect.getsource(desktop._open_ear)
    assert "CALLED_ASK" in source


def test_settings_reload_starts_the_python_ear() -> None:
    """Ayar kaydı kulağı açmazsa kullanıcı ne derse desin yalnız bas-konuş
    duyuluyor — tarayıcı PTT, Python kulağı ayrı."""
    import inspect

    from neocp import desktop

    reload_src = inspect.getsource(desktop.Bridge.reload)
    sync = inspect.getsource(desktop.Bridge.sync_hearing)
    boot = inspect.getsource(desktop._boot)
    wanted = inspect.getsource(desktop._hearing_wanted)
    power = inspect.getsource(desktop.Bridge.hearing_power)
    assert "self.sync_hearing(config)" in reload_src
    assert "_open_ear" in sync
    assert "listen.open" in sync
    assert "sync_hearing" in boot
    assert "ear=bridge.ear" in boot
    assert "listen.open" in wanted
    assert "wake.strip()" in wanted
    assert '"open": bool(on)' in power


def test_speaking_again_queues_instead_of_cancelling() -> None:
    """Kural (kullanıcı): süren turda yeni söz İPTAL değil, sıraya girer —
    yalnızca açık bir durdurma sözü ("dur/yeter/kes") süreni durdurur."""
    import inspect

    from neocp import desktop

    source = inspect.getsource(desktop._open_ear)
    # Yeni söz kuyruğa giriyor (submit), koşulsuz interrupt YOK.
    assert "bridge.submit(" in source
    # İptal yalnızca açık durdurma sözünde: interrupt bir _is_stop dalında.
    assert "_is_stop(" in source
    assert not re.search(r"if bridge\.busy:\s*\n\s*bridge\.interrupt\(\)\s*\n\s*bridge\.submit",
                         source), "koşulsuz araya-girme geri gelmiş olmamalı"


# -- sağırlık ve sohbet penceresi --------------------------------------


def test_deafness_always_expires_on_its_own() -> None:
    """Sağırlık `float("inf")` idi ve "konuşmam bitti" haberinin
    tarayıcıdan gelmesine bel bağlıyordu.

    O haber gelmezse — sekme yenilenirse, ses bağlamı askıda kalıp
    `onended` hiç tetiklenmezse — kulak sonsuza kadar kapalı kalıyordu.
    Seviye çubuğu hâlâ oynuyor (o ölçüm sağırlıktan önce yapılıyor), yani
    dışarıdan "sinyali görüyorum ama hiçbir şey olmuyor" gibi görünüyordu.
    """
    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.speaking(True)

    assert listening.deaf
    assert listening._deaf_until < float("inf")
    assert listening._deaf_until - time.monotonic() <= ear.DEAF_MAX_S + 1


def test_the_wake_word_is_only_needed_to_start() -> None:
    """Bir kez konuşmaya başlandıktan sonra her cümlede adını söylemek
    gerekmiyor: karşındaki insana da her cümlede adıyla başlamıyorsun."""
    from neocp import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "kamerada ne var"

    listening = ear.Ear(Hears(), caught.append, wake="neo")

    # Sohbet kapalı: söz yok, hiçbir şey geçmiyor.
    listening._settle([0.0])
    assert not caught

    # Ajan karşılık verdi: sohbet açıldı.
    listening.engage()
    listening._settle([0.0])

    assert len(caught) == 1
    assert caught[0].wake is False
    assert caught[0].command == "kamerada ne var"


def test_the_window_closes_again() -> None:
    """Süre dolduğunda söz yine gerekiyor — yoksa odadaki her konuşma
    modele gitmeye başlar."""
    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.engage(0.0)
    assert not listening.engaged

    listening.engage()
    assert listening.engaged
    listening.disengage()
    assert not listening.engaged


def test_the_turn_reopens_the_window() -> None:
    """Karşılık verildiğinde pencere açılmazsa kullanıcı her cümlede
    "neo" demek zorunda kalıyor."""
    import inspect

    from neocp import desktop

    # Mesaj işleme pump'tan _isle'ye taşındı (ilk-kurulum kapısı için);
    # kulağı açan çağrı artık orada.
    source = inspect.getsource(desktop.Bridge._isle)
    assert "self.ear.engage()" in source


def test_free_listening_needs_no_wake_word() -> None:
    """Evde tek başına çalışan biri için "hava nasıl?" derken başka kime
    soruyor olabilir ki. Uyandırma sözü beklemek asistan değil telsiz."""
    from neocp import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "hava nasıl"

    free = ear.Ear(Hears(), caught.append, wake="neo", open=True)
    free._settle([0.0])

    assert len(caught) == 1
    assert caught[0].command == "hava nasıl"
    assert caught[0].wake is False


def test_free_listening_is_off_until_asked_for(tmp_path: Path) -> None:
    """Odada televizyon varsa duyulan her şey modele gider."""
    assert not Config.load(tmp_path).listen.open


def test_the_conversation_window_outlasts_a_pause() -> None:
    """Kırk beş saniye kısaydı: konuşmanın ortasında düşünmek, bakmak,
    bir şey yazmak için verilen aralar onu rahatça geçiyor ve pencere tam
    da konuşmanın ortasında kapanıyordu."""
    from neocp import ear

    assert ear.ENGAGED_S >= 120


# -- gülme ve mırıltı ---------------------------------------------------


def test_laughter_is_not_a_message() -> None:
    """Serbest dinlemede kullanıcı güldüğünde ajan her kahkahaya cevap
    yetiştiriyordu — ona bir şey söylenmemişken. Gülmek konuşma değil."""
    for sound in ("ahahahah", "ıhıhıh.", "hahaha", "he he he", "hmm", "hı hı"):
        assert listen.chatter(sound), sound


def test_real_speech_is_not_mistaken_for_laughter() -> None:
    """Süzgecin dar olması önemli: tek bir gerçek kelime yetiyor.
    "harika" ve "hava" h taşıyor ama gülme değil."""
    for said in ("hava nasıl", "harika oldu", "ahah tamam devam et", "depoya bak"):
        assert not listen.chatter(said), said


def test_a_cough_is_not_a_message() -> None:
    """Öksürük Whisper'da 'öööö' oluyor ve sohbete hayali söz düşüyordu."""
    groaning = "ö" * 80
    assert listen.chatter(groaning)
    assert listen.chatter("eeeeee")
    assert not listen.chatter("öğretmen geldi")


def test_a_prompt_leak_is_not_a_message() -> None:
    """Anlamayınca sözlükten 'modbus.com' uyduruyordu — o bir komut değil."""
    vocab = "Modbus, SCADA, PLC, register"
    assert listen.hallucinated("modbus.com", vocab)
    assert listen.hallucinated("Modbus", vocab)
    assert listen.hallucinated("Altyazı M.K.")
    assert not listen.hallucinated("Modbus cihazını oku", vocab)
    assert not listen.hallucinated("hava nasıl", vocab)


def test_a_cough_never_reaches_the_agent() -> None:
    from neocp import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "ö" * 80

    listening = ear.Ear(Hears(), caught.append, wake="neo", open=True)
    listening._settle([0.0])
    assert not caught


def test_a_hallucinated_url_never_reaches_the_agent() -> None:
    from neocp import ear
    from types import SimpleNamespace

    caught: list[ear.Heard] = []

    class Hears:
        config = SimpleNamespace(vocab="Modbus, SCADA, PLC")

        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "modbus.com"

    listening = ear.Ear(Hears(), caught.append, wake="neo", open=True)
    listening._settle([0.0])
    assert not caught


def test_laughter_never_reaches_the_agent() -> None:
    from neocp import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "ahahahah"

    listening = ear.Ear(Hears(), caught.append, wake="neo", open=True)
    listening._settle([0.0])

    assert not caught


def test_laughter_does_not_keep_the_window_open() -> None:
    """Gülmek sohbeti açık tutmaz: pencere yalnızca gerçek konuşmayla
    tazeleniyor, yoksa kahkahalar arasında süre hiç dolmuyor."""
    from neocp import ear

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "hahaha"

    listening = ear.Ear(Hears(), lambda _h: None, wake="neo")
    listening.engage(0.0)
    listening._settle([0.0])

    assert not listening.engaged


def test_calling_it_while_laughing_still_works() -> None:
    """"neo hahaha" bilinçli bir sesleniş: adı geçiyorsa geçiyor."""
    from neocp import ear

    caught: list[ear.Heard] = []

    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return "neo hahaha"

    listening = ear.Ear(Hears(), caught.append, wake="neo")
    listening._settle([0.0])

    assert len(caught) == 1 and caught[0].wake


# -- mikrofon arızası ---------------------------------------------------


def test_a_dead_stream_is_not_reported_as_listening() -> None:
    """Akış açılamadığında thread sessizce ölüyordu ve organ "dinliyor"
    demeye devam ediyordu: kullanıcı "uyan neo" diyor, hiçbir şey olmuyor
    ve sebebi hiçbir yerde yazmıyordu."""
    from neocp import ear, organs
    from neocp.config import Config

    class Broken:
        deaf = False
        live = False
        failure = "PortAudioError: aygıt başka bir programda"

    mic = next(
        o for o in organs.inventory(Config.load(Path(".")), ear=Broken())
        if o["id"] == "mic"
    )
    assert mic["state"] == "arıza"
    assert "PortAudioError" in mic["detail"]
    assert not mic["live"]


def test_the_failure_reason_is_recorded_not_swallowed() -> None:
    """`except Exception: return` teşhis edilemez bir arıza bırakıyordu."""
    import inspect

    from neocp import ear

    source = inspect.getsource(ear.Ear._loop)
    assert "self.failure" in source
    assert "self.live" in source


# -- susturma ve pencere tavanı ----------------------------------------
#
# Gerçek kayıt: kullanıcı oyun oynarken takım arkadaşlarına söylediği her
# söz modele aktı, ajan her birine cevap yetiştirdi; "beni dinleme"
# dediğinde de "kapalıyım" deyip dinlemeye devam etti.


def _hears(text="merhaba"):
    class Hears:
        def transcribe_array(self, audio, rate):  # noqa: ANN001, ANN202
            return text

    return Hears()


def test_snooze_actually_silences() -> None:
    """"Kapalıyım" demek ancak gerçekten kapalı olmakla doğru olur."""
    from neocp import ear

    caught = []
    listening = ear.Ear(_hears(), caught.append, wake="neo", open=True)
    listening.snooze()

    listening._settle([0.0])
    assert not caught
    assert not listening.engaged     # serbest dinleme bile geçmiyor


def test_the_wake_word_pierces_the_snooze() -> None:
    """Tam kapanmak geri çağrılamamak demek olurdu: "neo" her zaman açar."""
    from neocp import ear

    caught = []
    listening = ear.Ear(_hears("neo geldim"), caught.append, wake="neo")
    listening.snooze()
    listening._settle([0.0])

    assert len(caught) == 1
    assert not listening.snoozed     # sesleniş susturmayı kaldırdı


def test_a_timed_snooze_expires() -> None:
    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.snooze(0.0001)
    import time as clock

    # Windows'ta time.monotonic() çözünürlüğü ~15 ms; 10 ms uyku bazen saati
    # hiç ilerletmiyor ve minik susturma "geçmemiş" görünüyordu (flaky). 50 ms
    # granülariteyi güvenle aşıyor.
    clock.sleep(0.05)
    assert not listening.snoozed


def test_engage_cannot_reopen_a_snoozed_ear() -> None:
    """Tur sonu tazelemesi susturmayı delerse "kapalıyım" yine yalan olur."""
    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening.snooze()
    listening.engage()

    assert not listening.engaged


def test_the_window_cannot_be_kept_open_forever() -> None:
    """Pencere kendi kendini besliyordu: her söz ve her cevap süreyi ileri
    itiyor, oda konuşması modele sonsuza kadar akıyordu — kayıtta yarım
    saat sürdü. Tavan son uyandırmadan ENGAGED_MAX_S sonra."""
    import time as clock

    from neocp import ear

    listening = ear.Ear(listener=None, heard=lambda _h: None)
    listening._wake_at = clock.monotonic() - ear.ENGAGED_MAX_S  # tavan geçildi
    listening.engage()

    assert not listening.engaged


def test_senses_tool_pauses_hearing_and_sight_together() -> None:
    """"Beni dinleme ve izleme" tek bir niyet: iki aracı ayrı ayrı
    çağırtmak, birinin unutulması demek. Gerçek kayıtta tam bu oldu —
    kulak sustu, ajan "izlemiyorum" dedi ama kamera kare almaya devam
    etti."""
    import asyncio

    from neocp import ear
    from neocp.tools import build_registry

    registry = build_registry(subagents=False)
    listening = ear.Ear(listener=None, heard=lambda _h: None, open=True)

    class Sight:
        snoozed = False

        def snooze(self, seconds=0.0):  # noqa: ANN001, ANN202
            self.snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    seeing = Sight()

    class Ctx:
        ear = listening
        lens = seeing
        watcher = None

    result = asyncio.run(registry.get("senses").handler({"action": "pause"}, Ctx()))
    assert listening.snoozed and seeing.snoozed
    assert "kulak" in result.content and "göz" in result.content

    asyncio.run(registry.get("senses").handler({"action": "resume"}, Ctx()))
    assert not listening.snoozed and not seeing.snoozed


def test_senses_sight_uses_camera_power_when_present() -> None:
    """HUD ile aynı kapı: sohbet 'kamerayı kapat' deyince aygıt bırakılır."""
    import asyncio

    from neocp.tools import build_registry

    registry = build_registry(subagents=False)
    called: list[bool] = []

    class Ctx:
        ear = None
        lens = None
        watcher = None

        @staticmethod
        def camera_power(on: bool) -> str:
            called.append(on)
            return "Kamera kapalı." if not on else "Kamera açık."

    result = asyncio.run(registry.get("senses").handler(
        {"action": "pause", "what": "sight"}, Ctx()))
    assert called == [False]
    assert "Kamera kapalı" in result.content
    asyncio.run(registry.get("senses").handler(
        {"action": "resume", "what": "sight"}, Ctx()))
    assert called == [False, True]


def test_the_wake_word_reopens_every_sense() -> None:
    """"Ben gelince seslenirim" tek bir sesleniş demek: "neo" duyunca
    göz de geri açılmalı, kullanıcı duyu duyu saymamalı."""
    from neocp import ear

    class Sight:
        snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    seeing = Sight()
    listening = ear.Ear(_hears("neo geldim"), lambda _h: None, wake="neo")
    listening.companions = [seeing]
    listening.snooze()
    listening._settle([0.0])

    assert not listening.snoozed
    assert not seeing.snoozed


def test_ear_gate_toggles_without_asking_the_agent() -> None:
    """Kompozer mikrofonu ajan aracını beklemeden kulağı kesebilmeli."""
    from neocp.web.server import ear_gate

    class Fake:
        snoozed = False

        def snooze(self, seconds=0.0):  # noqa: ANN001, ANN202
            self.snoozed = True

        def unsnooze(self):  # noqa: ANN202
            self.snoozed = False

    assert ear_gate(None, "toggle") == {"ok": True, "ear": False, "snoozed": False}
    ear = Fake()
    assert ear_gate(ear, "toggle")["snoozed"] is True
    assert ear.snoozed
    assert ear_gate(ear, "toggle")["snoozed"] is False
    assert not ear.snoozed
    ear_gate(ear, "pause")
    assert ear.snoozed
    ear_gate(ear, "resume")
    assert not ear.snoozed


def test_snooze_notifies_the_ui() -> None:
    """Düğme ve ajan aracı aynı kapı: arayüz susturulmayı görmeli."""
    from neocp import ear as hearing

    seen: list[bool] = []
    listening = hearing.Ear(listener=None, heard=lambda _h: None)
    listening.on_snooze = seen.append
    listening.snooze()
    listening.unsnooze()
    assert seen == [True, False]

def test_slow_cpu_downshifts_the_model_after_two_hits() -> None:
    """Canli sikayet (30.08): zayif laptopta surekli dinleme 10-20 sn
    geride. Cozum suresi sesi ust uste iki kez belirgin asarsa boyut
    bir kademe iner (small->base) — yalniz oturum icin, ayar dosyasina
    yazilmaz. Tek yavas cozum (isinma) dusurmez; GPU hic dusurmez."""
    from neocp.listen import Listener, ListenConfig
    l = Listener(ListenConfig(size='small'))
    l.device = 'cpu'
    l._loaded_size = 'small'
    # 2 sn ses, 8 sn cozum: bir kez -> daha inmez
    assert l._hiz_karari(2.0, 8.0) is None
    # ikinci kez -> base'e in
    assert l._hiz_karari(2.0, 9.0) == 'base'
    # hizli cozum sayaci sifirlar
    l._slow_hits = 1
    assert l._hiz_karari(2.0, 1.0) is None
    assert l._slow_hits == 0
    # GPU'da asla
    l.device = 'cuda'
    assert l._hiz_karari(2.0, 30.0) is None
    # base'in alti yok (tiny bilincli disarida)
    l.device = 'cpu'
    l._loaded_size = 'base'
    l._slow_hits = 1
    assert l._hiz_karari(2.0, 9.0) is None


def test_downshift_is_session_only_and_reloads_smaller() -> None:
    from neocp.listen import Listener, ListenConfig
    cfg = ListenConfig(size='small')
    l = Listener(cfg)
    l.device = 'cpu'
    l._loaded_size = 'small'
    l._model = object()
    l._slow_hits = 1
    l._belki_dusur(2.0, 9.0)
    assert l._force_size == 'base'
    assert l._model is None            # sonraki cozum kucugu yukler
    assert cfg.size == 'small'         # kullanicinin ayari degismedi

