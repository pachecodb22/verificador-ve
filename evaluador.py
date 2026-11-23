import os
import json
import time
from typing import List, Literal, Dict
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv
from buscador import buscar_evidencia_escalonada

load_dotenv()

MODELOS_FALLBACK = [
    "gemini-2.5-flash",
    "gemini-3.8-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash-lite",
]


class AfirmacionVerificada(BaseModel):
    afirmacion: str = Field(description="La afirmación factual específica extraída del texto.")
    veredicto: Literal[
        "Cierto",
        "Engañoso / Media verdad",
        "Falso",
        "Inverificable",
        "Opinión / No verificable",
    ] = Field(description="Clasificación estricta según el estándar metodológico.")
    explicacion_sencilla: str = Field(
        description="Explicación clara y directa en lenguaje ciudadano (máximo 3 líneas)."
    )
    analisis_experto: str = Field(
        description="Detalle técnico y contextual citando los medios, leyes o artículos constitucionales hallados."
    )
    nivel_confianza: Literal["Alto", "Medio", "Bajo"]


class ReporteVerificacion(BaseModel):
    veredicto_general: Literal[
        "Cierto",
        "Engañoso / Media verdad",
        "Falso",
        "Inverificable",
        "Opinión / No verificable",
    ]
    resumen_ejecutivo: str = Field(
        description="Síntesis ciudadana de 2 a 3 oraciones explicando por qué se asignó ese veredicto."
    )
    desglose_afirmaciones: List[AfirmacionVerificada]


class ConsultasBusqueda(BaseModel):
    queries: List[str] = Field(
        description="Entre 1 y 3 consultas cortas de búsqueda en Google (sin operadores site:) para verificar los hechos y su marco legal."
    )


def _obtener_cliente() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No se encontró GEMINI_API_KEY en el entorno o en Secrets.")
    return genai.Client(api_key=api_key)


def _llamar_gemini_con_respaldo(cliente: genai.Client, prompt: str, schema_clase) -> dict:
    """Ejecuta la consulta rotando entre modelos de distintas series si hay congestión (503/429)."""
    ultimo_error = None

    for modelo in MODELOS_FALLBACK:
        for intento in range(2):
            try:
                respuesta = cliente.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema_clase,
                        temperature=0.05,
                    ),
                )
                return json.loads(respuesta.text)
            except Exception as e:
                ultimo_error = e
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    time.sleep(1.2)
                    continue
                break

    raise RuntimeError(f"Saturación temporal en los servidores de IA: {ultimo_error}")


