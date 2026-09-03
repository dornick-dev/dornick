"""Otomasyonların hafızada bıraktığı iz.

İki şey yazılıyor, ikisi de aynı biçimde:

    yordam   Bir akış kurulduğunda/güncellendiğinde ne yaptığı
             (`kind="procedure"`). Amaç, aylar sonra "bunu daha önce
             otomasyonda yapmıştım" diye hatırlayıp oradan bakabilmek —
             işe yararsa kullanmak, yaramazsa yenisini yazmak.
    ders     Bir adım hata verdiğinde ne olduğu (`kind="lesson"`).

Biçim neden ÖNEMLİ: bu kayıtlar yalnız çağrışım için değil, gece koşan
kişisel ince ayarın da girdisi. Aynı olayın her seferinde aynı kalıpla
yazılması, modelin örüntüyü görmesini sağlıyor; serbest metin her
seferinde farklı yazılırsa ortada öğrenilecek bir kalıp kalmıyor.

Hafıza yoksa ya da yazma patlarsa sessizce geçiliyor: otomasyonun kendisi,
hatırlanmasından önemli.
"""

from __future__ import annotations

from typing import Any

from .workflows import Workflow

# Etiketler tek yerde: geri bulmanın anahtarı bunlar.
ETIKET = "otomasyon"
LESSON_TAG = "otomasyon-ders"

# Kayıtta taşınacak azami adım sayısı — elli düğümlük bir grafiği hafızaya
# olduğu gibi dökmek, çağrışımı kendi gürültüsüyle boğar.
AZAMI_ADIM = 12


def _ozet(wf: Workflow) -> str:
    adimlar = []
    for node in wf.nodes[:AZAMI_ADIM]:
        ad = (node.title or node.id).strip()
        adimlar.append(f"{node.type}: {ad}")
    if len(wf.nodes) > AZAMI_ADIM:
        adimlar.append(f"… ve {len(wf.nodes) - AZAMI_ADIM} adım daha")
    return " → ".join(adimlar) if adimlar else "(adım yok)"


def akis_metni(wf: Workflow) -> str:
    """Bir akışın hafızaya yazılan hâli. Kalıp sabit."""
    satirlar = [
        f"Otomasyon [{wf.id}] «{wf.title or wf.id}» — {len(wf.nodes)} adım.",
        f"Adımlar: {_ozet(wf)}",
    ]
    gizli = sorted({s for n in wf.nodes for s in n.secrets_needed if s})
    if gizli:
        satirlar.append(f"Gerektirdiği gizli alanlar: {', '.join(gizli)}")
    yetenekler = sorted({n.skill for n in wf.nodes if n.skill})
    if yetenekler:
        satirlar.append(f"Kullandığı yetenekler: {', '.join(yetenekler)}")
    return "\n".join(satirlar)


def lesson_text(wf_id: str, node: Any, exc: BaseException) -> str:
    """Bir adım hatasının hafızaya yazılan hâli. Kalıp sabit."""
    ad = (getattr(node, "title", "") or getattr(node, "id", "")).strip()
    return (
        f"Otomasyon [{wf_id}] adımı hata verdi — {getattr(node, 'type', '?')}: «{ad}». "
        f"Hata: {type(exc).__name__}: {exc}"
    )


def akisi_hatirla(mind: Any, wf: Workflow) -> bool:
    """Akışı yordam olarak yaz. Yazıldıysa True."""
    if mind is None or not hasattr(mind, "remember"):
        return False
    try:
        mind.remember(
            akis_metni(wf),
            kind="procedure",
            title=f"otomasyon:{wf.id}",
            tags=(ETIKET, f"{ETIKET}:{wf.id}"),
        )
        return True
    except Exception:
        return False


def recall_lesson(mind: Any, wf_id: str, node: Any, exc: BaseException) -> bool:
    """Adım hatasını ders olarak yaz. Yazıldıysa True."""
    if mind is None or not hasattr(mind, "remember"):
        return False
    try:
        mind.remember(
            lesson_text(wf_id, node, exc),
            kind="lesson",
            title=f"otomasyon-hata:{wf_id}:{getattr(node, 'id', '?')}",
            tags=(LESSON_TAG, f"{ETIKET}:{wf_id}"),
        )
        return True
    except Exception:
        return False


def akislari_ara(mind: Any, sorgu: str, *, limit: int = 5) -> list[Any]:
    """Bu işi daha önce otomasyonda yapmış mıyız?

    Hiçbir şey bulamamak normal ve sessiz: "yok" cevabı, uydurulmuş bir
    eşleşmeden iyidir. Çağıran bulduğunu KULLANMAK ZORUNDA DEĞİL — işe
    yaramıyorsa yenisini yazmak doğru olan.
    """
    if mind is None or not hasattr(mind, "recall"):
        return []
    try:
        bulunan = mind.recall(sorgu, limit=limit * 3) or []
    except Exception:
        return []
    sonuc = []
    for m in bulunan:
        # `recall` puanlanmış sarmalayıcı döndürüyor (`Scored.item`); doğrudan
        # hatıra dönen bir çağırana da açık kalsın diye ikisi de kabul.
        kayit = getattr(m, "item", m)
        etiketler = set(getattr(kayit, "tags", ()) or ())
        baslik = str(getattr(kayit, "title", ""))
        if ETIKET in etiketler or baslik.startswith("otomasyon:"):
            sonuc.append(kayit)
        if len(sonuc) >= limit:
            break
    return sonuc
