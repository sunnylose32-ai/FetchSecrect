/* ─────────────────────────────────────────────────────────────────────────────
   TeleLink — Supabase JavaScript Client & Shared Logic
───────────────────────────────────────────────────────────────────────────── */

'use strict';

// ── Supabase Configuration ───────────────────────────────────────────────────
// These will be injected by the server or defined here. 
// NOTE: For best security, use placeholders that the user can fill in .env
const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_KEY = "YOUR_SUPABASE_KEY"; 

// Initialize Supabase Client (This requires the Supabase JS lib in the HTML)
let sb = null;
if (typeof supabase !== 'undefined') {
  sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
}

// ── Auth Helpers ─────────────────────────────────────────────────────────────

async function signUp(email, password) {
  const { data, error } = await sb.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

async function logIn(email, password) {
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

async function logOut() {
  const { error } = await sb.auth.signOut();
  if (error) throw error;
  window.location.href = 'index.html';
}

async function getSession() {
  const { data } = await sb.auth.getSession();
  return data.session;
}

// ── Toast Notifications ──────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ── UI Helpers ───────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return 'N/A';
  return new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
}

function getStatusBadge(status) {
  const s = status.toLowerCase();
  return `<span class="badge badge-${s}">${status}</span>`;
}
