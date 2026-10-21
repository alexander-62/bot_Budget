"""Managed local profile pictures, independent of Telegram and token settings."""
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4
import warnings

from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 16_000_000
IMAGE_SIZE = (512, 512)
_FORMATS = {"PNG", "JPEG", "WEBP", "BMP"}
_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
_ERROR = "Не удалось открыть картинку. Выберите PNG, JPEG, WebP или BMP до 10 МБ и 16 миллионов пикселей."


def managed_image_path(image_file: str, base_dir: Path = BASE_DIR) -> Path | None:
    if not isinstance(image_file, str) or not re.fullmatch(r"\.profile-images/[0-9a-f]{32}\.png", image_file):
        return None
    try:
        base = Path(base_dir).resolve()
        directory = base / ".profile-images"
        path = base / image_file
        if directory.resolve() != directory or path.resolve() != path:
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return path


def _decode(path: Path, size: tuple[int, int]) -> Image.Image:
    if path.suffix.lower() not in _EXTENSIONS or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError(_ERROR)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            if source.format not in _FORMATS or source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError(_ERROR)
            source.load()
            transposed = ImageOps.exif_transpose(source)
            try:
                rgba = transposed.convert("RGBA")
                try:
                    return ImageOps.fit(rgba, size, method=Image.Resampling.LANCZOS)
                finally:
                    rgba.close()
            finally:
                transposed.close()


def import_profile_image(path: Path, base_dir: Path = BASE_DIR) -> str:
    image = None
    filename = None
    try:
        image = _decode(Path(path), IMAGE_SIZE)
        directory = Path(base_dir) / ".profile-images"
        # Managed storage cannot redirect outside the selected installation.
        target_name = uuid4().hex + ".png"
        relative = ".profile-images/" + target_name
        target = managed_image_path(relative, base_dir)
        if target is None:
            raise ValueError(_ERROR)
        directory.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "wb") as stream:
            image.save(stream, format="PNG")
        os.replace(filename, target)
        return relative
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError(_ERROR) from None
    finally:
        if image is not None:
            image.close()
        if filename is not None:
            Path(filename).unlink(missing_ok=True)


def load_profile_image(profile, base_dir: Path = BASE_DIR, size: tuple[int, int] = (146, 146)) -> Image.Image | None:
    if len(size) != 2 or any(type(value) is not int or not 1 <= value <= 512 for value in size):
        raise ValueError("Размер картинки должен быть от 1 до 512 пикселей.")
    selected = managed_image_path(getattr(profile, "image_file", ""), base_dir)
    for path in (selected, Path(base_dir) / "logo.png"):
        if path is None:
            continue
        try:
            return _decode(path, size)
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            continue
    return None
