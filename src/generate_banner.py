"""Genera dark.svg y light.svg.

Uso:
    python src/generate_banner.py --photo ruta/a/foto.jpg
    python src/generate_banner.py --photo foto.jpg --crop 320,140,900,1020 --contrast 1.35

El script es la fuente de la verdad, no el SVG. No edites los SVG a mano:
regenéralos.
"""

from __future__ import annotations

import argparse
import os
import sys
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import anim
import config as C
import logos
import portrait


# --------------------------------------------------------------------------
# Retrato -> tiras horizontales
# --------------------------------------------------------------------------
def dither_runs(dots: np.ndarray) -> np.ndarray:
    """Corridas horizontales máximas del dithering, como (fila, col_ini, col_fin).

    Dibujamos tiras y no puntos sueltos: los píxeles contiguos de un dithering
    forman zonas sólidas, así que una tira por corrida baja mucho el peso del
    archivo sin cambiar un solo píxel.
    """
    runs = []
    for r in range(dots.shape[0]):
        cols = np.nonzero(dots[r])[0]
        if len(cols) == 0:
            continue
        cut = np.nonzero(np.diff(cols) != 1)[0]
        starts = np.concatenate([[cols[0]], cols[cut + 1]])
        ends = np.concatenate([cols[cut], [cols[-1]]])
        runs.extend((r, s, e) for s, e in zip(starts, ends))
    return np.array(runs, dtype=np.int32)


def split_runs_by_group(runs: np.ndarray, group_grid: np.ndarray) -> np.ndarray:
    """Parte cada corrida donde cambie el grupo, y devuelve (fila, ini, fin, grupo)."""
    out = []
    for r, c0, c1 in runs:
        row = group_grid[r, c0:c1 + 1]
        cut = np.nonzero(np.diff(row) != 0)[0]
        starts = np.concatenate([[0], cut + 1])
        ends = np.concatenate([cut, [len(row) - 1]])
        out.extend((r, c0 + s, c0 + e, row[s]) for s, e in zip(starts, ends))
    return np.array(out, dtype=np.int32)


def runs_path(runs: np.ndarray) -> str:
    """Path en coordenadas ENTERAS de rejilla.

    Los enteros son el motivo por el que las capas del retrato van dentro de un
    `translate(...) scale(PITCH)`: `M12 3h5v1h-5z` pesa bastante menos que el
    mismo rectángulo escrito en píxeles con decimales, y son decenas de miles.
    """
    return "".join(
        f"M{c0} {r}h{c1 - c0 + 1}v1h-{c1 - c0 + 1}z" for r, c0, c1 in runs[:, :3]
    )


# --------------------------------------------------------------------------
# Capas
# --------------------------------------------------------------------------
GRID_TRANSFORM = f'transform="translate({C.ART_X} {C.ART_Y}) scale({C.PITCH})"'


def intro_layer(runs: np.ndarray, colour: str, rng: np.random.Generator,
                static: str | None = None) -> tuple[str, float]:
    """Capa que se ve una sola vez: el retrato titila hasta formarse.

    Es una copia completa del retrato. Fundirla con la capa del bucle rompe la
    animación, porque cada capa necesita su propio calendario de opacidades.

    Agrupamos CORRIDAS, no puntos sueltos. Repartir punto a punto obliga a
    escribir un rectángulo por píxel y dispara el peso del archivo; como las
    corridas de un dithering miden uno o dos píxeles, repartirlas conserva
    igual de bien el requisito de que cada grupo quede esparcido por todo el
    retrato.
    """
    centres = np.stack(
        [(runs[:, 1] + runs[:, 2]) / 2.0, runs[:, 0].astype(float)], axis=1
    )
    groups = anim.intro_groups(centres, C.INTRO_GROUPS, rng)
    score = anim.evenness(centres, groups)

    if static is not None:
        return "", score

    parts = [f'<g id="intro" fill="{colour}" shape-rendering="crispEdges" '
             f'{GRID_TRANSFORM}>']
    for g in range(C.INTRO_GROUPS):
        sel = runs[groups == g]
        if len(sel) == 0:
            continue
        begin = C.INTRO_SPREAD * g / max(1, C.INTRO_GROUPS - 1)
        parts.append(
            f'<path opacity="0" d="{runs_path(sel)}">'
            f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{begin:.2f}s" dur="{C.INTRO_FADE}s" fill="freeze"/></path>'
        )
    parts.append(f'<set attributeName="opacity" to="0" begin="{C.INTRO_DUR}s"/></g>')
    return "".join(parts), score


