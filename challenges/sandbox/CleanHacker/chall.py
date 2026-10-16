import ast
import base64

class RestrictedNodeVisitor(ast.NodeVisitor):
    def visit_Call(self,node):
        raise RuntimeError('Function Call Is Not Allowed')

    def visit_Attribute(self,node):
        raise RuntimeError('Attribute Not Allowed')

    def visit_Delete(self,node):
        raise RuntimeError('You Can\'t Delete Admin!')

def chall():
    global admin # noqa
    admin = 'NoHacker'
    import string
    allowed = string.ascii_letters + string.digits + '\'":;\t \n'
    user_input = input("Give me your code after base64 encoded:")

    if not user_input:
        print("Empty input")
        return
    code = base64.b64decode(user_input).decode('ascii')

    if len(code)>50:
        print("Too long")
        return

    for c in code:
        if c not in allowed:
            print('Hacker !')
            return

    tree = ast.parse(code)
    visitor = RestrictedNodeVisitor()
    visitor.visit(tree)

    try:
        exec(code)

    except SyntaxError as e:
        print(f"Syntax Error : {e}")

    except RuntimeError as e:
        print(f"RuntimeError : {e}")

    except Exception as e:
        print(f'Execution Error: {type(e).__name__}: {e}')

    if  'admin' in globals():
        print(globals()['admin'])
    else:
        with open('flag_name_is_l0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0o0ong.txt') as f:
            flag = f.read()
            print(flag)
