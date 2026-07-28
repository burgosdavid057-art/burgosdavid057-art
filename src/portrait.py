"""Foto -> rejilla de puntos 1-bit.

El retrato es lo que define el banner. El orden importa: recorte, segmentación
del fondo, contraste, y sólo al final el dithering. Invertir cualquiera de esos
pasos degrada el resultado.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from scipy import ndimage

GRID_W, GRID_H = 300, 340


def load_and_crop(path: str, crop: tuple[int, int, int, int] | None = None) -> Image.Image:
    """Carga la foto y la recorta a cabeza+hombros con el aspecto de la rejilla.

    `crop` es (x, y, w, h) en píxeles de la foto original. Sin él, tomamos un
    encuadre centrado en la parte alta de la imagen, que es donde suele estar la
    cara en un retrato. Casi siempre vas a querer ajustarlo a mano.
    """
    img = Image.open(path).convert("RGB")
    img = ImageOps.exif_transpose(img)
    W, H = img.size
    aspect = GRID_W / GRID_H

    if crop is None:
        # encuadre por defecto: ancho completo limitado por el aspecto, anclado arriba
        cw = min(W, int(H * aspect))
        ch = int(cw / aspect)
        cx = (W - cw) // 2
        cy = int(H * 0.04)
        if cy + ch > H:
            cy = max(0, H - ch)
        crop = (cx, cy, cw, ch)

    x, y, w, h = crop
    return img.crop((x, y, x + w, y + h)).resize((GRID_W, GRID_H), Image.LANCZOS)


def segment_subject(img: Image.Image, threshold: float = 42.0) -> np.ndarray:
    """Máscara booleana del sujeto, separándolo de un fondo plano.

    Estima el color de fondo con la mediana del borde, marca como sujeto todo lo
    que se aleje de ese color, y luego limpia: cierre binario, relleno de huecos
    y se queda con la componente conexa más grande.
    """
    a = np.asarray(img, dtype=np.float32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]], axis=0)
    bg = np.median(border, axis=0)

    dist = np.linalg.norm(a - bg, axis=2)
    mask = dist > threshold

    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5)))
    mask = ndimage.binary_fill_holes(mask)

    labels, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, labels, range(1, n + 1))
        mask = labels == (int(np.argmax(sizes)) + 1)
    mask = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
    return mask


def prepare_luma(img: Image.Image, contrast: float = 1.3) -> np.ndarray:
    """Luminancia lista para ditherar: autocontraste, contraste suave y enfoque.

    1.3x y no más: a 2.4x la cara se vuelve dura y calavérica.
    """
    g = img.convert("L")
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(contrast)
    g = g.filter(ImageFilter.UnsharpMask(radius=3, percent=140, threshold=2))
    return np.asarray(g, dtype=np.float32)


def dither(luma: np.ndarray) -> np.ndarray:
    """Floyd-Steinberg 1-bit en orden serpentina.

    Serpentina (izq->der, der->izq alternando) en vez de raster, porque el raster
    arrastra el error siempre hacia el mismo lado y deja vetas diagonales.
    Devuelve True donde el píxel queda blanco (claro).
    """
    buf = luma.astype(np.float32).copy()
    h, w = buf.shape
    out = np.zeros((h, w), dtype=bool)

    for y in range(h):
        ltr = (y % 2) == 0
        xs = range(w) if ltr else range(w - 1, -1, -1)
        step = 1 if ltr else -1
        for x in xs:
            old = buf[y, x]
            new = 255.0 if old >= 128.0 else 0.0
            out[y, x] = new > 0
            err = old - new
            nxt = x + step
            if 0 <= nxt < w:
                buf[y, nxt] += err * 7 / 16
            if y + 1 < h:
                if 0 <= x - step < w:
                    buf[y + 1, x - step] += err * 3 / 16
                buf[y + 1, x] += err * 5 / 16
                if 0 <= nxt < w:
                    buf[y + 1, nxt] += err * 1 / 16
    return out


def build_dots_from_art(path: str, spacing: int = 2, pad: float = 0.04) -> np.ndarray:
    """Rejilla de puntos para arte PLANO (un logo, un monograma).

    Un logo de dos colores no tiene rango tonal, así que pasarlo por el
    dithering no sirve de nada: Floyd-Steinberg reparte error entre grises, y
    aquí sólo hay dos valores. El resultado sería una mancha maciza.

    En su lugar recortamos la silueta y la calamos con una retícula regular:
    se lee como puntos a propósito, conserva los contornos nítidos, y las dos
    animaciones (el titileo de entrada y el arrastre por bandas) funcionan
    igual porque sólo necesitan un conjunto de puntos.
    """
    im = ImageOps.exif_transpose(Image.open(path).convert("RGBA"))
    arr = np.asarray(im)

    mask = arr[..., 3] > 128
    if mask.all():
        # PNG sin transparencia: separamos del fondo por distancia de color
        rgb = arr[..., :3].astype(np.float32)
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]], axis=0)
        mask = np.linalg.norm(rgb - np.median(border, axis=0), axis=2) > 40

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError(f"no encontré arte opaca en {path}")
    crop = mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

    h, w = crop.shape
    scale = min(GRID_W * (1 - 2 * pad) / w, GRID_H * (1 - 2 * pad) / h)
    resized = np.asarray(
        Image.fromarray(crop).resize(
            (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
        )
    ) > 0

    out = np.zeros((GRID_H, GRID_W), dtype=bool)
    y0 = (GRID_H - resized.shape[0]) // 2
    x0 = (GRID_W - resized.shape[1]) // 2
    out[y0: y0 + resized.shape[0], x0: x0 + resized.shape[1]] = resized

    rr, cc = np.mgrid[0:GRID_H, 0:GRID_W]
    return out & (rr % spacing == 0) & (cc % spacing == 0)


def build_dots(
    path: str,
    mode: str,
    crop: tuple[int, int, int, int] | None = None,
    contrast: float = 1.3,
    threshold: float = 42.0,
) -> np.ndarray:
    """Rejilla booleana de puntos a dibujar, para `mode` in {'dark','light'}.

    dark : se recorta el fondo y los puntos dibujan al sujeto ILUMINADO. Sin el
           recorte el modo oscuro parece un negativo fotográfico.
    light: se conserva el fondo y los puntos dibujan las zonas OSCURAS.
    """
    img = load_and_crop(path, crop)
    luma = prepare_luma(img, contrast)

    if mode == "dark":
        mask = segment_subject(img, threshold)
        # apagamos el fondo ANTES de ditherar para que no genere puntos,
        # y lo volvemos a limpiar DESPUÉS para matar el sangrado del error
        luma = np.where(mask, luma, 0.0)
        dots = dither(luma) & mask
    elif mode == "light":
        dots = ~dither(luma)
    else:
        raise ValueError(f"modo desconocido: {mode}")

    return dots
