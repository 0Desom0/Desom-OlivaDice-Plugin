"""独立运行：py -3.12 tests/bench_text_image.py [--samples 输出目录]。"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from statistics import median
from time import perf_counter

from PIL import Image


def narrow_text():
    # 60 行、2810 字符，使用插件没有安装字体时的 Pillow 默认字体。
    titles = ('Stasis', 'Travel', 'Sirius')
    return '\n'.join(
        f'{i + 1:02}. {titles[i % 3]} / Master: 15+ / Score: {987654 - i:07} / {"A" if i < 9 else "AA"}'
        for i in range(60)
    )


def wide_text():
    # 带曲目详情的成绩列表，使用随插件发布的实际中文字体。
    titles = ('Stasis', 'Travel', 'Sirius', 'Fallen', 'Prism')
    lines = ['01. 曲目 Stasis ／ Master 15+ ／ 定数 15.8 ／ 乐师 Feryquitous ／ 判定 Perfect ／ 得分 0987654 ／ A']
    for i in range(2, 53):
        song_id = f'[{1200 + i}] ' if i <= 42 else ''
        lines.append(f'{i:02}. {song_id}{titles[i % len(titles)]} ／ Master 15+ ／ 得分 {987655 - i:07}')
    return '\n'.join(lines)


def measure(render, label, text, samples_dir):
    durations = []
    sizes = []
    for _ in range(5):
        start = perf_counter()
        path = Path(render(text))
        durations.append(1000 * (perf_counter() - start))
        sizes.append(path.stat().st_size)
    with Image.open(path) as image:
        width, height = image.size
    print(f'{label}: {len(text)} chars, {len(text.splitlines())} lines, {width}x{height}, '
          f'median={median(durations):.1f} ms, {median(sizes)} bytes; '
          f'runs(ms)={", ".join(f"{ms:.1f}" for ms in durations)}')
    if samples_dir is not None:
        samples_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, samples_dir / f'{label}{path.suffix}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, help='保留各档最后一次渲染的图片，以供对照')
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from LanotaPlugin import config, function

    with tempfile.TemporaryDirectory() as temp_dir:
        config.plugin_data_dir = temp_dir
        measure(function.create_text_image, 'narrow', narrow_text(), args.samples)
        shutil.copyfile(config.asset_data_dir / config.font_file_name, Path(temp_dir) / config.font_file_name)
        measure(function.create_text_image, 'wide', wide_text(), args.samples)


if __name__ == '__main__':
    main()
