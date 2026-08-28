"""Sağlayıcı çevirisi ve OpenAI-uyumlu backend testleri.

Biçim hataları bu katmanın en sinsi hata sınıfı: sunucu 400 döndürür ama
sebebi mesaj dizisinin ortasında bir yerdedir. Çeviri saf fonksiyonlar
olduğu için hepsi ağ olmadan doğrulanabiliyor.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from neocp.backends import build_client
from neocp.backends.openai_backend import OpenAIBackend
from neocp.backends.translate import (
    map_finish_reason,
    parse_arguments,
    to_anthropic_blocks,
    to_openai_messages,
    to_openai_tools,
)
from neocp.config import ModelConfig
from neocp.context import Prepared

SYSTEM = [{"type": "text", "text": "çekirdek"}, {"type": "text", "text": "ruh"}]


# -- giden çeviri ------------------------------------------------------


def test_system_blocks_collapse_into_one_message() -> None:
    out = to_openai_messages(SYSTEM, [])
    assert out == [{"role": "system", "content": "çekirdek\n\nruh"}]


def test_tool_use_becomes_tool_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "bakıyorum"},
                {"type": "tool_use", "id": "t1", "name": "shell", "input": {"command": "ls"}},
            ],
        }
    ]
    assistant = to_openai_messages([], messages)[0]

    assert assistant["content"] == "bakıyorum"
    call = assistant["tool_calls"][0]
    assert call["id"] == "t1"
    assert call["function"]["name"] == "shell"
    assert json.loads(call["function"]["arguments"]) == {"command": "ls"}


def test_tool_results_precede_user_text() -> None:
    """OpenAI sıralaması katı: tool mesajları asistanın tool_calls'ını
    doğrudan izlemeli. Araya user mesajı girerse sunucu reddeder."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "bir de şuna bak"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "çıktı"},
            ],
        }
    ]
    out = to_openai_messages([], messages)

    assert [m["role"] for m in out] == ["tool", "user"]
    assert out[0]["tool_call_id"] == "t1"


def test_error_results_are_marked_for_the_model() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "yok", "is_error": True}
            ],
        }
    ]
    assert to_openai_messages([], messages)[0]["content"].startswith("HATA:")


def test_thinking_blocks_are_dropped() -> None:
    """Yerel modeller thinking bloğunu anlamaz; göndermek hataya yol açar."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "gizli akıl yürütme", "signature": "x"},
                {"type": "text", "text": "cevap"},
            ],
        }
    ]
    assistant = to_openai_messages([], messages)[0]
    assert assistant["content"] == "cevap"
    assert "gizli" not in json.dumps(assistant, ensure_ascii=False)


def test_images_become_data_urls() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "bu ne"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "AAA"},
                },
            ],
        }
    ]
    parts = to_openai_messages([], messages)[0]["content"]
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,AAA"


def test_lone_text_is_sent_as_a_plain_string() -> None:
    """Bazı uyumlu sunucular dizi biçimini yalnızca görüntü varken kabul ediyor."""
    messages = [{"role": "user", "content": [{"type": "text", "text": "selam"}]}]
    assert to_openai_messages([], messages)[0]["content"] == "selam"


def test_image_inside_tool_result_degrades_to_a_note() -> None:
    """role=tool içeriği dize olmak zorunda; görüntü sessizce kaybolmamalı."""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": [
                        {"type": "text", "text": "ekran alındı"},
                        {"type": "image", "source": {"type": "base64", "data": "AAA"}},
                    ],
                }
            ],
        }
    ]
    content = to_openai_messages([], messages)[0]["content"]
    assert "ekran alındı" in content
    assert "görüntü" in content


def test_tool_schema_shape() -> None:
    tools = to_openai_tools(
        [{"name": "shell", "description": "d", "input_schema": {"type": "object"}}]
    )
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["parameters"] == {"type": "object"}


# -- dönen çeviri ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),          # markdown çiti
        ('Tabii! {"a": 1}', {"a": 1}),                  # önüne sohbet eklemiş
        ("", {}),
        ("tamamen bozuk", {}),
        ('["liste"]', {}),                              # sözlük değil
    ],
)
def test_parse_arguments_repairs_common_local_model_mistakes(raw: str, expected: dict) -> None:
    assert parse_arguments(raw) == expected


def test_missing_call_id_is_synthesized() -> None:
    """tool_result eşleşmesi id'ye dayanıyor; eksikse üretmek zorundayız."""
    blocks = to_anthropic_blocks("", [{"name": "shell", "arguments": "{}"}])
    assert blocks[0]["id"]


@pytest.mark.parametrize(
    ("finish", "expected"),
    [("stop", "end_turn"), ("tool_calls", "tool_use"), ("length", "max_tokens"), (None, "end_turn")],
)
def test_finish_reason_mapping(finish: str | None, expected: str) -> None:
    assert map_finish_reason(finish) == expected


