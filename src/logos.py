"""Rasteriza logos reales (simple-icons) y los convierte en nubes de puntos.

No dibujamos los logos a mano: tomamos el path oficial de simple-icons, lo
aplanamos con svgelements y lo rellenamos con regla even-odd (cada subpath se
rasteriza aparte y se combina con XOR, que es lo que produce los huecos).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw
from svgelements import Path


def _subpath_polygons(d: str, samples_per_seg: int = 24) -> list[list[tuple[float, float]]]:
    """Aplana un path SVG en una lista de polígonos, uno por subpath."""
    path = Path(d)
    polys: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    for seg in path:
        name = type(seg).__name__
        if name == "Move":
            if len(current) >= 3:
                polys.append(current)
            current = [(seg.end.x, seg.end.y)]
            continue
        if name == "Close":
            if len(current) >= 3:
                polys.append(current)
            current = []
            continue
        if seg.start is None or seg.end is None:
            continue
        if name == "Line":
            current.append((seg.end.x, seg.end.y))
        else:  # Cubic, Quad, Arc -> muestreamos la curva
            for i in range(1, samples_per_seg + 1):
                p = seg.point(i / samples_per_seg)
                current.append((p.x, p.y))

    if len(current) >= 3:
        polys.append(current)
    return polys


def rasterize_icon(d: str, size: int = 512, viewbox: float = 24.0, pad: float = 0.06) -> np.ndarray:
    """Devuelve una máscara booleana size x size con la tinta del logo."""
    polys = _subpath_polygons(d)
    inner = size * (1.0 - 2 * pad)
    scale = inner / viewbox
    off = size * pad

    acc = np.zeros((size, size), dtype=bool)
    for poly in polys:
        img = Image.new("1", (size, size), 0)
        ImageDraw.Draw(img).polygon(
            [(x * scale + off, y * scale + off) for x, y in poly], fill=1
        )
        # even-odd: cada subpath invierte lo que ya había (así salen los huecos)
        acc ^= np.array(img, dtype=bool)
    return acc


def rasterize_glyph(text: str, size: int = 512, pad: float = 0.06) -> np.ndarray:
    """Máscara de un texto corto (p. ej. `</>`) en monoespaciada bold.

    Para el glifo genérico de dev no hay icono oficial que trazar, así que lo
    sacamos de la fuente del sistema y lo tratamos igual que un logo.
    """
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\consolab.ttf",
        r"C:\Windows\Fonts\CascadiaMono.ttf",
        r"C:\Windows\Fonts\lucon.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ]
    font = None
    for path in candidates:
        try:
            font = ImageFont.truetype(path, int(size * 0.6))
            break
        except OSError:
            continue
    if font is None:
        raise RuntimeError("no encontré una fuente monoespaciada en el sistema")

    probe = Image.new("1", (size * 3, size * 3), 0)
    ImageDraw.Draw(probe).text((size, size), text, font=font, fill=1)
    arr = np.array(probe, dtype=bool)
    ys, xs = np.nonzero(arr)
    crop = arr[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

    # encajamos el recorte en el lienzo final conservando el aspecto
    h, w = crop.shape
    inner = size * (1.0 - 2 * pad)
    scale = min(inner / w, inner / h)
    resized = np.array(
        Image.fromarray(crop).resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS
        ),
        dtype=bool,
    )
    out = np.zeros((size, size), dtype=bool)
    y0 = (size - resized.shape[0]) // 2
    x0 = (size - resized.shape[1]) // 2
    out[y0: y0 + resized.shape[0], x0: x0 + resized.shape[1]] = resized
    return out


def _fit_to_box(pts: np.ndarray, box_w: float, box_h: float) -> np.ndarray:
    """Escala y centra una nube de puntos dentro de una caja, conservando aspecto."""
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    scale = min(box_w / span[0], box_h / span[1])
    centred = (pts - (lo + hi) / 2.0) * scale
    return centred + np.array([box_w / 2.0, box_h / 2.0])


def sample_points(
    mask: np.ndarray,
    n: int,
    box_w: float,
    box_h: float,
    rng: np.random.Generator,
    relax_iters: int = 12,
) -> np.ndarray:
    """Muestrea n puntos bien repartidos sobre la tinta de la máscara.

    Muestreo aleatorio + relajación de Lloyd ligera, para que los puntos queden
    espaciados de forma pareja en vez de agrumarse.
    """
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError("la máscara del logo salió vacía")

    ink = np.stack([xs.astype(float), ys.astype(float)], axis=1)
    idx = rng.choice(len(ink), size=min(n, len(ink)), replace=False)
    pts = ink[idx]
    if len(pts) < n:  # logo diminuto: completamos con repetición jitterada
        extra = rng.choice(len(ink), size=n - len(pts), replace=True)
        pts = np.vstack([pts, ink[extra] + rng.normal(0, 0.5, (n - len(pts), 2))])

    # Lloyd: cada píxel de tinta se asigna a su punto más cercano; el punto se
    # mueve al centroide de los suyos. Espacia la nube sin salirse de la forma.
    from scipy.spatial import cKDTree

    sub = ink[rng.choice(len(ink), size=min(len(ink), 40000), replace=False)]
    for _ in range(relax_iters):
        tree = cKDTree(pts)
        _, owner = tree.query(sub, workers=-1)
        sums = np.zeros_like(pts)
        counts = np.zeros(len(pts))
        np.add.at(sums, owner, sub)
        np.add.at(counts, owner, 1)
        moved = counts > 0
        pts[moved] = sums[moved] / counts[moved][:, None]

    return _fit_to_box(pts, box_w, box_h)


def match_optimal_transport(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Reordena b para que b[i] sea el destino más barato de a[i] (asignación húngara).

    Minimiza la suma de distancias al cuadrado, así ningún punto cruza el logo
    entero mientras otro se queda quieto.
    """
    from scipy.optimize import linear_sum_assignment

    cost = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
    _, col = linear_sum_assignment(cost)
    return b[col]


def build_traveller_cloud(
    masks: list[np.ndarray], n: int, box_w: float, box_h: float, seed: int = 7
) -> list[np.ndarray]:
    """Nubes de n puntos, una por logo, con el índice i alineado entre todas."""
    rng = np.random.default_rng(seed)
    clouds = [sample_points(m, n, box_w, box_h, rng) for m in masks]
    for i in range(1, len(clouds)):
        clouds[i] = match_optimal_transport(clouds[i - 1], clouds[i])
    return clouds
