import textwrap
from ollama import chat
import json
import os

def generate_elaborated_intro(project_data):
    """
    Genera un resumen del proyecto y arquitectura más profundo usando Mistral.
    """
    name = project_data.get("name", "Proyecto sin nombre")
    desc = project_data.get("description", "Sin descripción")

    # Carpetas y archivos resumidos
    folders_summary = project_data.get("folders_summary", {})
    folder_info = []
    for folder, files in folders_summary.items():
        for f in files[:10]:  # más info para Mistral
            folder_info.append(
                f"{f.get('path')} → {f.get('narrative','')} "
                f"Funciones: {[fn['name'] for fn in f.get('functions', [])][:5]} "
                f"Exports: {f.get('exports', [])[:5]}"
            )
    folder_info_text = "\n".join(folder_info[:20])  # top 20

    # Rutas y handlers
    routes_info = []
    for folder_files in folders_summary.values():
        for f in folder_files:
            if os.path.basename(f.get("path", "")) == "router.js":
                for r in f.get("routes", []):
                    routes_info.append(f"{r['method']} {r['path']} → handler {r['handler']}")
    routes_text = "\n".join(routes_info[:20])

    # DB clients y SQL
    db_clients = []
    sql_info = []
    for folder_files in folders_summary.values():
        for f in folder_files:
            db_clients += f.get("db_clients", [])
            sql_info += [q[:100] + "..." for q in f.get("sql_queries", [])]
    db_clients = list(dict.fromkeys(db_clients))[:10]
    sql_info = sql_info[:20]

    prompt = textwrap.dedent(f"""
    Eres un asistente técnico experto en documentación de software Node.js.
    Tienes información completa sobre un proyecto llamado '{name}'.

    Breve descripción: {desc}

    Carpetas y archivos:
    {folder_info_text}

    Rutas y handlers:
    {routes_text}

    Clientes de DB usados: {', '.join(db_clients) or 'Ninguno'}
    Consultas SQL detectadas: {', '.join(sql_info) or 'Ninguna'}

    Redacta de manera profesional y detallada:

    1. **Resumen del proyecto**: Explica el propósito principal, problemas que resuelve, cómo interactúan módulos y capas, y el impacto real para usuarios y desarrolladores.
    2. **Arquitectura y flujo de datos**: Explica las capas, responsabilidades, flujo de datos desde la petición hasta la base de datos y respuesta, y cómo interactúan las dependencias críticas.
    """)
    
    response = chat(
        model="mistral:latest",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response['message']['content']


def generate_readme_explained(project_data, output_path):
    """
    Genera un README.md usando la información real de project_data,
    con secciones elaboradas de Resumen y Arquitectura.
    """

    # --- HEADER y metadatos ---
    name = project_data.get("name", "Proyecto sin nombre")
    desc = project_data.get("description", "Sin descripción")
    deps = ", ".join(project_data.get("dependencies", [])) or "Ninguna"
    devdeps = ", ".join(project_data.get("devDependencies", [])) or "Ninguna"
    scripts = project_data.get("scripts", {})

    # --- Estructura ---
    structure = project_data.get("structure", "")

    # --- Detalle por carpeta ---
    folders = project_data.get("folders_summary", {})
    folder_sections = []
    for folder, files in folders.items():
        folder_text = f"## Carpeta: `{folder}`\n\nDescripción general:\n"
        narratives = []
        for f in files:
            path = f.get("path")
            narrative = f.get("narrative", "")
            functions = f.get("functions", [])
            exports = f.get("exports", [])
            sql_count = len(f.get("sql_queries", []) or [])

            entry = f"- **{os.path.basename(path)}** (`{path}`): {narrative}."
            if functions:
                entry += f" Funciones principales: {', '.join([fn['name'] for fn in functions[:6]])}."
            if exports:
                entry += f" Exports: {', '.join(exports[:6])}."
            if sql_count:
                entry += f" Contiene ~{sql_count} consultas SQL detectadas."
            narratives.append(entry)

        folder_text += "\n".join(narratives)
        folder_sections.append(folder_text)

    folder_sections_text = "\n\n".join(folder_sections) or "No se detectaron carpetas con ficheros JS/TS."

    # --- Rutas detectadas ---
    routes_summary = []
    for folder_files in folders.values():
        for f in folder_files:
            if os.path.basename(f.get("path", "")) == "router.js":
                for r in f.get("routes", []):
                    routes_summary.append(
                        f"- `{r['method']} {r['path']}` → Handler: `{r['handler']}`. "
                        f"Propósito inferido: {r.get('purpose', 'No inferido')}"
                    )

    routes_text = "\n".join(routes_summary) or "No se detectaron rutas."

    # --- Archivos clave ---
    key_files = project_data.get("key_files", [])

    # --- Información de Kubernetes ---
    k8s = project_data.get("k8s", {})
    k8s_section = ""
    if k8s:
        resources = k8s.get("resources", {})
        dev_hosts = ", ".join(k8s.get("hosts", {}).get("dev", []))
        pro_hosts = ", ".join(k8s.get("hosts", {}).get("pro", []))

        def explain_resource(value, type_):
            if type_ == "cpu":
                if str(value).endswith("m"):
                    cpu_val = int(value[:-1]) / 1000
                    return f"{cpu_val} cores" if cpu_val >= 1 else f"{cpu_val*1000:.0f} milicores"
                else:
                    return f"{value} cores"
            elif type_ == "mem":
                if str(value).endswith("Mi"):
                    mem_val = int(value[:-2])
                    mem_mb = round(mem_val * 1.048576)
                    if mem_mb >= 1024:
                        mem_gb = round(mem_mb / 1024, 1)
                        return f"{mem_gb} Gigabytes"
                    else:
                        return f"{mem_mb} Megabytes"
                else:
                    return f"{value} bytes"
            return value

        if resources:
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})

            k8s_human = f"""
Kubernetes utiliza configuraciones de **requests** y **limits** para gestionar los recursos del contenedor:

- **Requests**: Recursos mínimos garantizados que se reservan para el contenedor.
  - CPU: {explain_resource(requests.get('cpu','0'), 'cpu')} → asegura que el contenedor siempre tenga CPU suficiente.
  - Memoria: {explain_resource(requests.get('memory','0'), 'mem')} → asegura memoria suficiente.

- **Limits**: Recursos máximos que el contenedor puede consumir.
  - CPU: {explain_resource(limits.get('cpu','0'), 'cpu')} → evita que el contenedor consuma toda la CPU del nodo.
  - Memoria: {explain_resource(limits.get('memory','0'), 'mem')} → protege la memoria de otros contenedores.

> **Motivo:** Balancear eficiencia y seguridad, garantizando recursos suficientes sin afectar al clúster.
"""
            k8s_section = f"""
## Despliegue Kubernetes

{k8s_human}

**Hosts detectados:**
- DEV: [{dev_hosts}](http://{dev_hosts})  
- PRO: [{pro_hosts}](http://{pro_hosts})
"""

    # --- Generar Resumen y Arquitectura elaborados con Mistral ---
    elaborated_intro = generate_elaborated_intro(project_data)

    # --- Construcción del prompt final para README ---
    prompt = textwrap.dedent(f"""
    Eres un asistente técnico. Con la información estricta que te doy, redacta un README.md completo en Markdown.
    NO INVENTES nada que no esté en la información.
    Usa un lenguaje claro y profesional.

    Proyecto: {name}
    Secciones iniciales generadas por Mistral (Resumen y Arquitectura):
    {elaborated_intro}

    Dependencias: {deps}
    DevDependencies: {devdeps}
    Scripts: {json.dumps(scripts, indent=2)}

    Estructura (parcial):
    {structure}

    Resumen por carpetas y ficheros:
    {folder_sections_text}

    Rutas detectadas:
    {routes_text}

    Información Kubernetes:
    {k8s_section}

    Archivos clave: {', '.join(key_files) or 'Ninguno'}

    Redacta el README completo incluyendo:
    - Resumen del proyecto
    - Arquitectura y flujo de datos
    - Carpeta por carpeta
    - Rutas y explicación
    - Instalación
    - Ejecución
    - Testing
    - Despliegue Kubernetes
    - Licencia
    """)

    # --- Llamada final al modelo para README completo ---
    response = chat(model="qwen2.5-coder:latest", messages=[
        {"role": "user", "content": prompt}
    ])
    content = response['message']['content']

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ README generado en {output_path}")
