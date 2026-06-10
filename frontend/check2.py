import re
with open('app.js', encoding='utf-8') as f:
    code = f.read()
code = re.sub(r'//.*|/\*[\s\S]*?\*/|`(?:[^`\\]|\\.)*`|\'(?:[^\'\\]|\\.)*\'|"(?:[^"\\]|\\.)*"', '', code)
for i, line in enumerate(code.split('\n')):
    c = line.count('{') - line.count('}')
    if c != 0:
        print(i+1, c)
