"""Import the official Fashion Product Images (Small) ZIP without changing personal clothes."""
import argparse
import csv
import io
import json
from pathlib import Path
import sqlite3
import zipfile

SOURCE = "https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-small"


def import_archive(archive, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.importing.sqlite3')
    if temporary.exists():
        temporary.unlink()
    counts = dict(imported=0, missing_images=0, repaired_rows=0)
    with zipfile.ZipFile(archive) as z, sqlite3.connect(temporary) as db:
        db.execute('''CREATE TABLE products (
            id INTEGER PRIMARY KEY, title TEXT, category TEXT, article_type TEXT,
            color TEXT, gender TEXT, season TEXT, usage TEXT, labels_json TEXT,
            image_bytes BLOB NOT NULL)''')
        names = set(z.namelist())
        with z.open('styles.csv') as f:
            rows = csv.reader(io.TextIOWrapper(f, encoding='utf-8-sig'))
            header = next(rows)
            expected = ['id','gender','masterCategory','subCategory','articleType',
                        'baseColour','season','year','usage','productDisplayName']
            if header != expected:
                raise ValueError('Unexpected dataset columns; import stopped.')
            for fields in rows:
                # Some source titles contain unquoted commas in the final column.
                if len(fields) > len(header):
                    fields = fields[:9] + [','.join(fields[9:])]
                    counts['repaired_rows'] += 1
                if len(fields) != len(header) or not fields[0].isdigit():
                    raise ValueError('Malformed dataset row; import stopped.')
                row = dict(zip(header, fields))
                name = 'images/' + row['id'] + '.jpg'
                if name not in names:
                    counts['missing_images'] += 1
                    continue
                db.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (int(row['id']), row['productDisplayName'], row['masterCategory'],
                     row['articleType'], row['baseColour'], row['gender'], row['season'],
                     row['usage'], json.dumps(row), z.read(name)))
                counts['imported'] += 1
        db.execute('CREATE INDEX product_filters ON products(category,article_type,color)')
        db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)')
        db.executemany('INSERT INTO metadata VALUES (?,?)',
                       [('source', SOURCE), ('counts', json.dumps(counts))])
    # Close before publishing: an incomplete import never replaces the library.
    temporary.replace(destination)
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parents[1] / 'data' / 'fashion.sqlite3')
    args = parser.parse_args()
    print(json.dumps(import_archive(args.archive, args.db), indent=2))
