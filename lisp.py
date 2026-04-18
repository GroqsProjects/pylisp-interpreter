import sys
import math # For sqrt, log, etc.
import operator

# --- Tokenizer ---

def tokenize(code):
    """
    Splits the input string into a list of tokens.
    Handles parentheses, numbers (int/float), symbols, strings, booleans, and comments.
    Also handles special characters for quote ('), backquote (`), unquote (,), unquote-splicing (,).
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
                # Basic escape sequence handling (for \" and \\)
                if code[i] == '\\' and i + 1 < len(code) and code[i+1] in ['"', '\\']:
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
        elif char == "'": # Quote shortcut
            tokens.append("'")
            i += 1
        elif char == '`': # Backquote shortcut
            tokens.append("`")
            i += 1
        elif char == ',': # Unquote / Unquote-splicing shortcut
            if i + 1 < len(code) and code[i+1] == '@':
                tokens.append(",@")
                i += 2
            else:
                tokens.append(",")
                i += 1
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
            while i < len(code) and char not in '() \t\n";`,\'': # Added '`' ',' "'" to delimiters
                i += 1
                if i < len(code):
                    char = code[i]
            tokens.append(code[start:i])
    return tokens

# --- Parser ---

def parse(tokens):
    """
    Parses a list of tokens into an Abstract Syntax Tree (AST).
    Handles ' (quote), ` (backquote), , (unquote), ,@ (unquote-splicing) shortcuts.
    """
    if not tokens:
        raise SyntaxError("Unexpected EOF while reading")

    token = tokens.pop(0)
    if token == '(':
        lst = []
        while tokens and tokens[0] != ')':
            lst.append(parse(tokens))
        if not tokens:
            raise SyntaxError("Unclosed parenthesis: Unexpected EOF")
        tokens.pop(0) # Pop ')'
        return lst
    elif token == ')':
        raise SyntaxError("Unexpected ')'")
    elif token == "'": # Quote shortcut
        return ['quote', parse(tokens)]
    elif token == '`': # Backquote shortcut
        return ['backquote', parse(tokens)]
    elif token == ',': # Unquote shortcut
        return ['unquote', parse(tokens)]
    elif token == ',@': # Unquote-splicing shortcut
        return ['unquote-splicing', parse(tokens)]
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
        return token[1:-1].replace('\\', '\\\\').replace('"', '\\"') # Corrected unescaping
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

# --- Macro System ---

class LispMacro:
    """Represents a user-defined Lisp macro."""
    def __init__(self, params, body, env):
        self.params = params
        self.body = body
        self.env = env # The environment where the macro was defined (for free variables in body)

    def __call__(self, args_ast):
        # Macros receive their arguments unevaluated (as AST nodes).
        # They expand into a new AST node, which is then evaluated.
        if len(args_ast) != len(self.params):
            raise TypeError(f"Macro expected {len(self.params)} arguments, got {len(args_ast)}")
        # Create a new environment for macro expansion, mapping params to args_ast
        # This environment extends the macro's definition environment
        macro_expansion_env = Environment(self.params, args_ast, self.env)
        
        # Evaluate the macro body in the macro_expansion_env
        # The body itself should evaluate to an AST (a Python list/atom)
        return evaluate_loop(self.body, macro_expansion_env)

# Global macro environment, separate from value environment
global_macro_env = Environment()

def macro_expand_backquote(exp, env):
    """
    Helper function to expand backquoted expressions.
    This is complex, handles unquote and unquote-splicing.
    `exp` is the expression *inside* the backquote.
    `env` is the evaluation environment for unquoted expressions.
    """
    if not isinstance(exp, list): # `atom
        return ['quote', exp] # Just quote the atom
    
    if not exp: # `()
        return []

    # Handle unquote and unquote-splicing
    if exp[0] == 'unquote': # `,x
        if len(exp) != 2:
            raise SyntaxError("Unquote requires exactly one argument")
        return evaluate_loop(exp[1], env) # Evaluate x
    elif exp[0] == 'unquote-splicing': # `,@x
        raise SyntaxError("Cannot unquote-splice an atom or at the top level of a backquote (must be within a list)")
        
    # Recursively process lists
    result = []
    for item in exp:
        if isinstance(item, list) and item and item[0] == 'unquote-splicing': # `,@x in a list
            if len(item) != 2:
                raise SyntaxError("Unquote-splicing requires exactly one argument")
            spliced_list = evaluate_loop(item[1], env)
            if not isinstance(spliced_list, list):
                raise TypeError(f"Unquote-splicing expected a list, got {type(spliced_list)}")
            result.extend(spliced_list)
        else:
            result.append(macro_expand_backquote(item, env)) # Recursively expand sub-expressions
            
    return result


def macro_expand(exp, env, macro_env=global_macro_env):
    """
    Recursively expands macros in the given expression.
    Returns the fully expanded AST.
    """
    if not isinstance(exp, list):
        return exp # Atoms are not macro calls

    if not exp:
        return [] # Empty list is not a macro call

    op = exp[0]

    # Handle special forms that are processed at expansion time
    if op == 'quote':
        return exp
    elif op == 'backquote': # `x => (backquote x)
        if len(exp) != 2:
            raise SyntaxError("Backquote requires exactly one argument")
        # `macro_expand_backquote` needs to evaluate expressions in `env`
        return macro_expand_backquote(exp[1], env)
    elif op == 'unquote' or op == 'unquote-splicing':
        raise SyntaxError(f"'{op}' cannot appear outside of a backquoted expression")
    
    # Check if the operator is a macro
    if isinstance(op, str) and op in macro_env:
        macro_transformer = macro_env[op]
        # Pass the unevaluated arguments (the rest of the list) to the macro
        expanded_exp = macro_transformer(exp[1:])
        # The expanded expression itself might contain macros, so re-expand
        return macro_expand(expanded_exp, env, macro_env)
    
    # If not a macro, recurse into sub-expressions (e.g., arguments of functions)
    return [macro_expand(sub_exp, env, macro_env) for sub_exp in exp]


# --- Environment --- (Re-declared for clarity in sequence, but using actual definition)
# (Moved to top of file for proper scope)

# --- Evaluator ---

global_env = Environment() # Initialize here before global_env is used for built-ins

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

def evaluate(x, env):
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
    elif op == 'defmacro':       # (defmacro (name params) body)
        if len(x) != 3 or not isinstance(x[1], list):
            raise SyntaxError("defmacro requires a list (name params) and a body: (defmacro (m-name p1 p2) body)")
        macro_name = x[1][0]
        params = x[1][1:]
        body = x[2]
        global_macro_env[macro_name] = LispMacro(params, body, env) # Macros live in global_macro_env
        return None
    elif op == 'begin':          # (begin exp...)
        if len(x) < 2:
            return None # Or raise error, or return a default value
        # Evaluate all but the last expression sequentially
        for exp_i in x[1:-1]:
            evaluate_loop(exp_i, env)
        # The last expression is in tail position
        return TailCall(x[-1], env)
    # The following are handled by macro_expand and should not appear here
    elif op == 'backquote' or op == 'unquote' or op == 'unquote-splicing':
        raise SyntaxError(f"Special form '{op}' should have been expanded by macro_expand. This is an internal error or misuse.")
    else:                          # (proc arg...)
        # Evaluate procedure and arguments (NOT in tail position)
        proc = evaluate_loop(x[0], env)
        args = [evaluate_loop(arg, env) for arg in x[1:]]
        
        if not callable(proc):
            raise TypeError(f"'{to_string(x[0])}' is not a function or macro")
        
        # When a LispFunction is called, its body is evaluated using evaluate_loop,
        # ensuring TCO within the function's own execution context.
        return proc(*args)

def create_global_env():
    """
    Creates the initial global environment with built-in functions.
    """
    env = global_env # Use the already defined global_env
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
        'string?': lambda x: isinstance(x, str),
        'bool?': lambda x: isinstance(x, bool),
        'list?': lambda x: isinstance(x, list),
        'callable?': lambda x: callable(x),
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

create_global_env() # Populate the global environment

# --- Read-Eval-Print Loop (REPL) ---

def to_string(exp):
    """
    Converts a Lisp expression (Python object) to a human-readable string.
    """
    if isinstance(exp, list):
        return '(' + ' '.join(map(to_string, exp)) + ')'
    elif isinstance(exp, str):
        # Enclose strings in quotes and escape internal quotes/backslashes for display
        return f'"{exp.replace('\\', '\\\\').replace('"', '\\"')}"'
    elif exp is True:
        return '#t'
    elif exp is False:
        return '#f'
    elif exp is None: # For statements like define, set!, defmacro which return None
        return "" # Don't print anything
    else:
        return str(exp)

def repl(prompt='pylisp> '):
    """
    A simple Read-Eval-Print Loop.
    """
    print("PyLisp Interpreter (v0.4 - with macros, backquote, unquote, unquote-splicing)")
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
            
            results = []
            while tokens:
                parsed_exp = parse(tokens)
                expanded_exp = macro_expand(parsed_exp, global_env, global_macro_env) # Macro expand before evaluation
                results.append(evaluate_loop(expanded_exp, global_env))
            
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
                while tokens:
                    parsed_exp = parse(tokens)
                    expanded_exp = macro_expand(parsed_exp, global_env, global_macro_env)
                    evaluate_loop(expanded_exp, global_env)
        except FileNotFoundError:
            print(f"Error: File '{sys.argv[1]}' not found.")
        except (SyntaxError, NameError, TypeError, IndexError, ValueError) as e:
            print(f"Error in file '{sys.argv[1]}': {e}")
    else:
        # Otherwise, start the REPL
        repl()