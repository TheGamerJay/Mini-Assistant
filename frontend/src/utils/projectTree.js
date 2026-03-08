/**
 * projectTree.js — Nested file tree model for Mini Assistant
 *
 * ProjectTree (version 2) shape:
 *   { version: 2, id, name, root: FileNode[], created_at, updated_at }
 *
 * FileNode shape:
 *   { id, name, path, type: 'file'|'folder',
 *     content?,   // text files
 *     dataUrl?,   // binary/asset files (base64 data URL)
 *     children?,  // folder nodes only
 *     metadata: { locked, source, created_at, updated_at, mime } }
 *
 * Backward compatible: all helpers accept v1 (flat) or v2 (tree) projects.
 * Migration: flatToTree() converts v1 → v2.  treeToFlat() converts v2 → v1.
 */

// ── ID generation ─────────────────────────────────────────────────────────────
let _idCounter = 0;
const genId = () => `fn_${Date.now()}_${++_idCounter}`;

// ── MIME detection ────────────────────────────────────────────────────────────
const MIME_MAP = {
  html: 'text/html', htm: 'text/html',
  css: 'text/css',
  js: 'application/javascript', mjs: 'application/javascript',
  ts: 'application/typescript', tsx: 'application/typescript',
  json: 'application/json',
  md: 'text/markdown', markdown: 'text/markdown',
  txt: 'text/plain',
  py: 'text/x-python',
  rb: 'text/x-ruby',
  rs: 'text/x-rust',
  go: 'text/x-go',
  java: 'text/x-java',
  sh: 'text/x-shellscript', bash: 'text/x-shellscript',
  yaml: 'text/yaml', yml: 'text/yaml',
  toml: 'text/x-toml',
  env: 'text/plain',
  svg: 'image/svg+xml',
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
  gif: 'image/gif', ico: 'image/x-icon', webp: 'image/webp',
  woff: 'font/woff', woff2: 'font/woff2', ttf: 'font/ttf',
  pdf: 'application/pdf',
  zip: 'application/zip',
};

export const guessMime = (name) => {
  const ext = (name || '').split('.').pop().toLowerCase();
  return MIME_MAP[ext] || 'text/plain';
};

// ── Node factories ────────────────────────────────────────────────────────────
export const makeFileNode = (name, path, content = '', opts = {}) => {
  const now = new Date().toISOString();
  return {
    id: opts.id || genId(),
    name,
    path,
    type: 'file',
    content,
    dataUrl: opts.dataUrl || null,
    metadata: {
      locked:     opts.locked     ?? false,
      source:     opts.source     || 'generated',
      created_at: opts.created_at || now,
      updated_at: opts.updated_at || now,
      mime:       opts.mime       || guessMime(name),
    },
  };
};

export const makeFolderNode = (name, path, children = [], opts = {}) => {
  const now = new Date().toISOString();
  return {
    id: opts.id || genId(),
    name,
    path,
    type: 'folder',
    children,
    metadata: {
      locked:     false,
      source:     opts.source || 'generated',
      created_at: opts.created_at || now,
      updated_at: opts.updated_at || now,
    },
  };
};

// ── Version detection ─────────────────────────────────────────────────────────
export const isV2 = (project) => project?.version === 2;

// ── Migration: flat v1 → tree v2 ─────────────────────────────────────────────
export const flatToTree = (oldProject, id = null, name = 'project') => {
  if (!oldProject) return null;
  if (isV2(oldProject)) return oldProject;

  const now = new Date().toISOString();
  const oldMeta = oldProject.file_metadata || {};

  const metaFor = (filename) => {
    const m = oldMeta[filename] || {};
    return {
      locked:     m.locked     || false,
      created_at: m.created_at || now,
      updated_at: m.updated_at || now,
    };
  };

  const root = [];

  if (oldProject.index_html) root.push(makeFileNode('index.html', 'index.html', oldProject.index_html, { ...metaFor('index.html'), mime: 'text/html' }));
  if (oldProject.style_css)  root.push(makeFileNode('style.css',  'style.css',  oldProject.style_css,  { ...metaFor('style.css'),  mime: 'text/css' }));
  if (oldProject.script_js)  root.push(makeFileNode('script.js',  'script.js',  oldProject.script_js,  { ...metaFor('script.js'),  mime: 'application/javascript' }));
  if (oldProject.readme)     root.push(makeFileNode('README.md',  'README.md',  oldProject.readme,     { mime: 'text/markdown' }));

  for (const ef of (oldProject.extra_files || [])) {
    root.push(makeFileNode(ef.name, ef.name, ef.content || '', { ...metaFor(ef.name) }));
  }

  const assets = oldProject.assets || [];
  if (assets.length > 0) {
    const assetNodes = assets.map(a =>
      makeFileNode(a.name, `assets/${a.name}`, '', {
        dataUrl: a.dataUrl,
        mime:    a.type || guessMime(a.name),
        source:  'imported',
      })
    );
    root.push(makeFolderNode('assets', 'assets', assetNodes));
  }

  return {
    version:    2,
    id:         id || genId(),
    name,
    root,
    created_at: now,
    updated_at: now,
  };
};

