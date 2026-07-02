"""
AI Dev Installer — Local bridge server
Receives install requests from the Chrome extension and runs them in a
visible Terminal window + opens VS Code / Cursor.

Run:  python3 server.py
Port: 9876
"""
import base64, json, os, re, subprocess, shutil, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9876

# ── Editor detection ─────────────────────────────────────────────────────────
def _find_editor(candidates):
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
        p = shutil.which(c)
        if p:
            return p
    return None

EDITORS = {
    'vscode': _find_editor([
        '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
        '/usr/local/bin/code',
        '/opt/homebrew/bin/code',
        'code',
    ]),
    'cursor': _find_editor([
        '/Applications/Cursor.app/Contents/Resources/app/bin/cursor',
        '/Applications/Cursor.app/Contents/MacOS/Cursor',
        '/usr/local/bin/cursor',
        'cursor',
    ]),
}

# ── Python/pip detection ─────────────────────────────────────────────────────
def _pip_cmd():
    if shutil.which('pip3'):
        return 'pip3'
    py = shutil.which('python3') or shutil.which('python')
    if py:
        return f'"{py}" -m pip'
    return 'pip3'

PIP = _pip_cmd()

def fix_pip(command):
    if command.startswith('pip install'):
        return command.replace('pip install', f'{PIP} install', 1)
    return command


# ── Smart README detection ────────────────────────────────────────────────────
_readme_cache = {}  # "owner/repo" → text or None

# Order matters: highest-priority package managers first
INSTALL_PRIORITY = ['brew', 'pipx', 'pip', 'npm', 'yarn', 'cargo', 'go', 'gem', 'curl', 'apt']

INSTALL_PATTERNS = [
    (r'brew\s+install(?:\s+--cask)?\s+[^\s\n]+',                  'brew'),
    (r'pipx\s+install\s+[^\s\n]+',                                 'pipx'),
    (r'pip3?\s+install\s+(?:-[^\s\n]+\s+)*[^\s\n]+',              'pip'),
    (r'npm\s+install(?:\s+-[gGsS])?\s+[^\s\n]+',                  'npm'),
    (r'yarn\s+(?:global\s+)?add\s+[^\s\n]+',                       'yarn'),
    (r'cargo\s+install\s+[^\s\n]+',                                'cargo'),
    (r'go\s+install\s+[^\s\n]+',                                   'go'),
    (r'gem\s+install\s+[^\s\n]+',                                  'gem'),
    (r'curl\s+[^\s\n]+.*?\|\s*(?:sudo\s+)?(?:bash|sh)',            'curl'),
    (r'(?:sudo\s+)?apt(?:-get)?\s+install\s+-?y?\s*[^\s\n]+',     'apt'),
]

def fetch_readme(owner, repo):
    key = f'{owner}/{repo}'
    if key in _readme_cache:
        return _readme_cache[key]
    url = f'https://api.github.com/repos/{owner}/{repo}/readme'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'ai-dev-installer/1.0',
        'Accept':     'application/vnd.github.v3+json',
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            text = base64.b64decode(data['content']).decode('utf-8', errors='replace')
            _readme_cache[key] = text
            return text
    except Exception:
        _readme_cache[key] = None
        return None

def extract_install_cmds(readme_text):
    """Return list of {cmd, type} dicts, ordered by priority."""
    # Prefer commands inside fenced code blocks (most authoritative)
    blocks = re.findall(r'```[a-z]*\n(.*?)```', readme_text, re.DOTALL | re.IGNORECASE)
    search = '\n'.join(blocks) if blocks else readme_text

    found, seen = [], set()
    for pattern, ptype in INSTALL_PATTERNS:
        for m in re.finditer(pattern, search, re.IGNORECASE):
            cmd = m.group(0).strip()
            if cmd not in seen:
                seen.add(cmd)
                found.append({'cmd': cmd, 'type': ptype})

    found.sort(key=lambda x: INSTALL_PRIORITY.index(x['type'])
               if x['type'] in INSTALL_PRIORITY else 99)
    return found

def smart_detect(github_url):
    """
    Given a github.com URL, fetch the README and return detected install
    commands plus a recommended one.
    Returns dict: {ok, commands, recommended, source}
    """
    # Strip trailing slashes, query strings, etc.
    clean_url = github_url.split('?')[0].split('#')[0].rstrip('/')

    # Extract owner/repo
    match = re.search(r'github\.com/([^/]+)/([^/]+)', clean_url)
    if not match:
        return {'ok': False, 'commands': [], 'error': 'Not a GitHub URL'}
    owner, repo = match.group(1), match.group(2)

    readme = fetch_readme(owner, repo)
    if not readme:
        fallback = f'{PIP} install git+{clean_url}'
        return {
            'ok': True,
            'commands': [{'cmd': fallback, 'type': 'pip'}],
            'recommended': fallback,
            'source': 'fallback',
        }

    cmds = extract_install_cmds(readme)
    if not cmds:
        fallback = f'{PIP} install git+{clean_url}'
        cmds = [{'cmd': fallback, 'type': 'pip'}]
        source = 'fallback'
    else:
        source = 'readme'

    return {
        'ok': True,
        'commands': cmds,
        'recommended': cmds[0]['cmd'],
        'source': source,
    }


