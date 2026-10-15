"""Dataset browsing: source labels stay separate from reviewed personal clothing."""
from contextlib import contextmanager
import sqlite3
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel


def create_router(root):
    router = APIRouter(prefix='/api/library')
    db_path = root / 'data' / 'fashion.sqlite3'

    @contextmanager
    def connection():
        if not db_path.exists():
            raise HTTPException(503, 'The clothing library has not been imported yet.')
        db = sqlite3.connect(f'{db_path.as_uri()}?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @router.get('/filters')
    def filters():
        with connection() as db:
            result = {key: [row[0] for row in db.execute(
                f'SELECT DISTINCT {key} FROM products WHERE {key} != \'\' ORDER BY {key}')]
                for key in ('category', 'article_type', 'color', 'gender')}
            result['total'] = db.execute('SELECT count(*) FROM products').fetchone()[0]
        return result

    @router.get('')
    def products(q: str = Query('', max_length=200), category: str = '',
                 article_type: str = '', color: str = '', gender: str = '',
                 page: int = Query(1, ge=1, le=100000), demo: bool = False):
        where, params = [], []
        for column, value in [('category', category), ('article_type', article_type),
                              ('color', color), ('gender', gender)]:
            if value:
                where.append(f'{column}=?')
                params.append(value)
        if q.strip():
            where.append("title LIKE ? ESCAPE '\\'")
            params.append('%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        if demo:
            ids = demo_ids()
            where.append('id IN (' + ','.join('?' for _ in ids) + ')' if ids else '0')
            params.extend(ids)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with connection() as db:
            total = db.execute('SELECT count(*) FROM products' + clause, params).fetchone()[0]
            rows = db.execute('SELECT id,title,category,article_type,color,gender,season,usage FROM products'
                              + clause + ' ORDER BY id LIMIT 24 OFFSET ?', params + [(page-1)*24]).fetchall()
        return dict(total=total, page=page, page_size=24, items=[dict(r) for r in rows])

    @router.get('/{product_id}/image')
    def image(product_id: int):
        with connection() as db:
            row = db.execute('SELECT image_bytes FROM products WHERE id=?', (product_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Product not found.')
        return Response(row[0], media_type='image/jpeg')

    def demo_ids():
        path = root / 'data' / 'demo.sqlite3'
        if not path.exists():
            return []
        with sqlite3.connect(path) as db:
            return [r[0] for r in db.execute('SELECT product_id FROM selected_products')]

    class Demo(BaseModel):
        size: int

    @router.post('/demo')
    def create_demo(body: Demo):
        if body.size not in (20, 50, 100):
            raise HTTPException(422, 'Choose 20, 50 or 100 items.')
        # Round-robin clothing types for variety; deterministic IDs make demos repeatable.
        with connection() as db:
            rows = db.execute('''SELECT id FROM (
                SELECT id,article_type,row_number() OVER (PARTITION BY article_type ORDER BY id) AS rank
                FROM products WHERE category IN ('Apparel','Footwear','Accessories'))
                ORDER BY rank,article_type,id LIMIT ?''', (body.size,)).fetchall()
        with sqlite3.connect(root / 'data' / 'demo.sqlite3') as db:
            db.execute('CREATE TABLE IF NOT EXISTS selected_products(product_id INTEGER PRIMARY KEY)')
            db.execute('DELETE FROM selected_products')
            db.executemany('INSERT INTO selected_products VALUES (?)', [(r[0],) for r in rows])
        return {'count': len(rows)}

    return router