# -- backend ----------------------------------------------------------


def chunk(
    content=None, tool_calls=None, finish=None, usage=None, reasoning=None, extra=None
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning,
        model_extra=extra or {},
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish)], usage=usage
    )


def fragment(index: int, *, id=None, name=None, arguments=None) -> SimpleNamespace:
    return SimpleNamespace(
        index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments)
    )


class FakeStream:
    """Kapatılıp kapatılmadığını kaydeden akış."""

    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.chunks = chunks
        self.closed = False

    def __aiter__(self):
        async def gen():
            for c in self.chunks:
                yield c

        return gen()

    async def close(self) -> None:
        self.closed = True


class FakeOpenAI:
    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.seen: dict = {}
        self.stream = FakeStream(chunks)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.seen = kwargs
        return self.stream

    async def close(self) -> None:
        pass


def backend(chunks: list[SimpleNamespace], **overrides) -> tuple[OpenAIBackend, FakeOpenAI]:
    fake = FakeOpenAI(chunks)
    model = ModelConfig(
        name="local-model", provider="openai", base_url="http://localhost:1234/v1", **overrides
    )
    return OpenAIBackend(model, client=fake), fake


def prepared() -> Prepared:
    return Prepared(
        system=SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": "merhaba"}]}],
        betas=[],
        context_management=None,
    )


