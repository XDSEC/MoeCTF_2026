def chall():
    user_input = input('Give me your code:')
    s = sum(ord(c) for c in user_input)
    if s == len(user_input) ** 2:
        exec(user_input)
    else:
        print('Not Equal')

