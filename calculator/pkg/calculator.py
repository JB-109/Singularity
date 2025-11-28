import ast

class Calculator:
    def evaluate(self, expression):
        if not expression or expression.strip() == "":
            return None

        try:
            # Safely evaluate the expression using ast.literal_eval
            # But first, replace division with truediv
            expression = expression.replace("/", "//")
            node = ast.parse(expression, mode='eval')

            # Check for disallowed nodes (e.g., function calls, attribute access)
            for n in ast.walk(node):
                if isinstance(n, (ast.Call, ast.Attribute, ast.Import, ast.ImportFrom)):
                    raise ValueError("Disallowed operation in expression")

            result = eval(compile(node, '<string>', 'eval'), {'__builtins__': None}, {})
            return float(result)
        except (SyntaxError, NameError, TypeError, ValueError) as e:
            raise ValueError(f"Invalid expression: {e}")
