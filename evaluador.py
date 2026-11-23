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

# Cadena de modelos vigentes en orden de prioridad
MODELOS_FALLBACK = [
    "gemini-3.8-flash",
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
        description="Detalle técnico y contextual citando los medios o datos hallados."
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
        description="Entre 1 y 3 consultas cortas de búsqueda en Google (sin operadores site:) para verificar los hechos."
    )


def _obtener_cliente() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No se encontró GEMINI_API_KEY en el entorno o en Secrets.")
    return genai.Client(api_key=api_key)


def _llamar_gemini_con_respaldo(cliente: genai.Client, prompt: str, schema_clase) -> dict:
    """Ejecuta la consulta rotando entre los modelos vigentes si hay congestión (503/429)."""
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
                        temperature=0.1,
                    ),
                )
                return json.loads(respuesta.text)
            except Exception as e:
                ultimo_error = e
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    time.sleep(1.5)
                    continue
                # Si el modelo no está disponible (404), salta directo al siguiente modelo
                break

    raise RuntimeError(
        f"No se pudo completar la consulta en los modelos disponibles. Detalle: {ultimo_error}"
    )


def verificar_declaracion(
    texto: str, autor: str = "", fecha: str = "", contexto: str = ""
) -> Dict:
    cliente = _obtener_cliente()

    # 1. Extraer las consultas de búsqueda clave
    prompt_queries = f"""
    Eres un periodista investigador experto en fact-checking en Venezuela.
    Analiza la siguiente declaración y extrae entre 1 y 3 consultas cortas de búsqueda para verificar si los hechos son ciertos o falsos.
    No uses comillas excesivas ni operadores 'site:'.

    Declaración: "{texto}"
    Autor atribuido: {autor or "No especificado"}
    Fecha: {fecha or "No especificada"}
    Contexto: {contexto or "No especificado"}
    """

    datos_queries = _llamar_gemini_con_respaldo(cliente, prompt_queries, ConsultasBusqueda)
    queries = datos_queries.get("queries", [texto[:100]])[:3]

    # 2. Buscar evidencia en la lista blanca jerárquica
    evidencia_consolidada = []
    urls_vistas = set()

    for q in queries:
        res_busqueda = buscar_evidencia_escalonada(q)
        for item in res_busqueda.get("evidencia", []):
            if item["url"] not in urls_vistas:
                evidencia_consolidada.append(item)
                urls_vistas.add(item["url"])

    # 3. Evaluar la declaración exclusivamente contra la evidencia recuperada
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
    Eres un editor jefe de verificación de datos (fact-checking) bajo los estándares de la IFCN y LatamChequea.
    Evalúa la siguiente declaración basándote ÚNICAMENTE en la evidencia documental proporcionada abajo.

    REGLAS ESTRICTAS:
    - Si la declaración es una opinión, proyección futura o juicio de valor sin datos comprobables, clasifícala como "Opinión / No verificable".
    - Si no hay evidencia documental suficiente para confirmar ni desmentir el hecho, clasifícala como "Inverificable". Nunca inventes datos.
    - Si los verificadores o medios citados desmienten explícitamente el rumor o cifra, clasifícala como "Falso".
    - Si mezcla un dato real con una exageración o falta de contexto, clasifícala como "Engañoso / Media verdad".

    DECLARACIÓN A EVALUAR:
    Texto: "{texto}"
    Autor: {autor or "No especificado"}
    Fecha: {fecha or "No especificada"}
    Contexto: {contexto or "No especificado"}

    EVIDENCIA DOCUMENTAL RECUPERADA:
    {bloque_evidencia}
    """

    reporte = _llamar_gemini_con_respaldo(cliente, prompt_evaluacion, ReporteVerificacion)
    reporte["fuentes_detalladas"] = evidencia_consolidada
    reporte["queries_busqueda"] = queries
    return reporte
