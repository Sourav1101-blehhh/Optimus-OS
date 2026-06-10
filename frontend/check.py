import re
with open('app.js', encoding='utf-8') as f:
    code = f.read()
# strip strings and comments
code = re.sub(r'//.*|/\*[\s\S]*?\*/|`(?:[^`\\]|\\.)*`|\'(?:[^\'\\]|\\.)*\'|"(?:[^"\\]|\\.)*"', '', code)
open_braces = code.count('{')
close_braces = code.count('}')
print('open:', open_braces, 'close:', close_braces)
if open_braces != close_braces:
    lines = code.split('\n')
    stack = []
    for i, line in enumerate(lines):
        for j, c in enumerate(line):
            if c == '{': stack.append((i+1, j+1))
            elif c == '}':
                if stack: stack.pop()
                else: print('Extra } at line', i+1)
    for loc in stack:
        print('Unclosed { at line', loc[0])
