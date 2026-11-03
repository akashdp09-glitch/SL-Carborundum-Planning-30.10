"""Production-order (WO) number and SPEC decoding, as printed in the supplied training deck
'การอ่านใบสั่งงานการผลิต.pptx' (slides 3, 4, 5, 6). Only what the deck states is decoded; every other prefix is
returned as UNDOCUMENTED rather than guessed.

Factory no. = <prefix><seq>-<DDMMYY>   e.g. P005-150118 -> Vitrify made-to-order, 5th order, opened 15 Jan 2018.
The date is the date the order was OPENED (slide 4). It is not a due date and must never be reused as one (rule DATE-1).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

SOURCE = "การอ่านใบสั่งงานการผลิต.pptx"

PREFIX_TABLE = {
    # prefix: (bond family, order kind, Thai text as printed, slide)
    "P": ("VITRIFY", "MADE_TO_ORDER", "ใบสั่งงาน Vitrify สั่งทำ", 3),
    "PM": ("VITRIFY", "MONTHLY_CONTINUOUS", "ใบสั่งงาน Vitrify แผนรายเดือนที่ผลิตเป็นงานต่อเนื่อง", 3),
    "PS": ("VITRIFY", "MONTHLY_MADE_TO_ORDER", "ใบสั่งงาน Vitrify แผนรายเดือน สั่งทำ", 3),
    "PB": ("RESIN", "MADE_TO_ORDER", "ใบสั่งงาน Rasin สั่งทำ", 3),
    "PBM": ("RESIN", "MONTHLY_CONTINUOUS", "ใบสั่งงาน Rasin แผนรายเดือนที่ผลิตเป็นงานต่อเนื่อง", 3),
    "PBS": ("RESIN", "MONTHLY_MADE_TO_ORDER", "ใบสั่งงาน Rasin แผนรายเดือน สั่งทำ", 3),
}
# slide 5: temperature ranges that distinguish the two order families
TEMPERATURE_C = {"RESIN": (170, 185, "อบ / cure"), "VITRIFY": (1180, 1260, "เผา / fire")}

_WO = re.compile(r"^\s*([A-Za-z]{1,4}?)\s*(\d{3})\s*[-_ ]?\s*(\d{6})\s*$")


@dataclass(frozen=True)
class WOCode:
    raw: str
    normalized: str
    prefix: str
    seq: int
    opened_ddmmyy: str
    opened_date: dt.date | None
    family: str | None            # VITRIFY / RESIN / None when the deck does not document the prefix
    kind: str | None
    documented: bool
    source: str


def parse_wo(code: str) -> WOCode | None:
    m = _WO.match(str(code or ""))
    if not m:
        return None
    pre, seq, d = m.group(1).upper(), int(m.group(2)), m.group(3)
    try:
        opened = dt.date(2000 + int(d[4:6]), int(d[2:4]), int(d[0:2]))
    except ValueError:
        opened = None
    info = PREFIX_TABLE.get(pre)
    return WOCode(str(code), f"{pre}{seq:03d}-{d}", pre, seq, d, opened, info[0] if info else None, info[1] if info else None, info is not None,
                  f"{SOURCE} slide {info[3]}" if info else f"UNDOCUMENTED prefix '{pre}': not defined in {SOURCE}")


SPEC_FIELDS = ("abrasive", "grain", "structures", "structures_no", "product_type", "bond_type", "m_per_sec", "shape", "diameter", "thickness", "hold")
_SPEC = re.compile(r"^([A-Z]{1,3}?)(\d{1,3})([A-Z])(\d{1,2})([A-Z])([A-Z]\d{1,3})(\d{2})(\d[A-Z]{0,2})(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$")


def decode_spec(spec: str) -> dict | None:
    """Decode a SPEC string using the field names printed in the deck's table (slide 6).

    The deck gives a single worked example (WA60L8VB21351A152.4X3.17X31.75). The pattern below is fitted to that
    example only, so a SPEC that does not match returns None instead of a guess. Column labels are the deck's own;
    their physical meaning beyond the deck (e.g. 'Structures' = hardness letter) is NOT asserted here."""
    m = _SPEC.match(re.sub(r"\s+", "", str(spec or "").upper()))
    if not m:
        return None
    out = dict(zip(SPEC_FIELDS, m.groups()))
    for k in ("grain", "structures_no", "m_per_sec"):
        out[k] = int(out[k])
    for k in ("diameter", "thickness", "hold"):
        out[k] = float(out[k])
    out["source"] = f"{SOURCE} slide 6 (single worked example; pattern fitted to it)"
    return out
