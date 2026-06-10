import re
with open('app.js', encoding='utf-8') as f: code = f.read()
code = re.sub(r'//.*|/\*[\s\S]*?\*/|`(?:[^`\\]|\\.)*`|\'(?:[^\'\\]|\\.)*\'|"(?:[^"\\]|\\.)*"', '', code)
total = 0
for i, line in enumerate(code.split('\n')):
    c = line.count('{') - line.count('}')
    total += c
    print(i+1, 'diff:', c, 'total:', total, 'line:', line.strip())
    if total < 0: exit()
