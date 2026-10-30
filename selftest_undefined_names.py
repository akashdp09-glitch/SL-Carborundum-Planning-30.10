import ast,sys,builtins,os,symtable
B=set(dir(builtins))|{'__file__','__name__','__doc__'}
def modnames(tree):
    s=set()
    for n in ast.walk(tree):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)): s.add(n.name)
        elif isinstance(n,ast.Import):
            for a in n.names: s.add((a.asname or a.name).split('.')[0])
        elif isinstance(n,ast.ImportFrom):
            for a in n.names: s.add(a.asname or a.name)
        elif isinstance(n,ast.Name) and isinstance(n.ctx,(ast.Store,ast.Del)): s.add(n.id)
        elif isinstance(n,ast.arg): s.add(n.arg)
        elif isinstance(n,ast.ExceptHandler) and n.name: s.add(n.name)
    return s
res=[]
SKIP={'.venv','venv','.cloud-test-data','__pycache__','node_modules','.git'}
for root,dirs,fs in os.walk('.'):
    dirs[:]=[d for d in dirs if d not in SKIP]
    for f in fs:
        if not f.endswith('.py'): continue
        p=os.path.join(root,f)
        try:src=open(p,encoding='utf-8').read(); tree=ast.parse(src)
        except Exception as e: res.append((p,'PARSE',str(e)));continue
        if any(isinstance(n,ast.ImportFrom) and any(a.name=='*' for a in n.names) for n in ast.walk(tree)): star=True
        else: star=False
        defined=modnames(tree)|B
        for n in ast.walk(tree):
            if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Load) and n.id not in defined:
                res.append((p,n.lineno,n.id))
for r in res[:80]: print(*r)
print(len(res))
