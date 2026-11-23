import os
import requests
from typing import List, Dict
from dotenv import load_dotenv

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

load_dotenv()

NIVEL_1_VERIFICADORES = [
    "cazadoresdefakenews.info",
    "cotejo.info",
    "espaja.com",
    "factcheck.afp.com",
]

NIVEL_2_INVESTIGACION = [
    "armando.info",
    "talcualdigital.com",
    "elpitazo.net",
    "runrun.es",
    "cronica.uno",
    "prodavinci.com",
]

NIVEL_3_OBSERVATORIOS_DATOS = [
    "observatoriodefinanzas.com",
    "bcv.org.ve",
    "accesoalajusticia.org",
    "provea.org",
    "vesinfiltro.org",
]

NIVEL_4_INTERNACIONAL = [
    "elpais.com",
    "elmundo.es",
    "infobae.com",
    "lasillavacia.com",
    "semana.com",
    "reuters.com",
    "apnews.com",
]

NOMBRES_FUENTES = {
    "cazadoresdefakenews.info": "Cazadores de Fake News",
    "cotejo.info": "Cotejo.info",
    "espaja.com": "EsPaja",
    "factcheck.afp.com": "AFP Factual",
    "armando.info": "Armando.info",
    "talcualdigital.com": "TalCual",
    "elpitazo.net": "El Pitazo",
    "runrun.es": "Runrun.es",
    "cronica.uno": "Crónica.Uno",
    "prodavinci.com": "Prodavinci",
    "observatoriodefinanzas.com": "Observatorio Venezolano de Finanzas",
    "bcv.org.ve": "Banco Central de Venezuela (BCV)",
    "accesoalajusticia.org": "Acceso a la Justicia",
    "provea.org": "PROVEA",
    "vesinfiltro.org": "VE sin Filtro",
    "elpais.com": "El País",
    "elmundo.es": "El Mundo",
    "infobae.com": "Infobae",
    "lasillavacia.com": "La Silla Vacía",
    "semana.com": "Semana",
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press (AP)",
}


def _identificar_nombre_medio(url: str) -> str:
    for dominio, nombre in NOMBRES_FUENTES.items():
        if dominio in url:
            return nombre
    return "Fuente externa"


def _construir_filtro_dominios(dominios: List[str]) -> str:
    return "(" + " OR ".join([f"site:{d}" for d in dominios]) + ")"


def _buscar_serper(query_completa: str, num_resultados: int = 5) -> List[Dict]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        raise ValueError("No se encontró SERPER_API_KEY en el entorno")

    url = "https://google.serper.dev/search"
    payload = {"q": query_completa, "gl": "ve", "hl": "es", "num": num_resultados}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    respuesta = requests.post(url, headers=headers, json=payload, timeout=10)
    respuesta.raise_for_status()
    datos = respuesta.json()

    resultados = []
    for item in datos.get("organic", []):
        link = item.get("link", "")
        resultados.append({
            "titulo": item.get("title", ""),
            "url": link,
            "fragmento": item.get("snippet", ""),
            "fecha": item.get("date", "Fecha no especificada"),
            "medio": _identificar_nombre_medio(link),
            "motor": "Serper (Google)",
        })
    return resultados


def _buscar_duckduckgo(query_completa: str, num_resultados: int = 5) -> List[Dict]:
    resultados = []
    with DDGS() as ddgs:
        busqueda = ddgs.text(query_completa, region="ve-es", max_results=num_resultados)
        for item in busqueda:
            link = item.get("href", "")
            resultados.append({
                "titulo": item.get("title", ""),
                "url": link,
                "fragmento": item.get("body", ""),
                "fecha": "Fecha no especificada",
                "medio": _identificar_nombre_medio(link),
                "motor": "DuckDuckGo (Respaldo)",
            })
    return resultados


