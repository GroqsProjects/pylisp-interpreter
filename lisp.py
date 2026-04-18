import sys
import math # For sqrt, log, etc.
import operator

# --- Tokenizer ---

def tokenize(code):
    """
    Splits the input string into a list of tokens.
    Handles parentheses, numbers (int/float), symbols, strings, booleans, and comments.
    """
    tokens = []
    i = 0
    while i < len(code):
        char = code[i]
        if char == ';': # Comments
            while i < len(code) and code[i] != '\n':
                i += 1
            continue # Skip to next char (will handle newline whitespace)
        elif char == '(' or char == ')':
            tokens.append(char)
            i += 1
        elif char.isspace():
            i += 1
        elif char == '"': # String literal
            start = i
            i += 1 # Skip opening quote
            while i < len(code) and code[i] != '"':
                # Basic escape sequence handling (for \" only, could be extended)
                if code[i] == '\\' and i + 1 < len(code) and code[i+1] in ['"', '\\']: # Handle \" and \\
                    i += 2
                else:
                    i += 1
            if i >= len(code) or code[i] != '"':
                raise SyntaxError("Unterminated string literal")
            i += 1 # Skip closing quote
            tokens.append(code[start:i])
        elif char == '#': # Booleans and other # keywords
            if i + 1 < len(code) and code[i+1] == 't':
                tokens.append('#t')
                i += 2
            elif i + 1 < len(code) and code[i+1] == 'f':
                tokens.append('#f')
                i += 2
            else:
                # Could be a different # keyword, for now just treat as symbol
                start = i
                while i < len(code) and char not in '() \t\n"':
                    i += 1
                    if i < len(code):
                        char = code[i]
                tokens.append(code[start:i])
        elif char.isdigit() or (char == '-' and i + 1 < len(code) and (code[i+1].isdigit() or code[i+1] == '.')):
            # Numbers (integers, floats, potentially negative)
            start = i
            if char == '-':
                i += 1
            while i < len(code) and (code[i].isdigit() or code[i] == '.'):
                # Allow a single decimal point for floats
                if code[i] == '.' and '.' in code[start:i]:
                    raise SyntaxError("Invalid number format: multiple decimal points")
                i += 1
            tokens.append(code[start:i])
        else:
            # Symbols
            start = i
            while i < len(code) and char not in '() \t\n";': # Added ';' to delimiters
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
        while tokens and tokens[0] != ')': # Ensure tokens exist before checking index
            lst.append(parse(tokens))
        if not tokens:
            raise SyntaxError("Unclosed parenthesis: Unexpected EOF")
        tokens.pop(0) # Pop ')'
        return lst
    elif token == ')':
        raise SyntaxError("Unexpected ')'")
    else:
        return atom(token)

def atom(token):
    """
    Converts a token into a number (int/float), boolean, or returns it as a symbol (str).
    """
    if token == '#t':
        return True
    elif token == '#f':
        return False
    elif token.startswith('"') and token.endswith('"'):
        # Remove quotes and unescape supported characters
        return token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return token # It's a symbol

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
        # List operations
        'append': lambda a, b: list(a) + list(b),
        'cons': lambda x, y: [x] + list(y),
        'car': lambda x: x[0],
        'cdr': lambda x: x[1:],
        'list': lambda *args: list(args),
        'map': lambda proc, lst: [proc(x) for x in lst],
        'filter': lambda pred, lst: [x for x in lst if pred(x)],
        # Type predicates
        'null?': lambda x: x == [],
        'symbol?': lambda x: isinstance(x, str) and not (x.startswith('"') and x.endswith('"')),
        'number?': lambda x: isinstance(x, (int, float)),
        'string?': lambda x: isinstance(x, str), # Python's string type
        'bool?': lambda x: isinstance(x, bool),
        'list?': lambda x: isinstance(x, list),
        # I/O
        'print': lambda x: print(to_string(x)),
        # Additional built-ins for convenience
        'min': min,
        'max': max,
        'abs': abs,
        'round': round,
        'len': len,
        'sqrt': math.sqrt,
        'log': math.log,
        'exp': math.exp,
        'pow': math.pow,
        # String operations
        'string-length': len,
        'substring': lambda s, start, end: s[start:end],
        'string-append': lambda *args: "".join(args),
        # Constants
        'true': True,
        'false': False,
    })
    return env

# --- Evaluator ---

global_env = create_global_env()

class LispFunction:
    """Represents a user-defined Lisp function (closure)."""
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env # The environment where the function was defined

    def __call__(self, *args):
        if len(args) != len(self.params):
            raise TypeError(f"Expected {len(self.params)} arguments, got {len(args)}")
        # Create a new environment for the function call,
        # extending the function's definition environment.
        return evaluate_loop(self.body, Environment(self.params, args, self.env))

# Trampoline for TCO
class TailCall:
    def __init__(self, expr, env):
        self.expr = expr
        self.env = env

def evaluate_loop(x, env):
    """
    Driver loop for evaluation, handling TailCall objects to achieve TCO.
    """
    while True:
        result = evaluate(x, env)
        if isinstance(result, TailCall):
            x = result.expr
            env = result.env
        else:
            return result

