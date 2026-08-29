`fatura.php` in the workshop calculates the wrong total.

For a 3-line order (2 × 10 TL, 1 × 30 TL, 4 × 5 TL) with 18% VAT the total
must be **82.60**. Running `php fatura.php` prints **68**.

Find the cause and fix it. Keep the function names — I call them from
elsewhere.
