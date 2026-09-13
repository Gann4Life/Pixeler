'''Source image -> crop (centered square of the selection) -> GRID x GRID -> adjustments -> palette limit -> output image.

Everything here is pure: same inputs, same output. The UI re-runs `process`
on every slider/crop change; at 32x32 that is essentially free.
'''
from dataclasses import dataclass, asdict, fields

from PIL import Image, ImageEnhance, ImageOps

from .calibration import GRID


@dataclass
class NormRect:
    '''Crop rectangle normalized to the source image (0..1), so it survives
    loading a new image of a different size.'''
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0

    @staticmethod
    def full() -> 'NormRect':
        return NormRect()

    def is_full(self) -> bool:
        return self.x <= 0 and self.y <= 0 and self.w >= 1 and self.h >= 1

    def clamped(self) -> 'NormRect':
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return NormRect(x, y, w, h)

    def to_box(self, width: int, height: int) -> tuple:
        '''Pixel box (left, top, right, bottom); never empty.'''
        r = self.clamped()
        left = int(round(r.x * width))
        top = int(round(r.y * height))
        right = int(round((r.x + r.w) * width))
        bottom = int(round((r.y + r.h) * height))
        right = max(right, min(left + 1, width))
        bottom = max(bottom, min(top + 1, height))
        left = min(left, right - 1)
        top = min(top, bottom - 1)
        return (left, top, right, bottom)

    def to_square_box(self, width: int, height: int) -> tuple:
        '''The centered square inside the crop box — what actually gets drawn.
        The output is always 1:1, so the selection is cropped to fit, never stretched.'''
        left, top, right, bottom = self.to_box(width, height)
        w, h = right - left, bottom - top
        side = min(w, h)
        left += (w - side) // 2
        top += (h - side) // 2
        return (left, top, left + side, top + side)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d) -> 'NormRect':
        if not d:
            return NormRect()
        return NormRect(**{f.name: float(d.get(f.name, getattr(NormRect(), f.name))) for f in fields(NormRect)}).clamped()


@dataclass
class Adjustments:
    brightness: float = 1.0      # ImageEnhance factor, 1.0 = unchanged
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    palette_limit: int = 0       # 0 = unlimited, else 2..256
    dither: bool = False
    invert: bool = False         # negative of the picture (after the other adjustments)
    alpha_threshold: int = 1     # pixels with alpha below this are skipped (0 = draw everything)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d) -> 'Adjustments':
        a = Adjustments()
        if not d:
            return a
        for f in fields(Adjustments):
            if f.name in d:
                try:
                    setattr(a, f.name, f.type(d[f.name]))
                except (TypeError, ValueError):
                    pass
        return a


def to_rgba(img: Image.Image) -> Image.Image:
    return img if img.mode == 'RGBA' else img.convert('RGBA')


def process(source: Image.Image, crop: NormRect, adj: Adjustments, size: int = GRID) -> Image.Image:
    '''Returns a size x size RGBA image; alpha is binary (0 = skip, 255 = draw).'''
    src = to_rgba(source)
    cropped = src.crop(crop.to_square_box(src.width, src.height))

    # Average when shrinking (keeps detail), nearest when enlarging (keeps pixels crisp).
    shrinking = cropped.width >= size and cropped.height >= size
    resample = Image.Resampling.BOX if shrinking else Image.Resampling.NEAREST
    small = cropped.resize((size, size), resample)

    rgb = small.convert('RGB')
    alpha = small.getchannel('A')

    if adj.brightness != 1.0:
        rgb = ImageEnhance.Brightness(rgb).enhance(adj.brightness)
    if adj.contrast != 1.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(adj.contrast)
    if adj.saturation != 1.0:
        rgb = ImageEnhance.Color(rgb).enhance(adj.saturation)
    if adj.gamma != 1.0 and adj.gamma > 0:
        inv = 1.0 / adj.gamma
        lut = [round(255 * ((i / 255) ** inv)) for i in range(256)]
        rgb = rgb.point(lut * 3)

    if adj.invert:
        rgb = ImageOps.invert(rgb)

    if adj.palette_limit and adj.palette_limit > 0:
        colors = max(2, min(256, int(adj.palette_limit)))
        # Pillow ignores `dither` unless a palette is given, so: pick the palette, then map with it.
        pal = rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
        if adj.dither:
            pal = rgb.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
        rgb = pal.convert('RGB')

    thr = max(0, min(255, int(adj.alpha_threshold)))
    alpha = alpha.point(lambda a: 255 if a >= thr else 0)

    out = rgb.convert('RGBA')
    out.putalpha(alpha)
    return out
