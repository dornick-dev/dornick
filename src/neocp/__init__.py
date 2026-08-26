"""neocp — bilgisayarı kullanabilen bir ajan harness'ı.

Katmanlar:
    config      yapılandırma
    events      append-only olay günlüğü (epizodik belleğin taşıyıcısı)
    session     olayları API mesajlarına projekte eder
    tools       araç kayıt defteri ve yürütücüsü
    permissions eylem öncesi politika kapısı
    context     önbellek breakpoint'leri ve bağlam budama
    client      Anthropic API sarmalayıcısı (streaming, iptal)
    loop        ajan döngüsü
"""

__version__ = "0.1.0"
