import ast
import base64

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Import(self, node):
        raise Exception('Not Allowed Import')

    def visit_ImportFrom(self, node):
        raise Exception('Not Allowed ImportFrom Either')


def chall():
    user_input = input("Give me your code after base64 encoded:")
    if not user_input:
        print("Empty input")
        return

    blacklist = ['os','exec','eval','open','file','breakpoint','sys','help']

    try:
        code = base64.b64decode(user_input).decode('ascii')
        tree = ast.parse(code)
        visitor = RestrictedNodeVisitor()
        visitor.visit(tree)

        for word in blacklist:
            if word in code:
                print('Hacker!')
                return

        exec(code)

    except SyntaxError as e:
        print(f"Syntax Error : {e}")

    except RuntimeError as e:
        print(f"RuntimeError : {e}")

    except Exception as e:
        print(f'Execution Error: {type(e).__name__}: {e}')
