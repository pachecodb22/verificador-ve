import streamlit as st
from datetime import datetime
from fpdf import FPDF
from evaluador import verificar_declaracion
from extractor import procesar_entrada_usuario

# --- CONFIGURACIÓN DE PÁGINA (MOBILE-FIRST Y PÚBLICA) ---
st.set_page_config(
    page_title="Verificador VE | Chequeo del Discurso Público",
    page_icon="🔍",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# --- ESTILOS VISUALES PARA TARJETAS DE VEREDICTO ---
COLORES_VEREDICTO = {
    "Cierto": ("#1b5e20", "#e8f5e9", "✅"),
    "Engañoso / Media verdad": ("#e65100", "#fff3e0", "⚠️"),
    "Falso": ("#b71c1c", "#ffebee", "❌"),
    "Inverificable": ("#37474f", "#eceff1", "❓"),
    "Opinión / No verificable": ("#1a237e", "#e8eaf6", "💬"),
}

EJEMPLOS_RAPIDOS = {
    "Rumor salarial ($500)": "Delcy Rodríguez anunció que el salario mínimo en Venezuela subirá a 500 dólares a partir del 1 de diciembre.",
    "Cifra económica (OVF/BCV)": "La inflación acumulada en Venezuela durante el último trimestre superó el 150 % según reportes independientes.",
    "Opinión política": "Venezuela tiene el potencial energético más importante de todo el hemisferio occidental para los próximos veinte años.",
}


# --- CACHÉ PARA PROTEGER CUOTAS EN WEB PÚBLICA ---
@st.cache_data(ttl=3600, show_spinner=False)
def ejecutar_verificacion_cacheada(texto: str, autor: str, fecha: str, contexto: str) -> dict:
    return verificar_declaracion(texto=texto, autor=autor, fecha=fecha, contexto=contexto)


# --- GENERADOR DE FICHA TÉCNICA EN PDF (FPDF2) ---
def _limpiar_texto_pdf(texto: str) -> str:
    reemplazos = {
        "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
        "…": "...", "•": "-", "€": "EUR",
    }
    for k, v in reemplazos.items():
        texto = texto.replace(k, v)
    return texto.encode("latin-1", "replace").decode("latin-1")


def generar_pdf_verificacion(texto_original: str, autor: str, fecha: str, reporte: dict) -> bytes:
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    ancho_util = pdf.epw

    pdf.set_font("Helvetica", "B", 15)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 8, _limpiar_texto_pdf("FICHA DE VERIFICACION DE DISCURSO PUBLICO - VE"))

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 100, 100)
    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf(f"Emitido el: {fecha_emision} | Estandar Metodologico: Contraste Documental"))
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf("1. DECLARACION ANALIZADA"))

    pdf.set_font("Helvetica", "I", 10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf(f'"{texto_original}"'))

    if autor or fecha:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf(f"Atribuida a: {autor or 'No especificado'} | Fecha declaracion: {fecha or 'No especificada'}"))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 12)
    veredicto = reporte.get("veredicto_general", "Inverificable")
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 7, _limpiar_texto_pdf(f"2. VEREDICTO: {veredicto.upper()}"))

    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf(reporte.get("resumen_ejecutivo", "")))
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf("3. DESGLOSE ANALITICO"))

    for idx, item in enumerate(reporte.get("desglose_afirmaciones", []), 1):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf(f"{idx}. [{item['veredicto']}] {item['afirmacion']}"))

        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf(f"Analisis: {item['analisis_experto']}"))
        pdf.ln(2)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(ancho_util, 6, _limpiar_texto_pdf("4. FUENTES INDEPENDIENTES CONSULTADAS"))

    pdf.set_font("Helvetica", "", 9)
    fuentes = reporte.get("fuentes_detalladas", [])
    if fuentes:
        for f in fuentes:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf(f"- {f['medio']}: {f['titulo']}"), wrapmode="CHAR")
            pdf.set_x(pdf.l_margin)
            pdf.set_text_color(40, 80, 150)
            pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf(f"  Enlace: {f['url']}"), wrapmode="CHAR")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)
    else:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(ancho_util, 5, _limpiar_texto_pdf("No se hallaron registros directos en la lista blanca de medios."))

    return bytes(pdf.output())


