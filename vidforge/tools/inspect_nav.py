import re

with open(r'd:\rea-projects\projects\01-generadorVideos\analisis\extracted_app\frontend\dist\assets\index-CFQRu9Eb.js', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Look for navigation labels like 'Prompts', 'Multimedia', 'Audios', 'Sync', 'Studio', etc.
matches = re.findall(r'"([^"\\]{3,30})"', content)
keywords = ['prompt', 'audio', 'multimedia', 'studio', 'sync', 'archivo', 'ajuste', 'configur', 'producc', 'director', 'srt']
filtered = [m for m in matches if any(k in m.lower() for k in keywords)]
print('Filtered candidates:', set(filtered[:60]))
