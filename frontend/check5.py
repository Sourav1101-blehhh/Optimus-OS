from pyjsparser import parse
import sys
code = open('app.js', encoding='utf-8').read()
code = code.replace('`', '\"')
try:
    parse(code)
    print('Syntax OK')
except Exception as e:
    import traceback
    traceback.print_exc()