async def test_text_stream_is_assembled(monkeypatch) -> None:
    be, _ = backend([chunk(content="mer"), chunk(content="haba", finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.content == [{"type": "text", "text": "merhaba"}]
    assert result.stop_reason == "end_turn"


async def test_tool_call_assembled_from_fragments() -> None:
    """Argümanlar parça parça gelir; birleştirme hatası sessizce bozuk JSON üretir."""
    be, _ = backend(
        [
            chunk(tool_calls=[fragment(0, id="c1", name="shell", arguments='{"comm')]),
            chunk(tool_calls=[fragment(0, arguments='and": "ls"}')]),
            chunk(finish="tool_calls"),
        ]
    )
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.stop_reason == "tool_use"
    assert result.tool_uses() == [
        {"type": "tool_use", "id": "c1", "name": "shell", "input": {"command": "ls"}}
    ]


async def test_parallel_tool_calls_keep_their_slots() -> None:
    be, _ = backend(
        [
            chunk(
                tool_calls=[
                    fragment(0, id="a", name="read_file", arguments='{"path":"x"}'),
                    fragment(1, id="b", name="list_dir", arguments='{"path":"y"}'),
                ]
            ),
            chunk(finish="tool_calls"),
        ]
    )
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert [b["name"] for b in result.tool_uses()] == ["read_file", "list_dir"]


async def test_tool_calls_imply_tool_use_even_without_finish_reason() -> None:
    """Bazı uyumlu sunucular finish_reason atlıyor; döngü o zaman turu
    end_turn sanıp aracı hiç çalıştırmadan dururdu."""
    be, _ = backend([chunk(tool_calls=[fragment(0, id="c1", name="shell", arguments="{}")])])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.stop_reason == "tool_use"


async def test_cancel_stops_mid_stream() -> None:
    cancel = asyncio.Event()
    cancel.set()
    be, _ = backend([chunk(content="hiç görünmemeli", finish="stop")])

    result = await be.turn(prepared(), [], cancel=cancel)
    assert result.interrupted is True
    assert result.message is None


async def test_usage_is_carried_over() -> None:
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=30)
    be, _ = backend([chunk(content="x", finish="stop", usage=usage)])

    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 30


async def test_usage_maps_cached_tokens_from_prompt_details() -> None:
    """OpenRouter/OpenAI prompt_tokens_details.cached_tokens → cache_read."""
    from neocp.backends.openai_backend import _usage
    from neocp.context import cache_report

    raw = SimpleNamespace(
        prompt_tokens=5000,
        completion_tokens=40,
        prompt_tokens_details=SimpleNamespace(cached_tokens=4200),
    )
    usage = _usage(raw)
    assert usage.cache_read_input_tokens == 4200
    assert usage.input_tokens == 800  # taze = toplam - cache
    report = cache_report(usage)
    assert report["cache_read"] == 4200
    assert report["prompt_total"] == 5000


async def test_anthropic_only_parameters_are_not_sent_to_local_servers() -> None:
    """effort ve thinking yerel sunucularda 400 sebebi olur."""
    be, fake = backend([chunk(content="x", finish="stop")], temperature=0.4)
    await be.turn(prepared(), [{"name": "shell", "description": "d", "input_schema": {}}], cancel=asyncio.Event())

    assert "output_config" not in fake.seen
    assert "thinking" not in fake.seen
    assert fake.seen["temperature"] == 0.4
    assert fake.seen["model"] == "local-model"


async def test_reasoning_only_turn_is_marked_incomplete_not_answered() -> None:
    """Düşünme modelleri turu bazen yalnızca reasoning kanalında bitirir:
    plan yapar, "şimdi şunu yapmalıyım" der ve durur.

    Bunu cevap diye sunmak kullanıcıyı yarıda bırakıyordu — gerçek bir
    koşuda ekranda "Şimdi bilgi toplayıp sunmalıyım:" yazıp konuşma bitti.
    Akıl yürütme geçmişe girmeli (model kendi planını görsün) ama cevap
    sayılmamalı; döngü `empty_turn` görünce turu sürdürüyor.
    """
    from neocp.backends import Callbacks

    shown: list[str] = []
    be, _ = backend([chunk(reasoning="Şimdi şunu yapmalıyım:", finish="stop")])
    result = await be.turn(
        prepared(), [], cancel=asyncio.Event(), callbacks=Callbacks(on_text=shown.append)
    )

    assert result.error is None
    assert result.stop_reason == "empty_turn"
    # Geçmişte duruyor...
    assert result.content == [{"type": "text", "text": "Şimdi şunu yapmalıyım:"}]
    # ...ama cevap kanalından akmadı.
    assert shown == []


async def test_reasoning_in_model_extra_is_found() -> None:
    """Alan OpenAI şemasında yok; SDK onu model_extra'ya koyuyor."""
    be, _ = backend([chunk(extra={"reasoning_content": "gizli kanal"}, finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())
    assert result.content == [{"type": "text", "text": "gizli kanal"}]


async def test_completely_empty_response_is_an_error_not_an_empty_turn() -> None:
    """Boş content dizisini geçmişe yazmak sonraki isteği bozar."""
    be, _ = backend([chunk(finish="stop")])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.message is None
    assert "boş yanıt" in (result.error or "")


async def test_stream_is_closed_after_normal_completion() -> None:
    """Kapatılmazsa httpx bağlantısı kapanışta toplanır ve hata basar."""
    be, fake = backend([chunk(content="bitti", finish="stop")])
    await be.turn(prepared(), [], cancel=asyncio.Event())
    assert fake.stream.closed is True


async def test_stream_is_closed_when_cancelled() -> None:
    cancel = asyncio.Event()
    cancel.set()
    be, fake = backend([chunk(content="x", finish="stop")])

    await be.turn(prepared(), [], cancel=cancel)
    assert fake.stream.closed is True


def test_unknown_provider_fails_loudly() -> None:
    with pytest.raises(ValueError, match="Bilinmeyen sağlayıcı"):
        build_client(ModelConfig(provider="llamafile"))


# -- metne sizan arac cagrilari ----------------------------------------


def test_inline_tool_call_in_text_is_executed_not_shown() -> None:
    """Bazi yerel modeller cagriyi tool_calls alaninda degil metinde uretiyor.

    Ayristirilmazsa cagri hic calismaz ve ham XML kullaniciya cevap gibi
    gorunur — gercek bir kosuda tam olarak bu oldu.
    """
    from neocp.backends.translate import extract_inline_calls

    raw = (
        "Tamam, kaydediyorum.\n"
        "<tool_call>\n<function=mind_memory>\n"
        "<parameter=action>\nsave\n</parameter>\n"
        "<parameter=content>\nFatih SCADA ile calisiyor.\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    text, calls = extract_inline_calls(raw)

    assert text == "Tamam, kaydediyorum."
    assert "<tool_call>" not in text
    assert calls == [
        {"name": "mind_memory",
         "arguments": {"action": "save", "content": "Fatih SCADA ile calisiyor."}}
    ]


def test_inline_json_form_is_parsed() -> None:
    from neocp.backends.translate import extract_inline_calls

    text, calls = extract_inline_calls(
        'Bak: <tool_call>{"name": "shell", "arguments": {"command": "ls"}}</tool_call>'
    )
    assert text == "Bak:"
    assert calls == [{"name": "shell", "arguments": {"command": "ls"}}]


def test_plain_text_is_left_alone() -> None:
    from neocp.backends.translate import extract_inline_calls

    assert extract_inline_calls("sadece bir cevap") == ("sadece bir cevap", [])


async def test_backend_turns_inline_calls_into_tool_use() -> None:
    be, _ = backend([
        chunk(content="Bakiyorum. <tool_call><function=list_dir>"),
        chunk(content="<parameter=path>src</parameter></function></tool_call>", finish="stop"),
    ])
    result = await be.turn(prepared(), [], cancel=asyncio.Event())

    assert result.stop_reason == "tool_use"
    assert result.tool_uses() == [
        {"type": "tool_use", "id": "inline_0", "name": "list_dir", "input": {"path": "src"}}
    ]
    # Ham etiket cevaba sizmamali.
    assert "<tool_call>" not in result.content[0]["text"]


# -- düşünme çabası ----------------------------------------------------
#
# "Çaba" ayarı OpenAI uyumlu sunuculara hiç gönderilmiyordu: qwen3 gibi
# düşünen modeller kendi kararlarıyla akıl yürütüyor ve ayar sayfasındaki
# değer hiçbir şey yapmıyordu. Ölçüm (qwen3-27b, OpenRouter, tek kelimelik
# istem): high 8,97 sn — low 1,60 sn. Selam vermek için dokuz saniye akıl
# yürütmek asistanı gerçek zamanlı olmaktan çıkarıyor.


def _backend(**fields):
    from neocp.backends.openai_backend import OpenAIBackend
    from neocp.config import ModelConfig

    return OpenAIBackend(ModelConfig(**{"name": "qwen", **fields}), client=object())


def test_the_effort_setting_actually_reaches_the_server() -> None:
    assert _backend(effort="low")._reasoning() == {"effort": "low"}
    assert _backend(effort="high")._reasoning() == {"effort": "high"}


def test_turning_thinking_off_says_so_explicitly() -> None:
    """Alanı hiç göndermemek "model bildiği gibi düşünsün" demek."""
    assert _backend(thinking=False)._reasoning() == {"enabled": False}


def test_efforts_the_server_does_not_know_are_folded_down() -> None:
    """xhigh/max yalnızca Claude'da var; olduğu gibi göndermek 400 demek."""
    assert _backend(effort="xhigh")._reasoning() == {"effort": "high"}
    assert _backend(effort="max")._reasoning() == {"effort": "high"}
    assert _backend(effort="")._reasoning() is None


def test_a_server_that_rejects_the_field_is_recognised() -> None:
    """Alanı tanımayan sunucu 400 dönüyor; bir kez alan atılıp yeniden
    deneniyor ve bir daha gönderilmiyor."""
    from neocp.backends.openai_backend import _rejects_reasoning

    assert _rejects_reasoning(Exception("400: unknown field 'reasoning'"))
    assert _rejects_reasoning(Exception("Unrecognized request argument: extra_body"))
    # Gerçek bir hatayı alan hatası sanıp sessizce yutmamalı.
    assert not _rejects_reasoning(Exception("rate limit exceeded"))


def test_the_field_is_only_dropped_once() -> None:
    """Her istekte 400 alıp yeniden denemek, her cevaba bir tur gecikme
    eklerdi."""
    backend = _backend(effort="low")
    assert backend._no_reasoning is False


# -- metin-only modelde görüntü sıyırma (auto-heal) --------------------


class ImageRejectingOpenAI:
    """İlk çağrıda görüntü hatası, sonra başarılı — metin-only modeli taklit."""

    def __init__(self, chunks: list[SimpleNamespace]) -> None:
        self.stream = FakeStream(chunks)
        self.calls: list[dict] = []
        self._fail_next = True
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail_next:
            self._fail_next = False
            exc = Exception("Error code: 404 - No endpoints found that support image input")
            exc.status_code = 404  # type: ignore[attr-defined]
            raise exc
        return self.stream

    async def close(self) -> None:
        pass


def _image_prepared() -> Prepared:
    return Prepared(
        system=SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": "bak"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
        ]}],
        betas=[],
        context_management=None,
    )


async def test_text_only_model_strips_images_and_retries() -> None:
    """Metin-only modele geçince geçmişteki kare 404 veriyor; backend bir
    kez öğrenip kareyi sıyırıp yeniden deniyor — kullanıcı hata görmüyor."""
    fake = ImageRejectingOpenAI([chunk(content="tamam", finish="stop")])
    model = ModelConfig(name="deepseek-flash", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)

    result = await be.turn(_image_prepared(), [], cancel=asyncio.Event())

    assert result.content == [{"type": "text", "text": "tamam"}]
    assert len(fake.calls) == 2, "hata sonrası yeniden denenmedi"
    second = str(fake.calls[1]["messages"])
    assert "image_url" not in second, "görüntü hâlâ istekte"
    assert "göremiyor" in second, "görüntü izi konmadı"
    assert be._no_vision, "metin-only olduğu öğrenilmedi"


async def test_learned_no_vision_strips_before_sending() -> None:
    """Bir kez öğrenildikten sonra sonraki turlar boşa 404 yememeli:
    kareler baştan sıyrılıyor."""
    fake = FakeOpenAI([chunk(content="ok", finish="stop")])
    model = ModelConfig(name="x", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)
    be._no_vision = True

    await be.turn(_image_prepared(), [], cancel=asyncio.Event())

    assert "image_url" not in str(fake.seen["messages"])


# -- kesme: ilk token'dan önce -----------------------------------------
#
# Yara: kesme yalnız parça GELİNCE yoklanıyordu. Önbelleksiz İLK turda
# istem işleme dakikalar sürebiliyor ve o sırada hiç parça yok — Durdur
# hiçbir şey yapmıyordu ("ilk konuşmada durdurma çalışmıyor" raporunun
# kökü). `cancellable` her adımı kesme bekleyişiyle yarıştırıyor.


class _SilentStream:
    """İlk token'ı hiç göndermeyen akış: sunucu istemi işliyor."""

    def __init__(self) -> None:
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(3600)

    async def close(self) -> None:
        self.closed = True


async def test_cancellable_fires_while_waiting_for_the_first_chunk() -> None:
    from neocp.backends.base import Interrupted, cancellable

    cancel = asyncio.Event()

    async def consume() -> None:
        async for _ in cancellable(_SilentStream(), cancel):
            raise AssertionError("parça gelmemeliydi")

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.01)
    assert not task.done(), "akış beklemede olmalı"
    cancel.set()
    with pytest.raises(Interrupted):
        await asyncio.wait_for(task, timeout=2)


async def test_cancellable_passes_chunks_through_untouched() -> None:
    from neocp.backends.base import cancellable

    cancel = asyncio.Event()
    got = []
    async for c in cancellable(FakeStream([chunk(content="a"), chunk(content="b")]).__aiter__(), cancel):
        got.append(c.choices[0].delta.content)
    assert got == ["a", "b"]


async def test_interrupt_before_first_token_returns_interrupted() -> None:
    """Uçtan uca: turun kendisi, parça beklerken kesilebiliyor ve sonuç
    `interrupted` — hata değil (oto-mod hanesine hata yazılmamalı)."""

    class SilentOpenAI:
        def __init__(self) -> None:
            self.stream = _SilentStream()
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create))

        async def _create(self, **kwargs):
            return self.stream

        async def close(self) -> None:
            pass

    fake = SilentOpenAI()
    model = ModelConfig(name="x", provider="openai", base_url="http://x/v1")
    be = OpenAIBackend(model, client=fake)

    cancel = asyncio.Event()
    task = asyncio.ensure_future(be.turn(prepared(), [], cancel=cancel))
    await asyncio.sleep(0.01)
    assert not task.done()

    cancel.set()
    result = await asyncio.wait_for(task, timeout=2)

    assert result.interrupted is True
    assert result.error is None
    assert fake.stream.closed, "kesilen akış kapatılmalı"


