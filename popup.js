const BRIDGE = 'http://localhost:9876';

// ── Package detection (fast local fallback) ──────────────────────────────────
function detect(url) {
  try {
    const u = new URL(url);
    const h = u.hostname;
    const p = u.pathname.split('/').filter(Boolean);

    if (h === 'github.com' && p.length >= 2) {
      const clean = url.split('?')[0].split('#')[0];
      return {
        type: 'github', badge: 'bg', badgeText: 'GitHub',
        name: `${p[0]}/${p[1]}`,
        cmd:  `pip3 install git+${clean}`,   // placeholder — smart-detect will replace this
        aiPrompt: `Install ${clean} — detect the right package manager and run the correct command. Show a usage example.`,
        url,
      };
    }
    if (h === 'pypi.org' && p[0] === 'project' && p[1]) {
      return {
        type: 'pip', badge: 'bp', badgeText: 'pip',
        name: p[1],
        cmd:  `pip3 install ${p[1]}`,
        aiPrompt: `pip3 install ${p[1]} — add to requirements.txt and show a quick usage snippet.`,
        url,
      };
    }
    if ((h === 'npmjs.com' || h === 'www.npmjs.com') && p[0] === 'package' && p[1]) {
      return {
        type: 'npm', badge: 'bn', badgeText: 'npm',
        name: p[1],
        cmd:  `npm install ${p[1]}`,
        aiPrompt: `npm install ${p[1]} — add to package.json and show usage.`,
        url,
      };
    }
    return {
      type: 'url', badge: 'bu', badgeText: 'URL',
      name: h, cmd: `# ${url}`,
      aiPrompt: `Help me use: ${url}`, url,
    };
  } catch {
    return { type: 'url', badge: 'bu', badgeText: 'URL', name: '—', cmd: '—', aiPrompt: '', url: '' };
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(ico, txt) {
  document.getElementById('status-ico').textContent = ico;
  document.getElementById('status-txt').textContent = txt;
}
function setBridge(ok) {
  const dot = document.getElementById('bdot');
  const lbl = document.getElementById('blbl');
  if (ok) { dot.className = 'dot g'; lbl.textContent = 'Bridge online — smart detection ready'; }
  else     { dot.className = 'dot r'; lbl.textContent = 'Bridge offline — clipboard fallback'; }
}
async function clip(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { return false; }
}
function setCmdDisplay(text, source) {
  document.getElementById('cmd-text').textContent = text;
  const badge = document.getElementById('detect-badge');
  if (source === 'readme') {
    badge.textContent = 'from README';
    badge.style.display = 'inline';
  } else if (source === 'fallback') {
    badge.textContent = 'fallback';
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
}

// ── Bridge calls ──────────────────────────────────────────────────────────────
async function bridgeSmartDetect(url) {
  const r = await fetch(`${BRIDGE}/smart-detect`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
    signal: AbortSignal.timeout(10000),
  });
  return r.json();
}
async function bridgeInstall(cmd, project) {
  const r = await fetch(`${BRIDGE}/install`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd, project }),
    signal: AbortSignal.timeout(4000),
  });
  return r.json();
}
async function bridgeOpenVSCode(project) {
  const r = await fetch(`${BRIDGE}/open-editor`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ editor: 'vscode', project }),
    signal: AbortSignal.timeout(4000),
  });
  return r.json();
}