// ── Ensure v2 (migrate in-place if needed) ───────────────────────────────────
export const ensureV2 = (project, id, name) => {
  if (!project) return null;
  if (isV2(project)) return project;
  return flatToTree(project, id, name);
};

// ── Migration: tree v2 → flat v1 (backward compat for any old callers) ────────
export const treeToFlat = (tree) => {
  if (!tree) return {};
  if (!isV2(tree)) return tree;

  const SPECIAL = new Set(['index.html', 'style.css', 'script.js', 'README.md']);
  const allFiles = getAllFileNodes(tree);

  return {
    version:    1,
    index_html: getContent(tree, 'index.html'),
    style_css:  getContent(tree, 'style.css'),
    script_js:  getContent(tree, 'script.js'),
    readme:     getContent(tree, 'README.md'),
    extra_files: allFiles
      .filter(n => !n.dataUrl && !SPECIAL.has(n.path))
      .map(n => ({ name: n.name, content: n.content || '' })),
    assets: allFiles
      .filter(n => n.dataUrl)
      .map(n => ({ name: n.name, type: n.metadata?.mime || '', dataUrl: n.dataUrl })),
    file_metadata: Object.fromEntries(
      allFiles
        .filter(n => n.metadata?.locked)
        .map(n => [n.path, { locked: true }])
    ),
  };
};

// ── Tree traversal ────────────────────────────────────────────────────────────
export const getAllFileNodes = (project) => {
  if (!isV2(project)) return [];
  const files = [];
  const traverse = (nodes) => {
    for (const node of (nodes || [])) {
      if (node.type === 'file') files.push(node);
      else if (node.type === 'folder') traverse(node.children);
    }
  };
  traverse(project.root);
  return files;
};

export const findNode = (project, path) => {
  if (!isV2(project)) return null;
  const traverse = (nodes) => {
    for (const node of (nodes || [])) {
      if (node.path === path) return node;
      if (node.type === 'folder') {
        const found = traverse(node.children);
        if (found) return found;
      }
    }
    return null;
  };
  return traverse(project.root);
};

export const getAllPaths = (project) => {
  if (!isV2(project)) {
    const paths = [];
    if (project?.index_html) paths.push('index.html');
    if (project?.style_css)  paths.push('style.css');
    if (project?.script_js)  paths.push('script.js');
    if (project?.readme)     paths.push('README.md');
    (project?.extra_files || []).forEach(ef => paths.push(ef.name));
    return paths;
  }
  return getAllFileNodes(project).map(n => n.path);
};

// ── Content get/set (v1 and v2 compatible) ───────────────────────────────────
const V1_FLAT_MAP = {
  'index.html': 'index_html',
  'style.css':  'style_css',
  'script.js':  'script_js',
  'README.md':  'readme',
};

export const getContent = (project, path) => {
  if (!project) return '';
  if (isV2(project)) {
    return findNode(project, path)?.content || '';
  }
  if (V1_FLAT_MAP[path]) return project[V1_FLAT_MAP[path]] || '';
  const ef = (project.extra_files || []).find(f => f.name === path);
  return ef?.content || '';
};

export const setContent = (project, path, value) => {
  if (!project) return project;
  if (isV2(project)) return _updateNodeContent(project, path, value);
  const p = { ...project };
  if (V1_FLAT_MAP[path]) p[V1_FLAT_MAP[path]] = value;
  else p.extra_files = (p.extra_files || []).map(f => f.name === path ? { ...f, content: value } : f);
  return p;
};

const _updateNodeContent = (project, path, value) => {
  const now = new Date().toISOString();
  const update = (nodes) => nodes.map(node => {
    if (node.path === path && node.type === 'file') {
      return { ...node, content: value, metadata: { ...node.metadata, updated_at: now } };
    }
    if (node.type === 'folder') return { ...node, children: update(node.children || []) };
    return node;
  });
  return { ...project, root: update(project.root), updated_at: now };
};

