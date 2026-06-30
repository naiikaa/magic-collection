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


## Import decks from [Moxfield](https://moxfield.com/) or paste a list of cards
<img width="2054" height="1565" alt="Screenshot_2026-06-30_19-13-09" src="https://github.com/user-attachments/assets/eba345a5-5d9d-4e89-88af-b21d32ecd58d" />

## Edit your decks, set a commander or view the mana curve
<img width="1395" height="1639" alt="Screenshot_2026-06-30_19-12-04" src="https://github.com/user-attachments/assets/f7082a42-b934-4387-836a-d1fb63cb2c6e" />

## Get an overview of your entire collection and see what decks share cards
<img width="3051" height="1973" alt="Screenshot_2026-06-30_19-11-39" src="https://github.com/user-attachments/assets/04e70621-406b-4d14-91c5-ced01c5084f8" />





