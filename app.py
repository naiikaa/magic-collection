"""Main Flask application for cEDHcube."""
import threading
from flask import Flask, render_template, request, jsonify, redirect, url_for
from database import (
    init_db, add_deck, get_decks, get_deck, rename_deck, delete_deck,
    add_card_to_deck, get_deck_cards, update_card, delete_card,
    clear_deck_cards, get_collection, get_db, get_deck_color_identity,
    update_deck_color, update_deck_commander,
    get_cards_missing_images, update_card_image,
    get_decks_missing_commander_images, update_deck_commander_image,
    get_deck_cmc_distribution,
)
from scryfall import parse_card_list, validate_and_resolve_card
from moxfield import fetch_moxfield_deck, extract_deck_id, fetch_card_images_bulk

app = Flask(__name__)


def refresh_all_images():
    """Refresh missing card and commander images in the background."""
    # Refresh card images
    missing = get_cards_missing_images()
    if missing:
        scryfall_ids = [c["scryfall_id"] for c in missing]
        id_to_url = fetch_card_images_bulk(scryfall_ids)
        for card in missing:
            url = id_to_url.get(card["scryfall_id"])
            if url:
                update_card_image(card["id"], url)

    # Refresh commander images
    missing_cmd = get_decks_missing_commander_images()
    if missing_cmd:
        scryfall_ids = [c["scryfall_id"] for c in missing_cmd]
        id_to_url = fetch_card_images_bulk(scryfall_ids)
        for entry in missing_cmd:
            url = id_to_url.get(entry["scryfall_id"])
            if url:
                update_deck_commander_image(entry["deck_id"], url)


init_db()


@app.before_request
def setup():
    init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/decks", methods=["GET"])
def api_decks():
    decks = get_decks()
    return jsonify(decks)


@app.route("/api/decks", methods=["POST"])
def api_add_deck():
    data = request.get_json()
    name = data.get("name", "").strip()
    card_list_text = data.get("card_list", "")
    color = data.get("color", "").strip()

    if not name:
        return jsonify({"error": "Deck name is required"}), 400

    existing = get_decks()
    if any(d["name"].lower() == name.lower() for d in existing):
        return jsonify({"error": "A deck with this name already exists"}), 409

    deck_id = add_deck(name, color=color if color else None)

    # If card_list provided, validate and add cards
    results = []
    commander_name = None
    commander_image_url = None
    if card_list_text.strip():
        parsed = parse_card_list(card_list_text)
        if not parsed:
            return jsonify({"id": deck_id, "name": name, "error": "Could not parse any cards"}), 201
        for quantity, card_name, set_code in parsed:
            resolved = validate_and_resolve_card(card_name, set_code)
            if resolved:
                add_card_to_deck(
                    deck_id,
                    card_name=resolved["name"],
                    quantity=quantity,
                    set_code=resolved["set_code"],
                    scryfall_id=resolved["scryfall_id"],
                    image_url=resolved["image_url"],
                    mana_cost=resolved.get("mana_cost", ""),
                    colors=resolved.get("colors", []),
                    color_identity=resolved.get("color_identity", []),
                    cmc=resolved.get("cmc", 0),
                    type_line=resolved.get("type_line", ""),
                )
                # Auto-detect commander: first legendary creature
                if not commander_name:
                    type_line = (resolved.get("type_line", "") or "").lower()
                    if "legendary" in type_line and "creature" in type_line:
                        commander_name = resolved["name"]
                        commander_image_url = resolved["image_url"]
                results.append({
                    "status": "ok",
                    "requested": card_name,
                    "resolved": resolved["name"],
                    "quantity": quantity,
                    "image_url": resolved["image_url"],
                })
            else:
                add_card_to_deck(
                    deck_id,
                    card_name=card_name,
                    quantity=quantity,
                    set_code=set_code or "",
                )
                results.append({
                    "status": "not_found",
                    "requested": card_name,
                    "quantity": quantity,
                })

    if commander_name:
        update_deck_commander(deck_id, commander_name, commander_image_url)

    return jsonify({"id": deck_id, "name": name, "results": results}), 201


