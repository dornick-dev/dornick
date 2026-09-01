"""Komut süresi ölçer: benchmark kurar, A/B kıyaslar, rapor yazar.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "olcum"
DESCRIPTION = """Bir komutu N kez koşup süre istatistiği çıkarır (medyan,
min, maks); ikinci bir komut verilirse A/B kıyaslar ve farkı yüzdeyle
söyler. Algoritma/performans iddiası ölçmeden teslim edilmez: "daha
hızlı", "optimize ettim" demeden önce bunu koş. Rapor atölyeye
olcum-rapor.md olarak yazılır."""

SCHEMA = {
    "type": "object",
    "properties": {
        "komut": {"type": "string",
                  "description": "Ölçülecek komut (kabukta koşar)."},
        "kiyas": {"type": "string",
                  "description": "İsteğe bağlı ikinci komut: A/B kıyası."},
        "tekrar": {"type": "integer",
                   "description": "Koşu sayısı (varsayılan 5, en çok 20)."},
        "cwd": {"type": "string",
                "description": "Çalışma klasörü (varsayılan atölye)."},
    },
    "required": ["komut"],
}


def _kos(cmd, cwd, tekrar):
    import subprocess
    import time

    sureler = []
    son_kod = 0
    for _ in range(tekrar):
        t0 = time.perf_counter()
        done = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                              text=True, timeout=300)
        sureler.append(time.perf_counter() - t0)
        son_kod = done.returncode
        if son_kod != 0:
            # Bozuk komutu tekrar tekrar ölçmenin anlamı yok.
            return sureler, son_kod, (done.stderr or done.stdout or "")[-400:]
    return sureler, son_kod, ""


def _ozet(sureler):
    s = sorted(sureler)
    n = len(s)
    medyan = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"medyan": medyan, "min": s[0], "maks": s[-1], "n": n}


def run(args, ctx):
    from pathlib import Path

    komut = str(args.get("komut") or "").strip()
    if not komut:
        return "Komut boş."
    tekrar = max(1, min(int(args.get("tekrar") or 5), 20))
    cwd = str(args.get("cwd") or ctx.sandbox.root)
    if not Path(cwd).is_dir():
        return f"Çalışma klasörü yok: {cwd}"

    satirlar = [f"# Ölçüm — {tekrar} koşu", ""]
    a_sure, a_kod, a_hata = _kos(komut, cwd, tekrar)
    if a_kod != 0:
        return (f"Komut kırmızı (çıkış {a_kod}) — süre ölçümü anlamsız.\n"
                f"Önce yeşile çek:\n{a_hata}")
    a = _ozet(a_sure)
    satirlar.append(f"A `{komut}`: medyan {a['medyan']:.3f} sn "
                    f"(min {a['min']:.3f} / maks {a['maks']:.3f}, n={a['n']})")

    kiyas = str(args.get("kiyas") or "").strip()
    if kiyas:
        b_sure, b_kod, b_hata = _kos(kiyas, cwd, tekrar)
        if b_kod != 0:
            satirlar.append(f"B `{kiyas}`: KIRMIZI (çıkış {b_kod}) — {b_hata}")
        else:
            b = _ozet(b_sure)
            satirlar.append(f"B `{kiyas}`: medyan {b['medyan']:.3f} sn "
                            f"(min {b['min']:.3f} / maks {b['maks']:.3f})")
            if a["medyan"] > 0:
                fark = (b["medyan"] - a["medyan"]) / a["medyan"] * 100
                satirlar.append(f"Fark: B, A'ya göre {fark:+.1f}% "
                                + ("(B yavaş)" if fark > 0 else "(B hızlı)"))

    metin = "\n".join(satirlar)
    try:
        (ctx.sandbox.root / "olcum-rapor.md").write_text(metin + "\n",
                                                         encoding="utf-8")
        metin += "\n\nRapor: olcum-rapor.md"
    except OSError:
        pass
    return metin