def test_tur_ortasi_sistem_notu_user_notuna_cevrilir():
    """Anthropic ailesi system'i yalnız dizi başında kabul ediyor; tur ortası
    notlar user-notu olarak gitmeli — yoksa Claude modelleri 400 döndürüyor."""
    from neocp.backends.translate import to_openai_messages

    mesajlar = [
        {"role": "user", "content": [{"type": "text", "text": "merhaba"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "selam"}]},
        {"role": "system", "content": [{"type": "text", "text": "hedef notu"}]},
    ]
    out = to_openai_messages([{"type": "text", "text": "sistem promptu"}], mesajlar)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
    assert out[-1]["content"].startswith("[Sistem notu]")


# -- yedek model -------------------------------------------------------
#
# Uzun bir iş koşarken kredi bitiyor (402) ya da ayarlardaki model kimliği
# geçersizleşiyor. Sağlayıcı her istekte aynı cevabı veriyor: beklemek işe
# yaramıyor ve saatlerdir süren iş yarıda kalıyor. Yedek model tanımlıysa
# tur ölmek yerine orada sürüyor.

from neocp.backends.base import Callbacks, TurnResult      # noqa: E402
from neocp.backends.fallback import FallbackBackend, is_permanent   # noqa: E402


class _SahteBackend:
    """Sırayla verilen sonuçları döndüren backend taklidi."""

    def __init__(self, name: str, results: list[TurnResult]) -> None:
        self.name = name
        self._results = list(results)
        self.calls = 0
        self.closed = False

    async def turn(self, prepared, tools, *, cancel=None, callbacks=None) -> TurnResult:
        self.calls += 1
        return self._results.pop(0) if self._results else TurnResult(error="senaryo bitti")

    async def count_tokens(self, prepared, tools) -> int:
        return 0

    async def close(self) -> None:
        self.closed = True


