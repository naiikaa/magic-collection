"""Moxfield API helpers for deck import."""
import re
import time
import requests

from scryfall import get_image_url

MOXFIELD_API = "https://api.moxfield.com/v2/decks/all/"
MOXFIELD_URL_RE = re.compile(r"https?://(?:www\.)?moxfield\.com/decks/([a-zA-Z0-9_-]+)")
HEADERS = {"User-Agent": "cEDHcube/1.0 (personal project)"}


def extract_deck_id(url):
    """Extract the Moxfield deck publicId from a URL."""
    m = MOXFIELD_URL_RE.search(url.strip())
    if m:
        return m.group(1)
    # If the user just pasted the ID directly
    if re.match(r"^[a-zA-Z0-9_-]+$", url.strip()):
        return url.strip()
    return None


def fetch_moxfield_deck(public_id):
    """Fetch a deck from Moxfield API.

    Returns a dict with:
        - name: deck name
        - format: deck format (e.g. 'commander')
        - commander_name: name of the commander card (or None)
        - commander_image_url: image URL of the commander (or None)
        - cards: list of (quantity, card_name, set_code, scryfall_id, image_url,
                          mana_cost, type_line, colors, color_identity, cmc)
    Returns None if the deck could not be fetched.
    """
    try:
        resp = requests.get(MOXFIELD_API + public_id, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    name = data.get("name", "Imported Deck")
    fmt = data.get("format", "commander")

    # Extract commander info
    commander_name = None
    commander_image_url = None
    commanders = data.get("commanders", {})
    if commanders:
        first_cmd = next(iter(commanders.values()))
        cmd_card = first_cmd.get("card", {})
        commander_name = cmd_card.get("name", "")
        commander_image_url = _get_card_image_url(cmd_card)

    # Build cards list: commanders first, then mainboard
    cards = []

    # Add commander cards first
    for entry in commanders.values():
        card = entry.get("card", {})
        quantity = entry.get("quantity", 1)
        cards.append(_parse_card_entry(card, quantity))

    # Add mainboard cards
    mainboard = data.get("mainboard", {})
    for entry in mainboard.values():
        card = entry.get("card", {})
        quantity = entry.get("quantity", 1)
        cards.append(_parse_card_entry(card, quantity))

    # Also include sideboard if present (but skip for now - commander decks don't usually have side)
    # We could add a note about it

    return {
        "name": name,
        "format": fmt,
        "commander_name": commander_name,
        "commander_image_url": commander_image_url,
        "cards": cards,
    }


def _parse_card_entry(card, quantity):
    """Parse a Moxfield card entry into our format."""
    set_code = card.get("set", "")
    scryfall_id = card.get("scryfall_id", "")
    image_url = _get_card_image_url(card)
    mana_cost = card.get("mana_cost", "")
    type_line = card.get("type_line", "")
    colors = card.get("colors", [])
    color_identity = card.get("color_identity", [])
    cmc = card.get("cmc", 0)

    return (
        quantity,
        card.get("name", ""),
        set_code,
        scryfall_id,
        image_url,
        mana_cost,
        type_line,
        colors,
        color_identity,
        cmc,
    )


def _get_card_image_url(card):
    """Get the best image URL from a Moxfield card object."""
    if "card_faces" in card and card["card_faces"]:
        face = card["card_faces"][0]
        imgs = face.get("image_uris", {})
        return imgs.get("normal", imgs.get("small", ""))
    imgs = card.get("image_uris", {})
    return imgs.get("normal", imgs.get("small", ""))


SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"


def fetch_card_images_bulk(scryfall_ids):
    """Fetch image URLs for multiple cards from Scryfall by their scryfall IDs.

    Returns a dict mapping {scryfall_id: image_url}.
    Handles bulk requests in batches of 75 (Scryfall limit).
    """
    result = {}
    # Filter out empty IDs
    ids = [sid for sid in scryfall_ids if sid]
    # Deduplicate
    ids = list(set(ids))

    for i in range(0, len(ids), 75):
        batch = ids[i:i+75]
        payload = {"identifiers": [{"id": sid} for sid in batch]}
        try:
            resp = requests.post(SCRYFALL_COLLECTION, json=payload, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for card in data.get("data", []):
                    img_url = get_image_url(card)
                    if img_url:
                        result[card["id"]] = img_url
        except Exception:
            pass
        # Be nice to the API
        if i + 75 < len(ids):
            time.sleep(0.1)

    return result
