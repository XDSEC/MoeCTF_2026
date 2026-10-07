import random
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

QUESTIONS = [
    {
        "id": 1,
        "question": "Python 中 len() 函数的作用是？",
        "options": [
            {"key": "A", "text": "返回字符串长度"},
            {"key": "B", "text": "返回列表长度"},
            {"key": "C", "text": "返回任意可迭代对象的长度"},
            {"key": "D", "text": "返回数字大小"},
        ],
        "answer": "C",
        "explanation": "len() 用于返回字符串、列表、元组、字典等任意可迭代对象的长度。",
    },
    {
        "id": 2,
        "question": "以下哪个不是 HTTP 请求方法？",
        "options": [
            {"key": "A", "text": "GET"},
            {"key": "B", "text": "POST"},
            {"key": "C", "text": "FETCH"},
            {"key": "D", "text": "DELETE"},
        ],
        "answer": "C",
        "explanation": "HTTP 标准方法包括 GET、POST、PUT、DELETE、PATCH、HEAD、OPTIONS 等，FETCH 是 JavaScript 的 API 名称，不是 HTTP 方法。",
    },
    {
        "id": 3,
        "question": "Docker 中 docker-compose up -d 的 -d 参数含义是？",
        "options": [
            {"key": "A", "text": "调试模式"},
            {"key": "B", "text": "后台运行（detached）"},
            {"key": "C", "text": "删除容器"},
            {"key": "D", "text": "指定 Dockerfile"},
        ],
        "answer": "B",
        "explanation": "-d 是 --detach 的缩写，表示在后台运行容器，不占用当前终端。",
    },
    {
        "id": 4,
        "question": "Git 中 git stash 的作用是？",
        "options": [
            {"key": "A", "text": "删除工作区的修改"},
            {"key": "B", "text": "暂存当前工作区的修改"},
            {"key": "C", "text": "创建一个新的分支"},
            {"key": "D", "text": "合并两个分支"},
        ],
        "answer": "B",
        "explanation": "git stash 将当前工作区和暂存区的未提交修改保存到一个栈中，使工作区变干净，之后可以用 git stash pop 恢复。",
    },
    {
        "id": 5,
        "question": "Linux 中哪个命令用于查看当前目录下的文件列表？",
        "options": [
            {"key": "A", "text": "cd"},
            {"key": "B", "text": "pwd"},
            {"key": "C", "text": "ls"},
            {"key": "D", "text": "cat"},
        ],
        "answer": "C",
        "explanation": "ls（list）用于列出当前目录下的文件和子目录。cd 切换目录，pwd 显示当前路径，cat 查看文件内容。",
    },
    {
        "id": 6,
        "question": "以下哪个数据库是关系型数据库？",
        "options": [
            {"key": "A", "text": "MongoDB"},
            {"key": "B", "text": "Redis"},
            {"key": "C", "text": "PostgreSQL"},
            {"key": "D", "text": "Cassandra"},
        ],
        "answer": "C",
        "explanation": "PostgreSQL 是关系型数据库，使用表和 SQL 查询。MongoDB 是文档型 NoSQL，Redis 是键值存储，Cassandra 是宽列 NoSQL。",
    },
    {
        "id": 7,
        "question": "CI/CD 中的 CI 代表什么？",
        "options": [
            {"key": "A", "text": "Computer Interface"},
            {"key": "B", "text": "Continuous Integration"},
            {"key": "C", "text": "Code Inspection"},
            {"key": "D", "text": "Common Infrastructure"},
        ],
        "answer": "B",
        "explanation": "CI 是 Continuous Integration（持续集成）的缩写，指开发人员频繁地将代码合并到主干，并自动运行构建和测试。",
    },
    {
        "id": 8,
        "question": "HTML 中哪个标签用于创建超链接？",
        "options": [
            {"key": "A", "text": "<link>"},
            {"key": "B", "text": "<a>"},
            {"key": "C", "text": "<href>"},
            {"key": "D", "text": "<url>"},
        ],
        "answer": "B",
        "explanation": "<a>（anchor）标签用于创建超链接。<link> 用于引入外部资源如样式表。",
    },
    {
        "id": 9,
        "question": "以下哪种是 Python 的包管理器？",
        "options": [
            {"key": "A", "text": "npm"},
            {"key": "B", "text": "pip"},
            {"key": "C", "text": "yarn"},
            {"key": "D", "text": "maven"},
        ],
        "answer": "B",
        "explanation": "pip 是 Python 的官方包管理器。npm 和 yarn 用于 JavaScript，maven 用于 Java。",
    },
    {
        "id": 10,
        "question": "西安电子科技大学南校区教学楼的编号从A到（ ）？",
        "options": [
            {"key": "A", "text": "D"},
            {"key": "B", "text": "F"},
            {"key": "C", "text": "G"},
            {"key": "D", "text": "H"},
        ],
        "answer": "C",
        "explanation": "通过地图搜索可以知道，从A教学楼到G教学楼哦。",
    },
    {
        "id": 11,
        "question": "SQL 中用于从表中选取数据的语句是？",
        "options": [
            {"key": "A", "text": "SELECT"},
            {"key": "B", "text": "GET"},
            {"key": "C", "text": "FETCH"},
            {"key": "D", "text": "EXTRACT"},
        ],
        "answer": "A",
        "explanation": "SQL 中使用 SELECT 语句查询数据：SELECT * FROM table_name。",
    },
    {
        "id": 12,
        "question": "以下关于 RESTful API 的说法，错误的是？",
        "options": [
            {"key": "A", "text": "使用 HTTP 方法表示操作类型"},
            {"key": "B", "text": "URL 中通常包含动词"},
            {"key": "C", "text": "无状态通信"},
            {"key": "D", "text": "资源通过 URL 定位"},
        ],
        "answer": "B",
        "explanation": "RESTful API 的 URL 中应使用名词表示资源（如 /users），动词由 HTTP 方法（GET/POST/PUT/DELETE）表达。",
    },
    {
        "id": 13,
        "question": "Python 中 with 语句主要用于？",
        "options": [
            {"key": "A", "text": "条件判断"},
            {"key": "B", "text": "循环控制"},
            {"key": "C", "text": "资源管理与上下文处理"},
            {"key": "D", "text": "异常处理"},
        ],
        "answer": "C",
        "explanation": "with 语句用于资源管理（如文件打开、锁获取），自动在代码块结束后释放资源，即使发生异常也会正确清理。",
    },
    {
        "id": 14,
        "question": "Nginx 的主要用途是？",
        "options": [
            {"key": "A", "text": "数据库管理"},
            {"key": "B", "text": "反向代理与 Web 服务器"},
            {"key": "C", "text": "容器编排"},
            {"key": "D", "text": "日志分析"},
        ],
        "answer": "B",
        "explanation": "Nginx 是一款高性能的 HTTP 服务器和反向代理服务器，常用于负载均衡、静态资源服务和反向代理。",
    },
    {
        "id": 15,
        "question": "HTTP 状态码 404 表示？",
        "options": [
            {"key": "A", "text": "服务器内部错误"},
            {"key": "B", "text": "资源未找到"},
            {"key": "C", "text": "请求成功"},
            {"key": "D", "text": "权限不足"},
        ],
        "answer": "B",
        "explanation": "404 Not Found 表示服务器无法找到请求的资源。200 表示成功，500 表示服务器内部错误，403 表示权限不足。",
    },
    {
        "id": 16,
        "question": "复旦大学邯郸校区 2024 年 6 月 13 日下午 3：30-5：30 王煜教授所作报告的题目为？",
        "options": [
            {"key": "A", "text": "变构激活 GRP120 治疗 AD"},
            {"key": "B", "text": "面对复杂海洋环境的鲁棒 OTFS 通感一体化"},
            {"key": "C", "text": "智能的边界：从人脑到大模型——人工智能如何改变我们对知识、学习、思维的理解"},
            {"key": "D", "text": "汉代墓葬中的天界表达"},
        ],
        "answer": "D",
        "explanation": "从复旦大学官网可找到 https://news.fudan.edu.cn/2024/0612/c248a141173/page.htm",
    },
    {
        "id": 17,
        "question": "以下哪项不是南京邮电大学的学院名称？",
        "options": [
            {"key": "A", "text": "通信与信息工程学院"},
            {"key": "B", "text": "人工智能学院"},
            {"key": "C", "text": "人文学院"},
            {"key": "D", "text": "经济学院"},
        ],
        "answer": "C",
        "explanation": "南京邮电大学内设教学机构 https://www.njupt.edu.cn/jxjg/list.htm",
    },
    {
        "id": 18,
        "question": "以下哪一个题词作者与其他三个不同？",
        "options": [
            {"key": "A", "text": "精心培育优秀人才努力攀登电子信息科学高峰"},
            {"key": "B", "text": "你们是科学的千里眼顺风耳"},
            {"key": "C", "text": "全心全意为人民服务"},
            {"key": "D", "text": "艰苦朴素"},
        ],
        "answer": "A",
        "explanation": "A项为 1996 年 2 月 18 日江泽民总书记为西安电子科技大学题词。",
    },
    {
        "id": 20,
        "question": "百度贴吧复旦大学吧的吧主是？",
        "options": [
            {"key": "A", "text": "rst"},
            {"key": "B", "text": "用户名是一款"},
            {"key": "C", "text": "昵称挂了"},
            {"key": "D", "text": "血魔小君"},
        ],
        "answer": "D",
        "explanation": "看百度贴吧。",
    },
    {
        "id": 21,
        "question": "以下哪个是 Linux 中强制删除目录及其子文件的命令？",
        "options": [
            {"key": "A", "text": "rm -r"},
            {"key": "B", "text": "rm -f"},
            {"key": "C", "text": "rm -rf"},
            {"key": "D", "text": "rm -d"},
        ],
        "answer": "C",
        "explanation": "rm -rf（recursive + force）递归强制删除目录及所有内容，使用时需格外谨慎。",
    },
    {
        "id": 22,
        "question": "JavaScript 中 typeof null 的返回值是？",
        "options": [
            {"key": "A", "text": "null"},
            {"key": "B", "text": "undefined"},
            {"key": "C", "text": "object"},
            {"key": "D", "text": "number"},
        ],
        "answer": "C",
        "explanation": "这是 JavaScript 的一个历史遗留 Bug，typeof null 返回 object，尽管 null 不是对象。",
    },
    {
        "id": 23,
        "question": "Python 中 is 和 == 的区别是？",
        "options": [
            {"key": "A", "text": "没有区别"},
            {"key": "B", "text": "is 比较值，== 比较身份"},
            {"key": "C", "text": "is 比较身份，== 比较值"},
            {"key": "D", "text": "is 只用于数字类型"},
        ],
        "answer": "C",
        "explanation": "== 比较两个对象的值是否相等，is 比较两个引用是否指向同一内存地址（身份标识）。",
    },
    {
        "id": 24,
        "question": "西安电子科技大学南校区两个综合楼共有几家蜜雪冰城？",
        "options": [
            {"key": "A", "text": "1"},
            {"key": "B", "text": "2"},
            {"key": "C", "text": "3"},
            {"key": "D", "text": "4"},
        ],
        "answer": "B",
        "explanation": "1家在老综，1家在新综。",
    },
    {
        "id": 25,
        "question": "以下哪个不是江南大学的内部道路？",
        "options": [
            {"key": "A", "text": "中央大道"},
            {"key": "B", "text": "内环南路"},
            {"key": "C", "text": "两江路"},
            {"key": "D", "text": "青山湾路"},
        ],
        "answer": "B",
        "explanation": "其他三个都是江南大学的内部道路。",
    },
    {
        "id": 26,
        "question": "忠诚、求实、勤奋、创新是以下哪所院校的校训？",
        "options": [
            {"key": "A", "text": "西安电子科技大学"},
            {"key": "B", "text": "南京邮电大学"},
            {"key": "C", "text": "江南大学"},
            {"key": "D", "text": "中国人民公安大学"},
        ],
        "answer": "D",
        "explanation": "https://www.ppsuc.edu.cn/xxgk/xxjj.htm",
    },
    {
        "id": 27,
        "question": "C 语言中，printf 函数用于？",
        "options": [
            {"key": "A", "text": "读取用户输入"},
            {"key": "B", "text": "格式化输出到标准输出"},
            {"key": "C", "text": "分配内存"},
            {"key": "D", "text": "打开文件"},
        ],
        "answer": "B",
        "explanation": "printf 是 C 语言标准库函数，用于格式化输出文本到控制台（stdout）。scanf 用于读取输入。",
    },
    {
        "id": 28,
        "question": "C 语言中，数组索引从几开始？",
        "options": [
            {"key": "A", "text": "0"},
            {"key": "B", "text": "1"},
            {"key": "C", "text": "由编译器决定"},
            {"key": "D", "text": "由操作系统决定"},
        ],
        "answer": "A",
        "explanation": "C 语言中数组索引从 0 开始，因此长度为 n 的数组有效索引范围是 0 到 n-1。",
    },
    {
        "id": 29,
        "question": "C 语言中，int moectf[5] = {1,2,3,4,5}; 访问 moectf[5] 会发生什么？",
        "options": [
            {"key": "A", "text": "返回 0"},
            {"key": "B", "text": "编译错误"},
            {"key": "C", "text": "越界访问（未定义行为）"},
            {"key": "D", "text": "自动扩展数组"},
        ],
        "answer": "C",
        "explanation": "C 语言不进行数组边界检查，访问 moectf[5] 越界，属于未定义行为（可能读到垃圾值或崩溃）。",
    },
    {
        "id": 30,
        "question": "Python 中，list(range(5)) 生成的序列是？",
        "options": [
            {"key": "A", "text": "[1, 2, 3, 4, 5]"},
            {"key": "B", "text": "[0, 1, 2, 3, 4]"},
            {"key": "C", "text": "(0, 1, 2, 3, 4)"},
            {"key": "D", "text": "{0, 1, 2, 3, 4}"},
        ],
        "answer": "B",
        "explanation": "list(range(5)) 返回从 0 到 4 的整数列表（左闭右开）。",
    },
    {
        "id": 31,
        "question": "以下选项中的图片隐写工具是？",
        "options": [
            {"key": "A", "text": "binwalk"},
            {"key": "B", "text": "steghide"},
            {"key": "C", "text": "strings"},
            {"key": "D", "text": "gdb"},
        ],
        "answer": "B",
        "explanation": "steghide 是常用的图片/音频隐写工具，可隐藏/提取数据。binwalk 用于分析固件和文件嵌入，strings 提取可打印字符串，gdb 是调试器。",
    },
    {
        "id": 32,
        "question": "维吉尼亚密码（Vigenère Cipher）中，用密钥 'HAPPY' 加密 'MOECTF'，第一个字母加密后是？",
        "options": [
            {"key": "A", "text": "R"},
            {"key": "B", "text": "M"},
            {"key": "C", "text": "T"},
            {"key": "D", "text": "S"},
        ],
        "answer": "C",
        "explanation": "M(12) + H(7) = 19 → T。",
    },
    {
        "id": 33,
        "question": "HTTP 协议中，GET 和 POST 请求的主要区别是？",
        "options": [
            {"key": "A", "text": "GET 有请求体，POST 没有"},
            {"key": "B", "text": "GET 参数在 URL 中，POST 参数在请求体中"},
            {"key": "C", "text": "POST 只能传输文本数据"},
            {"key": "D", "text": "GET 比 POST 更安全"},
        ],
        "answer": "B",
        "explanation": "GET 将参数附加在 URL 查询字符串中，POST 将参数放在请求体（body）中。GET 不应传输敏感数据，POST 也不一定安全。",
    },
    {
        "id": 34,
        "question": "以下哪个是典型的 SQL 注入攻击语句？",
        "options": [
            {"key": "A", "text": "'; DROP TABLE users; --"},
            {"key": "B", "text": "<script>alert('xss')</script>"},
            {"key": "C", "text": "../../../etc/passwd"},
            {"key": "D", "text": "http://moectf.example/steal"},
        ],
        "answer": "A",
        "explanation": "' ; DROP TABLE users; -- 是典型的 SQL 注入 payload，用于删除数据库表。",
    },
    {
        "id": 35,
        "question": "Cookie 和 Session 的区别是？",
        "options": [
            {"key": "A", "text": "Cookie 存储在服务器，Session 存储在客户端"},
            {"key": "B", "text": "Cookie 存储在客户端，Session 存储在服务器"},
            {"key": "C", "text": "两者都存储在客户端"},
            {"key": "D", "text": "两者都存储在服务器"},
        ],
        "answer": "B",
        "explanation": "Cookie 存储在浏览器端，Session 存储在服务器端。Session 通常通过 Cookie 中的 Session ID 来关联。",
    },
    {
        "id": 36,
        "question": "SQL 注入中，'1' OR '1'='1' 的作用是？",
        "options": [
            {"key": "A", "text": "使查询条件永远为真"},
            {"key": "B", "text": "使查询条件永远为假"},
            {"key": "C", "text": "报错显示数据库信息"},
            {"key": "D", "text": "延迟响应"},
        ],
        "answer": "A",
        "explanation": "'1'='1' 永远为真，可使 WHERE 条件绕过认证或返回所有数据。",
    },
    {
        "id": 37,
        "question": "以下哪个是文件包含漏洞的利用方式？",
        "options": [
            {"key": "A", "text": "/.git/config"},
            {"key": "B", "text": "?page=../../../../var/log/nginx/access.log"},
            {"key": "C", "text": "<script>alert(1)</script>"},
            {"key": "D", "text": "admin' --"},
        ],
        "answer": "B",
        "explanation": "B 是文件包含路径遍历，可读取服务器敏感文件。",
    },
    {
        "id": 38,
        "question": "JWT（JSON Web Token）通常用于什么场景？",
        "options": [
            {"key": "A", "text": "用户身份认证和授权"},
            {"key": "B", "text": "加密数据库字段"},
            {"key": "C", "text": "压缩图片"},
            {"key": "D", "text": "日志记录"},
        ],
        "answer": "A",
        "explanation": "JWT 是用于认证的轻量级令牌，包含用户信息和签名，常用于无状态分布式系统的身份验证。",
    },
]


