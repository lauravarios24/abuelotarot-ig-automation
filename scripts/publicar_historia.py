#!/usr/bin/env python3
"""
Genera y publica una historia de Instagram (9h / 13h / 18h) de forma automatica.
Se ejecuta desde GitHub Actions. No requiere intervencion manual.

- 9h: usa las plantillas subidas en templates/9h/ (sin tocar).
- 13h y 18h: el fondo se genera por codigo (gradiente + luna/mandala + paneles),
  ya no dependen de imagenes subidas a mano.
"""
import os
import sys
import json
import time
import random
import subprocess
import datetime
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont, ImageChops
from pilmoji import Pilmoji
from pilmoji.source import HTTPBasedSource

W, H = 1080, 1920

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, "templates")
OUTPUT = os.path.join(ROOT, "output")
TEXTOS_PATH = os.path.join(ROOT, "data", "textos.json")
FONTS = os.path.join(ROOT, "fonts")

# Fuentes del sistema (solo se usan en la historia de las 9h, que no se toca)
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

# Fuentes nuevas (13h y 18h), subidas por Laura a la carpeta fonts/
FONT_SEMIBOLD_NUEVA = os.path.join(FONTS, "CormorantGaramond-SemiBold.ttf")
FONT_REGULAR_NUEVA = os.path.join(FONTS, "CormorantGaramond-Regular.ttf")

IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # lo pone GitHub Actions solo, formato "usuario/repo"


def cargar_textos():
    with open(TEXTOS_PATH, encoding="utf-8") as f:
        return json.load(f)


def dia_del_anio():
    return datetime.date.today().timetuple().tm_yday


def fase_lunar(fecha=None):
    """Devuelve la edad de la luna en dias (0 = luna nueva, ~14.77 = luna llena).
    Calculo aproximado (precision de horas), suficiente para uso editorial."""
    fecha = fecha or datetime.datetime.utcnow()
    referencia = datetime.datetime(2000, 1, 6, 18, 14)
    sinodico = 29.53058867
    dias = (fecha - referencia).total_seconds() / 86400.0
    return dias % sinodico


def cargar_fuente(path, size, variacion=None):
    """Carga una fuente TTF. Si el archivo es una fuente variable (como la que
    exporta Google Fonts cuando solo hay un peso disponible) y se pide una
    variacion concreta (ej. 'SemiBold'), la aplica. Si es una fuente estatica
    normal, la usa tal cual sin fallar."""
    f = ImageFont.truetype(path, size)
    if variacion:
        try:
            nombres = f.get_variation_names()
            objetivo = variacion.encode()
            if objetivo in nombres:
                f.set_variation_by_name(variacion)
        except Exception:
            pass  # fuente estatica: ya tiene el peso correcto por si misma
    return f


class TwemojiGithubSource(HTTPBasedSource):
    """Sirve los PNG de emoji (estilo Twemoji) directamente desde GitHub,
    en vez del CDN por defecto de pilmoji. Mas estable/predecible."""

    BASE = "https://raw.githubusercontent.com/jdecked/twemoji/main/assets/72x72/"

    def get_emoji(self, emoji, /):
        codepoints = "-".join(f"{ord(c):x}" for c in emoji)
        for candidato in (codepoints, codepoints.replace("-fe0f", "")):
            try:
                data = self.request(self.BASE + candidato + ".png")
                if data:
                    return BytesIO(data)
            except Exception:
                continue
        return None

    def get_discord_emoji(self, id, /):
        return None


# ---------------------------------------------------------------------------
# Texto SIN emoticonos (historia de las 9h, no se toca)
# ---------------------------------------------------------------------------

def envolver_texto(draw, texto, font, max_width):
    palabras = texto.split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = (actual + " " + palabra).strip()
        bbox = draw.textbbox((0, 0), prueba, font=font)
        if bbox[2] - bbox[0] <= max_width:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def dibujar_centrado(draw, lineas, font, centro_x, centro_y, color="white", interlineado=1.3):
    if not lineas:
        return centro_y
    alturas = [draw.textbbox((0, 0), l, font=font)[3] for l in lineas]
    alto_linea = max(alturas) * interlineado
    alto_total = alto_linea * len(lineas)
    y = centro_y - alto_total / 2
    for linea in lineas:
        bbox = draw.textbbox((0, 0), linea, font=font)
        ancho = bbox[2] - bbox[0]
        x = centro_x - ancho / 2
        draw.text((x + 2, y + 2), linea, font=font, fill="black")  # sombra para legibilidad
        draw.text((x, y), linea, font=font, fill=color)
        y += alto_linea
    return y


