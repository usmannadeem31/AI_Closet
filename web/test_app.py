"""Integration checks using a temporary wardrobe; no model or real entries changed."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import model_runtime

from fastapi.testclient import TestClient
from PIL import Image

spec = importlib.util.spec_from_file_location("closet_gui", Path(__file__).with_name("app.py"))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


class CatalogWebsiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = gui.DB
        gui.DB = Path(self.tmp.name) / "wardrobe.sqlite3"
        gui.drafts.clear()
        self.client = TestClient(gui.app)
        self.client.__enter__()
        self.headers = {"x-closet-key": gui.KEY}
        self.attrs = dict(category="top", type="shirt", color="blue", formality="casual", season=None, brand=None)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        gui.DB = self.old_db
        self.tmp.cleanup()

    def post(self, path, data):
        return self.client.post(path, json=data, headers=self.headers)

    def draft(self, data):
        with patch.object(gui, "ask", return_value=(json.dumps(self.attrs), 0.6, "stop", "2b")):
            response = self.post("/api/analyze", data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_text_review_save_duplicate_edit_and_original_prediction(self):
        draft = self.draft({"text": "My blue shirt"})
        self.assertEqual(self.client.get("/api/items").json(), [])
        attrs = dict(self.attrs, color="navy")
        saved = self.post("/api/items", {"draft_id": draft["draft_id"], "attributes": attrs}).json()
        self.assertFalse(saved["duplicate"])
        again = self.post("/api/items", {"draft_id": draft["draft_id"], "attributes": attrs}).json()
        self.assertTrue(again["duplicate"])
        items = self.client.get("/api/items").json()
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["has_image"])
        self.assertEqual(items[0]["description"], "My blue shirt")
        edit = self.client.patch('/api/items/'+saved['item_id'], json={"attributes": dict(attrs, formality="smart casual")}, headers=self.headers)
        self.assertEqual(edit.status_code, 200)
        with sqlite3.connect(gui.DB) as db:
            predicted, reviewed = db.execute("SELECT predicted_json, attributes_json FROM wardrobe_items").fetchone()
        self.assertEqual(json.loads(predicted)["color"], "blue")
        self.assertEqual(json.loads(reviewed)["formality"], "smart casual")

    def test_photo_save_and_thumbnail(self):
        buffer = io.BytesIO()
        Image.new("RGB", (800, 600), "white").save(buffer, format="PNG")
        draft = self.draft({"image": "data:image/png;base64,"+base64.b64encode(buffer.getvalue()).decode()})
        saved = self.post("/api/items", {"draft_id": draft["draft_id"], "attributes": self.attrs}).json()
        photo = self.client.get('/api/items/'+saved['item_id']+'/image')
        self.assertEqual(photo.status_code, 200)
        with Image.open(io.BytesIO(photo.content)) as img:
            self.assertLessEqual(max(img.size), 640)

    def test_invalid_and_truncated_model_answers_do_not_save(self):
        for raw, finish in [('{}','stop'),(json.dumps(self.attrs),'length')]:
            with patch.object(gui, "ask", return_value=(raw, 0.6, finish, "2b")):
                self.assertEqual(self.post('/api/analyze',{'text':'shirt'}).status_code,422)
        self.assertEqual(self.client.get('/api/items').json(), [])

    def test_empty_invalid_photo_and_unauthorized_writes(self):
        self.assertEqual(self.post('/api/analyze',{}).status_code,400)
        self.assertEqual(self.post('/api/analyze',{'image':'not an image'}).status_code,400)
        self.assertEqual(self.client.post('/api/model/start',json={}).status_code,403)
        self.assertEqual(self.post('/api/items',{'draft_id':'missing','attributes':self.attrs}).status_code,410)

    def test_chat_is_not_saved_and_html_is_served(self):
        with patch.object(gui,'ask',return_value=('Hello from local AI',0.2,'stop','2b')):
            r=self.post('/api/chat',{'text':'Hello'})
        self.assertEqual(r.json()['answer'],'Hello from local AI')
        self.assertEqual(self.client.get('/api/items').json(),[])
        self.assertIn('Every piece has',self.client.get('/').text)

    def test_model_identity_survives_switch_before_saving(self):
        first = self.draft({'text':'blue shirt'})
        with patch.object(gui, 'ask', return_value=(json.dumps(self.attrs), 0.9, 'stop', '4b')):
            second = self.post('/api/analyze', {'text':'another blue shirt'}).json()
        self.assertEqual(second['model_id'], '4b')
        self.post('/api/items', {'draft_id': first['draft_id'], 'attributes': self.attrs})
        self.post('/api/items', {'draft_id': second['draft_id'], 'attributes': self.attrs})
        with sqlite3.connect(gui.DB) as db:
            saved = [r[0] for r in db.execute('SELECT model FROM wardrobe_items ORDER BY created_at')]
        self.assertEqual(saved, [gui.MODELS['2b']['repo'], gui.MODELS['4b']['repo']])


    def test_library_import_duplicate_edit_and_original_labels(self):
        original_root = gui.ROOT
        try:
            gui.ROOT = Path(self.tmp.name)
            (gui.ROOT / 'data').mkdir()
            photo = io.BytesIO()
            Image.new('RGB', (60, 80), 'blue').save(photo, format='JPEG')
            labels = dict(subCategory='Topwear', productDisplayName='Blue polo')
            with sqlite3.connect(gui.ROOT / 'data' / 'fashion.sqlite3') as db:
                db.execute('CREATE TABLE products(id INTEGER PRIMARY KEY,title TEXT,category TEXT,article_type TEXT,color TEXT,gender TEXT,season TEXT,usage TEXT,labels_json TEXT,image_bytes BLOB)')
                db.execute('INSERT INTO products VALUES (1,?,?,?,?,?,?,?,?,?)', ('Blue polo','Apparel','Tshirts','Blue','Men','Summer','Casual',json.dumps(labels),photo.getvalue()))
            self.assertEqual(self.client.post('/api/items/from-library',json={'product_ids':[1]}).status_code,403)
            self.assertEqual(self.post('/api/items/from-library',{'product_ids':[1,999]}).status_code,404)
            self.assertEqual(self.client.get('/api/items').json(),[])
            result = self.post('/api/items/from-library',{'product_ids':[1,1]}).json()
            self.assertEqual(result['added'],1)
            self.assertEqual(self.post('/api/items/from-library',{'product_ids':[1]}).json()['skipped'],1)
            entry = self.client.get('/api/items').json()[0]
            self.assertEqual(entry['origin'],'library')
            self.assertFalse(entry['reviewed'])
            self.assertEqual(entry['attributes']['type'],'polo shirt')
            self.assertIsNone(entry['attributes']['brand'])
            self.assertIsNone(entry['attributes']['formality'])
            self.assertEqual(self.client.get('/api/items/'+entry['id']+'/image').status_code,200)
            result = self.client.patch('/api/items/'+entry['id'],json={'attributes':dict(entry['attributes'],color='navy')},headers=self.headers)
            self.assertEqual(result.status_code,200)
            self.assertTrue(self.client.get('/api/items').json()[0]['reviewed'])
            with sqlite3.connect(gui.DB) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM wardrobe_items').fetchone()[0],0)
                self.assertEqual(json.loads(db.execute('SELECT source_labels_json FROM library_wardrobe_items').fetchone()[0]),labels)
            # An AI analysis of the same image must not create a second wardrobe item.
            draft = self.draft({'image':base64.b64encode(photo.getvalue()).decode()})
            saved = self.post('/api/items',{'draft_id':draft['draft_id'],'attributes':self.attrs}).json()
            self.assertTrue(saved['duplicate'])
            self.assertEqual(saved['item_id'],entry['id'])
        finally:
            gui.ROOT = original_root


class ModelLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.r = model_runtime.ModelRuntime(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reject_invalid_selection_and_external_switch(self):
        with self.assertRaises(HTTPException):
            self.r.launch('invalid')
        external = {'id': model_runtime.ALIAS, 'root': model_runtime.MODELS['2b']['repo']}
        with patch.object(model_runtime, 'served', return_value=external), patch.object(self.r, '_stop') as stop:
            with self.assertRaises(HTTPException) as error:
                self.r.launch('4b')
            self.assertEqual(error.exception.status_code, 409)
            stop.assert_not_called()

    def test_inference_blocks_switch_and_verifies_expected_model(self):
        current = {'id': model_runtime.ALIAS, 'root': model_runtime.MODELS['2b']['repo']}
        with patch.object(model_runtime, 'served', return_value=current):
            with self.r.inference('2b') as key:
                self.assertEqual(key, '2b')
                with self.assertRaises(HTTPException):
                    self.r.launch('4b')
                with self.assertRaises(HTTPException):
                    self.r.stop()
            with self.assertRaises(HTTPException):
                with self.r.inference('4b'):
                    pass
        self.assertFalse(self.r.inference_active)

    def test_switch_stops_old_before_starting_new(self):
        self.r.process = MagicMock()
        self.r.process.poll.return_value = None
        events = []
        def stopped():
            events.append('stop')
            self.r.process = None
        def started(*args, **kwargs):
            events.append('start')
            self.assertIn(model_runtime.MODELS['4b']['repo'], args[0])
            self.assertEqual(kwargs['env']['VLLM_USE_FLASHINFER_SAMPLER'], '0')
            return MagicMock()
        with patch.object(model_runtime, 'served', return_value=None), patch.object(self.r,'_stop',side_effect=stopped), patch.object(model_runtime.subprocess,'Popen',side_effect=started):
            self.r.launch('4b')
        self.assertEqual(events,['stop','start'])
        self.assertEqual(self.r.selected,'4b')
        self.assertFalse(self.r.transition)


if __name__ == '__main__':
    unittest.main()
