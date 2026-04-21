import os
import json
import re

ICON_DIR = "/Users/fanhcy/Documents/projects/across-agents-assistant/src/across_agents_assistant/assets/icons"
OUTPUT_FILE = "/Users/fanhcy/Documents/projects/across-agents-assistant/src/across_agents_assistant/file_icons.py"

icons = {}
for filename in os.listdir(ICON_DIR):
    if not filename.endswith(".svg"):
        continue
    
    # Extract the meaningful part of the name
    # e.g., icon.14.explorer.lang.python.svg -> python
    # e.g., icon.14.explorer.type.markdown.svg -> markdown
    match = re.search(r'icon\.14\.explorer\.(?:lang|type|file)\.(.+?)\.svg$', filename)
    if match:
        key = match.group(1)
        with open(os.path.join(ICON_DIR, filename), 'r', encoding='utf-8') as f:
            content = f.read().strip()
            # Clean up the SVG a bit to make it inline-friendly
            content = re.sub(r'xmlns=".*?"', '', content)
            content = re.sub(r'\s+', ' ', content)
            icons[key] = content

# Write to a Python file
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("# Auto-extracted Trae Solo file icons\n")
    f.write("FILE_ICONS = {\n")
    for key, svg in sorted(icons.items()):
        # Handle special keys like c# or c++
        safe_key = key.replace('c#', 'csharp').replace('c++', 'cpp').replace('.', '_')
        f.write(f"    '{safe_key}': '{svg}',\n")
    f.write("}\n")

print(f"Extracted {len(icons)} icons to {OUTPUT_FILE}")
