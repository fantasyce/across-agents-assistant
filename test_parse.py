import json

with open('/Applications/TRAE SOLO.app/Contents/Resources/app/extensions/theme-seti/icons/icube-seti-icon-theme.json', 'r') as f:
    data = json.load(f)

icon_defs = data.get('iconDefinitions', {})

# Find elements with iconPath
count = 0
for k, v in icon_defs.items():
    if 'iconPath' in v:
        print("Found iconPath:", k, v)
        count += 1
        if count > 5:
            break