def verificar_declaracion(
    texto: str, autor: str = "", fecha: str = "", contexto: str = ""
) -> Dict:
    cliente = _obtener_cliente()

    # 1. Extraer las consultas de búsqueda clave incluyendo contraste jurídico/constitucional si aplica
    try:
        prompt_queries = f"""
        Eres un periodista investigador experto en fact-checking en Venezuela.
        Analiza la siguiente declaración y extrae entre 1 y 3 consultas cortas de búsqueda para verificar los hechos.
        IMPORTANTE: Si la afirmación trata sobre cargos públicos, leyes, elecciones, TSJ, Asamblea Nacional o facultades del Estado venezolano, incluye al menos una consulta orientada al marco constitucional o análisis jurídico (por ejemplo: mencionando "Constitución", "inconstitucional", "Acceso a la Justicia" o "Cotejo").
        No uses comillas excesivas ni operadores 'site:'.

        Declaración: "{texto}"
        Autor atribuido: {autor or "No especificado"}
        Fecha: {fecha or "No especificada"}
        Contexto: {contexto or "No especificado"}
        """
        datos_queries = _llamar_gemini_con_respaldo(cliente, prompt_queries, ConsultasBusqueda)
        queries = datos_queries.get("queries", [texto[:110]])[:3]
    except Exception:
        queries = [texto[:120].strip()]

    # 2. Buscar evidencia en la lista blanca jerárquica
    evidencia_consolidada = []
    urls_vistas = set()

    for q in queries:
        res_busqueda = buscar_evidencia_escalonada(q)
        for item in res_busqueda.get("evidencia", []):
            if item["url"] not in urls_vistas:
                evidencia_consolidada.append(item)
                urls_vistas.add(item["url"])

    # 3. Evaluar la declaración exclusivamente contra la evidencia recuperada + rigor jurídico
    bloque_evidencia = ""
    if evidencia_consolidada:
        for idx, ev in enumerate(evidencia_consolidada, 1):
            bloque_evidencia += (
                f"[{idx}] Medio: {ev['medio']} ({ev['nivel_fuente']}) | Fecha: {ev['fecha']}\n"
                f"Título: {ev['titulo']}\n"
                f"Fragmento: {ev['fragmento']}\n"
                f"URL: {ev['url']}\n\n"
            )
    else:
        bloque_evidencia = "NO SE ENCONTRARON RESULTADOS EN LAS FUENTES AUDITADAS."

    prompt_evaluacion = f"""
    Eres un editor jefe de verificación de datos (fact-checking) bajo los estándares de la IFCN y LatamChequea en Venezuela.
    Evalúa la siguiente declaración basándote en la evidencia documental recuperada y en el ordenamiento constitucional venezolano vigente (Constitución de la República Bolivariana de Venezuela de 1999).

    REGLAS ESTRICTAS DE VERIFICACIÓN:
    1. DISTINCIÓN ENTRE LEGALIDAD Y HECHO CONSUMADO: Si una afirmación sostiene que algo "es legal", "está permitido" o que un funcionario "puede repetir en el cargo" cuando la Constitución de Venezuela de 1999 lo prohíbe expresamente (por ejemplo, el artículo 264 establece que los magistrados del TSJ son elegidos por un único período de 12 años sin posibilidad de reelección), DEBES clasificarla como "Falso" (si afirma que constitucionalmente pueden hacerlo) o "Engañoso / Media verdad" (si confunde una reelección ocurrida de facto o mediante reforma legal cuestionada con una facultad constitucional), explicando explícitamente qué dice la Constitución y lo documentado por observatorios jurídicos como Acceso a la Justicia.
    2. NO CONFUNDIR TITULARES DE HECHOS CON LEGALIDAD: Que una noticia reporte que un funcionario repitió en un cargo no convierte en "Cierta" la afirmación de que la ley o la Constitución lo permitan.
    3. OPINIONES: Si es un juicio de valor o proyección futura sin datos comprobables, clasifícala como "Opinión / No verificable".
    4. INVERIFICABLE: Si no hay evidencia documental suficiente para confirmar ni desmentir el hecho, clasifícala como "Inverificable". Nunca inventes datos.

    DECLARACIÓN A EVALUAR:
    Texto: "{texto}"
    Autor: {autor or "No especificado"}
    Fecha: {fecha or "No especificada"}
    Contexto: {contexto or "No especificado"}

    EVIDENCIA DOCUMENTAL RECUPERADA:
    {bloque_evidencia}
    """

    try:
        reporte = _llamar_gemini_con_respaldo(cliente, prompt_evaluacion, ReporteVerificacion)
    except Exception:
        reporte = {
            "veredicto_general": "Inverificable",
            "resumen_ejecutivo": (
                "Los servidores de análisis automático presentan alta demanda en este momento (error temporal 503). "
                "Sin embargo, el motor recuperó las siguientes publicaciones relacionadas en medios auditados para tu consulta directa."
            ),
            "desglose_afirmaciones": [
                {
                    "afirmacion": texto,
                    "veredicto": "Inverificable",
                    "explicacion_sencilla": "Revisa los enlaces de medios independientes mostrados abajo o intenta nuevamente en un par de minutos para obtener el análisis automatizado.",
                    "analisis_experto": "Contingencia activada por saturación temporal (HTTP 503) en la API de modelos generativos.",
                    "nivel_confianza": "Bajo",
                }
            ],
        }

    reporte["fuentes_detalladas"] = evidencia_consolidada
    reporte["queries_busqueda"] = queries
    return reporte
