Write a small todo-list tool in Node named `gorev.js`. I will use it like
this:

    node gorev.js ekle "süt al"
    node gorev.js liste
    node gorev.js bitir 1

`liste` must show the items with their numbers, and a completed item must
be visibly marked as done. Items must live in `gorevler.json` so nothing
is lost when the program exits.

If I type a command that does not exist ("node gorev.js zıpla") it must
print an error and exit with a non-zero code.
