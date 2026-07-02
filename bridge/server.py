"""
AI Dev Installer — Local bridge server
Receives install requests from the Chrome extension and runs them in VS Code / Cursor.

Run:  python server.py
Port: 9876
"""
import json, os, subprocess, sys, shutil, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 9876

# Detect available editors — also check common Mac install paths
def _find_editor(names):
    for n in names:
        p = shutil.which(n)
        if p: return p
    return None

EDITORS = {
    'vscode':  _find_editor([
        'code',
        '/usr/local/bin/code',
        '/opt/homebrew/bin/code',
        '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
    ]),
    'cursor':  _find_editor([
        'cursor',
        '/usr/local/bin/cursor',
        '/Applications/Cursor.app/Contents/MacOS/Cursor',
        '/Applications/Cursor.app/Contents/Resources/app/bin/cursor',
    ]),
}

# ── Install job state ────────────────────────────────────────────────────────
jobs = {}  # job_id → {status, output, error}


def run_install(job_id, command, cwd):
    jobs[job_id] = {'status': 'running', 'output': [], 'error': None}
    try:
        proc = subprocess.Popen(
            command, shell=True, cwd=cwd or os.path.expanduser('~'),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            jobs[job_id]['output'].append(line.rstrip())
        proc.wait()
        if proc.returncode == 0:
            jobs[job_id]['status'] = 'done'
        else:
            jobs[job_id]['status'] = 'error'
            jobs[job_id]['error'] = f'Exit code {proc.returncode}'
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)


def open_editor(editor, project):
    cmd = EDITORS.get(editor) or EDITORS.get('cursor') or EDITORS.get('vscode')
    if not cmd:
        return False, 'No editor found (install cursor or code CLI)'
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
            self.respond({'ok': True, 'editor': editor, 'editors': EDITORS})

        elif self.path.startswith('/job/'):
            job_id = self.path.split('/')[-1]
            if job_id in jobs:
                self.respond(jobs[job_id])
            else:
                self.respond({'error': 'not found'}, 404)
        else:
            self.respond({'error': 'not found'}, 404)

    def do_POST(self):
        body = self.read_body()

        if self.path == '/install':
            command = body.get('command', '')
            project = body.get('project', '')
            if not command:
                self.respond({'ok': False, 'error': 'command required'}, 400)
                return

            job_id = f'job_{int(time.time()*1000)}'
            # Use project venv python if available
            venv_pip = os.path.join(project, 'venv', 'bin', 'pip')
            if os.path.isfile(venv_pip) and command.startswith('pip install'):
                command = command.replace('pip install', f'"{venv_pip}" install', 1)

            threading.Thread(
                target=run_install, args=(job_id, command, project), daemon=True
            ).start()
            self.respond({'ok': True, 'job_id': job_id})

        elif self.path == '/install-ai':
            command  = body.get('command', '')
            prompt   = body.get('prompt', '')
            project  = body.get('project', '')
            editor   = body.get('editor', 'cursor')

            # 1. Run install command
            if command and not command.startswith('#'):
                job_id = f'job_{int(time.time()*1000)}'
                venv_pip = os.path.join(project, 'venv', 'bin', 'pip')
                if os.path.isfile(venv_pip) and command.startswith('pip install'):
                    command = command.replace('pip install', f'"{venv_pip}" install', 1)
                threading.Thread(
                    target=run_install, args=(job_id, command, project), daemon=True
                ).start()

            # 2. Open editor with project
            ok, err = open_editor(editor, project)

            # 3. Write AI prompt to a temp file the editor can pick up
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
    print(f'AI Dev Installer bridge — listening on http://localhost:{PORT}')
    print(f'  cursor: {EDITORS["cursor"] or "not found"}')
    print(f'  vscode: {EDITORS["vscode"] or "not found"}')
    print('  Press Ctrl+C to stop.')
    HTTPServer(('localhost', PORT), Handler).serve_forever()
