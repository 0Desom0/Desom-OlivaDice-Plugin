"""集中定义可选依赖对应的功能与用户提示。"""

from functools import lru_cache
from importlib import import_module
import warnings

_MODULES = {'pil': 'PIL', 'websocket': 'websocket', 'brotli': 'brotli', 'qrcode': 'qrcode', 'jieba': 'jieba'}
_FEATURES = {
    'dynamic_image': (('pil',), 'Pillow'),
    'live_stats': (('websocket',), 'websocket-client'),
    'live_report': (('pil', 'websocket'), 'Pillow 与 websocket-client'),
    'wordcloud': (('pil', 'websocket'), 'Pillow 与 websocket-client'),
    'qr_login': (('qrcode',), 'qrcode'),
}


@lru_cache(maxsize=len(_MODULES))
def _has_module(name):
    try:
        if name == 'jieba':
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', message=r'.*pkg_resources.*', category=Warning)
                import_module(name)
                return True
        import_module(name)
    except ImportError:
        return False
    return True


def snapshot():
    deps = {key: _has_module(name) for key, name in _MODULES.items()}
    features = {key: all(deps[dep] for dep in needed) for key, (needed, _) in _FEATURES.items()}
    return {
        'deps': deps,
        'features': features,
        'hints': {key: '' if features[key] else f'安装 {label} 后启用' for key, (_, label) in _FEATURES.items()},
        'segmenter': 'jieba' if deps['jieba'] else 'builtin',
    }


def can(feature_name):
    feature = _FEATURES.get(feature_name)
    return feature is not None and all(_has_module(_MODULES[dep]) for dep in feature[0])


def hint(feature_name):
    feature = _FEATURES.get(feature_name)
    return f'安装 {feature[1]} 后启用' if feature is not None and not can(feature_name) else ''
