def chall():
    import string
    items = {
        string.ascii_lowercase : 'lowers',
        string.ascii_uppercase : 'uppers',
        string.digits : 'digits',
        '()[]{}' : 'parens',
        '+-*/=' : 'operators'
    }

    user_input = input('Give me your shopping list: ')
    def check(list):
        count = 0
        items_list = ''.join(items.keys())
        for c in list:
            if c not in items_list:
                return False,f'Refuse! Bad item : {c}'

        for s in items:
            cost = sum(list.find(c) != -1 for c in s)
            if cost > 4:
                return False,f'Refuse! {items[s]} limited! '
            count += (cost != 0 )

        if count > 3 or len(set(list)) > 11:
            return False,'Refuse! Overstep the budget! '

        return True,'Shopping successfully! '


    res = check(user_input)
    if res[0]:
        print(res[1] + f'Result: {eval(user_input,globals())}')
    else:
        print(res[1])
