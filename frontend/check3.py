import re
with open('app.js', encoding='utf-8') as f:
    code = f.read()
code = re.sub(r'//.*|/\*[\s\S]*?\*/|`(?:[^`\\]|\\.)*`|\'(?:[^\'\\]|\\.)*\'|"(?:[^"\\]|\\.)*"', '', code)
total = 0
for i, line in enumerate(code.split('\n')):
    for c in line:
        if c == '{': total += 1
        elif c == '}':
            total -= 1
            if total < 0:
                print('EXTRA } AT LINE', i+1, line.strip())
                exit()
print('END TOTAL:', total)
