"""Otomasyonların hafızada bıraktığı iz.

İki vaat sınanıyor:

  1. Kurulan bir akış hafızaya YORDAM olarak giriyor ve sonradan
     bulunabiliyor — "bunu daha önce otomasyonda yapmıştım" anı ancak
     kayıt varsa geliyor.
  2. Bozulan bir adım hafızaya DERS olarak, HER ZAMAN AYNI KALIPLA
     giriyor. Kalıbın sabitliği yalnız düzen meselesi değil: bu kayıtlar
     gece koşan kişisel ince ayarın girdisi ve her seferinde başka türlü
     yazılan bir olayda öğrenilecek örüntü kalmıyor.
"""

from __future__ import annotations

from pathlib import Path

from neocp import workflow_mind, workflows


def _akis(tmp_path: Path) -> workflows.Workflow:
    return workflows.save(tmp_path, {
        "id": "posta", "title": "Günlük posta özeti",
        "nodes": [
            {"id": "n1", "title": "E-postaları oku", "type": "mail_read",
             "secrets_needed": ["MAIL_TOKEN"]},
            {"id": "n2", "title": "Önemlileri seç", "type": "agent"},
            {"id": "n3", "title": "WhatsApp'tan at", "type": "http",
             "secrets_needed": ["WP_TOKEN"], "skill": "wp_gonder"},
        ],
        "edges": [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}],
    })


class _SahteZihin:
    def __init__(self) -> None:
        self.kayitlar: list[dict] = []

    def remember(self, content, *, kind="fact", title="", tags=()):
        self.kayitlar.append({"content": content, "kind": kind,
                              "title": title, "tags": tuple(tags)})
        return object()


def test_a_saved_automation_becomes_a_procedure(tmp_path: Path) -> None:
    zihin = _SahteZihin()
    assert workflow_mind.akisi_hatirla(zihin, _akis(tmp_path)) is True

    (kayit,) = zihin.kayitlar
    assert kayit["kind"] == "procedure"
    assert kayit["title"] == "otomasyon:posta"
    assert workflow_mind.ETIKET in kayit["tags"]
    # İçerik aylar sonra okunabilir olmalı: ne yaptığı, neye ihtiyaç duyduğu.
    assert "Günlük posta özeti" in kayit["content"]
    assert "mail_read" in kayit["content"] and "http" in kayit["content"]
    assert "MAIL_TOKEN" in kayit["content"] and "WP_TOKEN" in kayit["content"]
    assert "wp_gonder" in kayit["content"]


def test_a_big_graph_does_not_flood_the_memory(tmp_path: Path) -> None:
    """Elli düğümlük bir grafiği olduğu gibi dökmek çağrışımı boğar."""
    wf = workflows.save(tmp_path, {
        "id": "buyuk", "title": "Büyük",
        "nodes": [{"id": f"n{i}", "title": f"Adım {i}", "type": "shell"}
                  for i in range(40)],
        "edges": [],
    })
    metin = workflow_mind.akis_metni(wf)
    assert "ve 28 adım daha" in metin
    assert len(metin) < 900


def test_the_lesson_shape_is_stable(tmp_path: Path) -> None:
    """Aynı olay her seferinde aynı kalıpla — ince ayarın görebilmesi için."""
    wf = _akis(tmp_path)
    bir = workflow_mind.ders_metni(wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    iki = workflow_mind.ders_metni(wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    assert bir == iki
    assert bir.startswith("Otomasyon [posta] adımı hata verdi")
    assert "RuntimeError: bağlanamadı" in bir

    zihin = _SahteZihin()
    workflow_mind.dersi_hatirla(zihin, wf.id, wf.nodes[0], RuntimeError("bağlanamadı"))
    (kayit,) = zihin.kayitlar
    assert kayit["kind"] == "lesson"
    assert workflow_mind.DERS_ETIKETI in kayit["tags"]
    # Akış etiketi de var: bir akışın bütün dersleri birlikte bulunabilsin.
    assert f"{workflow_mind.ETIKET}:posta" in kayit["tags"]


def test_no_mind_is_silent_not_fatal() -> None:
    """Hafıza yoksa otomasyon yine çalışmalı — kayıt ikincil."""
    assert workflow_mind.akisi_hatirla(None, None) is False
    assert workflow_mind.dersi_hatirla(None, "x", None, RuntimeError("y")) is False
    assert workflow_mind.akislari_ara(None, "posta") == []


def test_recall_returns_only_automations() -> None:
    """Arama otomasyon kayıtlarını süzüyor; alakasız hatıra dönmüyor."""

    class _Hatira:
        def __init__(self, title, tags):
            self.title, self.tags = title, tags

    class _Puanli:
        def __init__(self, item):
            self.item = item

    class _Zihin:
        def recall(self, _q, limit=8):
            return [
                _Puanli(_Hatira("kahve tarifi", ["mutfak"])),
                _Puanli(_Hatira("otomasyon:posta", [workflow_mind.ETIKET])),
                _Puanli(_Hatira("otomasyon:rapor", [])),
            ]

    bulunan = workflow_mind.akislari_ara(_Zihin(), "posta")
    assert [m.title for m in bulunan] == ["otomasyon:posta", "otomasyon:rapor"]


def test_a_broken_mind_never_breaks_the_caller() -> None:
    class _Bozuk:
        def remember(self, *a, **k):
            raise RuntimeError("zihin düştü")

        def recall(self, *a, **k):
            raise RuntimeError("zihin düştü")

    assert workflow_mind.akisi_hatirla(_Bozuk(), None) is False
    assert workflow_mind.akislari_ara(_Bozuk(), "x") == []
