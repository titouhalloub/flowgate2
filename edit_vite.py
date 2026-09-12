import io
import os

path = 'vite.config.ts'
src = io.open(path, encoding='utf-8').read()
lines = src.splitlines()
# Insert base: '/static/', before the server: { line if not already present
if "base: '/static/'," not in src:
    i = lines.index('    server: {')
    lines.insert(i, "    base: '/static/',")
io.open(path, 'w', encoding='utf-8').write('\n'.join(lines))