# ── VS Code integrated terminal ───────────────────────────────────────────────
def open_vscode_terminal(command, project):
    """
    Open VS Code with the project, open its integrated terminal via the
    Terminal menu, then type and run the install command.
    Needs Accessibility permission for whichever app runs this server.
    """
    vscode = EDITORS.get('vscode')
    if not vscode:
        return False, 'VS Code not found'

    args = [vscode]
    if project and os.path.isdir(project):
        args.append(project)
    subprocess.Popen(args)

    safe_cmd = command.replace('\\', '\\\\').replace('"', '\\"')
    script = f'''delay 3
tell application "Visual Studio Code"
    activate
end tell
delay 2
tell application "System Events"
    tell process "Code"
        click menu item "New Terminal" of menu "Terminal" of menu bar 1
        delay 1.5
        keystroke "{safe_cmd}"
        delay 0.3
        key code 36
    end tell
end tell'''
    try:
        subprocess.Popen(['osascript', '-e', script])
        return True, None
    except Exception as e:
        return False, str(e)


# ── Fallback: macOS Terminal.app ──────────────────────────────────────────────
def open_terminal(command, cwd):
    safe_cwd = (cwd or os.path.expanduser('~')).replace("'", "\\'")
    safe_cmd = command.replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        '    activate\n'
        f'    do script "cd \'{safe_cwd}\' && {safe_cmd}"\n'
        'end tell'
    )
    try:
        subprocess.Popen(['osascript', '-e', script])
        return True, None
    except Exception as e:
        return False, str(e)


# ── Job state ────────────────────────────────────────────────────────────────
jobs = {}

def run_install_bg(job_id, command, cwd):
    jobs[job_id] = {'status': 'running', 'output': [], 'error': None}
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd or os.path.expanduser('~'),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            jobs[job_id]['output'].append(line.rstrip())
        proc.wait()
        jobs[job_id]['status'] = 'done' if proc.returncode == 0 else 'error'
        if proc.returncode != 0:
            jobs[job_id]['error'] = f'Exit code {proc.returncode}'
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)


def open_editor(editor, project):
    cmd = EDITORS.get(editor) or EDITORS.get('cursor') or EDITORS.get('vscode')
    if not cmd:
        return False, 'No editor found (install VS Code or Cursor)'
    args = [cmd]
    if project and os.path.isdir(project):
        args.append(project)
    try:
        subprocess.Popen(args)
        return True, None
    except Exception as e:
        return False, str(e)


# ── HTTP handler ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'[bridge] {fmt % args}')

    def cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def respond(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.cors()
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        if self.path == '/status':
            editor = next((k for k, v in EDITORS.items() if v), None)
            self.respond({'ok': True, 'editor': editor, 'editors': EDITORS, 'pip': PIP})
        elif self.path.startswith('/job/'):
            job_id = self.path.split('/')[-1]
            self.respond(jobs.get(job_id, {'error': 'not found'}),
                         200 if job_id in jobs else 404)
        else:
            self.respond({'error': 'not found'}, 404)

    def do_POST(self):
        body = self.read_body()

        if self.path == '/smart-detect':
            url = body.get('url', '')
            if not url:
                self.respond({'ok': False, 'error': 'url required'}, 400)
                return
            result = smart_detect(url)
            self.respond(result)

        elif self.path == '/install':
            command = fix_pip(body.get('command', ''))
            project = body.get('project', '') or os.path.expanduser('~')
            if not command:
                self.respond({'ok': False, 'error': 'command required'}, 400)
                return

            job_id = f'job_{int(time.time()*1000)}'

            if command.startswith('#'):
                self.respond({'ok': True, 'job_id': job_id, 'terminal': False})
                return

            # Prefer VS Code integrated terminal; fall back to Terminal.app
            ok, err = open_vscode_terminal(command, project)
            if not ok:
                ok, err = open_terminal(command, project)
            if ok:
                jobs[job_id] = {'status': 'terminal', 'output': [], 'error': None}
                self.respond({'ok': True, 'job_id': job_id, 'terminal': True})
            else:
                threading.Thread(
                    target=run_install_bg, args=(job_id, command, project), daemon=True
                ).start()
                self.respond({'ok': True, 'job_id': job_id, 'terminal': False, 'warn': err})

        elif self.path == '/install-ai':
            command = fix_pip(body.get('command', ''))
            prompt  = body.get('prompt', '')
            project = body.get('project', '') or os.path.expanduser('~')
            editor  = body.get('editor', 'cursor')

            if command and not command.startswith('#'):
                open_vscode_terminal(command, project)

            ok, err = open_editor(editor, project)

            if prompt:
                prompt_file = os.path.expanduser('~/.ai_installer_prompt.md')
                with open(prompt_file, 'w') as f:
                    f.write(f'# AI Install Request\n\n{prompt}\n\n---\nPackage URL: {body.get("url","")}\n')

            self.respond({'ok': ok, 'error': err})

        elif self.path == '/open-editor':
            editor  = body.get('editor', 'cursor')
            project = body.get('project', '')
            ok, err = open_editor(editor, project)
            self.respond({'ok': ok, 'error': err})

        else:
            self.respond({'error': 'not found'}, 404)


if __name__ == '__main__':
    print(f'AI Dev Installer bridge — http://localhost:{PORT}')
    print(f'  pip:    {PIP}')
    print(f'  vscode: {EDITORS["vscode"] or "not found"}')
    print(f'  cursor: {EDITORS["cursor"] or "not found"}')
    print('  Press Ctrl+C to stop.')
    HTTPServer(('localhost', PORT), Handler).serve_forever()
