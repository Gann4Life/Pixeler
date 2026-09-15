'''An "artwork" is one picture ready to draw: the source image plus everything that decides
*what* gets drawn (crop, adjustments, draw order and seed, color order) and the Input view
(zoom/pan). How the machine draws it (pen, speed, FPS, hotkeys) is not part of it; that
lives in ui_state.json because it depends on the game's frame rate, not on the picture.

Layout on disk, one folder per artwork under ARTWORKS_DIR:
    <name>/source.png    the source image, lossless
    <name>/artwork.json  the settings below plus a little metadata for the list
    <name>/preview.png   the 32x32 output at save time, so listing never decodes a big photo
'''
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field

from PIL import Image

from .order import DEFAULT_METHOD, DEFAULT_COLOR_ORDER, method_keys, color_order_keys
from .pipeline import NormRect, Adjustments, to_rgba

ARTWORKS_DIR = 'artworks'
FORMAT = 1
SOURCE, META, PREVIEW = 'source.png', 'artwork.json', 'preview.png'
MAX_NAME = 64
_ILLEGAL = re.compile(r'[\/:*?"<>|\x00-\x1f]')


def safe_name(name: str) -> str:
    '''Artwork name -> folder name. Raises ValueError when nothing usable is left.'''
    name = _ILLEGAL.sub('', str(name or ''))
    name = ' '.join(name.split()).strip('. ')[:MAX_NAME].rstrip('. ')
    if not name:
        raise ValueError("Give the artwork a name.")
    return name


def default_view() -> dict:
    return {"zoom": 1.0, "pan": [0.0, 0.0]}


@dataclass
class Artwork:
    crop: NormRect = field(default_factory=NormRect)
    adjustments: Adjustments = field(default_factory=Adjustments)
    draw_method: str = DEFAULT_METHOD
    draw_seed: int = 0
    color_order: str = DEFAULT_COLOR_ORDER
    view: dict = field(default_factory=default_view)

    def to_dict(self) -> dict:
        return {
            "crop": self.crop.to_dict(),
            "adjustments": self.adjustments.to_dict(),
            "draw_method": self.draw_method,
            "draw_seed": self.draw_seed,
            "color_order": self.color_order,
            "view": self.view,
        }

    @staticmethod
    def from_dict(d) -> 'Artwork':
        '''Tolerant, like UiState.from_dict: anything odd falls back to its default.'''
        d = d or {}
        a = Artwork()
        a.crop = NormRect.from_dict(d.get("crop"))
        a.adjustments = Adjustments.from_dict(d.get("adjustments"))
        if d.get("draw_method") in method_keys():
            a.draw_method = d["draw_method"]
        if d.get("color_order") in color_order_keys():
            a.color_order = d["color_order"]
        try:
            a.draw_seed = int(d.get("draw_seed", 0))
        except (TypeError, ValueError):
            pass
        v = d.get("view") or {}
        try:
            zoom = float(v.get("zoom", 1.0))
            pan = [float(v.get("pan", [0, 0])[0]), float(v.get("pan", [0, 0])[1])]
            a.view = {"zoom": zoom, "pan": pan}
        except (TypeError, ValueError, IndexError, AttributeError):
            pass
        return a


@dataclass
class ArtworkInfo:
    '''One row of the list; built from artwork.json only, no image decoding.'''
    name: str
    path: str
    saved_at: float
    source_size: tuple
    colors: int
    steps: int


def _dir(name: str, root: str) -> str:
    return os.path.join(root, safe_name(name))


def artwork_exists(name: str, root: str = ARTWORKS_DIR) -> bool:
    try:
        return os.path.isfile(os.path.join(_dir(name, root), META))
    except ValueError:
        return False


def _info(name: str, path: str, meta: dict) -> ArtworkInfo:
    size = meta.get("source_size") or (0, 0)
    return ArtworkInfo(name=name, path=path,
                       saved_at=float(meta.get("saved_at") or os.path.getmtime(os.path.join(path, META))),
                       source_size=(int(size[0]), int(size[1])),
                       colors=int(meta.get("colors") or 0), steps=int(meta.get("steps") or 0))


def list_artworks(root: str = ARTWORKS_DIR) -> list:
    '''Newest first. Folders without a readable artwork.json are skipped (and reported once).'''
    if not os.path.isdir(root):
        return []
    infos = []
    for entry in os.scandir(root):
        if not entry.is_dir() or entry.name.endswith('.tmp'):
            continue
        try:
            with open(os.path.join(entry.path, META), 'r') as f:
                infos.append(_info(entry.name, entry.path, json.load(f)))
        except (OSError, ValueError, TypeError, KeyError, IndexError) as e:
            print(f"[artwork] skipping {entry.path}: {e}")
    infos.sort(key=lambda i: i.saved_at, reverse=True)
    return infos


def save_artwork(name: str, source: Image.Image, output, artwork: Artwork,
                 colors: int = 0, steps: int = 0, root: str = ARTWORKS_DIR) -> ArtworkInfo:
    '''Writes the folder atomically: everything goes to <name>.tmp, then replaces <name>.'''
    final = _dir(name, root)
    tmp = final + '.tmp'
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    to_rgba(source).save(os.path.join(tmp, SOURCE), 'PNG')
    if output is not None:
        to_rgba(output).save(os.path.join(tmp, PREVIEW), 'PNG')
    meta = artwork.to_dict()
    meta.update({"format": FORMAT, "saved_at": time.time(), "source_size": [source.width, source.height],
                 "colors": int(colors), "steps": int(steps)})
    with open(os.path.join(tmp, META), 'w') as f:
        json.dump(meta, f, indent=2)
    if os.path.isdir(final):
        shutil.rmtree(final)
    os.replace(tmp, final)
    return _info(os.path.basename(final), final, meta)


def load_artwork(name: str, root: str = ARTWORKS_DIR):
    '''Returns (RGBA source image, Artwork). FileNotFoundError / ValueError on a broken folder.'''
    path = _dir(name, root)
    with open(os.path.join(path, META), 'r') as f:
        meta = json.load(f)
    if not isinstance(meta, dict):
        raise ValueError(f"{META} is not an object")
    img = Image.open(os.path.join(path, SOURCE))
    img.load()
    return to_rgba(img), Artwork.from_dict(meta)


def load_preview(name: str, root: str = ARTWORKS_DIR):
    try:
        img = Image.open(os.path.join(_dir(name, root), PREVIEW))
        img.load()
        return to_rgba(img)
    except (OSError, ValueError):
        return None


def rename_artwork(old: str, new: str, root: str = ARTWORKS_DIR) -> str:
    '''Returns the (sanitised) new name. Refuses to clobber another artwork.'''
    src, dst = _dir(old, root), _dir(new, root)
    if src == dst:
        return os.path.basename(dst)
    if os.path.exists(dst) and os.path.normcase(src) != os.path.normcase(dst):   # case-only rename is fine
        raise FileExistsError(f"An artwork called '{os.path.basename(dst)}' already exists.")
    os.rename(src, dst)
    return os.path.basename(dst)


def delete_artwork(name: str, root: str = ARTWORKS_DIR):
    shutil.rmtree(_dir(name, root))
