import re

with open('frontend/app.js', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Remove comments
content = re.sub(r'//[^\n]*', '', content)
content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

# Remove strings
content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)
content = re.sub(r'`(?:[^`\\]|\\.)*`', '``', content)

# Remove regexes
content = re.sub(r'/(?:[^/\\\n]|\\.)+/[gimsuy]*', '///', content)

depth = 0
for i, line in enumerate(content.split('\n'), 1):
    for ch in line:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                print(f"ERROR: Too many '}}' at line {i}")
                
print(f"Final depth: {depth}")
