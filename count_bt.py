import re

with open('frontend/app.js', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Remove single-line comments
content_nc = re.sub(r'//[^\n]*', '', content)
# Remove double-quoted strings
content_ns = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content_nc)
# Remove single-quoted strings  
content_ns = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content_ns)
# Remove regex literals (basic)
content_ns = re.sub(r'/(?:[^/\\\n]|\\.)+/[gimsuy]*', '///', content_ns)

BACKTICK = chr(96)
bt = content_ns.count(BACKTICK)
print(f'Backticks outside strings/regexes: {bt} (even={bt%2==0})')

lines = content_ns.split('\n')
for i, line in enumerate(lines, 1):
    if BACKTICK in line:
        print(f'Line {i}: {repr(line[:120])}')
