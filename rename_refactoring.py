import openai
import subprocess
from pathlib import Path
import os
import argparse

# Funktion zum Laden des API-Schlüssels aus einer Textdatei
def load_api_key_from_file(file_path):
    if not Path(file_path).exists():
        raise FileNotFoundError(f"Die Datei {file_path} existiert nicht. Bitte füge deinen OpenAI-API-Schlüssel hinzu.")
    with open(file_path, "r", encoding="utf-8") as file:
        api_key = file.read().strip()  # Entfernt unnötige Leerzeichen/Zeilen
    if not api_key:
        raise ValueError(f"Die Datei {file_path} ist leer. Bitte füge deinen OpenAI-API-Schlüssel hinzu.")
    return api_key

# Pfad zur API-Schlüssel-Datei
API_KEY_FILE = "C:\\Users\\ronal\\colorame_rename_testing\\open_api_key.txt"  # Erstelle eine Datei mit diesem Namen und speichere darin deinen Schlüssel

# OpenAI API-Schlüssel laden
try:
    openai.api_key = load_api_key_from_file(API_KEY_FILE)
    print("API Key loaded: Yes")
except (FileNotFoundError, ValueError) as e:
    print(f"Fehler beim Laden des API-Schlüssels: {e}")
    openai.api_key = None

# Argumente für Projektpfad hinzufügen
parser = argparse.ArgumentParser(description="Projektpfad angeben")
parser.add_argument("--project-path", type=str, default="colorama", help="Pfad des Projekts")
args = parser.parse_args()

# Projektpfad
PROJECT_DIR = Path(args.project_path)

# Prompt-Template
PROMPT_TEMPLATE = """
Projektstruktur:
- colorama/
    |- ansi.py
    |- initialise.py
    |- utils.py
    |- win32.py
    |- winterm.py

Deine Aufgabe besteht darin, die folgenden Funktionen umzubenennen:
{tasks}

Passe jede Referenz im Code an, einschließlich:
- Alle Aufrufe der Funktionen,
- Import-Anweisungen,

Qualitätssicherung und Konsistenz:
- Stelle sicher, dass der Code nach der Namensänderung korrekt bleibt.
- Die Funktionslogik darf nicht unverändert werden.
- Der restliche Code und die Kommentare sollen im Stil unverändert bleiben.

Ausgabe: 
- Bitte liefere den vollständigen Code für jede Datei zurück, in der eine Änderung vorgenommen wurde. Markiere deutlich, welche Datei gerade angezeigt wird.
"""

# Funktion: Lese relevante Projektdateien
def load_project_code():
    code_segments = []
    for file in PROJECT_DIR.rglob("*.py"):
        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
                code_segments.append(f"Datei `{file.relative_to(PROJECT_DIR)}`:\n{f.read()}")
    return "\n\n".join(code_segments)

# API-Aufruf für Refactoring
def refactor_with_llm(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return response["choices"][0]["message"]["content"]
    except openai.error.OpenAIError as e:
        print(f"Fehler bei der GPT-4-Anfrage: {e}")
        return None

# Speichere Dateien
def save_refactored_code(refactored_code):
    try:
        current_file = None
        for line in refactored_code.splitlines():
            if line.startswith("Datei `"):
                if current_file:
                    current_file.close()
                file_name = line.split("`")[1]
                current_file = open(PROJECT_DIR / file_name, "w", encoding="utf-8")
            elif current_file:
                current_file.write(line + "\n")
        if current_file:
            current_file.close()
    except Exception as e:
        print(f"Fehler beim Speichern: {e}")

# Tests
def run_tests():
    result = subprocess.run(["pytest"], cwd=PROJECT_DIR, capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)
    return result.returncode == 0

# Automatisierung
def automate_refactoring_and_validation(tasks, runs=10):
    for i in range(1, runs + 1):
        print(f"\n==== Refactoring, Durchlauf {i} ====\n")
        project_code = load_project_code()
        prompt = PROMPT_TEMPLATE.format(tasks=tasks)
        refactored_code = refactor_with_llm(prompt)
        if refactored_code:
            save_refactored_code(refactored_code)
            if run_tests():
                print(f"Durchlauf {i}: Erfolg!")
            else:
                print(f"Durchlauf {i}: Fehler erkannt.")

# Hauptprogramm
if __name__ == "__main__":
    task_description = """
1. Benenne aus der Datei: `colorama/ansitowin32.py` und der Klasse: `AnsiToWin32` die Funktion: `reset_all` in `reset_console` um.
    """
    automate_refactoring_and_validation(task_description)