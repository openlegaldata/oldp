"""Sanity checks for German ECLIs supplied by upstream portals.

The portals are not always right about a decision's ECLI (#255): the Berlin
portal shows swapped ECLIs on pairs of decisions, NI-VORIS attaches ECLIs of
other states' courts, and the Hessen portal renders ``ECLI:ECLI:DE:…``. The
ingestor copies the value verbatim, so the check lives here, where every
source's cases arrive.

A German ECLI encodes the decision date and the docket number in its ordinal
(``ECLI:DE:VGBE:2018:0221.VG18L43.18.00`` is VG Berlin, 21 February 2018,
``18 L 43.18``). The formats differ per court and drop, pad or truncate parts
of the docket, so the check is deliberately loose: an ECLI only *contradicts*
a case when neither its docket numbers nor its day and month agree with the
case. Replayed against the 320k ECLIs in production this flags 26, nearly all
of them the misattributions reported in #255.
"""

import datetime
import re
from typing import Optional, Tuple

_REPEATED_PREFIX = re.compile(r"^(?:ECLI:)+", re.IGNORECASE)
_GERMAN_ECLI = re.compile(
    r"^ECLI:DE:(?P<court>[A-Za-z0-9]+):(?P<year>\d{4}):(?P<ordinal>.+)$",
    re.IGNORECASE,
)
# BVerfG: two-letter decision kind + YYYYMMDD, e.g. "rk20201208.1bvr011716".
_BVERFG_ORDINAL = re.compile(r"^[a-z]{2}(\d{4})(\d{2})(\d{2})\.(.*)$", re.IGNORECASE)
# Länder courts: MMDD, e.g. "0221.VG18L43.18.00".
_LAENDER_ORDINAL = re.compile(r"^(\d{2})(\d{2})\.(.*)$")
# Federal courts: DDMMYY + decision kind, e.g. "261115B2STR144.15.0".
_FEDERAL_ORDINAL = re.compile(r"^(\d{2})(\d{2})(\d{2})(.*)$")
# Separators between several file numbers in one field.
_FILE_NUMBER_SEPARATORS = re.compile(r"[,;+]|\bund\b|\s-\s")
# Leading register number, e.g. "(64) 4 T 184/21" (Thüringen) or "(4) 161 Ss …" (KG).
_LEADING_REGISTER = re.compile(r"^\s*\(\d+\)\s*")
# How many leading numbers of a file number must appear in the ECLI docket.
# Beyond three, ECLIs are often truncated.
_DOCKET_NUMBERS_COMPARED = 3


def normalize_ecli(ecli: Optional[str]) -> str:
    """Strip whitespace and collapse a repeated ``ECLI:`` prefix.

    ``"ECLI:ECLI:DE:VGFFM:2019:…"`` -> ``"ECLI:DE:VGFFM:2019:…"``.
    Returns ``""`` for ``None`` or blank input.
    """
    ecli = (ecli or "").strip()
    if not ecli:
        return ""
    return _REPEATED_PREFIX.sub("ECLI:", ecli)


def _date(year: int, month: int, day: int) -> Optional[datetime.date]:
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def split_ordinal(year: str, ordinal: str) -> Tuple[Optional[datetime.date], str]:
    """Split an ECLI ordinal into its decision date and its docket part.

    Returns ``(None, ordinal)`` when the ordinal carries no recognisable date.
    """
    m = _BVERFG_ORDINAL.match(ordinal)
    if m:
        return _date(int(m[1]), int(m[2]), int(m[3])), m[4]
    m = _LAENDER_ORDINAL.match(ordinal)
    if m:
        return _date(int(year), int(m[1]), int(m[2])), m[3]
    m = _FEDERAL_ORDINAL.match(ordinal)
    if m:
        return _date(2000 + int(m[3]), int(m[2]), int(m[1])), m[4]
    return None, ordinal


def docket_matches(docket: str, file_number: Optional[str]) -> bool:
    """Whether one of the file numbers appears in the ECLI's docket part.

    Compares numbers only, in order and ignoring leading zeros, because the
    letters and separators vary per court ("34 L 73.18 A" is "VG34L73.18A",
    "1 BvR 117/16" is "1bvr011716").
    """
    digits = re.sub(r"\D", "", docket)
    for piece in _FILE_NUMBER_SEPARATORS.split(file_number or ""):
        numbers = re.findall(r"\d+", _LEADING_REGISTER.sub("", piece))
        if not numbers:
            continue
        pos = 0
        for number in numbers[:_DOCKET_NUMBERS_COMPARED]:
            m = re.compile(r"0*" + str(int(number))).search(digits, pos)
            if not m:
                break
            pos = m.end()
        else:
            return True
    return False


def parse_ecli(
    ecli: Optional[str],
) -> Optional[Tuple[str, Optional[datetime.date], str]]:
    """Split a German ECLI into ``(court, date, docket)``.

    ``"ECLI:DE:VGBE:2018:0221.VG18L43.18.00"`` ->
    ``("VGBE", date(2018, 2, 21), "VG18L43.18.00")``. The date is ``None``
    when the ordinal carries none. Returns ``None`` for anything that is not
    a German ECLI.
    """
    m = _GERMAN_ECLI.match(normalize_ecli(ecli))
    if not m:
        return None
    ecli_date, docket = split_ordinal(m["year"], m["ordinal"])
    return m["court"], ecli_date, docket


def ecli_contradicts_case(
    ecli: Optional[str], file_number: Optional[str], date
) -> bool:
    """Whether a German ECLI clearly belongs to a different decision.

    True only when the docket numbers do not match *and* the ECLI's day and
    month differ from the case date. The year is not compared: portals get
    it wrong on otherwise correct ECLIs. Non-German, unparseable or dateless
    ECLIs are never reported as contradicting.

    Args:
        ecli: The ECLI, normalised or not.
        file_number: The case's file number(s).
        date: The case date (``datetime.date`` or ``YYYY-MM-DD``).
    """
    parsed = parse_ecli(ecli)
    if parsed is None or not file_number:
        return False
    _, ecli_date, docket = parsed
    if docket_matches(docket, file_number):
        return False
    if isinstance(date, str):
        try:
            date = datetime.date.fromisoformat(date)
        except ValueError:
            return False
    if ecli_date is None or not isinstance(date, datetime.date):
        return False
    return (ecli_date.month, ecli_date.day) != (date.month, date.day)
