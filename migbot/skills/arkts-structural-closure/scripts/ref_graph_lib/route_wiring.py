"""Conservative C2 evidence for literal Navigation routes.

A route string is never an instantiation. Recognize only a mounted, local
@Builder dispatcher with a matching literal branch rendering an exported type.
Other registration styles remain unresolved for router-verify to review.
"""
import re


def code_text(text):
    # Preserve quoted strings and line numbers while removing both comment forms.
    token = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|/\*[\s\S]*?\*/|//[^\n]*'''
    return re.sub(token, lambda m: re.sub(r'[^\n]', ' ', m[0])
                  if m[0].startswith(('//', '/*')) else m[0], text)


def block_at(text, start):
    depth, quote, escape = 0, None, False
    for i in range(start, len(text)):
        c = text[i]
        if quote:
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == quote:
                quote = None
            continue
        if c in "\"'`":
            quote = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return ''


def mask_literals(text):
    return re.sub(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`''',
                  lambda m: re.sub(r'[^\n]', ' ', m[0]), text)


def route_evidence(graph, caller, target):
    """Resolve only a local dispatcher mounted on the actual call's stack."""
    caller = caller.resolve()
    if len(graph.export_index.get(target, set())) != 1:
        return None
    target_file = next(iter(graph.export_index[target]))
    if caller != target_file and caller not in graph.importers_of_class(target):
        return None
    source = code_text(caller.read_text(encoding='utf-8', errors='replace'))
    masked = mask_literals(source)
    calls = set()
    for call in re.finditer(r'''\b(this\.\w+)\.(?:push|replace)PathByName\s*\(\s*['"]([^'"]+)['"]''', source):
        if masked[call.start():call.start() + 4] == 'this':
            calls.add((call[1], call[2]))
    if not calls:
        return None
    for builder in re.finditer(r'@Builder\s+(\w+)\s*\(\s*(\w+)\s*:\s*string\b[^)]*\)\s*\{', masked):
        name, param = builder.group(1, 2)
        stacks = set()
        for nav in re.finditer(r'\bNavigation\s*\(\s*(this\.\w+)\s*\)\s*\{', masked):
            body = block_at(source, nav.end() - 1)
            tail = masked[nav.end() + len(body) + 1:]
            chain = r'^\s*(?:\.\w+\s*\([^{};]*?\)\s*)*?\.navDestination\s*\(\s*this\.' + re.escape(name) + r'\s*\)'
            if re.search(chain, tail):
                stacks.add(nav[1])
        if not stacks:
            continue
        body = block_at(source, builder.end() - 1)
        masked_body = mask_literals(body)
        for branch in re.finditer(r'''\bif\s*\(\s*''' + re.escape(param) + r'''\s*===?\s*['"]([^'"]+)['"]\s*\)\s*\{''', body):
            if masked_body[branch.start():branch.start() + 2] != 'if':
                continue
            if not any((stack, branch[1]) in calls for stack in stacks):
                continue
            branch_body = mask_literals(block_at(body, branch.end() - 1))
            if re.search(r'(?<![\w.])' + re.escape(target) + r'\s*\(', branch_body):
                return f'{graph._rel(caller)}:{source.count(chr(10), 0, builder.start()) + 1} route={branch[1]}'
    return None


def without_builders(text):
    """Do not treat calls inside dispatcher declarations as direct render calls."""
    text = code_text(text)
    starts = list(re.finditer(r'@Builder\s+\w+\s*\([^)]*\)\s*\{', text))
    for match in reversed(starts):
        body = block_at(text, match.end() - 1)
        if body:
            end = match.end() + len(body) + 1
            text = text[:match.start()] + text[end:]
    return text
