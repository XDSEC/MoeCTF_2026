# ##### DO NOT MODIFY THIS FILE #####
import ast
import base64

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self,node):
        raise RuntimeError('Function Call Is Not Allowed')

    def visit_Attribute(self,node):
        raise RuntimeError('Attribute Not Allowed')

    def visit_Subscript(self,node):
        raise RuntimeError('Subscript Not Allowed')

def chall():
    # 来自题目附件的chall.py
    user_input = input("Give me your code after base64 encoded:")
    if not user_input:
        print("Empty input")
        return

    try:
        code = base64.b64decode(user_input).decode('utf-8')
        tree = ast.parse(code)
        visitor = RestrictedNodeVisitor()
        visitor.visit(tree)

        safe_builtins ={
            "Exception" : Exception,
            "object" : object,
        }

        safe_globals = {
            "__builtins__" : safe_builtins,
        }

        exec(code,safe_globals,{})

    except SyntaxError as e:
        print(f"Syntax Error : {e}")

    except RuntimeError as e:
        print(f"RuntimeError : {e}")

    except Exception as e:
        print(f'Execution Error: {type(e).__name__}: {e}')

def handle():
    import os
    os.setuid(65534)
    del os
    
    import random
    import string

    print(
        "HTTP/1.1 302 Found\r\nLocation: https://ctf.xidian.edu.cn/wiki/13\r\nContent-Length: 0\r\n\r\n===HTTP REQUEST BLOCK===\x00\033c"
    )
    try:
        count = 0
        while True:
            captcha = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=6)
            )
            captcha2 = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=6)
            )
            if (
                input(
                    f"Are you robot? Please enter '{captcha}'+'{captcha2}'=? to continue: "
                )
                .strip()
                .upper()
                != captcha + captcha2
            ):
                count += 1
                print("Robot detected, try again")
                if count > 5:
                    print("Too many tries, blocked")
                    break
                continue
            count = 0
            try:
                # chall() # type: ignore # noqa: F821
                import os
                print(f"Your flag is {os.getenv("FLAG")}")
                del os
            except Exception as e:
                print(f"Error: {e}")
    except Exception as e:
        print(
            f"\033c ========== Unhandled Error! ==========\n We cannot recover from error: {e}\nChild process exited. Please reconnect or ask administrators for help if error persist"
        )
        
def daemon_main():
    import os
    import socket
    import subprocess

    print("[Info] Server starting")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pwd = os.path.dirname(__file__)
    script = open(__file__, "rb").read()
    self_fd = os.memfd_create("main")
    os.write(self_fd, script)
    os.lseek(self_fd, 0, os.SEEK_SET)
    os.chmod(self_fd, 0o400)
    try:
        sock.bind(("0.0.0.0", 9999))
        sock.listen(1)
        while True:
            try:
                conn, addr = sock.accept()
                print(f"[Info] Connected with {addr}")
                fd = conn.fileno()
                subprocess.Popen(
                    [
                        "python",
                        "/proc/self/fd/{}".format(self_fd),
                        "fork",
                    ],
                    stdin=fd,
                    stdout=fd,
                    stderr=fd,
                    pass_fds=[self_fd],
                    cwd=pwd,
                    env=os.environ,
                )
            except Exception as e:
                print(f"[Error] {e}")
    except KeyboardInterrupt:
        print("[Info] Server stopped")
    finally:
        sock.close()
        print("[Info] Server closed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2 and sys.argv[1] == "fork":
        del sys
        handle()
    else:
        daemon_main()