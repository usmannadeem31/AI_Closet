"""Copy chosen dataset products into the wardrobe with explicit source provenance."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from fastapi import HTTPException

SCHEMA = '''CREATE TABLE IF NOT EXISTS library_wardrobe_items (
    item_id TEXT PRIMARY KEY, product_id INTEGER UNIQUE NOT NULL,
    created_at TEXT NOT NULL, image_sha256 TEXT UNIQUE NOT NULL,
    image_bytes BLOB NOT NULL, attributes_json TEXT NOT NULL,
    source_labels_json TEXT NOT NULL, description TEXT NOT NULL,
    user_reviewed INTEGER NOT NULL DEFAULT 0 CHECK(user_reviewed IN (0,1)))'''


def source_connection(root):
    path = root / 'data' / 'fashion.sqlite3'
    if not path.exists():
        raise HTTPException(503, 'The clothing library is unavailable.')
    db = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def starter_ids(root):
    # The owner requested men's clothing; source gender labels can misclassify kidswear.
    groups = [('Shirts', False), ('Tshirts', True), ('Tshirts', False),
              ('Shorts', False), ('Jeans', False), ('Trousers', False),
              ('Jackets', False), ('Sweaters', False), ('Sweatshirts', False),
              ('Casual Shoes', False)]
    ids = []
    db = source_connection(root)
    try:
        for article, polo in groups:
            sql = "SELECT id,color,gender FROM products WHERE article_type=? AND gender='Men'"
            for term in ('kids', 'boy', 'girl', 'infant', 'junior', 'baby'):
                sql += " AND lower(title) NOT LIKE '%" + term + "%'"
            if article == 'Tshirts':
                sql += " AND lower(title) " + ('LIKE' if polo else 'NOT LIKE') + " '%polo%'"
            rows = db.execute(sql + ' ORDER BY id', (article,)).fetchall()
            colors = set()
            for _ in range(3):
                candidates = [r for r in rows if r['id'] not in ids and r['color'] not in colors]
                if not candidates:
                    break
                row = candidates[0]
                ids.append(row['id']); colors.add(row['color'])
    finally:
        db.close()
    return ids


def attributes(row):
    labels = json.loads(row['labels_json'])
    article = row['article_type']
    sub = labels.get('subCategory')
    if article in ('Jackets', 'Blazers', 'Rain Jacket', 'Nehru Jackets', 'Waistcoat'):
        category = 'outerwear'
    elif sub == 'Topwear':
        category = 'top'
    elif sub == 'Bottomwear':
        category = 'bottom'
    elif article == 'Dresses':
        category = 'dress'
    elif row['category'] == 'Footwear':
        category = 'footwear'
    elif row['category'] == 'Accessories':
        category = 'accessory'
    else:
        category = 'other'
    kind = 'polo shirt' if article == 'Tshirts' and 'polo' in row['title'].lower() else article.lower()
    clean = lambda value: value if value and value.upper() != 'NA' else None
    # Usage is not equivalent to formality, and titles do not reliably identify brands.
    return dict(category=category, type=kind, color=clean(row['color']),
                season=clean(row['season']), formality=None, brand=None)


def import_products(root, connect, ids):
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > 100:
        raise HTTPException(422, 'Choose between 1 and 100 library items.')
    db = source_connection(root)
    try:
        rows = db.execute('SELECT * FROM products WHERE id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
    finally:
        db.close()
    if len(rows) != len(ids):
        raise HTTPException(404, 'One of the selected products was not found. Nothing was added.')
    added, skipped = [], []
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        for row in rows:
            digest = hashlib.sha256(row['image_bytes']).hexdigest()
            old = conn.execute('SELECT item_id FROM wardrobe_items WHERE image_sha256=?', (digest,)).fetchone()
            old = old or conn.execute('SELECT item_id FROM library_wardrobe_items WHERE image_sha256=? OR product_id=?',
                                      (digest, row['id'])).fetchone()
            if old:
                skipped.append(old[0])
                continue
            item_id = 'library_' + str(row['id'])
            conn.execute('INSERT INTO library_wardrobe_items VALUES (?,?,?,?,?,?,?,?,0)',
                         (item_id, row['id'], datetime.now(timezone.utc).isoformat(), digest,
                          row['image_bytes'], json.dumps(attributes(row)), row['labels_json'], row['title']))
            added.append(item_id)
    return {'added': len(added), 'skipped': len(skipped), 'item_ids': added + skipped}
