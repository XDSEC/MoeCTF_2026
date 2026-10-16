import types

def chall():
    safe_modules = types.ModuleType('starwalking')
    safe_globals = {'__builtins__':safe_modules}
    while True:
        code = ''
        while s:= input('> '):
            code += s + '\n'
        parens = '()[]{}'
        if any(c in parens for c in code):
            print('Hacker!')
            continue
        try:
            exec(code,safe_globals)
        except Exception as e:
            print(e)
