# autoreadme/src/main.py
import os
from analyzer import analyze_project_with_qwen as analyze_project
from generator import generate_readme_rag

def main():
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    output_path = os.path.join(project_path, "README.md")

    project_data = analyze_project(project_path)
    generate_readme_rag(project_data, output_path)

if __name__ == "__main__":
    main()
