"""Analysis routines. Each takes tables plus config and returns plain dataclasses."""

from .branded import BrandSplit, compile_brand, is_branded, split_branded
from .breakdown import ShareRow, breakdown
from .cannibalisation import Cannibalisation, find_cannibalisation, normalize_url
from .compare import Change, compare, declining
from .movers import Movers, find_movers
from .quick_wins import QuickWin, quick_wins

__all__ = [
    "BrandSplit",
    "Cannibalisation",
    "Change",
    "Movers",
    "QuickWin",
    "ShareRow",
    "breakdown",
    "compare",
    "compile_brand",
    "declining",
    "find_cannibalisation",
    "find_movers",
    "is_branded",
    "normalize_url",
    "quick_wins",
    "split_branded",
]