// ── File metadata (locked etc) ───────────────────────────────────────────────
export const getFileMeta = (project, path) => {
  if (!project) return {};
  if (isV2(project)) return findNode(project, path)?.metadata || {};
  return project.file_metadata?.[path] || {};
};

export const setFileMeta = (project, path, patch) => {
  if (!project) return project;
  const now = new Date().toISOString();
  if (isV2(project)) {
    const update = (nodes) => nodes.map(node => {
      if (node.path === path) return { ...node, metadata: { ...node.metadata, ...patch, updated_at: now } };
      if (node.type === 'folder') return { ...node, children: update(node.children || []) };
      return node;
    });
    return { ...project, root: update(project.root) };
  }
  return {
    ...project,
    file_metadata: {
      ...(project.file_metadata || {}),
      [path]: { ...(project.file_metadata?.[path] || {}), ...patch, updated_at: now },
    },
  };
};

// ── Assets and extra files ────────────────────────────────────────────────────
export const getAssets = (project) => {
  if (!project) return [];
  if (!isV2(project)) return project.assets || [];
  return getAllFileNodes(project)
    .filter(n => n.dataUrl)
    .map(n => ({ name: n.name, type: n.metadata?.mime || '', dataUrl: n.dataUrl, path: n.path }));
};

export const getExtraFiles = (project) => {
  if (!project) return [];
  if (!isV2(project)) return project.extra_files || [];
  const SPECIAL = new Set(['index.html', 'style.css', 'script.js', 'README.md']);
  return getAllFileNodes(project)
    .filter(n => !n.dataUrl && !SPECIAL.has(n.path))
    .map(n => ({ name: n.name, path: n.path, content: n.content || '' }));
};

// ── HTML reconstruction (v1 and v2) ──────────────────────────────────────────
export const reconstructHtmlFromProject = (project) => {
  if (!project) return '';
  const html = getContent(project, 'index.html');
  const css  = getContent(project, 'style.css');
  const js   = getContent(project, 'script.js');
  return _inlineHtml(html, css, js);
};

const _inlineHtml = (html, css, js) => {
  if (!html) return '';
  let out = html;
  if (css) {
    if (/< *link[^>]*href=["']style\.css["'][^>]*>/i.test(out)) {
      out = out.replace(/< *link[^>]*href=["']style\.css["'][^>]*>/gi, `<style>\n${css}\n</style>`);
    } else if (!/<style[\s>]/i.test(out)) {
      out = out.replace('</head>', `<style>\n${css}\n</style>\n</head>`);
    }
  }
  if (js) {
    if (/< *script[^>]*src=["']script\.js["'][^>]*><\/script>/i.test(out)) {
      out = out.replace(/< *script[^>]*src=["']script\.js["'][^>]*><\/script>/gi, `<script>\n${js}\n</script>`);
    } else if (!/<script[\s>]/i.test(out)) {
      out = out.replace('</body>', `<script>\n${js}\n</script>\n</body>`);
    }
  }
  return out;
};

// ── Tree mutation helpers ─────────────────────────────────────────────────────
export const addNodeToTree = (project, node, parentPath = null) => {
  if (!isV2(project)) return project;
  const now = new Date().toISOString();
  if (!parentPath) {
    return { ...project, root: [...project.root, node], updated_at: now };
  }
  const addTo = (nodes) => nodes.map(n => {
    if (n.path === parentPath && n.type === 'folder') {
      return { ...n, children: [...(n.children || []), node] };
    }
    if (n.type === 'folder') return { ...n, children: addTo(n.children || []) };
    return n;
  });
  return { ...project, root: addTo(project.root), updated_at: now };
};

export const removeNodeFromTree = (project, path) => {
  if (!isV2(project)) return project;
  const now = new Date().toISOString();
  const remove = (nodes) => nodes
    .filter(n => n.path !== path)
    .map(n => n.type === 'folder' ? { ...n, children: remove(n.children || []) } : n);
  return { ...project, root: remove(project.root), updated_at: now };
};

export const renameNode = (project, oldPath, newName) => {
  if (!isV2(project)) return project;
  const now = new Date().toISOString();
  const parentPath = oldPath.includes('/') ? oldPath.split('/').slice(0, -1).join('/') : null;
  const newPath = parentPath ? `${parentPath}/${newName}` : newName;
  const rename = (nodes) => nodes.map(n => {
    if (n.path === oldPath) return { ...n, name: newName, path: newPath, metadata: { ...n.metadata, updated_at: now } };
    if (n.type === 'folder') return { ...n, children: rename(n.children || []) };
    return n;
  });
  return { ...project, root: rename(project.root), updated_at: now };
};
