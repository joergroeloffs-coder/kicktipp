"""Gemeinsamer Fuzzy-Abgleich von Vereinsnamen.

OpenLigaDB nutzt volle Vereinsnamen ("SV Werder Bremen", "Borussia
Moenchengladbach"), Kicktipp zeigt oft kuerzere/abgekuerzte Varianten
("Werder Bremen", "Bor. Moenchengladbach"). Generische Vereinspraefixe/
-suffixe werden beim Vergleich ignoriert, damit der Abgleich ueber den
eigentlichen (unterscheidenden) Vereinsnamen funktioniert.
"""
from __future__ import annotations

import re
import unicodedata

_CLUB_STOPWORDS = {
    "fc", "sv", "sc", "sg", "vfl", "vfb", "tsv", "tsg", "fsv", "bsc",
    "spvgg", "borussia", "bor", "dynamo", "fk", "fka", "vfr", "ssv",
}


def fold(text: str) -> str:
    """Entfernt diakritische Zeichen (Umlaute/Akzente), damit der Vergleich
    unabhaengig von deren Schreibweise funktioniert."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def tokens(name: str) -> set[str]:
    folded = fold(name.lower())
    raw = re.split(r"[^a-z0-9]+", folded)
    return {t for t in raw if t and t not in _CLUB_STOPWORDS and len(t) >= 3}


def names_match(name_a: str, name_b: str) -> bool:
    a, b = tokens(name_a), tokens(name_b)
    if not a or not b:
        return False
    return bool(a & b)
