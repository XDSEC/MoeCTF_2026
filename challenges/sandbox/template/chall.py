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