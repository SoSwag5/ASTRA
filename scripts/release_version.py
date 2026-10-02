"""Read the reviewed release version; reject values unsafe for artifact paths."""
import re
from pathlib import Path

VERSION_PATH = Path(__file__).resolve().parents[1] / 'VERSION'


def load_version(path=VERSION_PATH):
    version = Path(path).read_text(encoding='utf-8').strip()
    number = r'(?:0|[1-9][0-9]*)'
    label = r'(?:alpha|beta|rc)\.' + number
    if not re.fullmatch(number + r'\.' + number + r'\.' + number + r'(?:-' + label + r')?', version):
        raise ValueError('VERSION must be a release or alpha/beta/rc Semantic Version')
    return version


VERSION = load_version()
