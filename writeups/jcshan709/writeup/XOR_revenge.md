# XOR_revenge

> 本题知识点：  
> :star::star::star: ​使用矩阵递推数列  
> :star::star::star: ​矩阵快速幂
>
> 综合难度： :star::star::star:

## 代码分析

先看源代码：

```python
from Crypto.Util.number import long_to_bytes

flag = b'moectf{???}'

# just a normal big prime
M = 2**521 - 1

COEFF = [3, 5, 7, 11, 13, 17, 36]
INIT  = [1, 2, 3, 4, 5, 6, 7]

def gen_key(n):
    f = INIT[:]
    if n < 7:
        return f[n]
    for _ in range(7, n + 1):
        nxt = sum(COEFF[j] * f[6 - j] for j in range(7)) % M
        f = f[1:] + [nxt]
    return f[6]

n = 10**25
key = gen_key(n)
enc = bytes([x ^ y for x, y in zip(flag, long_to_bytes(key))])
# b'lz\xb0T\xeb\x18\xec\xcfQ\x8bv#\x17t\xf0\xc7\xdaM\x87\xf5sr\xef\xd0\xfc3.\xdc%\xaaf\xf4\xd1\xc8\xb7\xef'
```

定义了两个数组 `COEFF` 和 `INIT`，  
之后使用 `gen_key` 来生成 `key`，  
最后用 `key` 进行 XOR 流加密得到密文。

我们知道，对于 XOR 流加密，只需要将密文再做一次加密，就可以得到明文。

因此我们的目标就是：算出 `key`。

## 最初的想法

生成 `key` 的过程已经给出，你大概会想：  
「诶，那我直接跑一遍不就有了吗？」  
可惜，这题行不通！

本题的 $n = 10^{25}$，如今的 CPU 的**单核**主频数量级在 **1GHz**，即每秒执行 $1 \times 10^9$ （十亿）次运算。  
用以上数据粗略估计，算出 `key` 大约要 $10^{16}$ 秒。等 `key` 算出来的时候都不知道办过多少届 MoeCTF 了......

因此，我们必须采取**更快的算法**。

## 矩阵递推

分析一下 `gen_key`，可以发现这其实是一个数列递推过程。

将列表 `f` 表示成一个数列 $a_n$，那么可以得到：

$$
a_n = \left\lbrace
\begin{aligned}
INIT[n] & , & 0 \le n \lt 7 \\
f(n) & , & n \ge 7
\end{aligned}
\right.
$$

其中，

$$
f(n) = 3a_{n-1} + 5a_{n-2} + 7a_{n-3} + 11a_{n-4} + 13a_{n-5} + 17a_{n-6} + 36a_{n-7}
$$

这便是递推式。

我们都知道，通过左乘矩阵可以实现向量的线性变换，即：

$$
\boldsymbol y = f(\boldsymbol x) = \boldsymbol{Ax}
$$

（此处 $\boldsymbol x, \boldsymbol y$ 维度相等）  

假设我们现在有一个向量

$$
\boldsymbol v_n = \left[
\begin{matrix}
a_{n+6} & a_{n+5} & a_{n+4} & a_{n+3} & a_{n+2} & a_{n+1} & a_n
\end{matrix}
\right]^\top
$$

那么，我们能否找到一个矩阵 $\boldsymbol A$，使得 $\boldsymbol{Av_n} = \boldsymbol{v_{n+1}}$ 呢？  
当然可以！这本质上就是一个线性方程组，自然可以写成这种形式！

列方程的过程我就省略了，这里直接贴结果吧。

$$
\boldsymbol A = \left[
\begin{matrix}
3 & 5 & 7 & 11 & 13 & 17 & 36 \\
1 \\
& 1 \\
&& 1 \\
&&& 1 \\
&&&& 1 \\
&&&&& 1 \\
\end{matrix}
\right]
$$

别忘了验算一下噢！

这样，我们就可以得到 $\boldsymbol{v_n} = \boldsymbol A^n \boldsymbol{v_0}$，接下来只要算出 $\boldsymbol A^n$ 即可。

## 快速幂

如果让你求 $x^n\ (n \in \mathbb N)$ ，你会怎么办？  
直接循环 $n$ 次累乘？这是最普通的办法，时间复杂度为 $O(n)$。

我们不妨将 $x^n$ 拆开，如：

$$
x^{13} = x^8 \cdot x^4 \cdot x
$$

将 $n$ **二进制划分**，即 $13 = (1101)_2$，从最低位向高位依次迭代，同时底数乘以自身，若当前位为 1，则乘上底数。

这么讲可能不够明白，让我们带上例子：

$$
13 = (1101)_2
$$

|迭代次数|当前位|底数|结果|
|-|-|-|-|
|1|1|$x$|$x$|
|2|0|$x^2$|$x$|
|3|1|$x^4$|$x^5$|
|4|1|$x^8$|$x^{13}$|

这样，我们就把 $O(n)$ 级的运算化为了 $O(log\ n)$ 级的运算！  
$10^{25}$ 量级的运算最终就被我们化成了 $25 \log 10$ 级的运算！

## 矩阵快速幂

矩阵快速幂本质上和标量的快速幂是一样的，只不过还要算上矩阵乘法的开销。

有了以上知识，我们不难写出一套快速幂算法：

```python
# 快速计算 a**exp % mod 的结果
# 这里 exp 和 mod 必须是整数
def quick_pow(a, exp: int, mod: int):
    ans = 1
    while exp:
        if exp & 1:
            ans = ans * a % mod
        a = a * a % mod
        exp >>= 1
    return ans
```

## 解出 flag

打开 python，进行计算即可：

```python
from Crypto.Util.number import *
from sage.all import *

def quick_pow(a, exp: int, mod: int):
    ans = 1
    while exp:
        if exp & 1:
            ans = ans * a % mod
        a = a * a % mod
        exp >>= 1
    return ans

A = matrix(7, 7)
A.set_row(0, [3, 5, 7, 11, 13, 17, 36])
for i in range(6):
    A[i+1,i] = 1

v = vector([*range(7, 0, -1)])
n = 10**25
M = 2**521 - 1
enc = b'lz\xb0T\xeb\x18\xec\xcfQ\x8bv#\x17t\xf0\xc7\xdaM\x87\xf5sr\xef\xd0\xfc3.\xdc%\xaaf\xf4\xd1\xc8\xb7\xef'

ans = quick_pow(A, n, M) * v % M
key = ans[6]
flag = bytes([x ^ y for x, y in zip(enc, long_to_bytes(key))])

print(flag.decode())
```


    moectf{m4tr1x_p0w3r_1s_4ll_y0u_n33d}


拿下 flag！