def loop_layer(runs: np.ndarray, dots_shape: tuple[int, int], xy: np.ndarray,
               ij: np.ndarray, colour: str, target: np.ndarray,
               rng: np.random.Generator,
               static: str | None = None) -> tuple[str, tuple[float, float]]:
    """Capa en bucle: el retrato se deshace en bandas hacia el primer logo y vuelve."""
    bands, direction = anim.drift_bands(
        xy, target, C.N_BANDS, rng, sigma_bands=C.BAND_NOISE
    )
    score = anim.boundary_metrics(ij, bands, direction, C.N_BANDS)

    grid = np.full(dots_shape, -1, dtype=np.int32)
    grid[ij[:, 0], ij[:, 1]] = bands
    tagged = split_runs_by_group(runs, grid)

    if static is not None:
        if static != "portrait":
            return "", score
        return (
            f'<g id="loop" fill="{colour}" shape-rendering="crispEdges" '
            f'{GRID_TRANSFORM}><path d="{runs_path(tagged)}"/></g>',
            score,
        )

    parts = [f'<g id="loop" opacity="0" fill="{colour}" '
             f'shape-rendering="crispEdges" {GRID_TRANSFORM}>'
             f'<set attributeName="opacity" to="1" begin="{C.INTRO_DUR}s"/>']

    for b in range(C.N_BANDS):
        sel = tagged[tagged[:, 3] == b]
        if len(sel) == 0:
            continue
        centre = xy[bands == b].mean(axis=0)
        # el desplazamiento va en unidades de rejilla: el `scale` del padre
        # ya convierte a píxeles
        dx, dy = (target - centre) * C.DRIFT / C.PITCH
        pos = f"{dx:.1f},{dy:.1f}"
        parts.append(
            f'<g><path d="{runs_path(sel)}"/>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0,0;0,0;{pos};{pos};{pos};{pos};{pos};{pos};0,0" '
            f'keyTimes="{C.KEYTIMES}" dur="{C.LOOP_DUR}s" '
            f'begin="{C.INTRO_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="1;1;0;0;0;0;0;0;1" '
            f'keyTimes="{C.KEYTIMES}" dur="{C.LOOP_DUR}s" '
            f'begin="{C.INTRO_DUR}s" repeatCount="indefinite"/></g>'
        )
    parts.append("</g>")
    return "".join(parts), score


