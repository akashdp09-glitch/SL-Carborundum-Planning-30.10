"""Small on-screen build identity from the release manifest; no live data paths."""
import json
from pathlib import Path


def text(root):
    root=Path(root)
    version=(root/'VERSION').read_text().strip() if (root/'VERSION').exists() else 'Unknown version'
    try:
        manifest=json.loads((root/'RELEASE_MANIFEST.json').read_text())
        built=manifest.get('built_at_bangkok') or 'Not recorded';commit=str(manifest.get('commit') or '')[:8]
    except (OSError,ValueError):built='Development copy';commit=''
    return f'{version} · โฟลเดอร์ / Folder: {root.name} · สร้างเมื่อ / Built: {built} · {commit}'
