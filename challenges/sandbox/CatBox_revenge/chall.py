class Cat:
    pass

def chall():
    print('Let\'s play with a cute cat!')
    cat = Cat()
    safe_globals = {
        '__builtins__': {},
        'cat' : cat,
    }

    blacklist = {
        '__' : 'double underline',
        '\'' : 'single quote',
        '"' : 'double quote',
        '\\' : 'backslash',
        ' ' : 'space',
        '(' : 'paren',
        ')' : 'paren',
    }
    while True:
        try:
            action = input('Action: ')
            if action == 'exit':
                print('Goodbye')
                break

            forbidden = next((b for b in blacklist if b in action), None)
            if forbidden is not None:
                print(f'Sorry, that\'s not a valid character: {blacklist[forbidden]}')
                continue
            eval(action, safe_globals)
        except Exception as e:
            print(e)
            print(f'{type(e).__name__}: {str(e)}')