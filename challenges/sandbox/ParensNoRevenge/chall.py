import types

def chall():
    safe_modules = types.ModuleType('starwalking')
    safe_globals = {'__builtins__':safe_modules}
    code = ''
    while s:= input('> ').strip():
        code += s + '\n'
    parens = '()[]{}'
    if any(c in parens for c in code):
        print('Hacker!')
        return
    try:
        exec(code,safe_globals)
    except Exception as e:
        print(e)
