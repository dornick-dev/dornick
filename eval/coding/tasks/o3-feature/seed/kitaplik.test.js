'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { Kitaplik } = require('./kitaplik');

test('kitap eklenebiliyor', () => {
  const k = new Kitaplik();
  const kayit = k.ekle('978-1', 'Kuyu', 'Ahmet');
  assert.strictEqual(kayit.baslik, 'Kuyu');
  assert.strictEqual(k.sayi, 1);
});

test('aynı ISBN iki kez eklenemiyor', () => {
  const k = new Kitaplik();
  k.ekle('978-1', 'Kuyu', 'Ahmet');
  assert.throws(() => k.ekle('978-1', 'Başka', 'Mehmet'), /zaten kayıtlı/);
});

test('bul olmayan ISBN icin null donuyor', () => {
  const k = new Kitaplik();
  assert.strictEqual(k.bul('yok'), null);
});

test('liste basliga gore sirali', () => {
  const k = new Kitaplik();
  k.ekle('978-2', 'Zeytin', 'Ayşe');
  k.ekle('978-1', 'Ateş', 'Ahmet');
  const adlar = k.liste().map((x) => x.baslik);
  assert.deepStrictEqual(adlar, ['Ateş', 'Zeytin']);
});

test('sil kaydi kaldiriyor', () => {
  const k = new Kitaplik();
  k.ekle('978-1', 'Kuyu', 'Ahmet');
  assert.strictEqual(k.sil('978-1'), true);
  assert.strictEqual(k.sayi, 0);
});