def _kur(primary_results, fallback_results=None):
    """Yedekli sarmalayıcı + iki sahte backend."""
    model = ModelConfig(name="asil", fallback_model="yedek")
    made: dict[str, _SahteBackend] = {}

    def build(cfg: ModelConfig) -> _SahteBackend:
        results = primary_results if cfg.name == "asil" else (fallback_results or [])
        made[cfg.name] = _SahteBackend(cfg.name, results)
        return made[cfg.name]

    return FallbackBackend(model, build), made


def _ok(text: str = "tamam") -> TurnResult:
    return TurnResult(message=SimpleNamespace(content=[{"type": "text", "text": text}],
                                              stop_reason="end_turn", usage=None))


def test_permanent_and_transient_errors_are_told_apart() -> None:
    """Ölçü tek soru: aynı istek birazdan tekrar gönderilse sonuç değişir mi?

    Değişecekse (bağlantı, 429, 5xx) döngünün yeniden deneme merdiveni
    doğru yer; yedeğe düşmek bir sağlayıcı hıçkırığında kalıcı olarak
    zayıf bir modele geçmek demek olurdu.
    """
    for kalici in ("openrouter 402: insufficient credits",
                   "qwen3.1-14b is not a valid model ID",
                   "openrouter 404: model bulunamadı",
                   "403: unsupported_country"):
        assert is_permanent(kalici), kalici

    for gecici in ("Connection error", "openrouter 429: rate limited",
                   "openrouter 500: upstream", "timeout", "", None):
        assert not is_permanent(gecici), gecici


