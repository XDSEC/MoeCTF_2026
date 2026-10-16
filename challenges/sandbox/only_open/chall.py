def chall():
    safe_globals={
        'open':open,
        '__builtins__' : {}
    }

    blacklist = ['_','.','\\']
    while True:
        try:
            message = input('Give me your code: ').encode('ascii').decode('ascii')
            if any(b in blacklist for b in message):
                raise RuntimeError('Can\'t input any characters in blacklist')
            eval(message,safe_globals)
        except Exception as e:
            print(f'{type(e).__name__} : {e}')
