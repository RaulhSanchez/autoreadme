# autoreadme/src/analyzer.py
import os
import re
import json
import yaml
import glob
from typing import List, Dict

# ------------------ UTILIDADES BÁSICAS ------------------
def read_file_sample(path, max_chars=20000):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read(max_chars)
    except:
        return ""

def extract_js_summary(file_content: str) -> List[str]:
    lines = file_content.splitlines()
    summary = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            summary.append(stripped)
        elif stripped.startswith("function ") or "=>" in stripped or stripped.startswith("class "):
            summary.append(stripped)
    return summary[:200]

# ------------------ NUEVAS FUNCIONES DE PARSEO ------------------
def extract_imports(file_content: str) -> List[str]:
    imports = []
    for m in re.finditer(r"^\s*(?:import\s+.*\s+from\s+['\"](.*?)['\"]|const\s+.*=\s*require\(['\"](.*?)['\"]\))", 
                         file_content, flags=re.MULTILINE):
        groups = m.groups()
        module = groups[0] or groups[1]
        if module:
            imports.append(module)
    return imports

def extract_jsdoc_blocks(file_content: str) -> List[str]:
    return re.findall(r"/\*\*[\s\S]*?\*/", file_content)

def extract_function_signatures(file_content: str) -> List[Dict]:
    results = []
    for m in re.finditer(r"function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)", file_content):
        name, params = m.groups()
        snippet = file_content[m.start():m.start()+300]
        results.append({"name": name, "params": [p.strip() for p in params.split(",") if p.strip()], "snippet": snippet})
    for m in re.finditer(r"(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", file_content):
        name, params = m.groups()
        snippet = file_content[m.start():m.start()+300]
        results.append({"name": name, "params": [p.strip() for p in params.split(",") if p.strip()], "snippet": snippet})
    return results

def extract_class_methods(file_content: str) -> List[Dict]:
    classes = []
    for cm in re.finditer(r"class\s+([A-Za-z0-9_$]+)\s*(?:extends\s+[A-Za-z0-9_$]+)?\s*\{", file_content):
        cname = cm.group(1)
        start = cm.end()
        rest = file_content[start:start+2000]
        methods = re.findall(r"^\s*([A-Za-z0-9_$]+)\s*\(([^)]*)\)\s*\{", rest, flags=re.MULTILINE)
        methods_list = [{"name": m[0], "params": [p.strip() for p in m[1].split(",") if p.strip()]} for m in methods]
        classes.append({"class": cname, "methods": methods_list})
    return classes

def extract_exports(file_content: str) -> List[str]:
    exports = []
    for m in re.finditer(r"(?:module\.exports\s*=|exports\.[A-Za-z0-9_$]+\s*=|export\s+default|export\s+(?:const|function|class)\s+([A-Za-z0-9_$]+))", file_content):
        g = m.group(1)
        if g:
            exports.append(g)
        else:
            line = file_content[m.start():m.start()+120].splitlines()[0].strip()
            exports.append(line)
    return exports

def extract_sql_queries(file_content: str) -> List[str]:
    queries = []
    for m in re.finditer(r"(['\"])(?:.*?)(SELECT|INSERT|UPDATE|DELETE|CALL)\s+[\s\S]{1,300}?\1", file_content, flags=re.IGNORECASE):
        snippet = file_content[m.start():m.end()]
        queries.append(snippet.strip())
    for m in re.finditer(r"`([\s\S]{0,500}?(SELECT|INSERT|UPDATE|DELETE|CALL)[\s\S]{0,500}?)`", file_content, flags=re.IGNORECASE):
        queries.append(m.group(1).strip())
    return list(dict.fromkeys(queries))

def detect_req_res_usage(file_content: str) -> Dict[str, bool]:
    return {
        "uses_req": bool(re.search(r"\breq\b", file_content)),
        "uses_res": bool(re.search(r"\bres\b", file_content)),
        "uses_next": bool(re.search(r"\bnext\b", file_content))
    }