def ejecutar_busqueda(query_completa: str, num_resultados: int = 5) -> List[Dict]:
    try:
        return _buscar_serper(query_completa, num_resultados)
    except Exception as e:
        print(f"[Aviso] Conmutando a DuckDuckGo por error en Serper: {e}")
        try:
            return _buscar_duckduckgo(query_completa, num_resultados)
        except Exception as e_ddg:
            print(f"[Error] Fallo también en DuckDuckGo: {e_ddg}")
            return []


def buscar_evidencia_escalonada(query_afirmacion: str) -> Dict:
    evidencia_total = []
    urls_vistas = set()

    # Nivel 1: Verificadores certificados
    filtro_n1 = _construir_filtro_dominios(NIVEL_1_VERIFICADORES)
    resultados_n1 = ejecutar_busqueda(f"{query_afirmacion} {filtro_n1}", num_resultados=4)

    for r in resultados_n1:
        if r["url"] not in urls_vistas and r["medio"] != "Fuente externa":
            r["nivel_fuente"] = "Nivel 1 - Verificador Certificado"
            evidencia_total.append(r)
            urls_vistas.add(r["url"])

    # Nivel 2 y 3: Investigación y Observatorios venezolanos
    if len(evidencia_total) < 3:
        dominios_n2_n3 = NIVEL_2_INVESTIGACION + NIVEL_3_OBSERVATORIOS_DATOS
        filtro_n2_n3 = _construir_filtro_dominios(dominios_n2_n3)
        resultados_n2_n3 = ejecutar_busqueda(f"{query_afirmacion} {filtro_n2_n3}", num_resultados=5)

        for r in resultados_n2_n3:
            if r["url"] not in urls_vistas and r["medio"] != "Fuente externa":
                r["nivel_fuente"] = "Nivel 2/3 - Investigación y Datos VE"
                evidencia_total.append(r)
                urls_vistas.add(r["url"])

    # Nivel 4: Medios internacionales y regionales de referencia
    if len(evidencia_total) < 4:
        filtro_n4 = _construir_filtro_dominios(NIVEL_4_INTERNACIONAL)
        resultados_n4 = ejecutar_busqueda(f"{query_afirmacion} {filtro_n4}", num_resultados=4)

        for r in resultados_n4:
            if r["url"] not in urls_vistas and r["medio"] != "Fuente externa":
                r["nivel_fuente"] = "Nivel 4 - Prensa Internacional / Regional"
                evidencia_total.append(r)
                urls_vistas.add(r["url"])

    return {
        "query_utilizada": query_afirmacion,
        "total_fuentes": len(evidencia_total),
        "evidencia": evidencia_total,
    }


def obtener_noticias_del_dia(max_noticias: int = 8) -> List[Dict]:
    """Recupera titulares recientes del día en medios venezolanos auditados y verificadores."""
    dominios_noticias = NIVEL_1_VERIFICADORES[:3] + NIVEL_2_INVESTIGACION
    filtro = _construir_filtro_dominios(dominios_noticias)
    query = f"Venezuela hoy noticias {filtro}"

    try:
        api_key = os.getenv("SERPER_API_KEY")
        if not api_key:
            return []

        url = "https://google.serper.dev/search"
        payload = {
            "q": query,
            "gl": "ve",
            "hl": "es",
            "num": max_noticias,
            "tbs": "qdr:d",
        }
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        respuesta = requests.post(url, headers=headers, json=payload, timeout=10)
        respuesta.raise_for_status()
        datos = respuesta.json()

        noticias = []
        urls_vistas = set()
        for item in datos.get("organic", []):
            link = item.get("link", "")
            medio = _identificar_nombre_medio(link)
            if (
                link not in urls_vistas
                and medio != "Fuente externa"
                and "/page/" not in link
                and "attachment_id" not in link
            ):
                noticias.append({
                    "titulo": item.get("title", ""),
                    "url": link,
                    "fragmento": item.get("snippet", ""),
                    "fecha": item.get("date", "Hoy"),
                    "medio": medio,
                })
                urls_vistas.add(link)
        return noticias
    except Exception:
        return []
