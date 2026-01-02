import os
import py_compile

def check_syntax(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    py_compile.compile(path, doraise=True)
                    print(f"OK: {path}")
                except py_compile.PyCompileError as e:
                    print(f"ERROR in {path}:")
                    print(e)
                except Exception as e:
                    print(f"EXCEPTION in {path}: {e}")

if __name__ == "__main__":
    check_syntax("src")
    check_syntax(".")
