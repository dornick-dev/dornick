"""Sepet regresyon takımı. Bu dosya DOĞRU — kod ona uymalı."""

from __future__ import annotations

import pytest

from sepet import (
    ara_toplam,
    cikar,
    ekle,
    indirim_orani,
    kalem_sayisi,
    toplam,
)


def test_bos_sepet_sifir():
    assert toplam({}) == 0.0


def test_ara_toplam_hesabi():
    s = {}
    ekle(s, "kablo", 25.0, 4)
    assert ara_toplam(s) == 100.0


def test_negatif_adet_reddediliyor():
    with pytest.raises(ValueError):
        ekle({}, "kablo", 25.0, 0)


def test_cikar_kalemi_siliyor():
    s = {}
    ekle(s, "kablo", 25.0, 4)
    cikar(s, "kablo")
    assert s == {}


def test_alti_yuz_lirada_yuzde_bes():
    s = {}
    ekle(s, "pano", 100.0, 6)
    assert toplam(s) == 570.0


def test_ayni_urun_iki_kez_eklenince_adetler_toplaniyor():
    s = {}
    ekle(s, "kablo", 10.0, 2)
    ekle(s, "kablo", 10.0, 3)
    assert kalem_sayisi(s) == 5
    assert ara_toplam(s) == 50.0


def test_tam_bin_lirada_yuzde_on_indirim():
    s = {}
    ekle(s, "pompa", 1000.0, 1)
    assert indirim_orani(1000.0) == pytest.approx(0.10)
    assert toplam(s) == pytest.approx(900.0)


def test_toplam_kurusu_koruyor():
    s = {}
    ekle(s, "vida", 33.33, 3)
    assert toplam(s) == pytest.approx(99.99)
