def chall():
    def check(code):
        if len(code) % 3:
            return False
        for i in range(0, len(code), 3):
            a,b,c = map(lambda x:ord(x) % 3 ,code[i:i+3])
            if len({a,b,c}) != 3:
                return False
        return code.isascii()

    inp = input('Give me your code:')
    if check(inp):
        print('Code Executed!')
        exec(inp)
    else :
        print('Not Accept')