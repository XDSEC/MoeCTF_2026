服务器突然涌入了大量的并发请求！而且每个请求体里，都只带了一小段零碎的字符串。  
运维人员抓包后发现，这些字符串似乎是某个重要机密（Flag）的碎片。它们没有序号、没有偏移量，顺序完全是乱的。  
你能写一个高性能的服务，接住这些高并发请求，并把完整的 Flag 拼凑出来吗？

你需要做什么？

- SSH 登录到题目提供的容器。
- 写一个监听在 3000 端口的 Web 服务。
- 接收请求体中的碎片（机器人会把碎片作为 plain text 放在 post body 中）。
- 积累一定数量的碎片后，运行你的“最短公共超串”算法，打印出完整的 Flag。
- 注意： 机器人发送频率比较高，如果你的服务处理太慢（比如每次请求都重新算一遍超串），服务可能会被打爆的哦！建议先收集，再计算。

服务器 ssh 账号`moectf`，密码`moectf`。服务器没有 Vim、Nano 这类文本编辑器，请在本地写好代码后学习用 scp 命令上传。

> **scp 命令的使用方法**
> 
> 如果你要将文件夹下的 Python 文件传到服务器的家目录，可以参考这样的命令。（22 换成具体的 ssh 端口）关于命令的更多介绍，详见 [Linux scp 命令](https://www.runoob.com/linux/linux-comm-scp.html)。
> 
> ```powershell
> scp -P 22 wp.py moectf@127.0.0.1:/home/moectf/
> ```

**你也可以不用编程，另辟蹊径，发挥聪明才智。怎么做呢？我发现了一种做法，可惜这里空间太小，写不下……**

## Re：从零开始的编程之旅

> 这一题对于刚进大一的你来说比较有挑战性，我们会尽力指引你克服困难。本题一改再改，难度一降再降。但帮助你克服困难不代表把路上的坑坑洼洼都填平，这无异于直接告诉你答案。自己从网上、人工智能找到答案是一种需要培养的能力。当然，山穷水尽之时，定当出手相助。

众所周知，这个世界上有很多种编程语言。又众所周知，编程语言大致分为低级编程语言和高级编程语言，其中，Python 属于高级编程语言。在 Misc 方向入门指北中，xing 大佬提到要学习一门编程语言，而且是学啥呢？Python！那我们的编程旅程就从 Python 开始吧。你可以从 [Python Releases for Windows](https://www.python.org/downloads/windows/) 下载并安装 Python，然后阅读 [Python 基础教程](https://www.runoob.com/python/python-tutorial.html)一步一步学习 Python，了解 Python 的数据类型、运算、流程控制，阅读完基础教程之后你就具备读懂后面框架文档的基础。

在 Python 中，我们可以直接使用`requests`、`re`这种库，而不用考虑它们提供的函数、对象的底层实现，更不用考虑 Python 是怎么解释成 C++，怎么进一步编译成二进制文件让计算机运行的。我们在需要进行 HTTP GET 请求的时候只要执行`requests.get()`就好了，不用考虑怎么打开连接、握手这些细节。你可以把它看成一种封装，函数看成一台封装好的机器。你只需要考虑输入和输出，不需要考虑内部细节。这给我们带来了很大的便利。

这跟我们这道题有什么关系呢？我们只需要了解一些函数的用法，通过**组装**就可以把一个东西实现出来。

这里给出 SCS 贪心算法在 Python 中封装好的函数，该函数的输入为碎片组成的列表，返回拼接好的字符串。

> **什么是字符串？**
> 
> Python 当中有很多数据类型，比如整数、浮点数、字符串、函数、元组、列表、字典等等。字符串，字面意义理解就是字符组成的“串”。举个例子，`moectf`就是由 m、o、e、c、t、f 六个字符组成的一个串。串是数据结构的类型之一，字符串在 C 语言中的处理是一个字符数组。

> **如何安装 Python 并安装好依赖？**
> 
> 安装 Python 的方法请查阅其他方向的入门指北，或者在网上搜集相关资料，在此不赘述。
> 
> 关于依赖管理，如果需要下载并安装`flask`包，请在命令行执行`pip install flask`，在 Python 代码中添加`import flask`即可。导入依赖的不同方式详见 [Python import 和 from … import 的主要区别](https://www.runoob.com/w3cnote/python-import-and-from-import.html)。

> **贪心算法是什么？**
> 
> 程序 = 数据结构 + 算法，算法是程序解决问题的方法。贪心算法的基本思想是：总是做出在当前看来是最好的选择，即贪心算法不从整体上考虑最优，而只考虑当前的局部最优。你会在《数据结构与算法分析》课程中了解常见的数据结构和算法。
> 
> SCS 贪心算法的计算步骤是：计算两两字符串之间的最大重叠长度，每次循环找出整个集合中**重叠度最高**的两个字符串，将它们合并，重复这一过程，直到集合中只剩下一个字符串。

```python
def solve_scs(fragments: list[str]) -> tuple[str, bool]:
    """
    Shortest Common Superstring solver.
    
    Args:
        fragments: 碎片列表（可含重复）
    Returns:
        (result, is_success)
        - result: 还原后的字符串
        - is_success: True = 贪心结果唯一可信；False = 存在歧义或碎片不连续
    """
    
    from itertools import permutations

    # 1. 去重 + 去冗余（被其他片段包含的直接丢弃）
    frags = list(dict.fromkeys(fragments))           # 去重，保序
    frags = [
        f for f in frags
        if not any(f in g for g in frags if g != f)
    ]

    if not frags:
        return ("", False)
    if len(frags) == 1:
        return (frags[0], True)

    # ── 内部工具 ──────────────────────────────────────────
    def max_overlap(a: str, b: str) -> int:
        """a 的后缀与 b 的前缀的最大重叠长度"""
        limit = min(len(a), len(b))
        for ol in range(limit, 0, -1):
            if a.endswith(b[:ol]):
                return ol
        return 0

    def greedy_merge(pool: list[str]) -> str:
        """标准贪心：每轮合并重叠最大的一对"""
        pool = pool[:]
        while len(pool) > 1:
            best_ol, bi, bj = -1, 0, 1
            for i in range(len(pool)):
                for j in range(len(pool)):
                    if i == j:
                        continue
                    ol = max_overlap(pool[i], pool[j])
                    if ol > best_ol:
                        best_ol, bi, bj = ol, i, j
            merged = pool[bi] + pool[bj][best_ol:]
            pool = [merged] + [pool[k] for k in range(len(pool)) if k not in (bi, bj)]
        return pool[0]

    # 2. 片段数量少时用精确暴力（≤8 个，8! = 40320，可接受）
    #    片段数量多时用贪心
    EXACT_THRESHOLD = 8

    if len(frags) <= EXACT_THRESHOLD:
        # 枚举所有排列，找真正最短的公共超串
        best: str | None = None
        for perm in permutations(frags):
            # 按排列顺序依次合并
            cur = perm[0]
            for nxt in perm[1:]:
                ol = max_overlap(cur, nxt)
                cur += nxt[ol:]
            if best is None or len(cur) < len(best):
                best = cur

        # 检查贪心结果是否与精确结果一致
        greedy_result = greedy_merge(frags)
        is_success = (greedy_result == best)
        return (best, is_success)     # type: ignore[return-value]

    else:
        # 片段太多，只跑贪心；用"所有片段都是结果子串"作为健全性检查
        result = greedy_merge(frags)
        is_success = all(f in result for f in frags)
        return (result, is_success)
```

**这段代码看起来很复杂，但我们并不想去读懂它。** 我们只需要把这段代码复制粘贴到我们自己的代码里面，然后用`solve_scs(["moe","ectf"])`去调用它就可以了。我们尝试执行一下。发现就这一行的代码量还是我们能解决的，这个函数的返回值是一个元组，元组的第一个值是拼接好的字符串，第二个值是表示是否成功的布尔值。为什么要返回布尔值呢？因为我们后面需要判断拼接 flag 成功了没有，而不是让函数硬拼接一个字符串给我们。

```python
>> print(solve_scs(["moe","ectf"]))
>> ('moectf', True)
```

我们应该如何用 Python 构建一个后端服务呢？我们先用 Flask 吧，毕竟这是一个比较好上手的库。下面给了一个框架，你只需要完成 3 个 TODO 即可。

参见：[Flask 教程 | 菜鸟教程](https://www.runoob.com/flask/flask-tutorial.html) [Flask 框架文档](https://flask.org.cn/en/stable/)

```python
# 提示：本文件需要你补充关键的 Web 接收与存储逻辑
import threading
from flask import Flask, request

app = Flask(__name__)

# 全局列表：用于存储机器人发来的碎片
fragments_list = []
# 互斥锁：用于保证高并发下列表读写安全，防止数据错乱
list_lock = threading.Lock()

# 触发拼接的碎片数量阈值，当收集到 100 个碎片时尝试拼接
THRESHOLD = 100

# SCS 贪心算法函数（请粘贴上方封装好的函数）
def solve_scs(fragments: list[str]) -> tuple[str, bool]:

# 路由处理（需要补全）
@app.route('/', methods=['POST'])
def handle():
    global fragments_list
    
    # -----------------------------------------------------------------
    # TODO 1: 获取请求体中的碎片
    # -----------------------------------------------------------------
    fragment = ""  # <- 请在这里实现你的代码
    
    if not fragment:
        return "Empty Fragment", 400

    # 引入锁机制，确保并发安全
    with list_lock:
        # -------------------------------------------------------------
        # TODO 2: 将获取到的碎片追加到全局列表 `fragments_list` 中
        # -------------------------------------------------------------
        pass  # <- 请在这里实现你的代码
        
        # -------------------------------------------------------------
        # TODO 3: 判断碎片数量是否达到了预设的阈值 THRESHOLD
        # 如果达到了，复制一份列表，调用上面的 solve_scs 函数尝试拼接。
        # 如果拼接成功（即返回的布尔值为 True），请在控制台打印出完整的 Flag！
        # -------------------------------------------------------------
        # <- 请在这里实现你的条件判断与函数调用逻辑
        
    return "OK"

if __name__ == '__main__':
    # 监听 3000 端口，threaded=True 开启多线程支持高并发
    app.run(host='0.0.0.0', port=3000, threaded=True)
```

敲完代码之后执行 Python 代码即可部署你的服务。使用完 Flask 之后，你可以尝试其他框架，比如 [Fastapi](https://fastapi.tiangolo.com/zh/) 等，并尝试去优化你写的这个服务。Python 的列表并不是并发安全的，如果有两个请求同时写列表会发生什么？你可以尝试查阅选课系统、抢票系统是怎么防止超选、超卖的。我们一起进步！