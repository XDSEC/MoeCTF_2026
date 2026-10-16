import ast

def chall():
    def filter(code):
        if len(code) > 50:
            print(f'Too long! Your code length is {len(code)} characters.')
            return False
        tree = ast.parse(code,mode='eval')
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                print('Bad Call!')
                return False
        return True

    inp = input('Give me your code: ')
    if filter(inp):
        print('\nCode Accepted!')
        try:
            print(eval(inp))
        except Exception as e:
            print(e)