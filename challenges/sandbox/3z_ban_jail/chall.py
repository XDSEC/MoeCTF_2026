import re

def chall():
    code = input('Give me your code: ')

    if re.search(r'[a-zA-Z0-9]',code):
        print('Letters and numbers are not allowed')
        return
    exec(code)