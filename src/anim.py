"""Agrupación de puntos para las dos animaciones, con métricas que la verifican.

Las dos agrupaciones tienen una trampa conocida y cada una trae su métrica:
  - intro: si los grupos son regiones espaciales, el retrato aparece por parches
    en vez de titilar entero. Métrica: distancia de variación total.
  - drift: el desplazamiento es lineal en la posición, así que cuantizarlo
    reconstruye una cuadrícula. Métrica: fracción de frontera recta.
"""

from __future__ import annotations

import numpy as np


def intro_groups(xy: np.ndarray, n_groups: int, rng: np.random.Generator) -> np.ndarray:
    """Asigna cada punto a un grupo de entrada, al azar y sin sesgo espacial.

    Barajamos los índices y repartimos en round-robin: cada grupo queda esparcido
    por todo el retrato, que es justo lo que hace que los puntos aparezcan por
    todas partes a la vez y engorden juntos.
    """
    order = rng.permutation(len(xy))
    groups = np.empty(len(xy), dtype=np.int32)
    groups[order] = np.arange(len(xy)) % n_groups
    return groups


def evenness(xy: np.ndarray, groups: np.ndarray, cells: int = 4,
             seed: int = 0) -> float:
    """Cuánto se aparta cada grupo de estar repartido por todo el retrato.

    Se mide como distancia de variación total contra el retrato completo, pero
    devolvemos la RAZÓN contra un reparto aleatorio del mismo tamaño. En bruto
    el número depende de cuántos puntos caen en cada grupo -- una retícula de
    logo tiene muchos menos que un retrato ditherado -- y entonces el ruido de
    muestreo se confunde con agrupamiento espacial.

    ~1.0 = tan esparcido como el azar (bien).
    >>1  = los grupos son parches y el retrato se revela por zonas.
    """
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    cell = np.clip(((xy - lo) / span * cells).astype(int), 0, cells - 1)
    cell_id = cell[:, 0] * cells + cell[:, 1]
    n_cells = cells * cells

    overall = np.bincount(cell_id, minlength=n_cells).astype(float)
    overall /= overall.sum()

    def mean_tv(assign: np.ndarray) -> float:
        scores = []
        for g in np.unique(assign):
            sel = cell_id[assign == g]
            if len(sel) == 0:
                continue
            p = np.bincount(sel, minlength=n_cells).astype(float)
            p /= p.sum()
            scores.append(0.5 * np.abs(p - overall).sum())
        return float(np.mean(scores)) if scores else 0.0

    observed = mean_tv(groups)
    baseline = mean_tv(np.random.default_rng(seed).permutation(groups))
    return observed / baseline if baseline > 1e-9 else 0.0


def drift_bands(
    xy: np.ndarray,
    target: np.ndarray,
    n_bands: int,
    rng: np.random.Generator,
    sigma_bands: float = 0.55,
) -> tuple[np.ndarray, np.ndarray]:
    """Agrupa los puntos en bandas según su avance hacia `target`.

    El ruido por punto es obligatorio: sin él, cuantizar una función lineal de
    la posición produce franjas de borde recto y la disolución se ve a bloques.
    Pero pasarse lo rompe igual por el otro lado, así que `sigma_bands` va en
    anchos de banda, no en píxeles: es la única escala en la que el valor
    significa lo mismo aunque cambien el tamaño del retrato o `n_bands`.
    """
    direction = target - xy.mean(axis=0)
    norm = np.linalg.norm(direction)
    direction = direction / norm if norm > 1e-9 else np.array([1.0, 0.0])

    proj = xy @ direction
    band_width = (proj.max() - proj.min()) / n_bands
    proj = proj + rng.normal(0.0, sigma_bands * band_width, size=len(proj))

    ranks = np.argsort(np.argsort(proj))
    return (ranks * n_bands // len(proj)).astype(np.int32), direction


def boundary_metrics(
    ij: np.ndarray, bands: np.ndarray, direction: np.ndarray, n_bands: int
) -> tuple[float, float]:
    """Dos formas de arruinar las bandas, medidas por separado.

    Hacen falta las dos: una sola se deja engañar. Contar celdas de frontera,
    por ejemplo, premia el ruido extremo, porque cuando la asignación es casi
    aleatoria *todo* es frontera y el número se dispara.

    flat   -- fracción de columnas donde el borde de ataque de la banda no se
              mueve ni una celda. ~1.0 = borde de cuchillo, el efecto bloque.
              Queremos < 0.30.
    spread -- dispersión de la banda medida en anchos de banda. 0.29 es una
              franja perfectamente compacta; por encima de ~1.5 las bandas se
              solapan tanto que dejan de leerse como franjas y el barrido se
              vuelve estática. Queremos ~0.4-1.2.
    """
    # el borde de ataque se mide cruzando las franjas: si las bandas son
    # horizontales barremos columnas, y al revés
    horizontal_stripes = abs(direction[1]) >= abs(direction[0])
    across = ij[:, 1] if horizontal_stripes else ij[:, 0]
    along = ij[:, 0] if horizontal_stripes else ij[:, 1]

    flats: list[float] = []
    for b in range(n_bands):
        sel = bands == b
        if sel.sum() < 8:
            continue
        a, l = across[sel], along[sel]
        order = np.argsort(a)
        a, l = a[order], l[order]
        # borde de ataque de la banda en cada columna transversal
        uniq, first = np.unique(a, return_index=True)
        edge = np.minimum.reduceat(l, first)
        if len(edge) < 2:
            continue
        step = np.diff(edge)[np.diff(uniq) == 1]
        if len(step):
            flats.append(float((step == 0).mean()))

    proj = ij @ np.array([direction[1], direction[0]])
    width = (proj.max() - proj.min()) / n_bands
    spreads = [
        float(proj[bands == b].std()) / width
        for b in range(n_bands)
        if (bands == b).sum() >= 8
    ]

    return float(np.mean(flats)) if flats else 0.0, float(np.median(spreads))