def generar_9h(textos, dia):
    idx_img = (dia % 10) + 1
    ruta_img = os.path.join(TEMPLATES, "9h", f"{idx_img:02d}.png")
    texto = textos["consejos_9h"][dia % len(textos["consejos_9h"])]
    cta = textos.get("cta_9h", "")

    img = Image.open(ruta_img).convert("RGB")
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype(FONT_BOLD, 58)
    lineas = envolver_texto(draw, texto, font, max_width=820)
    y_fin = dibujar_centrado(draw, lineas, font, centro_x=540, centro_y=1300)

    if cta:
        font_cta = ImageFont.truetype(FONT_REGULAR, 38)
        lineas_cta = envolver_texto(draw, cta, font_cta, max_width=760)
        dibujar_centrado(draw, lineas_cta, font_cta, centro_x=540, centro_y=y_fin + 90, color="#e8d9b5")

    return img


# ---------------------------------------------------------------------------
# Fondo generado por codigo + texto CON emoticonos (13h y 18h, via pilmoji)
# ---------------------------------------------------------------------------

def envolver_texto_emoji(pm, texto, font, max_width):
    palabras = texto.split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = (actual + " " + palabra).strip()
        ancho, _ = pm.getsize(prueba, font=font)
        if ancho <= max_width:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def bloque_alto(pm, lineas, font, interlineado=1.2):
    if not lineas:
        return 0
    alturas = [pm.getsize(l, font=font)[1] for l in lineas]
    return max(alturas) * interlineado * len(lineas)


def dibujar_centrado_emoji(pm, lineas, font, centro_x, centro_y, color="white", interlineado=1.2):
    if not lineas:
        return centro_y
    alto_linea = max(pm.getsize(l, font=font)[1] for l in lineas) * interlineado
    alto_total = alto_linea * len(lineas)
    y = centro_y - alto_total / 2
    for linea in lineas:
        ancho, _ = pm.getsize(linea, font=font)
        x = centro_x - ancho / 2
        pm.text((x, y), linea, fill=color, font=font)
        y += alto_linea
    return y


