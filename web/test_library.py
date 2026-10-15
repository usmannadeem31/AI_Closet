"""Exercise bulk import and browsing with isolated dataset and demo databases."""
import csv
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from library import create_router
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from import_fashion import import_archive


class LibraryTests(unittest.TestCase):
    def test_import_filters_pagination_demo_and_missing_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'dataset.zip'
            header = 'id,gender,masterCategory,subCategory,articleType,baseColour,season,year,usage,productDisplayName\n'
            rows = [f'{i},Men,Apparel,Topwear,{"Shirts" if i%2 else "Tshirts"},{"Blue" if i%2 else "White"},Summer,2012,Casual,Test shirt {i}\n' for i in range(1,122)]
            rows[0] = '1,Men,Apparel,Topwear,Shirts,Blue,Summer,2012,Casual,Test shirt, with comma\n'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('styles.csv', header + ''.join(rows))
                for i in range(1,121):
                    z.writestr(f'images/{i}.jpg', b'fixture-image')
            destination = root/'data'/'fashion.sqlite3'
            stats = import_archive(archive, destination)
            self.assertEqual(stats, dict(imported=120, missing_images=1, repaired_rows=1))
            # Reruns replace the library atomically without duplicating products.
            self.assertEqual(import_archive(archive, destination), stats)
            app = FastAPI()
            app.include_router(create_router(root))
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/library/filters').json()['total'],120)
                first = client.get('/api/library').json()
                second = client.get('/api/library?page=2').json()
                self.assertEqual(len(first['items']),24)
                self.assertTrue(set(x['id'] for x in first['items']).isdisjoint(x['id'] for x in second['items']))
                self.assertEqual(client.get('/api/library?color=Blue').json()['total'],60)
                self.assertEqual(client.get('/api/library',params={'q':'with comma'}).json()['total'],1)
                self.assertEqual(client.get('/api/library',params={'q':"' OR 1=1 --"}).json()['total'],0)
                self.assertEqual(client.get('/api/library?page=0').status_code,422)
                self.assertEqual(client.get('/api/library/1/image').content,b'fixture-image')
                self.assertEqual(client.get('/api/library/999/image').status_code,404)
                self.assertEqual(client.get('/api/library?demo=true').json()['total'],0)
                for size in (20,50,100):
                    self.assertEqual(client.post('/api/library/demo',json={'size':size}).json()['count'],size)
                    self.assertEqual(client.get('/api/library?demo=true').json()['total'],size)
                self.assertEqual(client.post('/api/library/demo',json={'size':200}).status_code,422)
                self.assertFalse((root/'data'/'wardrobe.sqlite3').exists())
                with sqlite3.connect(destination) as db:
                    labels=json.loads(db.execute('SELECT labels_json FROM products WHERE id=1').fetchone()[0])
                    self.assertEqual(labels['productDisplayName'],'Test shirt, with comma')

if __name__ == '__main__':
    unittest.main()