def test_a_permanent_failure_continues_on_the_fallback() -> None:
    client, made = _kur([TurnResult(error="openrouter 402: insufficient credits")], [_ok("yedek konuştu")])

    said: list[str] = []
    result = asyncio.run(client.turn(None, [], cancel=None,
                                     callbacks=Callbacks(on_text=said.append)))

    assert result.error is None
    assert made["yedek"].calls == 1
    assert client.switched
    # Kullanıcı ne olduğunu görmeli: sessiz bir model değişimi, kalitesi
    # sessizce düşmüş bir iş demek.
    assert any("yedek" in line for line in said)


def test_the_notice_never_enters_the_answer_content() -> None:
    """Satır GÖSTERİM kanalından gidiyor: geçmişe modelin söylemediği bir
    cümleyi yazmak, sonraki turlarda modelin kendi sözü sanılırdı."""
    client, _ = _kur([TurnResult(error="402: payment required")], [_ok("asıl cevap")])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    metin = " ".join(b.get("text", "") for b in result.content)
    assert "yedek modelle" not in metin
    assert metin == "asıl cevap"


def test_a_transient_failure_is_left_to_the_retry_ladder() -> None:
    """Geçici hata yedeğe hiç uğramamalı: döngü onu zaten yeniden deniyor."""
    client, made = _kur([TurnResult(error="Connection error")], [_ok()])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    assert result.error == "Connection error"
    assert "yedek" not in made          # yedek istemci hiç kurulmadı
    assert not client.switched


def test_an_interruption_is_a_decision_not_a_failure() -> None:
    client, made = _kur([TurnResult(interrupted=True)], [_ok()])
    result = asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    assert result.interrupted and "yedek" not in made


def test_once_switched_the_main_model_is_not_tried_again() -> None:
    """Her turda asıl modeli yeniden denemek turu iki isteğe çıkarır ve
    kredi bittiyse hiçbir zaman düzelmez."""
    client, made = _kur([TurnResult(error="402: no credit")], [_ok(), _ok()])
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    assert made["asil"].calls == 1      # ikinci turda hiç denenmedi
    assert made["yedek"].calls == 2


def test_without_a_fallback_nothing_changes() -> None:
    """Yedek yoksa bugünkü davranış aynen kalmalı: hata yüzeye çıkar."""
    plain = build_client(ModelConfig(name="asil"))
    assert not isinstance(plain, FallbackBackend)
    # Yedek asıl modelle aynıysa sarmalamak anlamsız: aynı model iki kez.
    same = build_client(ModelConfig(name="asil", fallback_model="asil"))
    assert not isinstance(same, FallbackBackend)


def test_the_fallback_client_keeps_the_provider_and_address() -> None:
    """Yedek "aynı kapıdaki başka model" demek. Sessizce başka bir
    sağlayıcıya düşmek, hangi anahtarla konuşulduğunu görünmez kılardı."""
    seen: list[ModelConfig] = []

    def build(cfg: ModelConfig):
        seen.append(cfg)
        return _SahteBackend(cfg.name, [_ok()])

    model = ModelConfig(name="asil", fallback_model="yedek",
                        base_url="http://localhost:1234/v1", api_key_env="LOCAL_KEY")
    client = FallbackBackend(model, build)
    client.switched = True
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))

    yedek = seen[-1]
    assert yedek.name == "yedek"
    assert yedek.base_url == "http://localhost:1234/v1"
    assert yedek.api_key_env == "LOCAL_KEY"
    # Yedeğin yedeği yok: sonsuz zincir olmasın.
    assert yedek.fallback_model == ""


