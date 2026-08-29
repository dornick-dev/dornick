I want a small short-link service in Python. Name it `servis.py`;
`py servis.py` must listen on port 8099.

Endpoints:

- `GET /saglik` → 200, so I can tell it is up.
- `POST /kisalt` → takes `{"url": "https://..."}` in the body, returns a
  code like `{"kod": "ab12cd"}`.
- `GET /<kod>` → redirect (302) to that code's address.
- An unknown code must return 404.

Write tests as well.
