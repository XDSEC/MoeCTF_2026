import ast
import base64

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self,node):
        raise RuntimeError('Function Call Is Not Allowed')

    def visit_FunctionDef(self,node):
        raise RuntimeError('Function Definition Is Not Allowed')

    def visit_ClassDef(self,node):
        raise RuntimeError('Class Definition Is Not Allowed')

    def visit_NamedExpr(self, node):
        raise RuntimeError('Walrus Is Not Allowed')

    def visit_Assign(self, node):
        raise RuntimeError('Assign Is Not Allowed')

    def visit_AnnAssign(self, node):
        raise RuntimeError('AnnAssign Is Also Not Allowed')

def chall():
    user_input = input("Give me your code after base64 encoded:")
    if not user_input:
        print("Empty input")
        return

    try:
        code = base64.b64decode(user_input).decode('utf-8')
        tree = ast.parse(code)
        visitor = RestrictedNodeVisitor()
        visitor.visit(tree)

        safe_globals = {
            "__builtins__" : {},
        }

        exec(code,safe_globals,{})

    except SyntaxError as e:
        print(f"Syntax Error : {e}")

    except RuntimeError as e:
        print(f"RuntimeError : {e}")

    except Exception as e:
        print(f'Execution Error: {type(e).__name__}: {e}')