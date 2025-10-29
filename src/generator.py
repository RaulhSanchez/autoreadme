# generator.py
import os
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from jinja2 import Environment, FileSystemLoader
from ollama import chat
from analyzer import analyze_project_with_qwen
import hashlib

MAX_LINES = 200
CACHE_DIR = "/tmp/analyze_cache"
SQL_CACHE_DIR = os.path.join(CACHE_DIR, "sql_cache")
os.makedirs(SQL_CACHE_DIR, exist_ok=True)
MAX_WORKERS = 3  # Paralelismo para SQL/JS/TS

# -------------------------------
# 🔍 Funciones de cache y hash
# -------------------------------
def file_hash(path):
    """Devuelve el hash MD5 de un archivo"""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def read_cache(cache_file):
    if os.path.exists(cache_file):
        try:
            return json.load(open(cache_file, encoding="utf-8"))
        except Exception:
            return None
    return None

def write_cache(cache_file, data):
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -------------------------------
# 🔍 Analiza cada archivo SQL/JS/TS en src/data
# -------------------------------
def analyze_db_file(path):
    cache_file = os.path.join(SQL_CACHE_DIR, os.path.basename(path) + ".json")
    cached = read_cache(cache_file)
    h = file_hash(path)
    if cached and cached.get("hash") == h:
        return cached["analysis"]

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        content_short = "\n".join(lines[:MAX_LINES]) if len(lines) > MAX_LINES else content

        prompt = f"""
Analiza este archivo del proyecto: {path}

1. Explica en castellano qué consultas SQL, conexiones a base de datos o servicios externos realiza.
2. Indica las tablas o endpoints afectados y el propósito técnico de cada operación.
3. Menciona desde qué funciones o métodos se invocan las consultas.
4. Resume cualquier lógica adicional relevante para la base de datos.

Archivo completo:
{content_short}
"""
        response = chat(model="qwen2.5-coder:14b", messages=[{"role": "user", "content": prompt}])
        analysis = f"### Archivo: {os.path.basename(path)}\n{response['message']['content']}"

        write_cache(cache_file, {"hash": h, "analysis": analysis})
        return analysis
    except Exception as e:
        return f"### Archivo: {os.path.basename(path)}\nNo se pudo analizar: {str(e)}"

def analyze_db_queries(project_path):
    data_folder = os.path.join(project_path, "src", "data")
    if not os.path.exists(data_folder):
        return "No se encontró la carpeta src/data."

    sql_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(data_folder)
        for f in files if f.endswith((".js", ".ts", ".sql"))
    ]
    if not sql_files:
        return "No se encontraron archivos .js, .ts o .sql en src/data."

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(analyze_db_file, f) for f in sql_files]
        for future in as_completed(futures):
            results.append(future.result())

    return "\n\n".join(results)

# -------------------------------
# 🔍 Funciones de RAG y rutas
# -------------------------------
def extract_routes_from_code(code, filename):
    routes = []
    pattern = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\)")
    comment_pattern = re.compile(r"//(.*)$|/\*\*(.*?)\*/", re.MULTILINE | re.DOTALL)
    comments = [m.group(1) or m.group(2) for m in comment_pattern.finditer(code)]
    matches = pattern.findall(code)

    for i, match in enumerate(matches):
        method, path, handler = match
        handler_list = [h.strip() for h in handler.split(",") if h.strip()]
        comment = comments[i] if i < len(comments) else ""
        routes.append({
            "file": filename,
            "method": method.upper(),
            "path": path,
            "handlers": handler_list,
            "comment": comment.strip(),
        })
    return routes

def generate_rag_text(prompt, context, model="qwen2.5-coder:14b"):
    rag_prompt = f"""
Usa el siguiente contexto técnico para responder en castellano, de forma profesional y detallada:
{chr(10).join(context)}

{prompt}
"""
    response = chat(model=model, messages=[{"role": "user", "content": rag_prompt}])
    return response["message"]["content"]

def generate_architecture_diagram(context_texts, project_name, model="qwen2.5-coder:14b"):
    prompt = f"""
Analiza la siguiente información del proyecto {project_name} y genera un diagrama ASCII
profesional que represente la arquitectura del sistema, incluyendo capas,
módulos, dependencias y flujo de datos.
"""
    return generate_rag_text(prompt, context_texts, model=model)

# -------------------------------
# 🔍 Generación del README
# -------------------------------
def generate_readme_rag(project_data, output_path, template_filename="README_template.md"):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    templates_dir = os.path.join(base_dir, "templates")
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template(template_filename)

    # Contexto general
    context_texts = []
    for folder, files in project_data.get("folders_summary", {}).items():
        for f in files:
            context_texts.append(
                f"{folder}/{f['file']}:\nExports: {' '.join(f.get('exports', []))}\n"
                f"Functions: {' '.join(f.get('functions', []))}\n"
                f"Classes: {' '.join(f.get('classes', []))}\n"
                f"Comments: {' | '.join(f.get('comments', []))}\n"
            )

    deps = project_data.get("dependencies", []) + project_data.get("devDependencies", [])
    if deps:
        context_texts.append("Dependencias: " + ", ".join(deps))

    # Diagrama arquitectura
    architecture_ascii = generate_architecture_diagram(context_texts, project_data.get("name", "Proyecto"))

    # Rutas detalladas
    detailed_routes = []
    for route in project_data.get("routes", []):
        filename = route.get("file")
        if not filename or not os.path.exists(filename):
            continue
        with open(filename, "r", encoding="utf-8") as f:
            code = f.read()
        extracted_routes = extract_routes_from_code(code, filename)
        for r in extracted_routes:
            rag_context = [
                f"Ruta: {r['method']} {r['path']}",
                f"Handlers: {', '.join(r['handlers'])}",
                f"Comentario: {r['comment']}"
            ]
            description = generate_rag_text(
                f"Explica detalladamente la finalidad, flujo de datos y validaciones de la ruta {r['method']} {r['path']}.",
                rag_context
            )
            r["description"] = description
            detailed_routes.append(r)

    # Kubernetes explicado
    explained_k8s = {}
    k8s_files = project_data.get("k8s", {})
    for filename, content in (k8s_files or {}).items():
        explained_k8s[filename] = content  # opcional: podrías generar explicación con RAG

    # Análisis SQL
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    db_analysis = analyze_db_queries(project_root)

    # Renderizado final
    print("🧠 Generando texto del README usando el modelo de Ollama...")
    readme_md = template.render(
        name=project_data.get("name", "Proyecto"),
        description=project_data.get("description", ""),
        elaborated_intro=generate_rag_text(
            f"Genera un README técnico exhaustivo del proyecto {project_data['name']}, "
            f"detallando arquitectura, módulos, rutas, dependencias y propósito general.",
            context_texts
        ),
        architecture_ascii=architecture_ascii,
        folders=project_data.get("folders_summary", {}),
        dependencies=project_data.get("dependencies", []),
        dev_dependencies=project_data.get("devDependencies", []),
        routes=detailed_routes,
        docker_section=project_data.get("docker", ""),
        k8s_section=project_data.get("k8s", {}),
        k8s_resources_explained=explained_k8s,
        db_analysis=db_analysis,
    )

    print(f"✏️ Generando README en: {output_path}")
    print(f"Longitud del texto generado: {len(readme_md)} caracteres")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(readme_md)

    print(f"✅ README generado correctamente en {output_path}")
