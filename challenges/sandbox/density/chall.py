import ast
import base64

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self,node):
        raise RuntimeError('Function Call Is Not Allowed')

    def visit_Assign(self,node):
        raise RuntimeError('Assign Is Not Allowed')

    def visit_Subscript(self, node):
        raise RuntimeError('Subscript Is Not Allowed')

def chall():
    blacklist = '@ \t\n\\'
    user_input = input("Give me your code after base64 encoded:")
    if not user_input:
        print("Empty input")
        return

    try:
        code = base64.b64decode(user_input).decode('utf-8')
        if any(c in blacklist for c in code):
            raise RuntimeError('Your Code Is So Sparse')
        tree = ast.parse(code)
        visitor = RestrictedNodeVisitor()
        visitor.visit(tree)


        safe_globals = {
            "__builtins__" : {}
        }

        exec(code,safe_globals)

    except SyntaxError as e:
        print(f"Syntax Error : {e}")

    except RuntimeError as e:
        print(f"RuntimeError : {e}")

    except Exception as e:
        print(f'Execution Error: {type(e).__name__}: {e}')
