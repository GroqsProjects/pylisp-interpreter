import sys

# --- Tokenizer ---

def tokenize(code):
    """
    Splits the input string into a list of tokens.
    Handles parentheses, numbers, symbols, and whitespace.
    """
    tokens = []
    i = 0
    while i < len(code):
        char = code[i]
        if char == '(' or char == ')':
            tokens.append(char)
            i += 1
        elif char.isspace():
            i += 1
        elif char.isdigit() or (char == '-' and i + 1 < len(code) and code[i+1].isdigit()):
            # Numbers (integers, potentially negative)
            start = i
            if char == '-':
                i += 1
            while i < len(code) and code[i].isdigit():
                i += 1
            tokens.append(code[start:i])
        else:
            # Symbols
            start = i
            while i < len(code) and char not in '() \t\n':
                i += 1
                if i < len(code):
                    char = code[i]
            tokens.append(code[start:i])
    return tokens

# --- Parser ---

def parse(tokens):
    """
    Parses a list of tokens into an Abstract Syntax Tree (AST).
    Expressions are represented as lists.
    """
    if not tokens:
        raise SyntaxError("Unexpected EOF while reading")

    token = tokens.pop(0)
    if token == '(':
        lst = []
        while tokens[0] != ')':
            lst.append(parse(tokens))
        tokens.pop(0) # Pop ')'
        return lst
    elif token == ')':
        raise SyntaxError("Unexpected ')'")
    else:
        return atom(token)

def atom(token):
    """
    Converts a token into a number (int) if possible, otherwise returns it as a symbol (str).
    """
    try:
        return int(token)
    except ValueError:
        return token

# --- Environment ---

class Environment(dict):
    """
    A class representing an environment for symbol lookup.
    Chains to an outer environment for lexical scoping.
    """
    def __init__(self, params=(), args=(), outer=None):
        super().__init__()
        self.update(zip(params, args))
        self.outer = outer

    def find(self, var):
        """Find the innermost environment where 'var' is defined."""
        if var in self:
            return self
        elif self.outer is not None:
            return self.outer.find(var)
        else:
            raise NameError(f"'{var}' is not defined")

def create_global_env():
    """
    Creates the initial global environment with built-in functions.
    """
    import operator
    env = Environment()
    env.update({
        '+': operator.add,
        '-': operator.sub,
        '*': operator.mul,
        '/': operator.truediv,
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '=': operator.eq,
        'eq?': operator.eq, # Lisp-style equality
        'not': operator.not_,
        'append': lambda a, b: list(a) + list(b),
        'cons': lambda x, y: [x] + list(y),
        'car': lambda x: x[0],
        'cdr': lambda x: x[1:],
        'list': lambda *args: list(args),
        'null?': lambda x: x == [],
        'symbol?': lambda x: isinstance(x, str),
        'number?': lambda x: isinstance(x, (int, float)), # Currently only ints
        'print': lambda x: print(to_string(x)),
        # Additional built-ins for convenience
        'min': min,
        'max': max,
        'abs': abs,
        'round': round,
        'len': len,
    })
    return env

# --- Evaluator ---

global_env = create_global_env()

class LispFunction:
    """Represents a user-defined Lisp function."""
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env # The environment where the function was defined

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError(f"Expected {len(self.params)} arguments, got {len(args)}")
        # Create a new environment for the function call,
        # extending the function's definition environment.
        return evaluate(self.body, Environment(self.params, args, self.env))

def evaluate(x, env=global_env):
    """
    Evaluates an expression in the given environment.
    """
    if isinstance(x, str):  # Symbol
        return env.find(x)[x]
    elif isinstance(x, (int, float)): # Number
        return x
    elif not isinstance(x, list): # Basic types
        return x
    elif x[0] == 'quote':          # (quote exp)
        (_, exp) = x
        return exp
    elif x[0] == 'if':             # (if test conseq alt)
        (_, test, conseq, alt) = x
        exp = (conseq if evaluate(test, env) else alt)
        return evaluate(exp, env)
    elif x[0] == 'define':         # (define var exp)
        (_, var, exp) = x
        env[var] = evaluate(exp, env)
    elif x[0] == 'set!':           # (set! var exp)
        (_, var, exp) = x
        env.find(var)[var] = evaluate(exp, env)
    elif x[0] == 'lambda':         # (lambda (params) body)
        (_, params, body) = x
        return LispFunction(params, body, env)
    else:                          # (proc arg...)
        proc = evaluate(x[0], env)
        args = [evaluate(arg, env) for arg in x[1:]]
        return proc(*args)

# --- Read-Eval-Print Loop (REPL) ---

def to_string(exp):
    """
    Converts a Lisp expression to a string representation.
    """
    if isinstance(exp, list):
        return '(' + ' '.join(map(to_string, exp)) + ')'
    else:
        return str(exp)

def repl(prompt='lisp> '):
    """
    A simple Read-Eval-Print Loop.
    """
    print("PyLisp Interpreter")
    print("Press Ctrl+D or type '(exit)' to quit.")
    while True:
        try:
            user_input = input(prompt)
            if user_input.strip() == '(exit)':
                print("Exiting PyLisp.")
                break
            tokens = tokenize(user_input)
            if not tokens:
                continue
            exp = parse(tokens)
            result = evaluate(exp)
            if result is not None: # Don't print for `define` etc.
                print(to_string(result))
        except (SyntaxError, NameError, TypeError, IndexError) as e:
            print(f"Error: {e}")
        except EOFError: # Ctrl+D
            print("\nExiting PyLisp.")
            break

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # If a file is provided, execute it
        try:
            with open(sys.argv[1], 'r') as f:
                code = f.read()
                tokens = tokenize(code)
                # Parse and evaluate expressions one by one
                # assuming top-level expressions are separated by parentheses
                # This simple loop isn't robust for arbitrary multi-expression files
                # For robust file parsing, would need a stream parser
                # For now, evaluate a single large expression or simple s-expr per line
                i = 0
                while i < len(tokens):
                    # Find the end of an S-expression
                    if tokens[i] == '(':
                        open_parens = 1
                        j = i + 1
                        while j < len(tokens) and open_parens > 0:
                            if tokens[j] == '(':
                                open_parens += 1
                            elif tokens[j] == ')':
                                open_parens -= 1
                            j += 1
                        if open_parens != 0:
                            raise SyntaxError("Unbalanced parentheses in file.")
                        
                        exp_tokens = tokens[i:j]
                        exp = parse(exp_tokens)
                        evaluate(exp)
                        i = j # Move past the evaluated expression
                    else: # Handle single atoms at top level (e.g., just a number or symbol, though not typical for Lisp files)
                        exp = parse([tokens[i]]) # Treat as single expression
                        evaluate(exp)
                        i += 1

        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found.")
        except (SyntaxError, NameError, TypeError, IndexError) as e:
            print(f"Error in file '{sys.argv[1]}': {e}")
    else:
        # Otherwise, start the REPL
        repl()