# cEDHcube

A web app to track your Magic: The Gathering card collection across multiple decks. Cheking for duplicates for a potential [sticker cube](https://www.youtube.com/watch?v=-LKhMkIi9nk) setup. Marks multiple occurencies of the same card across multiple decks.

## Features
- Add decks by pasting card lists or moxfield links
- Automatic card validation via Scryfall API
- Card images displayed from Scryfall
- Edit decks, adjust set versions, delete decks
- Persistent SQLite database

## Setup
```bash
pip install -r requirements.txt
python app.py
```
### Using uv
```bash
uv sync
uv run app.py
```

Then open http://localhost:5000 in your browser.


<img width="3838" height="2044" alt="Screenshot_2026-06-23_16-55-10" src="https://github.com/user-attachments/assets/27c4ec12-5d16-40c9-b23a-396a10a127f8" />

<img width="3838" height="2044" alt="Screenshot_2026-06-23_16-55-22" src="https://github.com/user-attachments/assets/fcb368aa-59ad-4aa8-a1d9-2e03e0320a9b" />




