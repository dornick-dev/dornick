'use strict';

/**
 * Küçük bir kitaplık defteri.
 * Kitaplar ISBN ile tutuluyor; ISBN benzersiz.
 */
class Kitaplik {
  constructor() {
    this.kitaplar = new Map();
  }

  ekle(isbn, baslik, yazar) {
    if (!isbn || !baslik) {
      throw new Error('ISBN ve başlık zorunlu');
    }
    if (this.kitaplar.has(isbn)) {
      throw new Error(`Bu ISBN zaten kayıtlı: ${isbn}`);
    }
    this.kitaplar.set(isbn, { isbn, baslik, yazar: yazar || 'bilinmiyor' });
    return this.kitaplar.get(isbn);
  }

  bul(isbn) {
    return this.kitaplar.get(isbn) || null;
  }

  sil(isbn) {
    return this.kitaplar.delete(isbn);
  }

  liste() {
    return [...this.kitaplar.values()].sort((a, b) =>
      a.baslik.localeCompare(b.baslik, 'tr'));
  }

  get sayi() {
    return this.kitaplar.size;
  }
}

module.exports = { Kitaplik };
