"""
Genera il logo FASAS in tutti i formati da un'unica geometria: il fascicolo (foglio con l'angolo piegato) con il
tracciato del battito.

    python scripts/genera_icone.py

Scrive:
  static/img/fasas.svg, fasas-mark.svg, favicon.ico, icon-192.png, icon-512.png, icon-maskable-512.png,
  apple-touch-icon.png, badge-96.png   (piattaforma: favicon, web app installata, iPhone, notifiche)
  mobile/android/app/src/main/res/drawable/ic_launcher_foreground.xml, ic_launcher_monochrome.xml, ic_logo.xml
                                        (app FASAS Signer: stesso foglio con il segno «appoggia la carta»)

Serve CairoSVG (pip install cairosvg, usa la libreria Cairo del sistema) e Pillow.
"""
import io
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "static" / "img"
DRAWABLE = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res" / "drawable"

BRAND_START, BRAND_END = "#2A74BD", "#164F86"   # come .brand-mark e @color/fasas_brand_*
PRIMARY = "#1D5FA0"

# Geometria in unità, centrata su (0, 0): foglio 40 × 50 con l'angolo in alto a destra piegato.
CARD = ("M-15.5 -25H8L20 -13V20.5A4.5 4.5 0 0 1 15.5 25H-15.5A4.5 4.5 0 0 1 -20 20.5V-20.5"
        "A4.5 4.5 0 0 1 -15.5 -25Z")
FOLD = "M8 -25V-16.5A3.5 3.5 0 0 0 11.5 -13H20Z"
LINES = "M-12.5 -15H1.5M-12.5 -6.5H9.5"
PULSE = "M-13 10H-6.5L-2.5 1L3 19L7 10H13"
# Segno «senza contatto» dell'app: tre archi in un bollino in basso a destra.
BADGE_C, BADGE_R = (16.0, 20.0), 11.5
WAVES = "M13.1 17.2A3.9 3.9 0 0 1 13.1 22.8M15.2 15.2A6.8 6.8 0 0 1 15.2 24.8M17.3 13.1A9.7 9.7 0 0 1 17.3 26.9"
SIGNER_SHIFT = (-4.5, -4.0)   # ricentra foglio + bollino


def mark_svg(lines=True, badge=False):
    parts = [f'<path d="{CARD}" fill="#FFFFFF"/>', f'<path d="{FOLD}" fill="#C9DCF0"/>']
    if lines:
        parts.append(f'<path d="{LINES}" fill="none" stroke="#A8C5E5" stroke-width="3.2" stroke-linecap="round"/>')
    parts.append(f'<path d="{PULSE}" fill="none" stroke="{PRIMARY}" stroke-width="4.4" stroke-linecap="round" '
                 'stroke-linejoin="round"/>')
    if badge:
        (cx, cy), r = BADGE_C, BADGE_R
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#0F4677" stroke="#FFFFFF" stroke-width="3"/>')
        parts.append(f'<path d="{WAVES}" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>')
    return "".join(parts)


def outline_svg(color="#FFFFFF"):
    """Solo contorni: icona monocromatica (notifiche, icone a tema di Android)."""
    return (f'<path d="{CARD}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>'
            f'<path d="M8 -24V-16.5A3.5 3.5 0 0 0 11.5 -13H19" fill="none" stroke="{color}" stroke-width="3.2" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{PULSE}" fill="none" stroke="{color}" stroke-width="4.4" stroke-linecap="round" '
            'stroke-linejoin="round"/>')


def gradient(size):
    return (f'<defs><linearGradient id="g" x1="0" y1="0" x2="{size}" y2="{size}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{BRAND_START}"/><stop offset="1" stop-color="{BRAND_END}"/>'
            '</linearGradient></defs>')


def tile_svg(size, scale, radius, lines=True, badge=False, shift=(0.0, 0.0)):
    """Quadrato con il gradiente del marchio e il foglio al centro; radius=0 → a tutto campo (maschere del sistema)."""
    tx, ty = size / 2 + shift[0] * scale, size / 2 + shift[1] * scale
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'{gradient(size)}<rect width="{size}" height="{size}" rx="{radius}" fill="url(#g)"/>'
            f'<g transform="translate({tx:g} {ty:g}) scale({scale:g})">{mark_svg(lines, badge)}</g></svg>')


def bare_svg(size, scale, body):
    c = size / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'<g transform="translate({c:g} {c:g}) scale({scale:g})">{body}</g></svg>')


def favicon_svg():
    # Piccolo: niente righe di testo, foglio più grande.
    return tile_svg(64, 1.02, 14, lines=False)