# --- ENCABEZADO DIDÁCTICO Y PROPÓSITO ---
st.title("🔍 Verificador VE")
st.markdown(
    "**¿Recibiste una cadena de WhatsApp, un tuit o una declaración política y dudas si es real?**  \n"
    "Esta herramienta cruza afirmaciones públicas sobre Venezuela exclusivamente contra medios de verificación "
    "certificados, prensa de investigación y observatorios técnicos."
)

# --- GUÍA VISUAL DE 3 PASOS ---
col_p1, col_p2, col_p3 = st.columns(3)
with col_p1:
    st.markdown(
        """
        <div style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px; height:100%;">
            <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">1️⃣ Pega el contenido</div>
            <div style="font-size:13px; color:#475569;">Copia una frase, un rumor de WhatsApp o el enlace de una publicación en X (Twitter).</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_p2:
    st.markdown(
        """
        <div style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px; height:100%;">
            <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">2️⃣ Contraste documental</div>
            <div style="font-size:13px; color:#475569;">El sistema rastrea chequeos previos y datos oficiales en fuentes venezolanas auditadas.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_p3:
    st.markdown(
        """
        <div style="background-color:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px; height:100%;">
            <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">3️⃣ Veredicto y PDF</div>
            <div style="font-size:13px; color:#475569;">Recibe una calificación clara con enlaces verificables y descarga la ficha técnica.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# --- GUÍA DE ETIQUETAS Y FUENTES (DIDÁCTICO Y COLAPSABLE) ---
with st.expander("📘 ¿Cómo leer los veredictos y qué fuentes consultamos?"):
    st.markdown(
        """
        **Significado de las etiquetas de calificación:**
        - ✅ **Cierto:** La afirmación coincide con datos oficiales verificables y registros de medios independientes.
        - ⚠️ **Engañoso / Media verdad:** Contiene un dato real, pero está sacado de contexto, desactualizado o exagerado.
        - ❌ **Falso:** Existen pruebas documentales o desmentidos oficiales que contradicen directamente la afirmación.
        - ❓ **Inverificable:** No hay registros públicos suficientes para confirmar ni desmentir el dato.
        - 💬 **Opinión / No verificable:** Es un juicio de valor, promesa futura o postura política, no un hecho medible.

        **Fuentes auditadas que consulta el motor:**
        - **Verificadores certificados (IFCN / LatamChequea):** *Cotejo.info, EsPaja, Cazadores de Fake News, AFP Factual*.
        - **Periodismo de investigación:** *Armando.info, TalCual, El Pitazo, Runrun.es, Crónica.Uno, Prodavinci*.
        - **Observatorios y entes técnicos:** *Observatorio Venezolano de Finanzas (OVF), BCV, Acceso a la Justicia, PROVEA, VE sin Filtro*.
        """
    )

st.divider()

# --- ÁREA PRINCIPAL DE VERIFICACIÓN ---
if "texto_input" not in st.session_state:
    st.session_state.texto_input = ""

st.markdown("**¿No sabes qué probar? Haz clic en uno de estos ejemplos:**")
cols_ej = st.columns(3)
for idx, (etiqueta, frase) in enumerate(EJEMPLOS_RAPIDOS.items()):
    if cols_ej[idx].button(etiqueta, use_container_width=True):
        st.session_state.texto_input = frase

texto_usuario = st.text_area(
    "Escribe o pega aquí lo que deseas verificar:",
    value=st.session_state.texto_input,
    height=130,
    max_chars=1500,
    placeholder="Ejemplo: Pega el texto de una cadena de WhatsApp, una cita de un funcionario o el enlace de un tuit (https://x.com/...)",
    help="Acepta texto directo, enlaces públicos de X (Twitter) y enlaces de noticias. Para Instagram o TikTok, copia y pega el texto de la publicación.",
)

with st.expander("⚙️ Opciones avanzadas (Para periodistas, investigadores o estudiantes)"):
    st.caption("Si conoces quién dijo la frase o cuándo circuló, añádelo aquí para afinar la búsqueda:")
    col1, col2 = st.columns(2)
    autor_input = col1.text_input("Personaje o institución", placeholder="Ej: Delcy Rodríguez / BCV")
    fecha_input = col2.text_input("Fecha aproximada", placeholder="Ej: Noviembre 2026")
    contexto_input = st.text_input("Medio o contexto donde circuló", placeholder="Ej: Cadena de WhatsApp / Rueda de prensa")
    modo_experto = st.checkbox("Activar vista de auditoría técnica (muestra metodología y consultas exactas)", value=False)

if st.button("🔍 Verificar declaración ahora", type="primary", use_container_width=True):
    if not texto_usuario.strip() or len(texto_usuario.strip()) < 12:
        st.warning("Por favor, escribe una afirmación completa o pega un enlace válido (mínimo 12 caracteres).")
    else:
        resultado_extraccion = procesar_entrada_usuario(texto_usuario)

        if not resultado_extraccion["exito"]:
            st.warning(resultado_extraccion["mensaje_error"])
        else:
            texto_a_verificar = resultado_extraccion["texto"]
            autor_final = autor_input.strip() or resultado_extraccion.get("autor", "")
            contexto_final = contexto_input.strip()

            if resultado_extraccion.get("es_enlace"):
                st.info(f"🔗 **Contenido extraído de {resultado_extraccion['plataforma']}:**\n\n*\"{texto_a_verificar}\"*")
                if not contexto_final:
                    contexto_final = f"Publicación extraída de {resultado_extraccion['plataforma']}"

            with st.spinner("Consultando verificadores certificados, medios de investigación y datos oficiales..."):
                try:
                    reporte = ejecutar_verificacion_cacheada(
                        texto_a_verificar,
                        autor_final,
                        fecha_input.strip(),
                        contexto_final,
                    )

                    veredicto = reporte.get("veredicto_general", "Inverificable")
                    color_texto, color_fondo, icono = COLORES_VEREDICTO.get(
                        veredicto, ("#37474f", "#eceff1", "❓")
                    )

                    st.markdown(
                        f"""
                        <div style="background-color:{color_fondo}; border-left: 6px solid {color_texto}; padding: 18px; border-radius: 8px; margin-top: 15px; margin-bottom: 15px;">
                            <h3 style="color:{color_texto}; margin:0 0 8px 0;">{icono} Veredicto: {veredicto}</h3>
                            <p style="color:#1f2937; font-size:16px; margin:0;">{reporte.get('resumen_ejecutivo', '')}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.subheader("Detalle del análisis")
                    for item in reporte.get("desglose_afirmaciones", []):
                        v_item = item["veredicto"]
                        _, _, ic_item = COLORES_VEREDICTO.get(v_item, ("#37474f", "#eceff1", "❓"))
                        with st.container(border=True):
                            st.markdown(f"**{ic_item} {v_item}** — *\"{item['afirmacion']}\"*")
                            st.write(item["explicacion_sencilla"])
                            if modo_experto:
                                st.info(f"**Análisis metodológico:** {item['analisis_experto']} (Confianza: {item['nivel_confianza']})")

                    st.subheader("Fuentes independientes consultadas")
                    fuentes = [
                        f for f in reporte.get("fuentes_detalladas", [])
                        if "/page/" not in f["url"] and "attachment_id" not in f["url"]
                    ]
                    if fuentes:
                        for f in fuentes:
                            st.markdown(
                                f"- **{f['medio']}** ({f['nivel_fuente']}): [{f['titulo']}]({f['url']})  \n"
                                f"  <small style='color:#6b7280;'>{f['fragmento']}</small>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.info("No se hallaron publicaciones previas sobre esta afirmación exacta en los medios auditados.")

                    if modo_experto:
                        with st.expander("🔎 Trazabilidad de búsqueda (Consultas enviadas al buscador)"):
                            st.write(reporte.get("queries_busqueda", []))

                    st.divider()
                    pdf_bytes = generar_pdf_verificacion(texto_a_verificar, autor_final, fecha_input, reporte)
                    st.download_button(
                        label="📄 Descargar Ficha de Verificación (PDF)",
                        data=pdf_bytes,
                        file_name=f"verificacion_ve_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )

                except Exception as e:
                    st.error(f"Ocurrió un inconveniente temporal al procesar la verificación: {e}")

st.divider()
st.caption("Nota metodológica: Herramienta de apoyo ciudadano y periodístico. Los resultados se generan cruzando declaraciones públicas con medios independientes y verificadores certificados en Venezuela.")
