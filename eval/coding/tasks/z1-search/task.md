Write a tool to search my notes, named `ara.py`. The workshop has my .txt
notes in a `notlar/` folder.

    py ara.py ekle notlar
    py ara.py bul "salmastra"

`ekle` indexes the notes in the folder; `bul` prints the matching notes'
file names and a snippet from each.

The index must persist in SQLite — after closing and reopening the
program I must not need to re-index; `bul` must work directly.

If I type several words ("rulman titresim") the notes containing all of
them must rank first. If nothing matches, say so explicitly.

Write its tests too.
