Write a module named `tckn.py` into the workshop. It must contain a
function `dogrula(no)` that checks whether the given Turkish national ID
number is valid: 11 digits, all numeric, the first digit not 0; the 10th
digit is ((sum of the odd-position digits among the first nine) × 7 −
(sum of the even-position digits)) mod 10; the 11th digit is (sum of the
first ten digits) mod 10.

Return True when valid, False otherwise. Broken input can arrive too
(empty string, letters, None instead of a number) — do not crash, return
False.

Write tests for it as well.
