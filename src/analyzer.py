import os
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from ollama import chat

MAX_WORKERS = 4        # Paralelismo en tu M2
CACHE_DIR = "/tmp/analyze_cache"
MAX_LINES = 500        # Limitar tamaño del archivo

os.makedirs(CACHE_DIR, exist_ok=True)

def analyze_file(file_path):
    cache_file = os.path.join(CACHE_DIR, os.path.basename(file_path) + ".json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.splitlines()
        content_short = "\n".join(lines[:MAX_LINES]) if len(lines) > MAX_LINES else content

        exports = re.findall(r"export\s+(?:const|function|class)?\s*(\w+)", content)
        functions = re.findall(r"function\s+(\w+)\s*\(", content)
        classes = re.findall(r"class\s+(\w+)", content)
        comments = [line.strip() for line in lines if line.strip().startswith("//")]

        rag_prompt = f"""
Analiza este archivo JS/TS y genera un resumen técnico en castellano:
{content_short}

Incluye: propósito del archivo, funciones y clases, rutas o controladores de API,
acceso a bases de datos o servicios externos.
"""
        narrative = chat(model="qwen2.5-coder:14b", messages=[{"role": "user", "content": rag_prompt}])["message"]["content"]

        result = {
            "file": file_path,
            "exports": exports,
            "functions": functions,
            "classes": classes,
            "comments": comments,
            "narrative": narrative
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    except Exception as e:
        return {"file": file_path, "error": str(e)}


def analyze_project_with_qwen(project_path):
    data = {
        "name": os.path.basename(project_path),
        "description": "",
        "folders_summary": {},
        "dependencies": [],
        "devDependencies": [],
        "routes": [],
        "docker": None,
        "k8s": None
    }

    # package.json
    pkg_path = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_path):
        with open(pkg_path, "r", encoding="utf-8") as f:
            pkg = json.load(f)
            data["description"] = pkg.get("description", "")
            data["dependencies"] = list(pkg.get("dependencies", {}).keys())
            data["devDependencies"] = list(pkg.get("devDependencies", {}).keys())

    # Archivos JS/TS
    all_files = []
    src_path = os.path.join(project_path, "src")
    for root, _, files in os.walk(src_path):
        for file in files:
            if file.endswith((".js", ".ts")):
                all_files.append(os.path.join(root, file))

    total_files = len(all_files)
    print(f"📂 Archivos a analizar: {total_files}")

    results = []
    start_time = time.time()
    processed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analyze_file, f): f for f in all_files}
        for future in as_completed(futures):
            results.append(future.result())
            processed += 1
            elapsed = time.time() - start_time
            avg_time = elapsed / processed
            remaining = avg_time * (total_files - processed)
            percent = processed / total_files * 100
            print(f"✅ {processed}/{total_files} ({percent:.1f}%) completado - "
                  f"Tiempo transcurrido: {elapsed:.1f}s - Estimado restante: {remaining:.1f}s")

    # Organizar por carpetas
    for r in results:
        file_path = r.get("file")
        if not file_path:
            continue
        folder_name = os.path.relpath(os.path.dirname(file_path), project_path)
        if folder_name not in data["folders_summary"]:
            data["folders_summary"][folder_name] = []
        data["folders_summary"][folder_name].append(r)

    # Detectar rutas Express
    for r in results:
        if "error" in r:
            continue
        content = r.get("narrative", "")
        matches = re.findall(r"(?:GET|POST|PUT|DELETE)\s+(/[^\s]+)", content)
        for m in matches:
            data["routes"].append({"file": r["file"], "path": m, "method": "AUTO"})

    # Docker y Kubernetes
    docker_path = os.path.join(project_path, "docker-compose.yml")
    if os.path.exists(docker_path):
        with open(docker_path, "r", encoding="utf-8") as f:
            data["docker"] = f.read()

    k8s_path = os.path.join(project_path, "deploy", "k8s")
    if os.path.exists(k8s_path):
        data["k8s"] = {}
        for k8s_file in os.listdir(k8s_path):
            if k8s_file.endswith((".yml", ".yaml")):
                with open(os.path.join(k8s_path, k8s_file), "r", encoding="utf-8") as f:
                    data["k8s"][k8s_file] = f.read()

    return data