@app.route("/api/decks/import", methods=["POST"])
def api_import_deck():
    data = request.get_json()
    url = data.get("url", "").strip()
    color = data.get("color", "").strip()

    if not url:
        return jsonify({"error": "Moxfield URL is required"}), 400

    public_id = extract_deck_id(url)
    if not public_id:
        return jsonify({"error": "Could not extract a Moxfield deck ID from the URL"}), 400

    moxfield_deck = fetch_moxfield_deck(public_id)
    if not moxfield_deck:
        return jsonify({"error": "Could not fetch deck from Moxfield. Make sure the URL is correct and the deck is public."}), 404

    name = moxfield_deck["name"]

    # Check for duplicate name
    existing = get_decks()
    if any(d["name"].lower() == name.lower() for d in existing):
        return jsonify({"error": 'A deck with the name "' + name + '" already exists'}), 409

    # Create the deck
    deck_id = add_deck(name, color=color if color else None)

    # Add cards (no images yet — will be fetched from Scryfall after)
    results = []
    cmd_name = moxfield_deck.get("commander_name")
    cmd_sf_id = None
    all_scryfall_ids = []
    for entry in moxfield_deck["cards"]:
        quantity, card_name, set_code, scryfall_id, _, mana_cost, type_line, colors, color_identity, cmc = entry
        add_card_to_deck(
            deck_id,
            card_name=card_name,
            quantity=quantity,
            set_code=set_code,
            scryfall_id=scryfall_id,
            mana_cost=mana_cost,
            colors=colors,
            color_identity=color_identity,
            cmc=cmc,
            type_line=type_line,
        )
        if scryfall_id:
            all_scryfall_ids.append(scryfall_id)
        if card_name == cmd_name:
            cmd_sf_id = scryfall_id
        results.append({
            "status": "ok",
            "requested": card_name,
            "resolved": card_name,
            "quantity": quantity,
        })

    # Set commander (no image yet)
    if cmd_name:
        update_deck_commander(deck_id, cmd_name, "")

    # Fetch images from Scryfall in background
    if all_scryfall_ids:
        if cmd_sf_id and cmd_sf_id not in all_scryfall_ids:
            all_scryfall_ids.append(cmd_sf_id)
        threading.Thread(
            target=_fetch_and_save_images,
            args=(deck_id, all_scryfall_ids, cmd_name, cmd_sf_id),
            daemon=True
        ).start()

    return jsonify({"id": deck_id, "name": name, "results": results}), 201


def _fetch_and_save_images(deck_id, scryfall_ids, cmd_name, cmd_sf_id):
    """Background: fetch images from Scryfall and update cards + commander."""
    id_to_url = fetch_card_images_bulk(scryfall_ids)
    # Update card images
    card_rows = get_deck_cards(deck_id)
    scryfall_to_db_id = {c["scryfall_id"]: c["id"] for c in card_rows if c.get("scryfall_id")}
    for scryfall_id, image_url in id_to_url.items():
        card_db_id = scryfall_to_db_id.get(scryfall_id)
        if card_db_id and image_url:
            update_card_image(card_db_id, image_url)
    # Update commander image
    if cmd_name and cmd_sf_id:
        cmd_image = id_to_url.get(cmd_sf_id, "")
        if cmd_image:
            update_deck_commander_image(deck_id, cmd_image)


            update_deck_commander_image(deck_id, img)


@app.route("/api/decks/<int:deck_id>", methods=["PUT"])
def api_rename_deck(deck_id):
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Deck name is required"}), 400
    rename_deck(deck_id, name)
    return jsonify({"ok": True})


@app.route("/api/decks/<int:deck_id>/color", methods=["PUT"])
def api_update_deck_color(deck_id):
    data = request.get_json()
    color = data.get("color", "").strip()
    if not color:
        return jsonify({"error": "Color is required"}), 400
    update_deck_color(deck_id, color)
    return jsonify({"ok": True})


@app.route("/api/decks/<int:deck_id>/commander", methods=["PUT"])
def api_update_deck_commander(deck_id):
    data = request.get_json()
    commander_name = data.get("commander_name", "").strip()
    commander_image_url = data.get("commander_image_url", "").strip()
    if not commander_name:
        # Clear commander
        update_deck_commander(deck_id, "", "")
    else:
        update_deck_commander(deck_id, commander_name, commander_image_url)
    return jsonify({"ok": True})


@app.route("/api/decks/<int:deck_id>/stats", methods=["GET"])
def api_deck_stats(deck_id):
    """Get mana curve stats for a deck."""
    stats = get_deck_cmc_distribution(deck_id)
    return jsonify(stats)


@app.route("/api/decks/<int:deck_id>/refresh-images", methods=["POST"])
def api_refresh_deck_images(deck_id):
    """Refresh images for a specific deck's cards."""
    card_rows = get_deck_cards(deck_id)
    # Get all cards with scryfall_id (not just missing images — re-fetch everything)
    scryfall_to_db_id = {c["scryfall_id"]: c["id"] for c in card_rows if c.get("scryfall_id")}
    if scryfall_to_db_id:
        scryfall_ids = list(scryfall_to_db_id.keys())
        id_to_url = fetch_card_images_bulk(scryfall_ids)
        for scryfall_id, image_url in id_to_url.items():
            card_db_id = scryfall_to_db_id.get(scryfall_id)
            if card_db_id and image_url:
                update_card_image(card_db_id, image_url)
    # Refresh commander image too
    deck = get_deck(deck_id)
    if deck and deck.get("commander_name"):
        cmd_rows = [c for c in card_rows if c["card_name"] == deck["commander_name"] and c.get("scryfall_id")]
        if cmd_rows:
            cmd_images = fetch_card_images_bulk([cmd_rows[0]["scryfall_id"]])
            img = cmd_images.get(cmd_rows[0]["scryfall_id"])
            if img:
                update_deck_commander_image(deck_id, img)
    return jsonify({"ok": True})