def traveller_layer(clouds: list[np.ndarray], colour: str,
                    static: str | None = None) -> str:
    """Enjambre disperso que viaja entre los logos.

    Van ocultos durante la fase del retrato: sus puntos son más gruesos y, si se
    ven encima del dithering fino, lo ensucian.
    """
    a, b, c = clouds
    size = 1.8
    off = -size / 2

    if static is not None:
        idx = {"logo1": 0, "logo2": 1, "logo3": 2}.get(static)
        if idx is None:
            return ""
        pts = clouds[idx]
        body = "".join(
            f'<rect x="{p[0] + off:.1f}" y="{p[1] + off:.1f}" '
            f'width="{size}" height="{size}"/>'
            for p in pts
        )
        return f'<g id="travellers" fill="{colour}" shape-rendering="crispEdges">{body}</g>'

    parts = [f'<g id="travellers" fill="{colour}" shape-rendering="crispEdges">']
    for i in range(len(a)):
        # enteros: el punto mide 1.8 px, la precisión decimal no se ve y
        # cada decimal se paga 900 veces por fotograma clave
        p1 = f"{a[i, 0]:.0f},{a[i, 1]:.0f}"
        p2 = f"{b[i, 0]:.0f},{b[i, 1]:.0f}"
        p3 = f"{c[i, 0]:.0f},{c[i, 1]:.0f}"
        parts.append(
            f'<g opacity="0">'
            f'<rect x="{off}" y="{off}" width="{size}" height="{size}"/>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="{p1};{p1};{p1};{p1};{p2};{p2};{p3};{p3};{p1}" '
            f'keyTimes="{C.KEYTIMES}" dur="{C.LOOP_DUR}s" '
            f'begin="{C.INTRO_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0;1;1;1;1;1;1;0" '
            f'keyTimes="{C.KEYTIMES}" dur="{C.LOOP_DUR}s" '
            f'begin="{C.INTRO_DUR}s" repeatCount="indefinite"/></g>'
        )
    parts.append("</g>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Panel de texto
# --------------------------------------------------------------------------
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"


def _text(x: float, y: float, s: str, size: float, fill: str,
          anchor: str = "start", weight: str = "400") -> str:
    """Texto con ancho bloqueado.

    textLength + lengthAdjust fija el ancho real: sin eso, cada navegador elige
    una monoespaciada distinta y los valores alineados a la derecha se desfasan.
    """
    length = len(s) * C.CHAR_W * (size / 14.0)
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
        f'textLength="{length:.1f}" lengthAdjust="spacingAndGlyphs" '
        f'xml:space="preserve">{escape(s)}</text>'
    )


def panel(p: dict, col: dict) -> str:
    rows = [
        ("Subject", p["name"]),
        ("Role", p["role"]),
        ("Origin", p["origin"]),
        ("Education", p["education"]),
        ("Status", p["status"]),
        ("ToolChain", p["toolchain"]),
        None,
        ("Core.Lang", p["lang"]),
        ("Core.Frontend", p["frontend"]),
        ("Core.Backend", p["backend"]),
        ("Core.Database", p["database"]),
        ("Core.Infra", p["infra"]),
        None,
        ("Grid.Mail", p["mail"]),
        ("Grid.Portfolio", p["portfolio"]),
        ("Grid.LinkedIn", p.get("linkedin", "")),
        ("Grid.GitHub", p["username"]),
        ("Grid.Facebook", p.get("facebook", "")),
    ]
    # un valor vacío quita la fila entera, en vez de dejar el guion colgando
    rows = [r for r in rows if r is None or r[1]]

    out = [_text(C.PANEL_X, 108, "SYSTEM.INFO", 13, col["chrome"], weight="700")]

    # badge LIVE, con el punto latiendo
    out.append(
        f'<circle cx="{C.PANEL_R - 46:.1f}" cy="104" r="4" fill="{col["live"]}">'
        f'<animate attributeName="opacity" values="1;0.25;1" dur="1.4s" '
        f'repeatCount="indefinite"/></circle>'
    )
    out.append(_text(C.PANEL_R, 108, "LIVE", 12, col["live"], anchor="end", weight="700"))
    out.append(
        f'<line x1="{C.PANEL_X}" y1="118" x2="{C.PANEL_R}" y2="118" '
        f'stroke="{col["leader"]}" stroke-width="1"/>'
    )

    y = 142.0
    for row in rows:
        if row is None:
            y += 12.0
            continue
        label, value = row
        out.append(_text(C.PANEL_X, y, label, 14, col["muted"]))
        out.append(_text(C.PANEL_R, y, value, 14, col["text"], anchor="end"))

        # los guías punteados se calculan del largo de etiqueta y valor
        x1 = C.PANEL_X + len(label) * C.CHAR_W + 8
        x2 = C.PANEL_R - len(value) * C.CHAR_W - 8
        if x2 - x1 > 10:
            out.append(
                f'<line x1="{x1:.1f}" y1="{y - 4:.1f}" x2="{x2:.1f}" y2="{y - 4:.1f}" '
                f'stroke="{col["leader"]}" stroke-width="1.5" '
                f'stroke-dasharray="1 5" stroke-linecap="round"/>'
            )
        y += C.ROW_H

    # pastilla con el handle
    handle = "@" + p["username"]
    pw = len(handle) * C.CHAR_W + 26
    py = y + 12
    out.append(
        f'<rect x="{C.PANEL_X}" y="{py:.1f}" width="{pw:.1f}" height="30" rx="15" '
        f'fill="{col["accent"]}" fill-opacity="0.14" stroke="{col["accent"]}" '
        f'stroke-opacity="0.5"/>'
    )
    out.append(_text(C.PANEL_X + 13, py + 20, handle, 14, col["accent"], weight="700"))
    return "".join(out)