def get_random_question():
    """从题库中随机抽题，并复制一份用于返回"""
    q = random.choice(QUESTIONS)
    # 深拷贝一份，避免修改原始数据
    return {
        "id": q["id"],
        "question": q["question"],
        "options": q["options"],
        "answer": q["answer"],
        "explanation": q["explanation"],
    }


# ── 路由 ────────────────────────────────────────────────────────


@app.route("/")
def index():
    """渲染首页"""
    return render_template("index.html")


@app.route("/api/question")
def api_question():
    """返回随机题目（不含答案字段）"""
    q = get_random_question()
    # 返回给前端的只包含 question / options / id，不暴露 answer
    return jsonify({
        "id": q["id"],
        "question": q["question"],
        "options": q["options"],
    })


@app.route("/api/check", methods=["POST"])
def api_check():
    """校验答案，返回结果"""
    data = request.get_json(force=True)
    qid = data.get("id")
    selected = data.get("selected", "").strip().upper()

    # 在题库中查找题目
    question = None
    for q in QUESTIONS:
        if q["id"] == qid:
            question = q
            break

    if question is None:
        return jsonify({"ok": False, "error": "题目未找到"}), 404

    correct = question["answer"]
    is_correct = selected == correct

    return jsonify({
        "ok": True,
        "correct": is_correct,
        "correctAnswer": correct,
        "correctText": next(
            (opt["text"] for opt in question["options"] if opt["key"] == correct),
            "",
        ),
        "explanation": question["explanation"],
    })


# ── 启动 ────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
