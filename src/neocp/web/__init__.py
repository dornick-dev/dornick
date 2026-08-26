"""Zihin arayüzü.

Yalnızca standart kütüphane. Kullanıcı tarafında Node, npm ya da derleme
adımı yok: `pip install` yeter, arayüz tek bir HTML dosyası olarak servis
edilir.
"""

from __future__ import annotations

from .graph import build_graph
from .server import MindServer

__all__ = ["MindServer", "build_graph"]
