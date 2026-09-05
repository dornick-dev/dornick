"""Komut süresi ölçer: benchmark kurar, A/B kıyaslar, rapor yazar.

Standart yetenek — paketle geldi. Değiştirebilir, silebilirsin.
"""

NAME = "measure"
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


def _run(cmd, cwd, repeats):
    import subprocess
    import time

    durations = []
    son_kod = 0
    for _ in range(repeats):
        t0 = time.perf_counter()
        done = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                              text=True, timeout=300)
        durations.append(time.perf_counter() - t0)
        son_kod = done.returncode
        if son_kod != 0:
            # Bozuk komutu tekrar tekrar ölçmenin anlamı yok.
            return durations, son_kod, (done.stderr or done.stdout or "")[-400:]
    return durations, son_kod, ""


def _summary(durations):
    s = sorted(durations)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {"medyan": median, "min": s[0], "maks": s[-1], "n": n}


def run(args, ctx):
    from pathlib import Path

    command = str(args.get("komut") or "").strip()
    if not command:
        return "Komut boş."
    repeats = max(1, min(int(args.get("tekrar") or 5), 20))
    cwd = str(args.get("cwd") or ctx.sandbox.root)
    if not Path(cwd).is_dir():
        return f"Çalışma klasörü yok: {cwd}"

    lines = [f"# Ölçüm — {repeats} koşu", ""]
    a_time, a_kod, a_err = _run(command, cwd, repeats)
    if a_kod != 0:
        return (f"Komut kırmızı (çıkış {a_kod}) — süre ölçümü anlamsız.\n"
                f"Önce yeşile çek:\n{a_err}")
    a = _summary(a_time)
    lines.append(f"A `{command}`: medyan {a['medyan']:.3f} sn "
                    f"(min {a['min']:.3f} / maks {a['maks']:.3f}, n={a['n']})")

    compare = str(args.get("kiyas") or "").strip()
    if compare:
        b_time, b_kod, b_err = _run(compare, cwd, repeats)
        if b_kod != 0:
            lines.append(f"B `{compare}`: KIRMIZI (çıkış {b_kod}) — {b_err}")
        else:
            b = _summary(b_time)
            lines.append(f"B `{compare}`: medyan {b['medyan']:.3f} sn "
                            f"(min {b['min']:.3f} / maks {b['maks']:.3f})")
            if a["medyan"] > 0:
                diff = (b["medyan"] - a["medyan"]) / a["medyan"] * 100
                lines.append(f"Fark: B, A'ya göre {diff:+.1f}% "
                                + ("(B yavaş)" if diff > 0 else "(B hızlı)"))

    text = "\n".join(lines)
    try:
        (ctx.sandbox.root / "olcum-rapor.md").write_text(text + "\n",
                                                         encoding="utf-8")
        text += "\n\nRapor: olcum-rapor.md"
    except OSError:
        pass
    return text
