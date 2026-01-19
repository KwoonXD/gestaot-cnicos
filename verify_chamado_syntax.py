import sys
import os

# Add the current directory to sys.path to ensure we can import 'src'
sys.path.insert(0, os.getcwd())

print("--- Attempting to import src.services.chamado_service ---")
try:
    from src.services.chamado_service import ChamadoService
    print("SUCCESS: ChamadoService imported successfully.")
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    print(f"File: {e.filename}, Line: {e.lineno}")
    print(f"Text: {e.text}")
except Exception as e:
    print(f"OTHER ERROR: {type(e).__name__}: {e}")
