def chall():
    blacklist = ['os','exec','eval','import','system']
    code = input('Give me your code: ')
    for b in blacklist:
        if b in code:
            print(f'Blacklist word: {b}')
            return
    exec(code)