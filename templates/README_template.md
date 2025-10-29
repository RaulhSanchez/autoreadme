# {{ name }}

> {{ description }}

{% if architecture_ascii %}
## 🏗️ Arquitectura del Sistema
{{ architecture_ascii }}

{% endif %}

## 📑 Resumen Técnico
{{ elaborated_intro }}

{% if folders %}
## 📁 Estructura del Proyecto
{% for folder, files in folders.items() %}
### {{ folder }}
{% for f in files %}
- **{{ f.file }}**
  - Exports: {{ f.exports|join(", ") }}
  - Funciones: {{ f.functions|join(", ") }}
  - Clases: {{ f.classes|join(", ") }}
  {% if f.routes %}- Rutas: {{ f.routes|join(", ") }}{% endif %}
{% endfor %}
{% endfor %}
{% endif %}

{% if routes %}
## 🌐 Rutas Detalladas
{% for r in routes %}
### {{ r.method }} {{ r.path }}
**Archivo:** {{ r.file }}  
**Handlers:** {{ r.handlers|join(", ") }}  
{% if r.comment %}**Comentario:** {{ r.comment }}{% endif %}

**Descripción técnica:**  
{{ r.description }}
{% endfor %}
{% endif %}


{% if connections %}
## 🔗 Conexiones a Bases de Datos y Servicios Externos
Se listan las conexiones detectadas en el código y las variables de entorno relacionadas. **No se incluyen contraseñas reales.**

{% for c in connections %}
- **Archivo:** {{ c.file }}
  {% if c.match %}- Conexión: {{ c.match }}{% endif %}
  {% if c.env_var %}- Variable de entorno: {{ c.env_var }}{% endif %}
  - Línea: {{ c.line }}
{% endfor %}
{% endif %}



{% if dependencies %}
## 🛠️ Dependencias
- **Runtime:** {{ dependencies|join(", ") }}
- **Desarrollo:** {{ dev_dependencies|join(", ") }}
{% endif %}

{% if docker_section %}
## 🐳 Docker Compose
{{ docker_section }}
{% endif %}


{% if k8s_section %}
## ☸️ Kubernetes
{% for filename in k8s_section.keys() %}
### {{ filename }}
💡 Recursos de CPU y Memoria explicados:
{{ k8s_resources_explained[filename] }}

{% endfor %}
{% endif %}


{% if db_analysis %}
## 🧮 Análisis de Consultas a la Base de Datos
{{ db_analysis }}
{% endif %}
