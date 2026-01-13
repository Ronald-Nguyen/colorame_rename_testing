import os
import re
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from google import genai

# --- Konfiguration & API-Client ---
try:
    # Initialisiert den Client (erwartet GOOGLE_API_KEY in den Umgebungsvariablen)
    client = genai.Client()
    print("✓ Gemini API Key aus Umgebungsvariable geladen")
except Exception as e:
    print(f"✗ Fehler beim Laden des API-Keys: {e}")
    exit(1)

# --- Argumente ---
parser = argparse.ArgumentParser(description="Projektpfad angeben")
parser.add_argument("--project-path", type=str, default="colorama", help="Pfad des Projekts")
args = parser.parse_args()

PROJECT_DIR = Path(args.project_path)
RESULTS_DIR = Path("Ergebnisse")
RESULTS_DIR.mkdir(exist_ok=True)
# Prompt-Template für Rename
RENAME_PROMPT_TEMPLATE = """
Projektstruktur:
{project_structure}
    
Deine Aufgabe besteht darin, eine Refactoring-Änderung für ein Python-Projekt vorzunehmen. Es sollen eine Methode umbenannt werden. Die Umbenennung muss konsistent im gesamten Projekt umgesetzt werden, indem jede Instanz der Nutzung angepasst wird.

Beachte:
1. Der Code funktioniert nach der Umbenennung weiterhin korrekt.
2. Alle Importe und Funktionsaufrufe müssen ebenfalls angepasst werden.
3. Der Stil und die Struktur des Codes sollte beibehalten werden.

Hier sind Beispiele für andere Umbenennungsaufgaben:
Beispiel 1:
Original Code:
def calculate_sum(a, b):
    return a + b

print(calculate_sum(2, 3))

Nach der Umbenennung zu `add`:
def add(a, b):
    return a + b

print(add(2, 3))

---

Beispiel 2:
Original Code:
def find_maximum(numbers):
    return max(numbers)

result = find_maximum([1, 2, 3])

Nach der Umbenennung zu `get_max`:
def get_max(numbers):
    return max(numbers)

result = get_max([1, 2, 3])

---
Gesamtes Projekt:
{code_block}



Deine Aufgabe:
1. Benenne folgende Funktion: `isatty` in der Datei: `ansitowin32.py` in `is_terminal` um.
2. Passe jede relevante Stelle im gesamten Projekt an.

Ausgabe:
Antworte für JEDE geänderte Datei exakt in diesem Format: 

Datei `dateiname.py`:
```python
[Vollständiger Code der Datei]
"""

# --- Hilfsfunktionen ---

def get_project_structure(project_dir: Path) -> str:
    """Erstellt eine Übersicht der Projektstruktur."""
    structure = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'pycache']
        level = root.replace(str(project_dir), '').count(os.sep)
        indent = ' ' * 2 * level
        structure.append(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            if "test" in file:
                continue
            if file.endswith('.py'):
                structure.append(f'{subindent}{file}')
    return '\n'.join(structure)

def get_all_python_files(project_dir: Path) -> str:
    """Liest alle Python-Dateien ein und liefert einen großen Textblock."""
    code_block = ""
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'pycache']
        for file in files:
            if "test" in file:
                continue
            if file.endswith('.py'):
                file_path = Path(root) / file
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    relative_path = file_path.relative_to(project_dir)
                    code_block += f"\n{'='*60}\nDatei: {relative_path}\n{'='*60}\n"
                    code_block += content + "\n"
                except Exception as e:
                    print(f"Fehler beim Lesen von {file_path}: {e}")
    return code_block

def parse_ai_response(response_text: str) -> dict:
    """Parst die AI-Antwort und extrahiert Dateinamen und Code."""
    files = {}
    pattern = r"Datei\s+`([^`]+)`:\s*```python\s*(.*?)\s*```"
    matches = re.findall(pattern, response_text, re.DOTALL)
    for filename, code in matches:
        files[filename] = code.strip()
    return files