def evaluate(x, env=global_env):
    """
    Evaluates an expression in the given environment.
    Identifies tail calls and returns a TailCall object for the driver loop.
    """
    if isinstance(x, str):  # Symbol
        return env.find(x)[x]
    elif isinstance(x, (int, float, bool)): # Number or Boolean
        return x
    elif not isinstance(x, list): # Basic types that are not S-expressions
        return x
    
    # --- Special Forms ---
    op = x[0]
    if op == 'quote':          # (quote exp)
        if len(x) != 2:
            raise SyntaxError("quote requires exactly 1 argument")
        (_, exp) = x
        return exp
    elif op == 'if':             # (if test conseq alt)
        if len(x) != 4:
            raise SyntaxError("if requires 3 arguments: (if test conseq alt)")
        (_, test, conseq, alt) = x
        if evaluate_loop(test, env): # Test condition is NOT in tail position
            return TailCall(conseq, env) # Consequent is in tail position
        else:
            return TailCall(alt, env)    # Alternative is in tail position
    elif op == 'define':         # (define var exp) or (define (func params) body)
        if len(x) < 3:
            raise SyntaxError("define requires at least 2 arguments: (define var exp) or (define (func params) body)")
        if isinstance(x[1], list): # (define (func params) body) -> sugar for (define func (lambda (params) body))
            func_name = x[1][0]
            params = x[1][1:]
            body = x[2]
            env[func_name] = LispFunction(params, body, env)
        else: # (define var exp)
            (_, var, exp) = x
            env[var] = evaluate_loop(exp, env) # The value evaluated for `define` is not in tail context
        return None # Define doesn't return a value in the REPL
    elif op == 'set!':           # (set! var exp)
        if len(x) != 3:
            raise SyntaxError("set! requires 2 arguments: (set! var exp)")
        (_, var, exp) = x
        env.find(var)[var] = evaluate_loop(exp, env) # The value evaluated for `set!` is not in tail context
        return None # Set! doesn't return a value in the REPL
    elif op == 'lambda':         # (lambda (params) body)
        if len(x) != 3 or not isinstance(x[1], list):
            raise SyntaxError("lambda requires a list of parameters and a body: (lambda (p1 p2) body)")
        (_, params, body) = x
        return LispFunction(params, body, env)
    elif op == 'begin':          # (begin exp...)
        if len(x) < 2:
            return None # Or raise error, or return a default value
        # Evaluate all but the last expression sequentially
        for exp in x[1:-1]:
            evaluate_loop(exp, env)
        # The last expression is in tail position
        return TailCall(x[-1], env)
    else:                          # (proc arg...)
        # Evaluate procedure and arguments (NOT in tail position)
        proc = evaluate_loop(x[0], env)
        args = [evaluate_loop(arg, env) for arg in x[1:]]
        
        if not callable(proc):
            raise TypeError(f"'{to_string(x[0])}' is not a function or macro")
        
        # If the procedure is a user-defined LispFunction,
        # its body evaluation is a tail call relative to the current context.
        if isinstance(proc, LispFunction):
            # The function call itself is a tail call if it's the last thing
            # to be evaluated. We need to manually set up the env for its body.
            # This is complex because we've already evaluated arguments.
            # A simpler approach is to let LispFunction.__call__ handle it,
            # and ensure evaluate_loop is used there.
            # For now, we return the direct call result.
            # The TCO applies *within* the LispFunction's body.
            return proc(*args) # This will call evaluate_loop inside LispFunction.__call__
        else:
            # Built-in functions are not tail-recursive in our interpreter
            return proc(*args)

# --- Read-Eval-Print Loop (REPL) ---

def to_string(exp):
    """
    Converts a Lisp expression (Python object) to a human-readable string.
    """
    if isinstance(exp, list):
        return '(' + ' '.join(map(to_string, exp)) + ')'
    elif isinstance(exp, str):
        # Enclose strings in quotes and escape internal quotes/backslashes
        return f'"{exp.replace('\\', '\\\\').replace('"', '\\"')}"'
    elif exp is True:
        return '#t'
    elif exp is False:
        return '#f'
    elif exp is None: # For statements like define, set! which return None
        return "" # Don't print anything
    else:
        return str(exp)

def repl(prompt='pylisp> '):
    """
    A simple Read-Eval-Print Loop.
    """
    print("PyLisp Interpreter (v0.3 - with floats, strings, booleans, comments, TCO, new built-ins)")
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
            
            # Allow multiple expressions in REPL input for convenience
            results = []
            while tokens:
                exp = parse(tokens)
                results.append(evaluate_loop(exp)) # Use evaluate_loop for top-level
            
            # Only print the last non-None result for REPL
            if results:
                last_result = None
                for res in reversed(results):
                    if res is not None:
                        last_result = res
                        break
                if last_result is not None:
                    print(to_string(last_result))

        except (SyntaxError, NameError, TypeError, IndexError, ValueError) as e:
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
                # Keep parsing and evaluating expressions until no tokens are left
                while tokens:
                    exp = parse(tokens)
                    evaluate_loop(exp) # Evaluate top-level expressions for side effects
        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found.")
        except (SyntaxError, NameError, TypeError, IndexError, ValueError) as e:
            print(f"Error in file '{sys.argv[1]}': {e}")
    else:
        # Otherwise, start the REPL
        repl()