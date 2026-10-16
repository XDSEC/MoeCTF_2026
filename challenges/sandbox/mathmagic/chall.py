import time

class Random:
    _P = 1000000021
    _A = 320560990
    _BASE = 123456789 % _P
    def __init__(self, seed=0):
        self.state = (self._BASE * pow(self._A, seed % 60, self._P)) % self._P

    def random(self, mod):
        self.state = (self.state * self._A) % self._P
        return self.state % mod + 1

def chall():
    MOD = 15
    seed = int(time.time())
    r = Random(seed)
    gift = [r.random(MOD) for _ in range(3)]
    print("Wlecome to the word of mathmagic!")
    print("I hope you like the puzzle I prepared for you.")
    print('I will give you a gift!')
    print('I hope you like it. Here is your gift:')
    print(gift)
    print("Now, I will give you the puzzle!")
    print("Have fun!")
    CODE = ''

    while code:=input('>> ').strip():
        if len(code) != r.random(MOD):
            raise ValueError("Invalid code length! You are not a genius!")
        CODE += code + '\n'
    print("Good job! You are a genius!")
    eval(CODE,{'__builtins__': {}})
