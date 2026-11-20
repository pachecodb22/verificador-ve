import re
import html
import requests
from typing import Dict


def es_url(texto: str) -> bool:
    """Detecta si la entrada del usuario es principalmente un enlace web."""
    texto_limpio = texto.strip()
    return bool(re.match(r"^https?://\S+$", texto_limpio))


def _limpiar_html(raw_html: str) -> str:
    """Elimina etiquetas HTML de respuestas oEmbed y decodifica entidades."""
    sin_tags = re.sub(r"<[^>]+>", " ", raw_html)
    limpio = html.unescape(sin_tags)
    return re.sub(r"\s+", " ", limpio).strip()


def _extraer_tuit(url: str) -> Dict:
    """Extrae texto y autor de publicaciones públicas de X/Twitter sin API paga."""
    match = re.search(r"(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)", url)
    if not match:
        return {
            "exito": False,
            "mensaje_error": "El enlace de X/Twitter no parece apuntar a una publicación específica (status). Copia el enlace directo del tuit o pega el texto."
        }

    usuario, tweet_id = match.group(1), match.group(2)

    try:
        resp = requests.get(
            f"https://api.fxtwitter.com/{usuario}/status/{tweet_id}",
            headers={"User-Agent": "VerificadorVE/1.0"},
            timeout=8,
        )
        if resp.status_code == 200:
            datos = resp.json().get("tweet", {})
            texto_tuit = datos.get("text", "").strip()
            autor_nombre = datos.get("author", {}).get("name", usuario)
            if texto_tuit:
                return {
                    "exito": True,
                    "texto": texto_tuit,
                    "autor": f"{autor_nombre} (@{usuario})",
                    "plataforma": "X (Twitter)",
                }
    except Exception:
        pass

    try:
        resp_oembed = requests.get(
            "https://publish.twitter.com/oembed",
            params={"url": url, "omit_script": "true"},
            timeout=8,
        )
        if resp_oembed.status_code == 200:
            data = resp_oembed.json()
            texto_limpio = _limpiar_html(data.get("html", ""))
            autor = data.get("author_name", usuario)
            if texto_limpio:
                return {
                    "exito": True,
                    "texto": texto_limpio,
                    "autor": f"{autor} (@{usuario})",
                    "plataforma": "X (Twitter)",
                }
    except Exception:
        pass

    return {
        "exito": False,
        "mensaje_error": "No se pudo leer este tuit (puede ser de una cuenta privada o haber sido eliminado). Por favor, copia y pega el texto directamente."
    }


def _extraer_articulo_web(url: str) -> Dict:
    """Extrae título y descripción de portales de noticias o blogs mediante metadatos OpenGraph."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; VerificadorVE/1.0)"},
            timeout=8,
        )
        resp.raise_for_status()
        contenido = resp.text

        titulo_match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
            contenido,
            re.IGNORECASE,
        ) or re.search(r"<title[^>]*>([^<]+)</title>", contenido, re.IGNORECASE)

        desc_match = re.search(
            r'<meta[^>]+(?:property=["\']og:description["\']|name=["\']description["\'])[^>]+content=["\']([^"\']+)["\']',
            contenido,
            re.IGNORECASE,
        )

        titulo = html.unescape(titulo_match.group(1)).strip() if titulo_match else ""
        desc = html.unescape(desc_match.group(1)).strip() if desc_match else ""

        texto_combinado = f"{titulo}. {desc}".strip(". ")
        if len(texto_combinado) >= 20:
            return {
                "exito": True,
                "texto": texto_combinado,
                "autor": "",
                "plataforma": "Artículo / Sitio Web",
            }
    except Exception:
        pass

    return {
        "exito": False,
        "mensaje_error": "El sitio web bloqueó la lectura automática del enlace. Copia el titular o párrafo que deseas verificar y pégalo aquí."
    }


def procesar_entrada_usuario(entrada: str) -> Dict:
    """
    Evalúa si el usuario ingresó texto directo o una URL.
    Si es URL, intenta extraer el contenido o devuelve un aviso claro según la plataforma.
    """
    entrada_limpia = entrada.strip()
    if not es_url(entrada_limpia):
        return {
            "exito": True,
            "es_enlace": False,
            "texto": entrada_limpia,
            "autor": "",
            "plataforma": "Texto directo",
        }

    url_lower = entrada_limpia.lower()

    redes_cerradas = {
        "instagram.com": "Instagram",
        "tiktok.com": "TikTok",
        "facebook.com": "Facebook",
        "fb.watch": "Facebook",
        "threads.net": "Threads",
        "whatsapp.com": "WhatsApp",
    }
    for dominio, nombre_red in redes_cerradas.items():
        if dominio in url_lower:
            return {
                "exito": False,
                "es_enlace": True,
                "mensaje_error": (
                    f"Por restricciones técnicas de **{nombre_red}**, no es posible leer el contenido directamente desde el enlace. "
                    f"Por favor, **copia el texto de la publicación o transcribe la frase** y pégala en el cuadro de arriba."
                ),
            }

    if "x.com/" in url_lower or "twitter.com/" in url_lower:
        res = _extraer_tuit(entrada_limpia)
        res["es_enlace"] = True
        return res

    res = _extraer_articulo_web(entrada_limpia)
    res["es_enlace"] = True
    return res