def test_closing_releases_both_clients() -> None:
    client, made = _kur([TurnResult(error="402")], [_ok()])
    asyncio.run(client.turn(None, [], cancel=None, callbacks=Callbacks()))
    asyncio.run(client.close())
    assert made["asil"].closed and made["yedek"].closed


def test_the_fallback_field_survives_a_settings_round_trip(tmp_path) -> None:
    """Alan config.json'a yazılıp geri okunmazsa ayar sayfası çalışıyor
    görünür ama hiçbir şey değişmez."""
    from neocp import settings
    from neocp.config import Config

    config = Config.load(tmp_path)
    config.ensure_dirs()
    updated = settings.apply(config, {"model": {"fallback_model": "yedek-model"}})
    assert updated.model.fallback_model == "yedek-model"
    assert Config.load(tmp_path).model.fallback_model == "yedek-model"


# -- sağlayıcıya özel alanların gidiş-dönüşü ----------------------------
#
# Gemini düşünen modellerde her araç çağrısına bir `thought_signature`
# iliştiriyor ve SONRAKİ turda onu geri göndermeni ŞART koşuyor. neo bir tur
# içinde aracı çağırıp cevabı geri yolladığı için bu tam da bizim yolumuza
# düşüyordu ve alan çeviride kayboluyordu:
#
#   400 — Function call is missing a thought_signature in functionCall parts.
#
# Çözüm alanı MODELLEMEK değil KAYBETMEMEK: adını bilmediğimiz bir alanı da
# taşıyoruz, böylece böyle bir alan ekleyen bir sonraki sağlayıcıda kırılmıyoruz.


def test_provider_fields_survive_the_round_trip() -> None:
    from neocp.backends.translate import to_anthropic_blocks, to_openai_messages

    bloklar = to_anthropic_blocks("", [{
        "id": "call_1", "name": "mind_memory", "arguments": '{"kind": "fact"}',
        "ek": {"thought_signature": "ABC123", "extra_content": {"google": {"x": 1}}},
    }])
    (blok,) = bloklar
    assert blok["saglayici"]["thought_signature"] == "ABC123"

    mesajlar = to_openai_messages([], [{"role": "assistant", "content": bloklar}])
    (cagri,) = mesajlar[0]["tool_calls"]
    assert cagri["thought_signature"] == "ABC123"
    assert cagri["extra_content"] == {"google": {"x": 1}}
    # Kimlik ve argüman BİZİM: sağlayıcı alanı onların üstüne yazmıyor.
    assert cagri["id"] == "call_1"
    assert cagri["function"]["name"] == "mind_memory"


def test_a_call_without_provider_fields_is_unchanged() -> None:
    """Alanı olmayan sağlayıcıda çıktı bir harf bile değişmemeli."""
    from neocp.backends.translate import to_anthropic_blocks, to_openai_messages

    bloklar = to_anthropic_blocks("", [
        {"id": "c1", "name": "shell", "arguments": '{"command": "ls"}'}])
    assert "saglayici" not in bloklar[0]
    (cagri,) = to_openai_messages([], [{"role": "assistant", "content": bloklar}])[0]["tool_calls"]
    assert set(cagri) == {"id", "type", "function"}


def test_provider_fields_never_reach_anthropic() -> None:
    """Anthropic tanımadığı alanı reddediyor; aynı konuşma iki sağlayıcı
    arasında taşınabildiği için (yedek model, model değiştirme) ayıklama şart."""
    from neocp.context import saglayici_alanlarini_at

    mesajlar = [
        {"role": "user", "content": [{"type": "text", "text": "selam"}]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "bakıyorum"},
            {"type": "tool_use", "id": "c1", "name": "shell", "input": {"command": "ls"},
             "saglayici": {"thought_signature": "ABC123"}},
        ]},
    ]
    temiz = saglayici_alanlarini_at(mesajlar)
    arac = temiz[1]["content"][1]
    assert "saglayici" not in arac
    assert arac["id"] == "c1" and arac["input"] == {"command": "ls"}
    # Kaynak liste DEĞİŞMEMELİ: aynı konuşma OpenAI yoluna da gidiyor.
    assert "saglayici" in mesajlar[1]["content"][1]


def test_stripping_does_not_copy_when_there_is_nothing_to_strip() -> None:
    """Alan yoksa liste olduğu gibi dönüyor — her istekte derin kopya değil."""
    from neocp.context import saglayici_alanlarini_at

    mesajlar = [{"role": "user", "content": [{"type": "text", "text": "selam"}]}]
    assert saglayici_alanlarini_at(mesajlar) is mesajlar