def content_frame(dots: np.ndarray, pad: float = 46.0) -> dict:
    """Marco ajustado verticalmente a lo que realmente ocupa el sujeto.

    Un monograma es apaisado y el marco de un retrato es vertical, así que a
    altura fija queda flotando en medio de un hueco. Como el contenido siempre
    se centra en la rejilla, ceñir el marco a su caja lo deja centrado igual.
    """
    rows = np.nonzero(dots.any(axis=1))[0]
    if len(rows) == 0:
        return dict(C.FRAME)
    top = C.ART_Y + rows[0] * C.PITCH
    bottom = C.ART_Y + (rows[-1] + 1) * C.PITCH
    height = min(bottom - top + 2 * pad, C.FRAME["h"])
    return {**C.FRAME, "y": top - pad, "h": height}


def chrome(col: dict, frame: dict) -> str:
    w = C.WIN
    out = [f'<rect width="{C.W}" height="{C.H}" fill="{col["page"]}"/>']
    out.append(
        f'<rect x="{w["x"]}" y="{w["y"]}" width="{w["w"]}" height="{w["h"]}" '
        f'rx="{w["rx"]}" fill="{col["window"]}" stroke="{col["chrome"]}" '
        f'stroke-opacity="0.35"/>'
    )
    ty = w["y"] + C.TITLEBAR_H
    out.append(
        f'<line x1="{w["x"]}" y1="{ty}" x2="{w["x"] + w["w"]}" y2="{ty}" '
        f'stroke="{col["chrome"]}" stroke-opacity="0.35"/>'
    )
    for i, c in enumerate(["#EF4444", "#F59E0B", "#10B981"]):
        out.append(f'<circle cx="{w["x"] + 24 + i * 20}" cy="{w["y"] + 20}" r="5.5" fill="{c}"/>')
    out.append(_text(C.W / 2, w["y"] + 25, "profile.sh --live", 13, col["muted"], anchor="middle"))

    f = frame
    out.append(
        f'<rect x="{f["x"]}" y="{f["y"]}" width="{f["w"]}" height="{f["h"]}" '
        f'rx="{f["rx"]}" fill="none" stroke="{col["chrome"]}" stroke-opacity="0.45"/>'
    )
    # tapamos el trazo del marco para que la etiqueta se lea encima
    out.append(
        f'<rect x="{f["x"] + 14}" y="{f["y"] - 8}" width="94" height="16" fill="{col["window"]}"/>'
    )
    out.append(_text(f["x"] + 20, f["y"] + 4, "VISUAL.MAP", 12, col["chrome"], weight="700"))
    return "".join(out)


