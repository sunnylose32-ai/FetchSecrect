/* ─────────────────────────────────────────────────────────────────────────────
   TeleLink — Shared JavaScript Utilities
   Auth helpers, API wrappers, toast notifications
───────────────────────────────────────────────────────────────────────────── */

'use strict';

// ── Constants ──────────────────────────────────────────────────────────────────
const SESSION_KEY = 'tl_session_token';
const USER_KEY    = 'tl_user';

// ── Session Helpers ────────────────────────────────────────────────────────────
function getSessionToken() { return localStorage.getItem(SESSION_KEY); }
function setSession(token, user) {
  localStorage.setItem(SESSION_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
function clearSession() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(USER_KEY);
}
function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
  catch { return null; }
}

// ── API Helpers ────────────────────────────────────────────────────────────────
async function apiCall(method, path, body = null, token = null) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['X-Session-Token'] = token;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ detail: res.statusText }));

  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

// ── Auth check — redirect to /login if not authenticated ──────────────────────
async function requireAuth() {
  const token = getSessionToken();
  if (!token) { window.location.href = '/login'; return null; }
  try {
    const data = await apiCall('GET', '/api/auth/me', null, token);
    return data.user;
  } catch {
    clearSession();
    window.location.href = '/login';
    return null;
  }
}

// ── Redirect to /tool if already logged in ─────────────────────────────────────
async function redirectIfLoggedIn() {
  const token = getSessionToken();
  if (!token) return;
  try {
    await apiCall('GET', '/api/auth/me', null, token);
    window.location.href = '/tool';
  } catch {
    clearSession();
  }
}

// ── Logout ─────────────────────────────────────────────────────────────────────
async function logout() {
  const token = getSessionToken();
  if (token) {
    try { await apiCall('POST', '/api/auth/logout', null, token); } catch {}
  }
  clearSession();
  window.location.href = '/';
}

// ── Toast Notifications ────────────────────────────────────────────────────────
function ensureToastContainer() {
  if (!document.getElementById('toast-container')) {
    const c = document.createElement('div');
    c.id = 'toast-container';
    document.body.appendChild(c);
  }
  return document.getElementById('toast-container');
}

function showToast(message, type = 'info', duration = 4000) {
  const container = ensureToastContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.textContent = `${icon}  ${message}`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = '0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Format file size ───────────────────────────────────────────────────────────
function fmtSize(bytes) {
  if (!bytes) return '';
  const units = ['B','KB','MB','GB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return `${bytes.toFixed(1)} ${units[i]}`;
}

// ── Format date ────────────────────────────────────────────────────────────────
function fmtDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium', timeStyle: 'short'
    });
  } catch { return iso; }
}

// ── Media type icon ────────────────────────────────────────────────────────────
function mediaIcon(type) {
  const map = {
    photo: '🖼️', video: '🎬', audio: '🎵', voice: '🎤',
    document: '📄', sticker: '🎭', animation: '🎞️', file: '📁'
  };
  return map[type] || '📁';
}

// ── Copy text to clipboard ─────────────────────────────────────────────────────
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('Copied to clipboard!', 'success', 2000);
  } catch {
    showToast('Could not copy', 'error', 2000);
  }
}
