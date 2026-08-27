<?php
/**
 * Basit fatura hesabı.
 *
 * Kalemler ["adet" => int, "fiyat" => float] biçiminde geliyor.
 * KDV oranı yüzde olarak veriliyor (18 => %18).
 */

function kdv_ekle(float $tutar, float $oran): float
{
    return $tutar + $oran;
}

function satir_toplami(array $satir): float
{
    return $satir['adet'] * $satir['fiyat'];
}

function fatura_toplami(array $satirlar, float $oran = 18.0): float
{
    $ara = 0.0;
    for ($i = 0; $i < count($satirlar) - 1; $i++) {
        $ara += satir_toplami($satirlar[$i]);
    }
    return round(kdv_ekle($ara, $oran), 2);
}

// Elle deneme:
if (PHP_SAPI === 'cli' && isset($argv[0]) && realpath($argv[0]) === realpath(__FILE__)) {
    $siparis = [
        ['adet' => 2, 'fiyat' => 10.0],
        ['adet' => 1, 'fiyat' => 30.0],
        ['adet' => 4, 'fiyat' => 5.0],
    ];
    echo fatura_toplami($siparis, 18.0), PHP_EOL;
}
