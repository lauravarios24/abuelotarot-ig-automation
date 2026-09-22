#!/usr/bin/env python3
"""
Genera y publica una historia de Instagram (9h / 13h / 18h) de forma automatica.
Se ejecuta desde GitHub Actions. No requiere intervencion manual.
"""
import os
import sys
import json
import time
import subprocess
import datetime

import requests
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji

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


# ---------------------------------------------------------------------------
# Texto CON emoticonos (historias de las 13h y 18h, via pilmoji)
# ---------------------------------------------------------------------------

def envolver_texto_emoji(pilmoji, texto, font, max_width):
    palabras = texto.split()
    lineas, actual = [], ""
    for palabra in palabras:
        prueba = (actual + " " + palabra).strip()
        ancho, _ = pilmoji.getsize(prueba, font=font)
        if ancho <= max_width:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def dibujar_centrado_emoji(pilmoji, lineas, font, centro_x, centro_y, color="white", interlineado=1.35):
    if not lineas:
        return centro_y
    alturas = [pilmoji.getsize(l, font=font)[1] for l in lineas]
    alto_linea = max(alturas) * interlineado
    alto_total = alto_linea * len(lineas)
    y = centro_y - alto_total / 2
    for linea in lineas:
        ancho, _ = pilmoji.getsize(linea, font=font)
        x = centro_x - ancho / 2
        pilmoji.text((x, y), linea, fill=color, font=font, stroke_width=2, stroke_fill="black")
        y += alto_linea
    return y


# ---------------------------------------------------------------------------
# Generadores por franja
# ---------------------------------------------------------------------------

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


def generar_13h(textos, dia):
    letra = "a" if dia % 2 == 0 else "b"
    ruta_img = os.path.join(TEMPLATES, "13h", f"{letra}.png")
    par = textos["preguntas_13h"][dia % len(textos["preguntas_13h"])]

    img = Image.open(ruta_img).convert("RGB")
    font_pregunta = ImageFont.truetype(FONT_SEMIBOLD_NUEVA, 46)
    font_opcion = ImageFont.truetype(FONT_REGULAR_NUEVA, 40)

    with Pilmoji(img) as pilmoji:
        lineas_p = envolver_texto_emoji(pilmoji, par["pregunta"], font_pregunta, max_width=780)
        dibujar_centrado_emoji(pilmoji, lineas_p, font_pregunta, centro_x=540, centro_y=250)

        lineas_a = envolver_texto_emoji(pilmoji, par["opcion_a"], font_opcion, max_width=360)
        dibujar_centrado_emoji(pilmoji, lineas_a, font_opcion, centro_x=280, centro_y=650)

        lineas_b = envolver_texto_emoji(pilmoji, par["opcion_b"], font_opcion, max_width=360)
        dibujar_centrado_emoji(pilmoji, lineas_b, font_opcion, centro_x=800, centro_y=650)

    return img


def generar_18h(textos, dia):
    edad = fase_lunar()
    sinodico = 29.53058867
    es_nueva = edad <= 1 or edad >= sinodico - 1
    es_llena = abs(edad - sinodico / 2) <= 1

    if es_nueva:
        ruta_img = os.path.join(TEMPLATES, "18h", "especial.png")
        texto = textos["cierre_18h_luna_nueva"]
    elif es_llena:
        ruta_img = os.path.join(TEMPLATES, "18h", "especial.png")
        texto = textos["cierre_18h_luna_llena"]
    else:
        ruta_img = os.path.join(TEMPLATES, "18h", "normal.png")
        texto = textos["cierres_18h_normal"][dia % len(textos["cierres_18h_normal"])]

    img = Image.open(ruta_img).convert("RGB")
    font = ImageFont.truetype(FONT_SEMIBOLD_NUEVA, 44)

    with Pilmoji(img) as pilmoji:
        lineas = envolver_texto_emoji(pilmoji, texto, font, max_width=780)
        dibujar_centrado_emoji(pilmoji, lineas, font, centro_x=540, centro_y=1380)

    return img


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