// ── Main ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const pkg = detect(tab?.url || '');

  // currentCmd is what gets sent to the bridge — updated by smart-detect
  let currentCmd = pkg.cmd;
  let allCommands = [];   // all detected commands from README

  // Populate static UI
  const badgeEl = document.getElementById('pkg-badge');
  badgeEl.className = `badge ${pkg.badge}`;
  badgeEl.textContent = pkg.badgeText;
  document.getElementById('pkg-name').textContent = pkg.name;
  setCmdDisplay(pkg.cmd, null);

  // Check bridge
  let bridgeOk = false;
  try {
    const s = await fetch(`${BRIDGE}/status`, { signal: AbortSignal.timeout(1500) });
    bridgeOk = s.ok;
  } catch {}
  setBridge(bridgeOk);

  // Load saved projects
  const { projects = [], lastProject = '' } = await chrome.storage.local.get(['projects', 'lastProject']);
  const sel = document.getElementById('proj-sel');
  projects.forEach(p => {
    const o = document.createElement('option');
    o.value = p.path; o.textContent = p.name;
    sel.insertBefore(o, sel.querySelector('[value="__add__"]'));
  });
  if (lastProject) sel.value = lastProject;

  sel.addEventListener('change', async () => {
    if (sel.value === '__add__') {
      const path = prompt('Full project path:');
      const name = prompt('Display name:');
      if (path && name) {
        const all = (await chrome.storage.local.get('projects')).projects || [];
        all.push({ path, name });
        await chrome.storage.local.set({ projects: all });
        const o = document.createElement('option');
        o.value = path; o.textContent = name;
        sel.insertBefore(o, sel.querySelector('[value="__add__"]'));
        sel.value = path;
      } else sel.value = '';
    }
    if (sel.value) chrome.storage.local.set({ lastProject: sel.value });
  });

  // Smart detect: fetch README and find the real install command
  if (pkg.type === 'github' && bridgeOk) {
    setStatus('🔍', 'Reading README…');
    setCmdDisplay('⏳ detecting…', null);
    try {
      const data = await bridgeSmartDetect(pkg.url);
      if (data.ok && data.recommended) {
        currentCmd = data.recommended;
        allCommands = data.commands || [];
        setCmdDisplay(currentCmd, data.source);

        if (data.source === 'readme') {
          setStatus('✅', `Detected from README (${data.commands.length} option${data.commands.length > 1 ? 's' : ''})`);
          // If multiple options found, populate the command picker
          if (allCommands.length > 1) renderCmdPicker(allCommands, (cmd) => { currentCmd = cmd; });
        } else {
          setStatus('🟡', 'No install found in README — using git+URL');
        }
      } else {
        currentCmd = pkg.cmd;
        setCmdDisplay(currentCmd, null);
        setStatus('🟡', 'Could not read README — using default');
      }
    } catch {
      currentCmd = pkg.cmd;
      setCmdDisplay(currentCmd, null);
      setStatus('🟡', 'Detection timed out — using default');
    }
  } else {
    setStatus('🟡', 'Ready');
  }

  // ── Copy command ────────────────────────────────────────────────────────────
  document.getElementById('copy-cmd').addEventListener('click', async () => {
    await clip(currentCmd);
    document.getElementById('copy-cmd').textContent = '✓';
    setTimeout(() => { document.getElementById('copy-cmd').textContent = '⎘'; }, 1500);
  });

  // ── ONE-CLICK: Install + open VS Code ──────────────────────────────────────
  document.getElementById('btn-one-click').addEventListener('click', async () => {
    const project = sel.value;
    const btn = document.getElementById('btn-one-click');
    btn.textContent = '⏳ Working…';
    btn.disabled = true;

    if (bridgeOk && currentCmd !== '—') {
      try {
        setStatus('🔧', 'Opening VS Code + running install…');
        await bridgeInstall(currentCmd, project);
        setStatus('✅', 'VS Code opened — install running in integrated terminal');
        btn.textContent = '✅ Done!';
        btn.style.background = '#238636';
      } catch (e) {
        setStatus('⚠️', 'Bridge error — copying to clipboard');
        await clip(currentCmd);
        chrome.tabs.create({ url: `vscode://file/${encodeURIComponent(project || '')}` });
        setStatus('📋', 'Command copied — paste in VS Code terminal');
        btn.textContent = '📋 Copied!';
      }
    } else {
      await clip(currentCmd);
      const uri = project ? `vscode://file/${encodeURIComponent(project)}` : 'vscode://';
      chrome.tabs.create({ url: uri });
      setStatus('📋', 'Copied command — paste in VS Code terminal');
      btn.textContent = '📋 Copied!';
    }

    setTimeout(() => {
      btn.textContent = '⚡ Install & Open VS Code';
      btn.disabled = false;
      btn.style.background = '';
    }, 3000);
  });

  // ── Just open VS Code ───────────────────────────────────────────────────────
  document.getElementById('btn-vscode-only').addEventListener('click', async () => {
    const project = sel.value;
    setStatus('📂', 'Opening VS Code…');
    if (bridgeOk) {
      try { await bridgeOpenVSCode(project); setStatus('✅', 'VS Code opened!'); return; } catch {}
    }
    const uri = project ? `vscode://file/${encodeURIComponent(project)}` : 'vscode://';
    chrome.tabs.create({ url: uri });
    setStatus('✅', 'VS Code opened via URI');
  });

  // ── Copy all ────────────────────────────────────────────────────────────────
  document.getElementById('btn-copy-all').addEventListener('click', async () => {
    const full = `${currentCmd}\n\n# AI prompt:\n# ${pkg.aiPrompt}`;
    await clip(full);
    setStatus('📋', 'Install command + AI prompt copied!');
    setTimeout(() => setStatus('🟡', 'Ready'), 3000);
  });
});

// ── Command picker (shown when README has multiple install options) ──────────
function renderCmdPicker(commands, onChange) {
  const container = document.getElementById('cmd-picker');
  if (!container) return;
  container.innerHTML = '';
  container.style.display = 'block';

  const lbl = document.createElement('div');
  lbl.className = 'sect-lbl';
  lbl.textContent = 'Multiple methods detected — pick one:';
  lbl.style.cssText = 'font-size:10px;color:#8b949e;padding:4px 10px 3px;text-transform:uppercase;letter-spacing:.6px';
  container.appendChild(lbl);

  const sel = document.createElement('select');
  sel.style.cssText = 'width:calc(100% - 20px);margin:0 10px 6px;background:#161b22;border:1px solid #30363d;border-radius:5px;color:#e6edf3;padding:6px 8px;font-size:11px;font-family:\'SF Mono\',monospace';
  commands.forEach((c, i) => {
    const o = document.createElement('option');
    o.value = c.cmd;
    o.textContent = `[${c.type}] ${c.cmd.length > 48 ? c.cmd.slice(0, 45) + '…' : c.cmd}`;
    if (i === 0) o.selected = true;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => {
    document.getElementById('cmd-text').textContent = sel.value;
    onChange(sel.value);
  });
  container.appendChild(sel);
}