@app.route("/api/refresh-images", methods=["POST"])
def api_refresh_all_images():
    """Trigger a full image refresh for all cards."""
    threading.Thread(target=refresh_all_images, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/decks/<int:deck_id>", methods=["DELETE"])
def api_delete_deck(deck_id):
    delete_deck(deck_id)
    return jsonify({"ok": True})


@app.route("/api/decks/<int:deck_id>/cards", methods=["GET"])
def api_deck_cards(deck_id):
    cards = get_deck_cards(deck_id)
    return jsonify(cards)


@app.route("/api/decks/<int:deck_id>/cards", methods=["POST"])
def api_add_cards(deck_id):
    data = request.get_json()
    card_list_text = data.get("card_list", "")

    if not card_list_text.strip():
        return jsonify({"error": "No cards provided"}), 400

    parsed = parse_card_list(card_list_text)
    if not parsed:
        return jsonify({"error": "Could not parse any cards from the input"}), 400

    results = []
    for quantity, card_name, set_code in parsed:
        resolved = validate_and_resolve_card(card_name, set_code)
        if resolved:
            add_card_to_deck(
                deck_id,
                card_name=resolved["name"],
                quantity=quantity,
                set_code=resolved["set_code"],
                scryfall_id=resolved["scryfall_id"],
                image_url=resolved["image_url"],
                mana_cost=resolved.get("mana_cost", ""),
                colors=resolved.get("colors", []),
                color_identity=resolved.get("color_identity", []),
                cmc=resolved.get("cmc", 0),
                type_line=resolved.get("type_line", ""),
            )
            results.append({
                "status": "ok",
                "requested": card_name,
                "resolved": resolved["name"],
                "quantity": quantity,
                "image_url": resolved["image_url"],
            })
        else:
            add_card_to_deck(
                deck_id,
                card_name=card_name,
                quantity=quantity,
                set_code=set_code or "",
            )
            results.append({
                "status": "not_found",
                "requested": card_name,
                "quantity": quantity,
            })

        return jsonify({"results": results})


@app.route("/api/decks/<int:deck_id>/cards", methods=["DELETE"])
def api_clear_deck(deck_id):
    clear_deck_cards(deck_id)
    return jsonify({"ok": True})


@app.route("/api/cards/<int:card_id>", methods=["PUT"])
def api_update_card(card_id):
    data = request.get_json()
    update_card(
        card_id,
        quantity=data.get("quantity"),
        set_code=data.get("set_code"),
        card_name=data.get("card_name"),
    )
    return jsonify({"ok": True})


@app.route("/api/cards/<int:card_id>", methods=["DELETE"])
def api_delete_card(card_id):
    delete_card(card_id)
    return jsonify({"ok": True})


@app.route("/api/collection", methods=["GET"])
def api_collection():
    collection = get_collection()
    return jsonify(collection)


@app.route("/api/cards/<int:card_id>/refresh", methods=["POST"])
def api_refresh_card(card_id):
    """Re-lookup a card on Scryfall to update its info/image."""
    conn = get_db()
    row = conn.execute("SELECT * FROM deck_cards WHERE id = ?", (card_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Card not found"}), 404

    card = dict(row)
    resolved = validate_and_resolve_card(card["card_name"], card.get("set_code"))
    if resolved:
        update_card(
            card_id,
            scryfall_id=resolved["scryfall_id"],
            image_url=resolved["image_url"],
            set_code=resolved["set_code"],
            mana_cost=resolved.get("mana_cost", ""),
            colors=resolved.get("colors", []),
            color_identity=resolved.get("color_identity", []),
            cmc=resolved.get("cmc", 0),
            type_line=resolved.get("type_line", ""),
        )
        return jsonify({"ok": True, "image_url": resolved["image_url"]})
    return jsonify({"error": "Could not find card on Scryfall"}), 404


@app.route("/api/decks/<int:deck_id>/color-identity", methods=["GET"])
def api_deck_color_identity(deck_id):
    """Get the combined color identity for a deck."""
    identity = get_deck_color_identity(deck_id)
    return jsonify({"color_identity": identity})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
