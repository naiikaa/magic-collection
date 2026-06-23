"""Database models and helpers for the cEDHcube app."""
import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collection.db")

# Predefined deck colors - assigned in order of deck creation
DECK_COLORS = [
    "#e94560",  # red-pink
    "#4ecdc4",  # teal
    "#ffe66d",  # yellow
    "#a8dadc",  # light blue
    "#f4a261",  # orange
    "#9b5de5",  # purple
    "#00bbf9",  # blue
    "#00f5d4",  # mint
    "#fee440",  # bright yellow
    "#f15bb5",  # pink
    "#8338ec",  # violet
    "#3a86ff",  # bright blue
    "#ff006e",  # magenta
    "#fb5607",  # deep orange
    "#80b918",  # lime
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#e94560',
            commander_name TEXT DEFAULT '',
            commander_image_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS deck_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_id INTEGER NOT NULL,
            card_name TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            set_code TEXT,
            scryfall_id TEXT,
            image_url TEXT,
            mana_cost TEXT DEFAULT '',
            colors TEXT DEFAULT '[]',
            color_identity TEXT DEFAULT '[]',
            cmc REAL DEFAULT 0,
            type_line TEXT DEFAULT '',
            FOREIGN KEY (deck_id) REFERENCES decks(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_deck_cards_deck_id ON deck_cards(deck_id);
        CREATE INDEX IF NOT EXISTS idx_deck_cards_name ON deck_cards(card_name);
    """)
    # Migrate existing DB: add commander columns if they don't exist
    cols = [row[1] for row in conn.execute("PRAGMA table_info(decks)").fetchall()]
    if 'commander_name' not in cols:
        conn.execute("ALTER TABLE decks ADD COLUMN commander_name TEXT DEFAULT ''")
    if 'commander_image_url' not in cols:
        conn.execute("ALTER TABLE decks ADD COLUMN commander_image_url TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def get_deck_color():
    """Get the next available color for a new deck."""
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM decks").fetchone()[0]
        return DECK_COLORS[count % len(DECK_COLORS)]
    finally:
        conn.close()


# --- Deck operations ---

def add_deck(name, color=None):
    conn = get_db()
    try:
        if not color:
            color = get_deck_color()
        cursor = conn.execute("INSERT INTO decks (name, color) VALUES (?, ?)", (name, color))
        deck_id = cursor.lastrowid
        conn.commit()
        return deck_id
    finally:
        conn.close()


def get_decks():
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT d.*, COUNT(dc.id) as card_count, COALESCE(SUM(dc.quantity), 0) as total_cards
            FROM decks d
            LEFT JOIN deck_cards dc ON dc.deck_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
        """).fetchall()
        result = [dict(r) for r in rows]
        # Add color identity for each deck
        for deck in result:
            deck["color_identity"] = json.dumps(get_deck_color_identity(deck["id"]))
        return result
    finally:
        conn.close()


def get_deck(deck_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def rename_deck(deck_id, new_name):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE decks SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_name, deck_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_deck_color(deck_id, color):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE decks SET color = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (color, deck_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_deck_commander(deck_id, commander_name, commander_image_url):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE decks SET commander_name = ?, commander_image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (commander_name or "", commander_image_url or "", deck_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_deck(deck_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
        conn.commit()
    finally:
        conn.close()


def get_cards_missing_images():
    """Get cards that have a scryfall_id but no image_url.

    Returns a list of dicts with keys: id, scryfall_id, card_name
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, scryfall_id, card_name
            FROM deck_cards
            WHERE scryfall_id IS NOT NULL AND scryfall_id != ''
              AND (image_url IS NULL OR image_url = '')
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_card_image(card_id, image_url):
    """Update the image_url for a specific card."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE deck_cards SET image_url = ? WHERE id = ?",
            (image_url, card_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_decks_missing_commander_images():
    """Get decks that have a commander_name but no commander_image_url.
    Tries to find the commander card in deck_cards to get its scryfall_id.
    Returns list of dicts: deck_id, commander_name, scryfall_id
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT d.id as deck_id, d.commander_name, dc.scryfall_id
            FROM decks d
            JOIN deck_cards dc ON dc.deck_id = d.id AND dc.card_name = d.commander_name
            WHERE d.commander_name IS NOT NULL AND d.commander_name != ''
              AND (d.commander_image_url IS NULL OR d.commander_image_url = '')
              AND dc.scryfall_id IS NOT NULL AND dc.scryfall_id != ''
            GROUP BY d.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_deck_commander_image(deck_id, image_url):
    """Update the commander_image_url for a deck."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE decks SET commander_image_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (image_url, deck_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_deck_cmc_distribution(deck_id):
    """Get CMC distribution for a deck.

    Returns a dict with:
      - cmc_bars: list of {cmc, count} for cmc 0-5 and 6+ bucket
      - total_cards: total card count (sum of quantities)
      - avg_cmc: average CMC (weighted by quantity, lands excluded)
    """
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT cmc, SUM(quantity) as count
            FROM deck_cards
            WHERE deck_id = ?
            GROUP BY cmc
            ORDER BY cmc
        """, (deck_id,)).fetchall()

        # Build distribution: 0, 1, 2, 3, 4, 5, 6+
        cmc_map = {}
        for r in rows:
            cmc_map[r["cmc"]] = r["count"]

        cmc_bars = []
        total_cards = 0
        weighted_cmc_sum = 0
        for cmc in range(6):
            count = cmc_map.get(cmc, 0)
            cmc_bars.append({"cmc": cmc, "count": count})
            total_cards += count
            weighted_cmc_sum += cmc * count
        # 6+ bucket
        plus_count = sum(v for k, v in cmc_map.items() if k >= 6)
        cmc_bars.append({"cmc": 6, "count": plus_count, "label": "6+"})
        total_cards += plus_count
        weighted_cmc_sum += 6 * plus_count  # approximate for 6+

        avg_cmc = round(weighted_cmc_sum / total_cards, 2) if total_cards > 0 else 0

        return {
            "cmc_bars": cmc_bars,
            "total_cards": total_cards,
            "avg_cmc": avg_cmc,
        }
    finally:
        conn.close()


# --- Card operations ---

def add_card_to_deck(deck_id, card_name, quantity=1, set_code=None, scryfall_id=None,
                     image_url=None, mana_cost=None, colors=None, color_identity=None,
                     cmc=None, type_line=None):
    conn = get_db()
    try:
        import json
        conn.execute("""
            INSERT INTO deck_cards (deck_id, card_name, quantity, set_code, scryfall_id,
                                    image_url, mana_cost, colors, color_identity, cmc, type_line)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (deck_id, card_name, quantity, set_code, scryfall_id, image_url,
              mana_cost or "",
              json.dumps(colors or []),
              json.dumps(color_identity or []),
              cmc or 0,
              type_line or ""))
        conn.commit()
    finally:
        conn.close()


def get_deck_cards(deck_id):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT * FROM deck_cards WHERE deck_id = ? ORDER BY card_name
        """, (deck_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_card(card_id, quantity=None, set_code=None, scryfall_id=None, image_url=None, card_name=None):
    conn = get_db()
    try:
        fields = []
        values = []
        if quantity is not None:
            fields.append("quantity = ?")
            values.append(quantity)
        if set_code is not None:
            fields.append("set_code = ?")
            values.append(set_code)
        if scryfall_id is not None:
            fields.append("scryfall_id = ?")
            values.append(scryfall_id)
        if image_url is not None:
            fields.append("image_url = ?")
            values.append(image_url)
        if card_name is not None:
            fields.append("card_name = ?")
            values.append(card_name)
        if fields:
            values.append(card_id)
            conn.execute(f"UPDATE deck_cards SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
    finally:
        conn.close()


def delete_card(card_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM deck_cards WHERE id = ?", (card_id,))
        conn.commit()
    finally:
        conn.close()


def clear_deck_cards(deck_id):
    conn = get_db()
    try:
        conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (deck_id,))
        conn.commit()
    finally:
        conn.close()


def get_collection():
    """Get the full collection: all unique cards across all decks with total quantities and deck info."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT card_name, scryfall_id, image_url, set_code, type_line, mana_cost,
                   colors, color_identity, cmc,
                   SUM(quantity) as total_quantity,
                   COUNT(DISTINCT deck_id) as deck_count
            FROM deck_cards
            GROUP BY card_name
            ORDER BY card_name
        """).fetchall()
        result = [dict(r) for r in rows]

        # Add deck info for each card (which decks contain it, with colors)
        for card in result:
            deck_rows = conn.execute("""
                SELECT d.name, d.color
                FROM deck_cards dc
                JOIN decks d ON d.id = dc.deck_id
                WHERE dc.card_name = ?
                GROUP BY d.id
                ORDER BY d.name
            """, (card["card_name"],)).fetchall()
            card["decks"] = [{"name": r["name"], "color": r["color"]} for r in deck_rows]

        return result
    finally:
        conn.close()


def get_deck_color_identity(deck_id):
    """Calculate the combined color identity of all cards in a deck."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT color_identity FROM deck_cards WHERE deck_id = ?
        """, (deck_id,)).fetchall()
        import json
        all_colors = set()
        for row in rows:
            ci = json.loads(row["color_identity"]) if row["color_identity"] else []
            all_colors.update(ci)
        return sorted(all_colors)
    finally:
        conn.close()
