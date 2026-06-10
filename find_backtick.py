with open('frontend/app.js', encoding='utf-8', errors='replace') as f:
    content = f.read()

BACKTICK = chr(96)
total = content.count(BACKTICK)
print(f'Total backticks: {total} (even={total % 2 == 0})')

# Walk through finding unclosed template literals
# Simple greedy scan (ignores nested ${} but finds the broken one)
pos = 0
count = 0
while True:
    start = content.find(BACKTICK, pos)
    if start == -1:
        break
    count += 1
    end = content.find(BACKTICK, start + 1)
    if end == -1:
        line_no = content[:start].count('\n') + 1
        print(f'UNCLOSED template literal starts at char {start}, LINE {line_no}')
        print('Context:', repr(content[max(0,start-50):start+100]))
        break
    pos = end + 1

print(f'Closed pairs found: {count}')