def detect_db_clients(file_content: str) -> List[str]:
    candidates = []
    db_tokens = ["mysql", "mysql2", "oracledb", "pg", "pg-pool", "mongoose", "sequelize", "knex"]
    for token in db_tokens:
        if token in file_content:
            candidates.append(token)
    return candidates

# ------------------ UTILIDADES PARA TEXTO HUMANO ------------------
def short_description_from_jsdoc(jsdoc_blocks: List[str]) -> str:
    if not jsdoc_blocks:
        return ""
    first = jsdoc_blocks[0]
    lines = [l.strip(" *") for l in first.splitlines()]
    for l in lines:
        if l and not l.strip().startswith("@"):
            return l.strip()
    return ""

def narrative_for_file(parsed: Dict) -> str:
    parts = []
    if parsed.get("jsdoc_summary"):
        parts.append(parsed["jsdoc_summary"])
    if parsed.get("imports"):
        parts.append(f"Importa módulos: {', '.join(parsed['imports'][:8])}" + ("..." if len(parsed['imports'])>8 else ""))
    if parsed.get("exports"):
        parts.append(f"Exporta: {', '.join(parsed['exports'][:8])}" + ("..." if len(parsed['exports'])>8 else ""))
    if parsed.get("functions"):
        fnames = [f['name'] for f in parsed['functions'][:8]]
        parts.append(f"Define funciones principales: {', '.join(fnames)}")
    if parsed.get("classes"):
        cnames = [c['class'] for c in parsed['classes']]
        parts.append(f"Clases: {', '.join(cnames)}" if cnames else "")
    if parsed.get("sql_queries"):
        parts.append(f"Contiene consultas SQL detectadas ({len(parsed['sql_queries'])})")
    if parsed.get("db_clients"):
        parts.append(f"Uso de clientes BD: {', '.join(parsed['db_clients'])}")
    rr = parsed.get("req_res", {})
    if rr.get("uses_req") or rr.get("uses_res"):
        parts.append("Funciona como handler HTTP (usa req/res)." if rr.get("uses_req") and rr.get("uses_res") else "Usa req o res en el código.")
    text = ". ".join([p for p in parts if p])
    if not text:
        text = "Archivo sin indicios claros de responsabilidades; revisar contenido manualmente."
    return text

