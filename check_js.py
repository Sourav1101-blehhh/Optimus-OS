import re
from collections import Counter

with open('frontend/app.js', encoding='utf-8', errors='replace') as f:
    content = f.read()
    lines = content.splitlines()

# Top-level let/const declarations
top_lets = []
for i, line in enumerate(lines, 1):
    if re.match(r'^(let|const)\s+\w+', line):
        m = re.match(r'^(let|const)\s+(\w+)', line)
        if m:
            top_lets.append((i, m.group(1), m.group(2)))

names = [x[2] for x in top_lets]
dupes = {k for k, v in Counter(names).items() if v > 1}
if dupes:
    print('DUPLICATE TOP-LEVEL VARS:', dupes)
    for i, kind, name in top_lets:
        if name in dupes:
            print(f'  Line {i}: {kind} {name}')
else:
    print('No duplicate top-level vars.')

# col-c and canvas
print()
for i, line in enumerate(lines, 1):
    if 'col-c' in line or 'cognitive-canvas' in line:
        print(f'Line {i}: {line.strip()[:100]}')

# connectSocket call
print()
for i, line in enumerate(lines, 1):
    if 'connectSocket()' in line and 'function' not in line and 'setTimeout' not in line:
        print(f'connectSocket() called at line {i}: {line.strip()}')

# textInput declared
print()
for i, line in enumerate(lines, 1):
    if re.match(r'^const textInput', line) or re.match(r'^let textInput', line):
        print(f'textInput declared at line {i}: {line.strip()}')

# The keydown listener uses textInput - check order
print()
for i, line in enumerate(lines, 1):
    if 'keydown' in line:
        print(f'keydown at line {i}: {line.strip()[:80]}')
