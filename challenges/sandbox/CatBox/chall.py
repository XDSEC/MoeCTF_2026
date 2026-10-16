class Cat:

    def __init__(self,name):
        self.name=name
        self.hunger = 50
        self.energy = 50
        self.feed_amount =20
        self.play_time = 20
        self.sleep_hours = 10

    @property
    def feed(self):
        amount = self.feed_amount
        self.hunger = max(0,self.hunger - amount)
        if self.hunger == 0:
            print(f'{self.name} if full and rolls over happily~')
        else:
            print(f'You fed {self.name}. Hunger Level: {self.hunger}')
        return None

    @property
    def play(self):
        time = self.play_time
        if self.energy >= time:
            self.energy -= time
            self.hunger = min(100,self.hunger + time * 2)
            print(f'You palyed {self.name} for {time} min!')
            if self.energy <= 20:
                print(f'{self.name} is a bit of tired')

        else :
            print(f'{self.name} is too tired to play.Let it slepp for a while')
        return None

    @property
    def sleep(self):
        hours = self.sleep_hours
        self.energy = min(100,self.energy + hours * 5)
        self.hunger = min(100,self.hunger + hours)
        print(f'{self.name} is sleeping for {hours} hours')
        return None

def chall():
    print('Let\'s play with a cute cat!')
    name = input('Give your kitten a name:')
    cat = Cat(name)
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
        '(' : 'left paren',
        ')' : 'right paren',
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