"""Bağlam dolduğunda ne olacağı.

Model penceresi sonlu, konuşma değil. Pencere dolduğunda üç seçenek var:
düşürmek (en eskiyi at — ajan neden orada olduğunu unutur), reddetmek
("bağlam doldu, yeni oturum aç" — kullanıcının işini bölmek) ya da
**özetleyip devam etmek**. Burada üçüncüsü yapılıyor.

Sıkıştırma iki yere birden yazıyor ve asıl fikir bu:

    bağlama   özet, yeni pencerenin ilk mesajı olur — konuşma kesilmez
    zihne     aynı özet kalıcı belleğe düşer — oturum kapansa da durur

İkincisi olmadan sıkıştırma sadece kontrollü bir unutma olurdu. Zihne de
yazıldığı için, aylar sonra ilgisiz bir konuşmada geçen bir kelime bu özeti
çağrışımla geri getirebiliyor.

Kesme noktası rastgele seçilemez. API iki şeyi şart koşuyor: her tool_use
karşılığını almalı ve pencere bir kullanıcı turuyla başlamalı. Bu yüzden
kesim her zaman gerçek bir kullanıcı mesajının önüne düşüyor — araç sonucu
taşıyan kullanıcı turları kesme noktası olamaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Message = dict[str, Any]

# Pencerenin bu oranı dolduğunda sıkıştırma tetiklenir. Tavana kadar
# beklemek işe yaramaz: özet isteğinin kendisi de pencereye sığmalı.
PRESSURE = 0.75

# Sıkıştırmadan sonra olduğu gibi taşınacak asgari mesaj sayısı. Özet
# "ne konuşulduğunu" verir, bu mesajlar "az önce ne olduğunu".
KEEP_MESSAGES = 6

SUMMARY_SYSTEM = """Sen bir oturum özetleyicisin. Sana bir ajan oturumunun
dökümü veriliyor. Görevin, oturumun kaldığı yerden kesintisiz devam
edebilmesi için gereken her şeyi kaydetmek.

Şunları mutlaka koru:
  - kullanıcının ne istediği ve neden istediği
  - alınan kararlar ve gerekçeleri
  - dokunulan dosyalar, komutlar, adresler, kimlikler — birebir
  - denenip işe yaramayan yollar (tekrar denenmesin)
  - şu an yarım kalan iş ve bir sonraki adım

Şunları atla: nezaket cümleleri, tekrarlar, uzun araç çıktılarının gövdesi.

Düz Türkçe yaz, madde madde. Kendinden bahsetme, özetlediğini söyleme —
doğrudan içerikle başla."""

SUMMARY_REQUEST = """Aşağıdaki oturum dökümünü yukarıdaki kurallara göre özetle.

--- DÖKÜM BAŞLANGICI ---
{transcript}
--- DÖKÜM SONU ---"""

# Yeni pencerenin ilk mesajı. Modelin bunu bir kullanıcı isteği sanmaması
# için ne olduğu açıkça söyleniyor.
CARRY_OVER = """[önceki bağlamın özeti — konuşma buradan devam ediyor]

{summary}

[özet sonu. Bir soru sorulmadıysa yanıt verme; kaldığın işe devam et.]"""


@dataclass(slots=True)
class Pressure:
    """Pencerenin ne kadarının dolu olduğu."""

    used: int
    window: int

    @property
    def ratio(self) -> float:
        return self.used / self.window if self.window > 0 else 0.0

    @property
    def full(self) -> bool:
        return self.ratio >= PRESSURE

    @property
    def percent(self) -> int:
        return int(self.ratio * 100)


def measure(usage: dict[str, int], window: int) -> Pressure:
    """Kullanım raporundan pencere doluluğunu çıkarır.

    `prompt_total` kullanılıyor, `input_tokens` değil: ikincisi yalnızca
    önbelleğe girmemiş artığı sayar ve pencere doluyken bile küçük kalır.
    """
    return Pressure(used=int(usage.get("prompt_total") or 0), window=window)


def cut_point(messages: list[Message], *, keep: int = KEEP_MESSAGES) -> int:
    """Kesimin düşeceği indeks. 0 dönerse sıkıştırılacak bir şey yok.

    Geriye doğru, `keep` mesaj bırakacak kadar gerilenip oradan ileri ilk
    **gerçek** kullanıcı mesajı aranıyor. Gerçek olması şart: araç sonucu
    taşıyan kullanıcı turu bir asistan turunun devamıdır, önünden kesmek
    karşılıksız tool_use bırakır.
    """
    if len(messages) <= keep:
        return 0

    for index in range(len(messages) - keep, 0, -1):
        if _is_user_turn(messages[index]):
            return index
    return 0


def work_cut(messages: list[Message], *, keep: int = KEEP_MESSAGES) -> int:
    """Tek koşunun ORTASI için kesim: bir asistan mesajının önü.

    Yüz araçlık tek bir koşuda gerçek kullanıcı turu yalnızca en başta —
    `cut_point` 0 döner ve sıkıştırma hiç çalışamazdı: pencere dolunca
    koşu "yeni oturum aç" ile ölüyordu. Oysa bir asistan mesajının önü de
    güvenli bir kesimdir: o mesajın tool_use'ları ve karşılıkları birlikte
    pencerede kalır, öncekiler birlikte özete katlanır; pencerenin başını
    zaten carry_over (user) mesajı açıyor.

    `cut_point` yine önce deneniyor (gerçek kullanıcı turu daha iyi bir
    sınır); burası yalnızca onun bulamadığı durumun yedeği.
    """
    if len(messages) <= keep:
        return 0
    for index in range(len(messages) - keep, 0, -1):
        if messages[index].get("role") == "assistant":
            return index
    return 0


def _is_user_turn(message: Message) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if not isinstance(content, list):
        return bool(content)
    # Araç sonucu içeren tur kullanıcının kendi turu sayılmaz.
    return not any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def transcript(messages: list[Message], *, tool_output_limit: int = 400) -> str:
    """Mesajları özetleyiciye verilecek düz metne çevirir.

    Araç çıktıları kırpılıyor: bir dizin listesinin tamamı özet için bilgi
    değil gürültü, ama ilk satırları hangi araca ne sorulduğunu gösteriyor.
    """
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "?"))
        for piece in _render(message.get("content"), tool_output_limit):
            lines.append(f"{role}: {piece}")
    return "\n".join(lines)


def _render(content: Any, limit: int) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []

    out: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            out.append(str(block.get("text", "")))
        elif kind == "tool_use":
            out.append(f"[araç: {block.get('name')} {_short(block.get('input'), 200)}]")
        elif kind == "tool_result":
            out.append(f"[sonuç: {_short(block.get('content'), limit)}]")
        # thinking blokları atlanıyor: özete girmesi gereken sonuçlar,
        # oraya varılan yol değil.
    return [piece for piece in out if piece.strip()]


def _short(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + f"… (+{len(text) - limit} karakter)"


def carry_over(summary: str) -> Message:
    """Özeti yeni pencerenin ilk mesajı haline getirir."""
    return {"role": "user", "content": [{"type": "text", "text": CARRY_OVER.format(summary=summary)}]}
