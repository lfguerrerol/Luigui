"""
Map a retailer's free-text category/breadcrumb onto the category keys our FBA
fee calculator understands (see fba_calculator.REFERRAL_FEE_PCT).

Retailers all use different taxonomies, so this is a best-effort keyword match.
Unknown categories fall back to "default" (15% referral fee).
"""
from __future__ import annotations

# Ordered: first keyword that appears in the source category string wins.
_KEYWORD_TO_CATEGORY = [
    (("laptop", "computer", "monitor", "keyboard", "printer"), "computers"),
    (("electronic", "phone", "headphone", "camera", "tv", "charger", "cable", "audio"), "electronics"),
    # Check tools BEFORE home so "Home Improvement" doesn't match the "home" key.
    (("tool", "hardware", "drill", "improvement", "paint", "plumbing", "garden", "outdoor power"), "tools_home_improvement"),
    (("kitchen", "cookware", "appliance", "vacuum", "home", "furniture", "bedding", "decor"), "home_kitchen"),
    (("toy", "game", "lego", "puzzle", "doll", "hobby"), "toys_games"),
    (("grocery", "food", "snack", "beverage", "coffee", "pantry", "household essential", "cleaning"), "grocery"),
    (("beauty", "health", "personal care", "vitamin", "supplement", "skin", "hair", "wellness"), "health_beauty"),
    (("cloth", "apparel", "shoe", "shirt", "dress", "jacket", "fashion"), "clothing"),
    (("pet", "dog", "cat"), "pet_supplies"),
    (("office", "school", "stationery", "paper"), "office_products"),
    (("sport", "fitness", "exercise", "camp", "bike", "outdoor rec"), "sports_outdoors"),
]


def map_category(raw: str | None) -> str:
    if not raw:
        return "default"
    text = raw.lower()
    for keywords, cat in _KEYWORD_TO_CATEGORY:
        if any(k in text for k in keywords):
            return cat
    return "default"
