import ast
import importlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


def test_manifest_and_python_sources_are_valid():
    root = Path(__file__).resolve().parents[1] / 'StatusHud'
    manifest_bytes = (root / 'app.json').read_bytes()
    assert not manifest_bytes.startswith(b'\xef\xbb\xbf')
    manifest = json.loads(manifest_bytes.decode('utf-8'))
    assert manifest['namespace'] == 'StatusHud'
    assert manifest['priority'] < 20000
    assert 'webui_config' not in manifest
    for path in root.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def test_first_command_after_opk_extraction_is_removed(runtime, monkeypatch):
    root = Path(__file__).resolve().parents[1] / 'StatusHud'
    archive = runtime.path / 'StatusHud.opk'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
        for path in root.iterdir():
            if path.is_file() and path.suffix in ('.py', '.json', '.md'):
                package.write(path, path.name)
    unpacked = runtime.path / 'plugin/tmp/StatusHud'
    with zipfile.ZipFile(archive) as package:
        package.extractall(unpacked)
    monkeypatch.syspath_prepend(str(unpacked.parent))
    for name in list(sys.modules):
        if name == 'StatusHud' or name.startswith('StatusHud.'):
            monkeypatch.delitem(sys.modules, name)
    plugin = importlib.import_module('StatusHud')
    plugin.main.Event.init(None, runtime.proc)
    assert unpacked.is_relative_to(runtime.path)
    shutil.rmtree(unpacked)
    plugin.main.Event.init_after(None, runtime.proc)
    try:
        assert plugin.main.gManager is not None
        runtime.card()
        event = runtime.Event('.hud show')
        runtime.proc.run(event, plugin.main.Event.group_message, namespace='StatusHud', mode='olivos_string')
        assert 'HUD：开启' in event.sent[0][2]
        assert not unpacked.exists()
        event = runtime.Event('.r 1d6')
        runtime.proc.run(event)
        assert event.sent[0][2].startswith('『Alice HP10/12 SAN65/94』\n\n')
    finally:
        plugin.main.Event.save(None, runtime.proc)
