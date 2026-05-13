"""Pytest config — adds the project root to sys.path so `import builder` works
without an editable install.  Also provides a tiny slugify shim when the real
python-slugify package isn't installed (e.g. in restricted CI/dev sandboxes)
so the smoke tests can still run.  Real environments install python-slugify
via requirements.txt.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import slugify  # noqa: F401
except ImportError:  # pragma: no cover — only triggers in offline sandboxes
    shim = types.ModuleType("slugify")

    def _shim(s: str, **_kwargs) -> str:
        import re
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9]+", "-", s)
        return s.strip("-")

    shim.slugify = _shim
    sys.modules["slugify"] = shim