def render(svgs):
    """{nome: (svg, lato_px)} → {nome: PNG RGBA} con lo sfondo trasparente."""
    import cairosvg

    return {name: Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=px,
                                                          output_height=px))).convert("RGBA")
            for name, (svg, px) in svgs.items()}


def vector(paths, scale, shift=(0.0, 0.0)):
    """Drawable vettoriale Android 108 × 108 dp (livello dell'icona adattiva) con la stessa geometria."""
    tx, ty = 54 + shift[0] * scale, 54 + shift[1] * scale
    body = "\n".join(f"        {p}" for p in paths)
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!-- Generato da scripts/genera_icone.py: modificare lì. -->\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            '    android:width="108dp" android:height="108dp" android:viewportWidth="108" '
            'android:viewportHeight="108">\n'
            f'    <group android:translateX="{tx:g}" android:translateY="{ty:g}" android:scaleX="{scale:g}" '
            f'android:scaleY="{scale:g}">\n{body}\n    </group>\n</vector>\n')


def fill(d, color):
    return f'<path android:pathData="{d}" android:fillColor="{color}" />'


def stroke(d, color, width, join=True):
    extra = ' android:strokeLineJoin="round"' if join else ""
    return (f'<path android:pathData="{d}" android:fillColor="#00000000" android:strokeColor="{color}" '
            f'android:strokeWidth="{width}" android:strokeLineCap="round"{extra} />')


def circle_path(cx, cy, r):
    return f"M{cx - r:g} {cy:g}A{r:g} {r:g} 0 1 1 {cx + r:g} {cy:g}A{r:g} {r:g} 0 1 1 {cx - r:g} {cy:g}Z"


def android_files():
    (cx, cy), r = BADGE_C, BADGE_R
    foreground = [
        fill(CARD, "#FFFFFFFF"), fill(FOLD, "#FFC9DCF0"), stroke(LINES, "#FFA8C5E5", 3.2, join=False),
        stroke(PULSE, "#FF1D5FA0", 4.4),
        fill(circle_path(cx, cy, r + 1.5), "#FFFFFFFF"), fill(circle_path(cx, cy, r - 1.5), "#FF0F4677"),
        stroke(WAVES, "#FFFFFFFF", 2.2, join=False),
    ]
    monochrome = [
        stroke(CARD, "#FFFFFFFF", 4), stroke("M8 -24V-16.5A3.5 3.5 0 0 0 11.5 -13H19", "#FFFFFFFF", 3.2),
        stroke(PULSE, "#FFFFFFFF", 4.4),
    ]
    logo = [fill(CARD, "#FFFFFFFF"), fill(FOLD, "#FFC9DCF0"), stroke(LINES, "#FFA8C5E5", 3.2, join=False),
            stroke(PULSE, "#FF1D5FA0", 4.4)]
    # Zona sicura delle icone adattive: cerchio di 33 dp di raggio attorno al centro.
    return {
        "ic_launcher_foreground.xml": vector(foreground, 0.86, SIGNER_SHIFT),
        "ic_launcher_monochrome.xml": vector(monochrome, 0.9),
        "ic_logo.xml": vector(logo, 1.3),
    }


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    (IMG / "fasas.svg").write_text(favicon_svg() + "\n", encoding="utf-8")
    (IMG / "fasas-mark.svg").write_text(bare_svg(64, 0.8, mark_svg()) + "\n", encoding="utf-8")

    png = render({
        "icon-512.png": (tile_svg(512, 5.8, 112), 512),
        "icon-192.png": (tile_svg(512, 5.8, 112), 192),
        "icon-maskable-512.png": (tile_svg(512, 5.0, 0), 512),     # zona sicura: cerchio dell'80%
        "apple-touch-icon.png": (tile_svg(180, 2.0, 0), 180),      # iOS arrotonda da sé; niente trasparenza
        "badge-96.png": (bare_svg(96, 1.5, outline_svg()), 96),    # notifiche: conta solo la trasparenza
        "fav-16": (favicon_svg(), 16), "fav-32": (favicon_svg(), 32), "fav-48": (favicon_svg(), 48),
    })
    for name, im in png.items():
        if name.endswith(".png"):
            if name == "apple-touch-icon.png":
                im = im.convert("RGB")
            im.save(IMG / name, optimize=True)
    png["fav-48"].save(IMG / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)],
                       append_images=[png["fav-16"], png["fav-32"]])

    for name, xml in android_files().items():
        (DRAWABLE / name).write_text(xml, encoding="utf-8")
    print("Icone generate in", IMG.relative_to(ROOT), "e", DRAWABLE.relative_to(ROOT))


if __name__ == "__main__":
    main()
