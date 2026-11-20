import os
import re
import json
from typing import List, Literal
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

from buscador import buscar_evidencia_escalonada

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Modelos activos confirmados para tu cuenta (el lite responde ultra rápido y sin saturación)
MODELOS_RESPALDO = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
]


class AfirmacionEvaluada(BaseModel):
    afirmacion: str = Field(description="Frase factual exacta extraída del texto original.")
    veredicto: Literal[
        "Cierto",
        "Engañoso / Media verdad",
        "Falso",
        "Inverificable",
        "Opinión / No verificable"
    ]
    explicacion_sencilla: str = Field(
        description="Explicación clara en 2-3 líneas en lenguaje llano para cualquier ciudadano."
    )
    analisis_experto: str = Field(
        description="Análisis metodológico detallado citando cifras, fechas y contradicciones halladas."
    )
    nivel_confianza: Literal["Alto", "Medio", "Bajo"]
    fuentes_respaldo: List[str] = Field(
        description="Nombres de los medios usados para esta afirmación (ej. Cotejo.info, EsPaja)."
    )


class ReporteVerificacion(BaseModel):
    veredicto_general: Literal[
        "Cierto",
        "Engañoso / Media verdad",
        "Falso",
        "Inverificable",
        "Opinión / No verificable"
    ]
    resumen_ejecutivo: str = Field(
        description="Conclusión directa y neutral en máximo 3 oraciones."
    )
    queries_busqueda: List[str] = Field(
        description="Consultas utilizadas para buscar evidencia."
    )
    desglose_afirmaciones: List[AfirmacionEvaluada]


def _extraer_palabras_clave(texto: str, autor: str = "") -> List[str]:
    """Extrae palabras clave limpias al instante sin gastar cuota de LLM."""
    stop_words = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
        "al", "a", "en", "con", "por", "para", "que", "se", "su", "sus",
        "y", "o", "pero", "como", "mas", "más", "este", "esta", "esto",
        "ese", "esa", "eso", "partir", "sobre", "entre", "hasta", "desde"
    }
    texto_limpio = re.sub(r"[^\w\sáéíóúñÁÉÍÓÚÑ0-9]", " ", texto)
    palabras = [
        p for p in texto_limpio.split()
        if p.lower() not in stop_words and len(p) > 2
    ]
    query_principal = " ".join(palabras[:9])
    queries = [query_principal]

    if autor and autor.lower() not in query_principal.lower():
        queries.append(f"{autor} {' '.join(palabras[:5])}")

    return queries


def _llamar_gemini_con_respaldo(prompt: str, schema) -> str:
    """Ejecuta la evaluación usando gemini-3.5-flash-lite con respaldo a gemini-3.8-flash."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.1,
    )

    ultimo_error = None
    for modelo in MODELOS_RESPALDO:
        try:
            respuesta = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=config,
            )
            return respuesta.text
        except Exception as e:
            print(f"[Aviso] {modelo} no disponible ({e}). Probando respaldo...")
            ultimo_error = e

    raise RuntimeError(f"Error al conectar con Gemini: {ultimo_error}")


def verificar_declaracion(texto: str, autor: str = "", fecha: str = "", contexto: str = "") -> dict:
    contexto_completo = f"Autor: {autor} | Fecha: {fecha} | Contexto: {contexto}".strip(" |")
    queries = _extraer_palabras_clave(texto, autor)

    evidencia_recopilada = []
    urls_vistas = set()

    for q in queries:
        resultado_busqueda = buscar_evidencia_escalonada(q)
        for item in resultado_busqueda.get("evidencia", []):
            if "google.com/goto" not in item["url"] and item["medio"] != "Fuente externa":
                if item["url"] not in urls_vistas:
                    evidencia_recopilada.append(item)
                    urls_vistas.add(item["url"])

    bloque_evidencia = ""
    for i, ev in enumerate(evidencia_recopilada, 1):
        bloque_evidencia += (
            f"[{i}] Medio: {ev['medio']} ({ev['nivel_fuente']})\n"
            f"    Título: {ev['titulo']}\n"
            f"    Fecha: {ev['fecha']}\n"
            f"    Extracto: {ev['fragmento']}\n"
            f"    URL: {ev['url']}\n\n"
        )

    if not bloque_evidencia:
        bloque_evidencia = "No se encontraron registros en los medios auditados sobre esta afirmación exacta."

    prompt_evaluacion = f"""
    Actúa como un verificador de datos (fact-checker) riguroso, imparcial y adherido a los estándares de la IFCN, especializado en Venezuela.

    DECLARACIÓN A VERIFICAR:
    "{texto}"

    METADATOS APORTADOS:
    {contexto_completo if contexto_completo else "No especificados"}

    EVIDENCIA RECUPERADA DE MEDIOS INDEPENDIENTES Y OBSERVATORIOS:
    {bloque_evidencia}

    REGLAS ESTRICTAS DE EVALUACIÓN:
    1. Basa tu veredicto EXCLUSIVAMENTE en la evidencia recuperada y en hechos comprobables. Nunca inventes cifras ni enlaces.
    2. Si la frase es un juicio de valor, promesa futura o postura ideológica sin datos factuales auditables, clasifícala como "Opinión / No verificable".
    3. Si un dato es real pero se usa fuera de fecha o para llegar a una conclusión manipulada, usa "Engañoso / Media verdad".
    4. Si no hay evidencia suficiente en las fuentes consultadas para confirmar o desmentir, usa "Inverificable" y explica qué dato oficial falta.
    5. Mantén un tono neutral, periodístico y libre de adjetivos partidistas.
    """

    texto_reporte = _llamar_gemini_con_respaldo(prompt_evaluacion, schema=ReporteVerificacion)
    reporte = json.loads(texto_reporte)
    reporte["queries_busqueda"] = queries
    reporte["fuentes_detalladas"] = evidencia_recopilada
    return reporte


if __name__ == "__main__":
    frase_prueba = "Delcy Rodríguez anunció que el salario mínimo en Venezuela subirá a 500 dólares a partir del 1 de diciembre."
    print(f"Analizando: '{frase_prueba}'...\n")
    resultado = verificar_declaracion(frase_prueba)
    print(f"VEREDICTO GENERAL: {resultado['veredicto_general']}")
    print(f"RESUMEN: {resultado['resumen_ejecutivo']}\n")
    print(f"FUENTES CONSULTADAS ({len(resultado['fuentes_detalladas'])}):")
    for f in resultado["fuentes_detalladas"]:
        print(f" - {f['medio']}: {f['titulo']} ({f['url']})")