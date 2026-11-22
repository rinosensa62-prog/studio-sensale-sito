#!/usr/bin/env python3
"""Remove only accidentally introduced news widget from already verified Netlify release ZIP."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import re, sys

src = Path(sys.argv[1] if len(sys.argv) > 1 else "source/studio-sensale-notizie-live.zip")
dst = Path(sys.argv[2] if len(sys.argv) > 2 else "studio-sensale-home-originale.zip")
if not src.is_file():
    raise RuntimeError(f"Pacchetto origine non trovato: {src}")
removed = 0
with ZipFile(src) as old:
    names = set(old.namelist())
    assert "index.html" in names and "notizie/index.html" in names
    assert "argomenti/fisco-dichiarazioni/index.html" in names
    assert "assets/studio-news-live.js" in names
    with ZipFile(dst, "w", ZIP_DEFLATED) as new:
        for info in old.infolist():
            if info.filename == "assets/studio-news-live.js":
                continue
            body = old.read(info.filename)
            if info.filename.endswith(".html"):
                original = body
                body = re.sub(
                    rb'\s*<script\s+src=["\']/assets/studio-news-live\.js["\']\s+defer\s*></script>',
                    b"", body, flags=re.I)
                if body != original: removed += 1
            new.writestr(info, body)
assert removed >= 45, f"Iniezione script non trovata nel numero previsto di pagine: {removed}"
with ZipFile(dst) as check:
    names = set(check.namelist())
    assert "assets/studio-news-live.js" not in names
    assert len([n for n in names if n.endswith("index.html")]) >= 45
    for p in ["index.html", "notizie/index.html", "argomenti/fisco-dichiarazioni/index.html"]:
        assert b"studio-news-live.js" not in check.read(p)
print(f"Ripristino verificato: {len(names)} file, {removed} pagine corrette, nessun'altra modifica HTML.")
