"""Datos del perfil y paleta. Es lo único que deberías editar a mano."""

PROFILE = {
    "name": "David Burgos",
    "username": "burgosdavid057-art",
    "role": "AI Developer",
    "origin": "Medellin, Colombia",
    "education": "Ing. de Sistemas",
    "status": "Building + Learning + Shipping",
    "toolchain": "VS Code, Git, XAMPP, n8n",
    "lang": "PHP, Python, JavaScript, Dart",
    "frontend": "Tailwind, Alpine.js, GSAP",
    "backend": "Laravel, Flask, Node",
    "database": "MySQL, SQLite, Postgres",
    "infra": "Plesk, Vercel, Docker",
    "mail": "burgosdavid057@gmail.com",
    "portfolio": "davidburgos.dev",
    "phone": "+57 302 489 3987",
    # La ruta real de LinkedIn, no la corta: la corta no existe y el enlace
    # quedaría roto. Se arregla poniendo una URL personalizada en LinkedIn.
    "linkedin": "in/david-burgos-ab673433a",
    # Una fila vacía no se dibuja: mejor omitirla que publicar un hueco.
    "facebook": "",
}

# Colores sacados de los PNG de marca de David, no inventados:
#   monograma indigo #5468FF · monograma blanco #EDEFF5
#   wordmark oscuro #11131A + #2F3BB0 · QR #0B0D12
# El sujeto tiene que ser de un tono distinto al del chrome de la UI, o se
# funde con su propio marco: por eso el monograma va indigo y el chrome cian.
PALETTE = {
    "dark": {
        "page": "#0B0D12",
        "window": "#11131A",
        "chrome": "#22D3EE",
        "portrait": "#5468FF",
        "accent": "#5468FF",
        "text": "#EDEFF5",
        "muted": "#8A93A6",
        "leader": "#2A2F3D",
        "live": "#EF4444",
    },
    "light": {
        "page": "#EDEFF5",
        "window": "#FFFFFF",
        "chrome": "#0891B2",
        "portrait": "#2F3BB0",
        "accent": "#2F3BB0",
        "text": "#11131A",
        "muted": "#4B5563",
        "leader": "#CBD5E1",
        "live": "#DC2626",
    },
}

# --- Geometría del lienzo -------------------------------------------------
W, H = 1180, 610

WIN = dict(x=16, y=16, w=1148, h=578, rx=10)
TITLEBAR_H = 40

FRAME = dict(x=44, y=84, w=396, h=462, rx=6)
PITCH = 1.2                       # px por celda de la rejilla 300x340
ART_X, ART_Y = 62.0, 111.0        # esquina del retrato dentro del marco

LOGO_PAD = 26.0                   # aire entre el enjambre de logos y el marco

PANEL_X = 468.0
PANEL_R = 1140.0                  # borde derecho: los valores se alinean aquí

CHAR_W = 8.4                      # ancho de carácter que fijamos con textLength
ROW_H = 23.0

# --- Tiempos --------------------------------------------------------------
INTRO_DUR = 3.2
INTRO_GROUPS = 60
INTRO_SPREAD = 2.0                # los grupos arrancan repartidos en esta ventana
INTRO_FADE = 0.55

LOOP_DUR = 14.2
# retrato 3.0 | logo 2.0 cada uno | transiciones 1.3
_STOPS = [0.0, 3.0, 4.3, 6.3, 7.6, 9.6, 10.9, 12.9, 14.2]
# 4 decimales = 1.4 ms de precisión, de sobra. Esta cadena se repite en cada
# elemento animado (~2000 veces), así que cada decimal de más cuesta ~20 KB.
KEYTIMES = ";".join(f"{t / LOOP_DUR:.4f}" for t in _STOPS)

N_BANDS = 94
DRIFT = 0.42                      # fracción del camino al centroide del primer logo
# Ruido por punto en ANCHOS DE BANDA. Barrido medido sobre el retrato de prueba:
#   0.00 -> flat 0.55  (borde de cuchillo: el efecto bloque)
#   0.45 -> flat 0.18 / spread 0.52  <- franjas legibles con borde dentado
#   0.80 -> flat 0.11 / spread 0.84  (las franjas empiezan a diluirse)
#   2.00 -> spread 1.99 (ya es estática, no una disolución)
BAND_NOISE = 0.45
N_TRAVELLERS = 900
