"""Oturum kaydından DAVRANIŞ ölçütleri — puana katılmaz, raporlanır.

Puan "ne teslim etti"yi ölçüyor. Bu dosya "nasıl çalıştı"yı ölçüyor: kaç araç
çağırdı, kendi kodunu doğruladı mı, plan yazdı mı, kaç token yaktı. İkisi
ayrı tutuluyor çünkü davranış bir HİPOTEZ kaynağı, bir hedef değil: "plan
yazana puan" dersek ajan plan yazar, kod yine çalışmaz.

Dürüstlük kuralı burada da geçerli: her ölçüt oturum günlüğündeki SOMUT bir
kayda dayanıyor. Kanıt bulunamayan ölçüt `None` döner ("çıkarılamadı"), 0
dönmez — "doğrulamadı" ile "günlükten okuyamadım" farklı şeyler.

Günlük biçimi (neocp.events.EventLog, JSONL):
  {"kind":"meta","content":"tool_start","meta":{"tool":"shell","input":{...}}}
  {"kind":"meta","content":"tool_end","meta":{"tool":"...","error":bool,"ms":int}}
  {"kind":"message","role":"assistant","content":[...],"meta":{"usage":{...}}}
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# Kendi kodunu doğrulama izi: kabuktan koşturulan sınayıcılar.
DOGRULAMA_KOMUT = re.compile(
    r"\bpytest\b|\bunittest\b|python\s+-m\s+py_compile|\bpy_compile\b|"
    r"\bruff\b|\bmypy\b|node\s+--test|node\s+--check|\bnpm\s+test\b|"
    r"php\s+-l\b|\bphpunit\b|\bcurl\b|Invoke-WebRequest|\bwget\b|"
    r"python\s+-c|py\s+-c|node\s+-e|php\s+-r",
    re.IGNORECASE,
)
# Ürünü gerçekten koşturmak da doğrulamadır: `py servis.py`, `node gorev.js …`
CALISTIRMA_KOMUT = re.compile(
    r"^\s*(py|python|python3|node|php)\s+[\w./\\-]+\.(py|js|mjs|php)\b",
    re.IGNORECASE | re.MULTILINE,
)
# Tanı/tarayıcı araçları: adı yetiyor.
DOGRULAMA_ARAC = {"denetle", "browser"}

# Plan izi: numaralı ya da imli en az üç satır, ilk araç çağrısından önce.
PLAN_SATIR = re.compile(r"^\s*(?:\d+[.)]\s+|[-*•]\s+|\[[ x]\]\s*)", re.MULTILINE)


def _metin(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(str(b.get("text", "")) for b in content
                     if isinstance(b, dict) and b.get("type") == "text")


def olaylar(gunluk: Path) -> list[dict[str, Any]]:
    if not gunluk.is_file():
        return []
    cikan: list[dict[str, Any]] = []
    for satir in gunluk.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            cikan.append(json.loads(satir))
        except ValueError:
            continue
    return cikan


def cikar(gunluk: Path, *, kapi: dict[str, Any] | None = None,
          model_adi: str = "", durum_dizini: Path | None = None) -> dict[str, Any]:
    """Oturum günlüğünden davranış ölçütlerini çıkarır.

    `kapi`: dış kapının (POST /api/gate) döndürdüğü sözlük — süre ve değişen
    dosyalar oradan geliyor, günlükte yok.
    """
    kayitlar = olaylar(gunluk)
    if not kayitlar:
        return {"cikarilamadi": f"oturum günlüğü okunamadı: {gunluk}"}

    araclar: Counter[str] = Counter()
    hatali = 0
    dogrulama: list[str] = []
    calistirma: list[str] = []
    ilk_arac_seq: int | None = None
    plan_kaniti = ""
    turlar = 0
    cikti_token = 0
    son_prompt = 0
    prompt_toplam = 0
    cagri = 0
    api_hatasi = 0

    for ev in kayitlar:
        tur = ev.get("kind")
        icerik = ev.get("content")
        meta = ev.get("meta") or {}

        if tur == "meta" and icerik == "tool_start":
            ad = str(meta.get("tool") or "")
            araclar[ad] += 1
            if ilk_arac_seq is None:
                ilk_arac_seq = int(ev.get("seq") or 0)
            girdi = meta.get("input")
            komut = ""
            if isinstance(girdi, dict):
                komut = str(girdi.get("command") or girdi.get("path") or "")
            if ad in DOGRULAMA_ARAC:
                dogrulama.append(f"{ad}: {komut[:70]}")
            elif ad == "shell" and komut:
                if DOGRULAMA_KOMUT.search(komut):
                    dogrulama.append(f"shell: {komut[:90]}")
                elif CALISTIRMA_KOMUT.search(komut):
                    calistirma.append(f"shell: {komut[:90]}")

        elif tur == "meta" and icerik == "tool_end":
            if meta.get("error"):
                hatali += 1

        elif tur == "meta" and icerik == "api_error":
            api_hatasi += 1

        elif tur == "message" and ev.get("role") == "assistant":
            turlar += 1
            kullanim = meta.get("usage")
            if isinstance(kullanim, dict) and kullanim.get("prompt_total"):
                son_prompt = int(kullanim.get("prompt_total") or 0)
                prompt_toplam += son_prompt
                cikti_token += int(kullanim.get("output") or 0)
                cagri += 1
            # Plan: ilk araç çağrısından ÖNCEKİ metinde listeli anlatım.
            if ilk_arac_seq is None and not plan_kaniti:
                govde = _metin(ev.get("content"))
                if len(PLAN_SATIR.findall(govde)) >= 3:
                    plan_kaniti = " ".join(govde.split())[:120]

    maliyet = _maliyet(model_adi, prompt_toplam, cikti_token, durum_dizini)

    cikan: dict[str, Any] = {
        "arac_cagrisi": sum(araclar.values()),
        "araclar": dict(araclar.most_common()),
        "hatali_arac": hatali,
        "model_turu": turlar,
        "api_hatasi": api_hatasi,
        "dogruladi_mi": bool(dogrulama),
        "dogrulama_izi": dogrulama[:8],
        "calistirma_izi": calistirma[:5],
        "plan_yazdi_mi": bool(plan_kaniti),
        "plan_kaniti": plan_kaniti,
        # `prompt_son` bağlamın en son ne kadar dolduğu; `prompt_toplam`
        # faturaya giren şey (her çağrı kendi promptunu ödetiyor).
        "token_prompt_son": son_prompt or None,
        "token_prompt_toplam": prompt_toplam or None,
        "token_cikti": cikti_token or None,
        "model_cagrisi": cagri or None,
        "maliyet_usd": maliyet,
    }
    if kapi:
        cikan["sure_sn"] = kapi.get("gecen_sn")
        cikan["degisen_dosya"] = len(kapi.get("dosyalar") or [])
        cikan["kapi_ok"] = bool(kapi.get("ok"))
        if not kapi.get("ok"):
            cikan["kapi_hatasi"] = kapi.get("error")
    if not cagri:
        # Sağlayıcı sayaç vermediyse uydurmuyoruz.
        cikan["token_notu"] = "sağlayıcı token sayacı vermedi — ölçülemedi"
    return cikan


def _maliyet(model_adi: str, prompt_token: int, cikti_token: int,
             durum_dizini: Path | None) -> float | None:
    """USD maliyet — ürünün kendi fiyat tablosundan. Fiyat bilinmiyorsa None.

    `fiyat.etiket` katalogda olmayan model ya da başka sağlayıcı için None
    döndürüyor; biz de None döndürüyoruz. Uydurma bir rakam basmıyoruz.
    """
    if not model_adi or not prompt_token:
        return None
    try:
        from neocp.config import ModelConfig, OPENROUTER_URL
        from neocp import fiyat as fiyat_modulu
    except Exception:
        return None
    try:
        etiket = fiyat_modulu.etiket(
            ModelConfig(name=model_adi, base_url=OPENROUTER_URL),
            durum_dizini, ag=False)
    except Exception:
        return None
    if not etiket:
        return None
    return round(prompt_token * etiket["girdi"] + cikti_token * etiket["cikti"], 4)
