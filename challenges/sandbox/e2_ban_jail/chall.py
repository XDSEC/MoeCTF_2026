def chall():
    forbidden_chars = 'pyjail0123456789'
    code = input('Give me your code: ')
    for c in code:
        if c in forbidden_chars:
            print(f'Forbidden character: {c}')
            return
    exec(code)