# --------------------------------------------------------------------------
def build(mode: str, photo: str | None, crop, contrast: float, threshold: float,
          out_path: str, static: str | None = None, art: str | None = None,
          spacing: int = 2) -> None:
    col = C.PALETTE[mode]
    rng = np.random.default_rng(11)

    if art:
        dots = portrait.build_dots_from_art(art, spacing)
    else:
        dots = portrait.build_dots(photo, mode, crop, contrast, threshold)
    ij = np.argwhere(dots)
    frame = content_frame(dots)

    # los logos se encajan DENTRO del marco ya ajustado; si no, un marco
    # ceñido al monograma dejaría el enjambre desbordando por fuera
    side = min(frame["w"], frame["h"]) - 2 * C.LOGO_PAD
    box = {
        "x": frame["x"] + (frame["w"] - side) / 2,
        "y": frame["y"] + (frame["h"] - side) / 2,
        "w": side,
        "h": side,
    }
    masks = [
        logos.rasterize_icon(_icon("php")),
        logos.rasterize_glyph("</>"),
        logos.rasterize_icon(_icon("laravel")),
    ]
    clouds = logos.build_traveller_cloud(masks, C.N_TRAVELLERS, box["w"], box["h"])
    clouds = [c + np.array([box["x"], box["y"]]) for c in clouds]
    xy = np.stack(
        [C.ART_X + ij[:, 1] * C.PITCH, C.ART_Y + ij[:, 0] * C.PITCH], axis=1
    )
    runs = dither_runs(dots)
    target = clouds[0].mean(axis=0)

    intro, even = intro_layer(runs, col["portrait"], rng, static)
    loop, (flat, spread) = loop_layer(
        runs, dots.shape, xy, ij, col["portrait"], target, rng, static
    )
    trav = traveller_layer(clouds, col["chrome"], static)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {C.W} {C.H}" '
        f'width="{C.W}" height="{C.H}" role="img" '
        f'aria-label="{escape(C.PROFILE["name"])} — {escape(C.PROFILE["role"])}">'
        f"{chrome(col, frame)}{intro}{loop}{trav}{panel(C.PROFILE, col)}</svg>"
    )

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(svg)

    kb = os.path.getsize(out_path) / 1024
    ink = dots.mean()
    print(
        f"{mode:5s} -> {os.path.basename(out_path)}  {kb:6.0f} KB  "
        f"puntos={len(ij):6d}  corridas={len(runs):6d}  tinta={ink:5.1%}  "
        f"disperso={even:.2f}x (~1)  flat={flat:.3f} (<0.30)  spread={spread:.2f} (0.4-1.2)"
    )
    if ink > 0.45:
        print(
            f"        AVISO: {ink:.0%} de tinta. El retrato se va a leer como una mancha "
            f"sólida y el archivo se dispara. En modo claro suele significar que la foto "
            f"tiene el fondo oscuro; en oscuro, que la segmentación no separó el fondo."
        )
    if kb > 1200:
        print(f"        AVISO: {kb:.0f} KB. Por encima de ~1 MB GitHub tarda en pintarlo.")


def _icon(name: str) -> str:
    from simpleicons.all import icons

    return icons.get(name).path


def main() -> None:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--photo", help="retrato: se segmenta y se dithera")
    src.add_argument("--art", help="arte plana (logo/monograma): se calan puntos")
    ap.add_argument("--spacing", type=int, default=2,
                    help="separación de la retícula de puntos en modo --art")
    ap.add_argument("--crop", default=None, help="x,y,w,h en px de la foto original")
    ap.add_argument("--contrast", type=float, default=1.3)
    ap.add_argument("--threshold", type=float, default=42.0,
                    help="distancia de color que separa sujeto de fondo")
    ap.add_argument("--out", default=".")
    ap.add_argument("--static", default=None,
                    choices=["portrait", "logo1", "logo2", "logo3"],
                    help="emite un SVG sin animación, para inspeccionar un fotograma")
    ap.add_argument("--mode", default=None, choices=["dark", "light"])
    args = ap.parse_args()

    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None
    modes = [args.mode] if args.mode else ["dark", "light"]
    suffix = f"-{args.static}" if args.static else ""
    for mode in modes:
        build(mode, args.photo, crop, args.contrast, args.threshold,
              os.path.join(args.out, f"{mode}{suffix}.svg"), args.static,
              args.art, args.spacing)


if __name__ == "__main__":
    main()
