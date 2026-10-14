import os
import re
from . import config


def path_for(document_id: int, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    ext = ext if re.fullmatch(r"\.[a-z0-9]{1,5}", ext) else ".bin"
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    return os.path.join(config.UPLOAD_DIR, f"{document_id}{ext}")