def backup_project(project_dir: Path, backup_dir: Path) -> None:
    """Erstellt ein Backup des Projekts."""
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    shutil.copytree(
        project_dir, backup_dir, 
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', 'test')
    )

def restore_project(backup_dir: Path, project_dir: Path) -> None:
    """Stellt das Projekt aus dem Backup wieder her."""
    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(backup_dir, project_dir)

def apply_changes(project_dir: Path, files: dict) -> None:
    """Wendet die Änderungen auf die Dateien an."""
    for filename, code in files.items():
        file_path = project_dir / filename
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)
            print(f" ✓ {filename} aktualisiert")
        except Exception as e:
            print(f" ✗ Fehler beim Schreiben von {filename}: {e}")

def run_pytest(project_dir: Path) -> dict:
    """Führt pytest aus und gibt das Ergebnis zurück."""
    try:
        result = subprocess.run(
            ['pytest', '-v', '--tb=short'], 
            cwd=project_dir, 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'stdout': '', 'stderr': 'Timeout', 'returncode': -1}
    except Exception as e:
        return {'success': False, 'stdout': '', 'stderr': str(e), 'returncode': -1}

def save_results(iteration: int, result_dir: Path, files: dict, test_result: dict, response_text: str) -> None:
    """Speichert die Ergebnisse einer Iteration."""
    result_dir.mkdir(parents=True, exist_ok=True)
    code_dir = result_dir / "code"
    code_dir.mkdir(exist_ok=True)
    for filename, code in files.items():
        file_path = code_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)

    with open(result_dir / "test_result.txt", 'w', encoding='utf-8') as f:
        f.write(f"Iteration {iteration}\nTimestamp: {datetime.now().isoformat()}\n")
        f.write(f"Success: {test_result['success']}\n")
        f.write("\n" + "="*60 + "\nSTDOUT:\n" + test_result['stdout'])
        f.write("\n" + "="*60 + "\nSTDERR:\n" + test_result['stderr'])

    with open(result_dir / "ai_response.txt", 'w', encoding='utf-8') as f:
        f.write(response_text)

# --- Hauptprogramm ---

def main():
    # HIER DEINEN PROMPT DEFINIEREN ODER LADEN
    YOUR_PROMPT = RENAME_PROMPT_TEMPLATE

    print(f"{'='*60}\nStarte Refactoring-Experiment\n{'='*60}\n")

    backup_dir = Path("backup_original")
    backup_project(PROJECT_DIR, backup_dir)

    project_structure = get_project_structure(PROJECT_DIR)
    code_block = get_all_python_files(PROJECT_DIR)

    # Zusammenbau des finalen Prompts für die API
    final_prompt = f"{YOUR_PROMPT}\n\nStruktur:\n{project_structure}\n\nCode:\n{code_block}"

    successful_iterations = 0
    failed_iterations = 0

    for i in range(1, 2):
        print(f"\nITERATION {i}/1")
        restore_project(backup_dir, PROJECT_DIR)

        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=final_prompt
            )
            
            response_text = getattr(response, "text", None)
            if not response_text and hasattr(response, "candidates"):
                parts = [p.text for c in response.candidates for p in c.content.parts if hasattr(p, "text")]
                response_text = "\n".join(parts)
            
            if not response_text:
                raise ValueError("Leere Antwort erhalten")

            files = parse_ai_response(response_text)
            if not files:
                failed_iterations += 1
                continue

            apply_changes(PROJECT_DIR, files)
            test_result = run_pytest(PROJECT_DIR)

            if test_result['success']:
                successful_iterations += 1
            else:
                failed_iterations += 1

            save_results(i, RESULTS_DIR / f"iteration_{i:02d}", files, test_result, response_text)

        except Exception as e:
            print(f"Fehler: {e}")
            failed_iterations += 1

    print(f"\nFertig. Erfolgsrate: {successful_iterations/1*100:.1f}%")
    restore_project(backup_dir, PROJECT_DIR)

if __name__ == "__main__":
    main()