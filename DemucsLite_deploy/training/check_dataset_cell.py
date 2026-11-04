"""Offline checks for the notebook's shared-Drive ZIP resolver.

Runs the generated cell with a tiny ZIP and mocked Google APIs. It never
authenticates, downloads the real dataset, or writes outside a temporary folder.
"""
import contextlib
import hashlib
import importlib.machinery
import io
import json
import shutil
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent


class DatasetCellChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.content = Path(self.directory.name) / 'content'
        self.mydrive = self.content / 'drive' / 'MyDrive'
        self.mydrive.mkdir(parents=True)
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('musdb18hq/train/song/mixture.wav', b'tiny mock WAV')
        self.payload = data.getvalue()
        self.meta = {
            'id': '1leTZccqRToe17S7DcDXSRsqovnwNaZb5',
            'name': 'musdb18hq.zip', 'mimeType': 'application/zip',
            'size': str(len(self.payload)),
            'md5Checksum': hashlib.md5(self.payload).hexdigest(),
            'modifiedTime': '2026-10-09T00:00:00Z',
            'capabilities': {'canDownload': True},
        }
        self.calls = {'auth': 0, 'media': 0, 'chunks': 0}
        self.free_bytes = 100 * 2**30
        notebook = json.loads((ROOT / 'main_v2_training_colab.ipynb').read_text())
        self.source = next(''.join(cell['source']) for cell in notebook['cells']
                           if cell['cell_type'] == 'code'
                           and 'DATASET_ARCHIVE_ID =' in ''.join(cell['source']))
        # All /content paths in this cell are isolated before execution.
        self.source = self.source.replace('/content', str(self.content))
        # Fake metadata describes the tiny fixture, never the 22 GB archive.
        self.source = self.source.replace('DATASET_ARCHIVE_SIZE = 22656664047',
                                          f'DATASET_ARCHIVE_SIZE = {len(self.payload)}')

    def google_modules(self):
        modules = {}
        for name in ('google', 'google.colab', 'google.colab.auth', 'google.auth',
                     'googleapiclient', 'googleapiclient.discovery',
                     'googleapiclient.http', 'googleapiclient.errors',
                     'tqdm', 'tqdm.auto'):
            module = types.ModuleType(name)
            module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
            module.__path__ = []
            modules[name] = module
        for name, module in modules.items():
            if '.' in name:
                parent, child = name.rsplit('.', 1)
                setattr(modules[parent], child, module)
        owner = self

        def authenticate_user(*args, **kwargs):
            owner.calls['auth'] += 1

        class Files:
            def get(self, **kwargs):
                assert kwargs['fileId'] == owner.meta['id']
                return types.SimpleNamespace(execute=lambda: dict(owner.meta))

            def get_media(self, **kwargs):
                assert kwargs['fileId'] == owner.meta['id']
                owner.calls['media'] += 1
                return object()

        class Downloader:
            def __init__(self, handle, request, chunksize=2**20):
                assert chunksize <= 64 * 2**20
                self.handle = handle
                self.position = 0

            def next_chunk(self, **kwargs):
                owner.calls['chunks'] += 1
                midpoint = (len(owner.payload) + 1) // 2
                end = min(len(owner.payload), self.position + midpoint)
                self.handle.write(owner.payload[self.position:end])
                self.position = end
                progress = self.position / len(owner.payload)
                return types.SimpleNamespace(progress=lambda: progress), progress == 1

        class HttpError(Exception):
            pass

        class Progress:
            def __init__(self, items=(), **kwargs):
                self.items = items
                self.n = 0

            def __iter__(self):
                return iter(self.items)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def update(self, count):
                self.n += count

        modules['google.colab.auth'].authenticate_user = authenticate_user
        modules['google.auth'].default = lambda *args, **kwargs: (object(), None)
        modules['googleapiclient.discovery'].build = lambda *args, **kwargs: types.SimpleNamespace(files=Files)
        modules['googleapiclient.http'].MediaIoBaseDownload = Downloader
        modules['googleapiclient.errors'].HttpError = HttpError
        modules['tqdm.auto'].tqdm = Progress
        return modules

    def execute(self, source=None, extra_namespace=None):
        namespace = {'Path': Path}
        namespace.update(extra_namespace or {})
        disk = shutil._ntuple_diskusage(200 * 2**30, 0, self.free_bytes)
        with patch.dict(sys.modules, self.google_modules()), \
                patch('shutil.disk_usage', return_value=disk), \
                contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source or self.source, 'generated_dataset_cell', 'exec'), namespace)
        return namespace

    def mounted_zip(self, folder='musdb18hq'):
        target = self.mydrive / folder / 'musdb18hq.zip'
        target.parent.mkdir()
        target.write_bytes(self.payload)
        return target

    def test_mounted_shortcut_avoids_auth_and_download(self):
        target = self.mounted_zip()
        result = self.execute()
        self.assertEqual(Path(result['ZIP_PATH']), target)
        self.assertEqual(self.calls['auth'], 0)
        self.assertEqual(self.calls['media'], 0)

    def test_explicit_path_avoids_auth_and_download(self):
        target = self.content / 'explicit.zip'
        target.write_bytes(self.payload)
        result = self.execute(extra_namespace={'ZIP_PATH': target})
        self.assertEqual(Path(result['ZIP_PATH']), target)
        self.assertEqual(self.calls['auth'], 0)

    def test_shared_zip_downloads_into_colab_and_extracts(self):
        result = self.execute()
        target = Path(result['ZIP_PATH'])
        self.assertTrue(target.is_relative_to(self.content))
        self.assertFalse(target.is_relative_to(self.mydrive))
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual(self.calls['media'], 1)
        self.assertEqual(self.calls['chunks'], 2)
        extracted = list(Path(result['EXTRACT_ROOT']).rglob('mixture.wav'))
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].read_bytes(), b'tiny mock WAV')

    def test_verified_local_zip_is_reused(self):
        first = Path(self.execute()['ZIP_PATH'])
        before = first.stat().st_mtime_ns
        second = Path(self.execute()['ZIP_PATH'])
        self.assertEqual(second, first)
        self.assertEqual(second.stat().st_mtime_ns, before)
        self.assertEqual(self.calls['media'], 1)

    def test_multiple_mounted_zips_require_explicit_choice(self):
        self.mounted_zip('first')
        self.mounted_zip('second')
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.calls['auth'], 0)

    def test_download_permission_denied_stops_before_media(self):
        self.meta['capabilities']['canDownload'] = False
        with self.assertRaises(PermissionError):
            self.execute()
        self.assertEqual(self.calls['media'], 0)

    def test_low_disk_stops_before_download(self):
        self.free_bytes = 0
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.calls['chunks'], 0)

    def test_bad_checksum_never_publishes_or_extracts_zip(self):
        self.meta['md5Checksum'] = '0' * 32
        with self.assertRaises(RuntimeError):
            self.execute()
        completed = [p for p in self.content.rglob('*.zip') if not p.is_relative_to(self.mydrive)]
        self.assertEqual(completed, [])
        self.assertEqual(list(self.content.rglob('mixture.wav')), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