def gradiente_vertical(size, arriba, abajo):
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        r = int(arriba[0] + (abajo[0] - arriba[0]) * t)
        g = int(arriba[1] + (abajo[1] - arriba[1]) * t)
        b = int(arriba[2] + (abajo[2] - arriba[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def agregar_estrellas(img, dia, n=110):
    draw = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(dia)  # fija segun el dia, para que no cambien entre intentos
    for _ in range(n):
        x = rnd.randint(0, W)
        y = rnd.randint(0, H)
        r = rnd.choice([1, 1, 1, 2, 2, 3])
        alpha = rnd.randint(60, 200)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 244, 214, alpha))


def panel_redondeado(img, box, radius=40, fill=(20, 8, 24, 150)):
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    capa = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    ImageDraw.Draw(capa).rounded_rectangle([0, 0, x1 - x0, y1 - y0], radius=radius, fill=fill)
    img.alpha_composite(capa, (x0, y0))


def luna_creciente(img, centro, radio, glow=True):
    cx, cy = centro
    capa = Image.new("RGBA", (radio * 4, radio * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    lc = (radio * 2, radio * 2)
    if glow:
        for gr in range(radio + 60, radio, -6):
            a = max(int(70 * (1 - (gr - radio) / 60)), 0)
            d.ellipse([lc[0] - gr, lc[1] - gr, lc[0] + gr, lc[1] + gr], fill=(240, 205, 140, a))

    mascara = Image.new("L", capa.size, 0)
    ImageDraw.Draw(mascara).ellipse(
        [lc[0] - radio, lc[1] - radio, lc[0] + radio, lc[1] + radio], fill=255
    )
    sombra = Image.new("L", capa.size, 0)
    off = int(radio * 0.55)
    ImageDraw.Draw(sombra).ellipse(
        [lc[0] - radio + off, lc[1] - radio - int(radio * 0.1),
         lc[0] + radio + off, lc[1] + radio - int(radio * 0.1)], fill=255
    )
    mascara_final = ImageChops.subtract(mascara, sombra)
    solido = Image.new("RGBA", capa.size, (247, 224, 175, 255))
    capa.paste(solido, (0, 0), mascara_final)
    img.alpha_composite(capa, (cx - radio * 2, cy - radio * 2))


def fondo_base(dia, arriba, abajo):
    img = gradiente_vertical((W, H), arriba, abajo).convert("RGBA")
    agregar_estrellas(img, dia)
    return img


def generar_13h(textos, dia):
    par = textos["preguntas_13h"][dia % len(textos["preguntas_13h"])]

    img = fondo_base(dia, (36, 10, 28), (70, 14, 30))
    draw = ImageDraw.Draw(img, "RGBA")

    cx = W // 2
    cy_top = 240
    for i, rr in enumerate([140, 105, 72]):
        draw.ellipse([cx - rr, cy_top - rr, cx + rr, cy_top + rr],
                     outline=(230, 200, 150, 90 - i * 10), width=2)
    draw.ellipse([cx - 12, cy_top - 12, cx + 12, cy_top + 12], fill=(240, 205, 140, 230))

    f_pregunta = cargar_fuente(FONT_SEMIBOLD_NUEVA, 96, "SemiBold")
    f_opcion = cargar_fuente(FONT_SEMIBOLD_NUEVA, 72, "SemiBold")
    f_vs = cargar_fuente(FONT_REGULAR_NUEVA, 44, "Regular")
    f_foot = cargar_fuente(FONT_SEMIBOLD_NUEVA, 58, "SemiBold")

    with Pilmoji(img, source=TwemojiGithubSource) as pm:
        # panel de la pregunta (alto dinamico segun el texto real)
        lineas_p = envolver_texto_emoji(pm, par["pregunta"], f_pregunta, 900)
        pad = 70
        alto_p = bloque_alto(pm, lineas_p, f_pregunta, 1.15)
        panel_top = 420
        panel_bottom = panel_top + pad * 2 + alto_p
        panel_redondeado(img, (50, panel_top, 1030, panel_bottom), radius=40, fill=(20, 6, 16, 150))
        dibujar_centrado_emoji(pm, lineas_p, f_pregunta, cx, (panel_top + panel_bottom) / 2,
                                color=(255, 244, 224), interlineado=1.15)

        # divisor + "VS"
        y_div = panel_bottom + 130
        draw.line([(120, y_div), (960, y_div)], fill=(230, 200, 150, 140), width=2)
        draw.ellipse([cx - 40, y_div - 40, cx + 40, y_div + 40],
                     fill=(70, 14, 30, 255), outline=(230, 200, 150, 200), width=2)
        vsw, vsh = pm.getsize("VS", font=f_vs)
        pm.text((cx - vsw / 2, y_div - vsh / 2), "VS", fill=(230, 200, 150, 255), font=f_vs)

        # opciones A / B (tamano dinamico)
        panel_w = 470
        lineas_a = envolver_texto_emoji(pm, par["opcion_a"], f_opcion, panel_w - 70)
        lineas_b = envolver_texto_emoji(pm, par["opcion_b"], f_opcion, panel_w - 70)
        panel_h = max(bloque_alto(pm, lineas_a, f_opcion, 1.2),
                      bloque_alto(pm, lineas_b, f_opcion, 1.2)) + 90

        top_opts = y_div + 90
        left_box = (60, top_opts, 60 + panel_w, top_opts + panel_h)
        right_box = (W - 60 - panel_w, top_opts, W - 60, top_opts + panel_h)
        panel_redondeado(img, left_box, radius=32, fill=(20, 6, 16, 150))
        panel_redondeado(img, right_box, radius=32, fill=(20, 6, 16, 150))
        draw.rounded_rectangle(left_box, radius=32, outline=(230, 200, 150, 170), width=3)
        draw.rounded_rectangle(right_box, radius=32, outline=(230, 200, 150, 170), width=3)

        lcx = (left_box[0] + left_box[2]) / 2
        rcx = (right_box[0] + right_box[2]) / 2
        pcy = (left_box[1] + left_box[3]) / 2
        dibujar_centrado_emoji(pm, lineas_a, f_opcion, lcx, pcy, color=(255, 244, 224), interlineado=1.2)
        dibujar_centrado_emoji(pm, lineas_b, f_opcion, rcx, pcy, color=(255, 244, 224), interlineado=1.2)

        # pie
        pie = "Responde en comentarios ✨"
        pw, ph = pm.getsize(pie, font=f_foot)
        pm.text((cx - pw / 2, top_opts + panel_h + 90), pie, fill=(230, 200, 150, 235), font=f_foot)

    return img.convert("RGB")


def generar_18h(textos, dia):
    edad = fase_lunar()
    sinodico = 29.53058867
    es_nueva = edad <= 1 or edad >= sinodico - 1
    es_llena = abs(edad - sinodico / 2) <= 1

    if es_nueva:
        texto = textos["cierre_18h_luna_nueva"]
        colores = ((10, 8, 40), (40, 14, 60))
    elif es_llena:
        texto = textos["cierre_18h_luna_llena"]
        colores = ((10, 8, 40), (40, 14, 60))
    else:
        texto = textos["cierres_18h_normal"][dia % len(textos["cierres_18h_normal"])]
        colores = ((18, 10, 30), (48, 18, 34))

    img = fondo_base(dia, *colores)
    cx = W // 2
    luna_creciente(img, (cx, 420), 140)

    f_txt = cargar_fuente(FONT_SEMIBOLD_NUEVA, 78, "SemiBold")
    f_badge = cargar_fuente(FONT_SEMIBOLD_NUEVA, 42, "SemiBold")
    draw = ImageDraw.Draw(img, "RGBA")

    with Pilmoji(img, source=TwemojiGithubSource) as pm:
        lineas = envolver_texto_emoji(pm, texto, f_txt, 900)
        pad = 60
        alto = bloque_alto(pm, lineas, f_txt, 1.2)
        panel_y0 = 700
        panel_h = pad * 2 + alto
        panel_redondeado(img, (50, panel_y0, 1030, panel_y0 + panel_h), radius=40, fill=(15, 6, 20, 160))
        dibujar_centrado_emoji(pm, lineas, f_txt, cx, panel_y0 + panel_h / 2,
                                color=(255, 244, 224), interlineado=1.2)

        # chip con el enlace de la comunidad (puede ocupar 1 o 2 lineas)
        badge_texto = "\U0001F517 Únete a mi Comunidad de Telegram Gratuita — Link en mi perfil"
        pad_b = 40
        lineas_badge = envolver_texto_emoji(pm, badge_texto, f_badge, 820)
        alto_badge = bloque_alto(pm, lineas_badge, f_badge, 1.25)
        ancho_badge = max(pm.getsize(l, font=f_badge)[0] for l in lineas_badge)
        badge_y0 = panel_y0 + panel_h + 60
        badge_h = pad_b * 2 + alto_badge
        badge_w = ancho_badge + 100
        badge_box = (cx - badge_w / 2, badge_y0, cx + badge_w / 2, badge_y0 + badge_h)
        radio_badge = min(50, badge_h / 2)
        draw.rounded_rectangle(badge_box, radius=radio_badge, fill=(230, 200, 150, 235))
        dibujar_centrado_emoji(pm, lineas_badge, f_badge, cx, badge_y0 + badge_h / 2,
                                color=(40, 14, 20), interlineado=1.25)

    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Publicacion en Instagram (sin cambios de logica)
# ---------------------------------------------------------------------------

def git(*args):
    subprocess.run(["git", *args], check=True, cwd=ROOT)


def commit_y_url(ruta_relativa):
    git("config", "user.name", "abuelotarot-bot")
    git("config", "user.email", "bot@abuelotarot.local")
    git("add", ruta_relativa)

    sin_cambios = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0
    if sin_cambios:
        print("Aviso: no hay cambios que commitear (¿ya se publico hoy esta franja?). Se usara el ultimo commit.")
    else:
        git("commit", "-m", f"auto: historia {ruta_relativa}")
        git("push")

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    return f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{sha}/{ruta_relativa}"


def esperar_contenedor_listo(creation_id, intentos=10, espera=3):
    url = f"https://graph.instagram.com/v21.0/{creation_id}"
    for _ in range(intentos):
        r = requests.get(url, params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN})
        r.raise_for_status()
        estado = r.json().get("status_code")
        print("Estado del contenedor:", estado)
        if estado == "FINISHED":
            return
        if estado == "ERROR":
            raise RuntimeError(f"Instagram no pudo procesar la imagen: {r.json()}")
        time.sleep(espera)
    raise TimeoutError("El contenedor no termino de procesar a tiempo.")


def publicar_en_instagram(image_url):
    base = f"https://graph.instagram.com/v21.0/{IG_USER_ID}"

    r = requests.post(f"{base}/media", data={
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": IG_ACCESS_TOKEN,
    })
    if not r.ok:
        print("Error al crear el contenedor:", r.status_code, r.text)
    r.raise_for_status()
    creation_id = r.json()["id"]
    print("Contenedor creado:", creation_id)

    esperar_contenedor_listo(creation_id)

    r2 = requests.post(f"{base}/media_publish", data={
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN,
    })
    if not r2.ok:
        print("Error al publicar:", r2.status_code, r2.text)
    r2.raise_for_status()
    print("Historia publicada:", r2.json())


def main():
    slot = sys.argv[1] if len(sys.argv) > 1 else None
    if slot not in ("9h", "13h", "18h"):
        print("Uso: publicar_historia.py [9h|13h|18h]")
        sys.exit(1)

    textos = cargar_textos()
    dia = dia_del_anio()

    if slot == "9h":
        img = generar_9h(textos, dia)
    elif slot == "13h":
        img = generar_13h(textos, dia)
    else:
        img = generar_18h(textos, dia)

    os.makedirs(OUTPUT, exist_ok=True)
    fecha = datetime.date.today().isoformat()
    nombre = f"{slot}_{fecha}.png"
    ruta_relativa = f"output/{nombre}"
    img.save(os.path.join(ROOT, ruta_relativa))

    url = commit_y_url(ruta_relativa)
    print("URL publica de la imagen:", url)

    publicar_en_instagram(url)


if __name__ == "__main__":
    main()