# ------------------ KUBERNETES ------------------
def parse_k8s_yaml_files(project_path: str) -> Dict:
    k8s_info = {
        "resources": {},
        "hosts": {"dev": [], "pro": []}
    }

    # buscar cualquier deployment.yaml
    deployment_candidates = glob.glob(os.path.join(project_path, "deploy", "k8s", "*deployment.yaml"))
    if deployment_candidates:
        deployment_path = deployment_candidates[0]
        try:
            with open(deployment_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    containers = data.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
                    if containers:
                        k8s_info["resources"] = containers[0].get("resources", {})
        except Exception as e:
            k8s_info["resources_error"] = str(e)
    else:
        k8s_info["resources_error"] = "No se encontró archivo deployment.yaml en deploy/k8s/"

    # ingress dev
    dev_ingress_path = os.path.join(project_path, "deploy", "k8s", "dev", "2-ingress.yaml")
    if os.path.exists(dev_ingress_path):
        try:
            with open(dev_ingress_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    rules = data.get("spec", {}).get("rules", [])
                    hosts = [r.get("host") for r in rules if r.get("host")]
                    k8s_info["hosts"]["dev"] = hosts
        except Exception as e:
            k8s_info["hosts"]["dev"] = [f"Error: {e}"]

    # ingress pro
    pro_ingress_path = os.path.join(project_path, "deploy", "k8s", "pro", "2-ingress.yaml")
    if os.path.exists(pro_ingress_path):
        try:
            with open(pro_ingress_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    rules = data.get("spec", {}).get("rules", [])
                    hosts = [r.get("host") for r in rules if r.get("host")]
                    k8s_info["hosts"]["pro"] = hosts
        except Exception as e:
            k8s_info["hosts"]["pro"] = [f"Error: {e}"]

    return k8s_info

# ------------------ FUNCION PRINCIPAL ------------------
def analyze_project(project_path: str):
    summary = {
        "name": "",
        "description": "",
        "dependencies": [],
        "devDependencies": [],
        "scripts": {},
        "structure": "",
        "files_summary": {},
        "key_files": [],
        "folders_summary": {},
    }

    pkg_path = os.path.join(project_path, "package.json")
    if os.path.exists(pkg_path):
        with open(pkg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            summary["name"] = data.get("name", "")
            summary["description"] = data.get("description", "")
            summary["dependencies"] = list(data.get("dependencies", {}).keys())
            summary["devDependencies"] = list(data.get("devDependencies", {}).keys())
            summary["scripts"] = data.get("scripts", {})

    src_path = os.path.join(project_path, "src")
    structure_lines = []
    files_summary = {}

    if os.path.exists(src_path):
        for root, dirs, files in os.walk(src_path):
            level = root.replace(project_path, "").count(os.sep)
            indent = " " * 2 * level
            structure_lines.append(f"{indent}- {os.path.basename(root)}/")

            folder_name = os.path.relpath(root, src_path)
            if folder_name == ".":
                folder_name = os.path.basename(root)

            folder_details = []

            for file in files:
                structure_lines.append(f"{indent}  - {file}")
                if file.endswith((".js", ".ts")):
                    fpath = os.path.join(root, file)
                    content = read_file_sample(fpath, 20000)
                    summary_lines = extract_js_summary(content)
                    imports = extract_imports(content)
                    jsdocs = extract_jsdoc_blocks(content)
                    jsdoc_summary = short_description_from_jsdoc(jsdocs)
                    functions = extract_function_signatures(content)
                    classes = extract_class_methods(content)
                    exports = extract_exports(content)
                    sql_queries = extract_sql_queries(content)
                    req_res = detect_req_res_usage(content)
                    db_clients = detect_db_clients(content)
                    narrative = narrative_for_file({
                        "jsdoc_summary": jsdoc_summary,
                        "imports": imports,
                        "functions": functions,
                        "classes": classes,
                        "exports": exports,
                        "sql_queries": sql_queries,
                        "req_res": req_res,
                        "db_clients": db_clients
                    })

                    file_parsed = {
                        "path": os.path.relpath(fpath, project_path),
                        "short_summary_lines": summary_lines,
                        "jsdoc_summary": jsdoc_summary,
                        "imports": imports,
                        "functions": functions,
                        "classes": classes,
                        "exports": exports,
                        "sql_queries": sql_queries,
                        "req_res": req_res,
                        "db_clients": db_clients,
                        "narrative": narrative
                    }

                    if file == "router.js":
                        route_pattern = re.compile(r"(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['\"](.*?)['\"]\s*,\s*(\w+)")
                        routes = []
                        for match in route_pattern.finditer(content):
                            method, path, handler = match.groups()
                            purpose = f"Handler `{handler}` (propósito inferido por nombre)"
                            routes.append({"method": method.upper(), "path": path, "handler": handler, "purpose": purpose})
                        if routes:
                            file_parsed["routes"] = routes

                    folder_details.append(file_parsed)
                    files_summary[os.path.relpath(fpath, project_path)] = summary_lines

            if folder_details:
                summary["folders_summary"][folder_name] = folder_details

    summary["structure"] = "\n".join(structure_lines[:2000])
    summary["files_summary"] = files_summary
    summary["key_files"] = list(files_summary.keys())

    # --- Información K8s ---
    summary["k8s"] = parse_k8s_yaml_files(project_path)

    # otros archivos clave
    for f in ["Dockerfile", ".env", "tsconfig.json", "swagger.json", "README.md"]:
        if os.path.exists(os.path.join(project_path, f)):
            summary["key_files"].append(f)

    return summary
