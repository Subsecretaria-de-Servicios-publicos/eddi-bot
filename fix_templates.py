import os
import re

PROJECT_DIR = "app"  # ajustá si hace falta

pattern = re.compile(r"TemplateResponse\s*\((.*?)\)", re.DOTALL)

def fix_signature(args_str):
    args = args_str.strip()

    # Si ya está bien (empieza con request), no tocar
    if args.startswith("request"):
        return None

    # Separar argumentos (naive pero funciona para este caso)
    parts = [p.strip() for p in args.split(",", 1)]

    if len(parts) < 2:
        return None

    template = parts[0]
    rest = parts[1]

    # Construir nueva firma
    fixed = f"request, {template}, {rest}"
    return fixed


def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    def replacer(match):
        nonlocal modified
        args = match.group(1)

        fixed_args = fix_signature(args)
        if fixed_args:
            modified = True
            print(f"🔧 Fix en {filepath}")
            return f"TemplateResponse({fixed_args})"

        return match.group(0)

    new_content = pattern.sub(replacer, content)

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

    return modified


def main():
    total = 0

    for root, _, files in os.walk(PROJECT_DIR):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if process_file(filepath):
                    total += 1

    if total == 0:
        print("✅ Nada para corregir")
    else:
        print(f"\n🚀 Archivos corregidos: {total}")


if __name__ == "__main__":
    main()