def test_every_array_in_a_tool_schema_declares_items() -> None:
    """Gemini `items`siz bir array görünce ARACIN değil, araç listesinin
    TAMAMINI reddediyor — yani tek bir aracın eksiği neo'yu o modelde
    tümüyle çalışmaz yapıyor. Canlıda birebir bu oldu:

        function_declarations[23].parameters.properties[steps].items: missing
        function_declarations[37].parameters.properties[nodes].items: missing
    """
    import pathlib
    import tempfile

    from neocp.config import Config
    from neocp.tools import build_registry

    cfg = Config.load(pathlib.Path(tempfile.mkdtemp()))
    cfg.ensure_dirs()
    registry = build_registry(cfg)

    def eksikler(sema, yol=""):
        if not isinstance(sema, dict):
            return []
        bulunan = []
        if sema.get("type") == "array" and "items" not in sema:
            bulunan.append(yol or "(kök)")
        for ad, alt in (sema.get("properties") or {}).items():
            bulunan += eksikler(alt, f"{yol}.{ad}" if yol else ad)
        if isinstance(sema.get("items"), dict):
            bulunan += eksikler(sema["items"], yol + "[]")
        return bulunan

    kusurlu = {s.name: e for s in registry.all() if (e := eksikler(s.input_schema))}
    assert not kusurlu, f"`items` eksik: {kusurlu}"


def test_the_converter_repairs_a_schema_that_slipped_through() -> None:
    """Şemaları elle düzeltmek şart ama yetmez: bir sonraki araç aynı
    hatayla yazıldığında da sağlayıcıya bozuk şema gitmemeli."""
    from neocp.backends.translate import to_openai_tools

    (arac,) = to_openai_tools([{
        "name": "deneme",
        "description": "d",
        "input_schema": {
            "type": "object",
            "properties": {
                "liste": {"type": "array"},
                "ic": {"type": "object", "properties": {"derin": {"type": "array"}}},
                "saglam": {"type": "array", "items": {"type": "string"}},
            },
        },
    }])
    alanlar = arac["function"]["parameters"]["properties"]
    assert alanlar["liste"]["items"] == {}
    assert alanlar["ic"]["properties"]["derin"]["items"] == {}
    # Zaten doğru olan şemaya DOKUNULMUYOR.
    assert alanlar["saglam"]["items"] == {"type": "string"}


# -- istem önbelleği işaretleri (OpenRouter) ---------------------------
#
# OpenCode incelemesinden alınan ölçülmüş kalıp: ilk sistem + son iki
# mesaja ephemeral nokta. İşaretsiz gidiş, aynı model/aynı işte ~6,7x
# maliyet farkı olarak ölçüldü (kiyas-opencode-2608.md).


def test_cache_markers_land_on_system_and_last_two() -> None:
    from neocp.backends.openai_backend import _cache_isaretle

    messages = [
        {"role": "system", "content": "sistem istemi"},
        {"role": "user", "content": "ilk soru"},
        {"role": "assistant", "content": "cevap"},
        {"role": "tool", "content": "araç çıktısı", "tool_call_id": "t1"},
    ]
    _cache_isaretle(messages)

    # Sistem: düz metin tek parçaya sarılıp işaretlenir.
    sistem = messages[0]["content"]
    assert isinstance(sistem, list) and sistem[0]["cache_control"] == {"type": "ephemeral"}
    assert sistem[0]["text"] == "sistem istemi"
    # Son iki (assistant + tool) işaretli; ilk kullanıcı mesajı DEĞİL.
    assert isinstance(messages[1]["content"], str)
    assert messages[2]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert messages[3]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # Toplam üç nokta: Anthropic ailesinin 4 sınırının altında.
    noktalar = sum(
        1
        for m in messages
        if isinstance(m.get("content"), list)
        for p in m["content"]
        if isinstance(p, dict) and "cache_control" in p
    )
    assert noktalar == 3


def test_cache_markers_can_be_stripped_after_rejection() -> None:
    from neocp.backends.openai_backend import _cache_isaretle, _cache_sok

    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    _cache_isaretle(messages)
    _cache_sok(messages)
    for m in messages:
        icerik = m.get("content")
        if isinstance(icerik, list):
            assert all("cache_control" not in p for p in icerik if isinstance(p, dict))


def test_cache_markers_only_for_openrouter_base() -> None:
    """LM Studio / Ollama gibi uçlara işaret hiç gitmez: bayrak adresten."""
    import re
    from pathlib import Path

    kaynak = (Path(__file__).parent.parent / "src/neocp/backends/openai_backend.py").read_text(encoding="utf-8")
    assert re.search(r'_cache_isaretli = "openrouter" in', kaynak)
    assert "_cache_isaretle(messages)" in kaynak
