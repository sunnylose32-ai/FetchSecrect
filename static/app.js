/* ─────────────────────────────────────────────────────────────────────────────
   TeleLink — Supabase JavaScript Client & Shared Logic
───────────────────────────────────────────────────────────────────────────── */

'use strict';

// ── Supabase Configuration ───────────────────────────────────────────────────
// These are now loaded automatically from /static/config.js (from your .env)
const SUPABASE_URL = window.SUPABASE_URL;
const SUPABASE_KEY = window.SUPABASE_KEY; 

let sb = null;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error("❌ Supabase keys not found in window. Are you running via main.py?");
} else {
  if (typeof supabase !== 'undefined') {
    sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
  } else {
    console.error("❌ Supabase library (CDN) not loaded.");
  }
}

// ── Auth Helpers ─────────────────────────────────────────────────────────────

async function signUp(email, password) {
  if (!sb) throw new Error("Supabase is not initialized.");
  const { data, error } = await sb.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

async function logIn(email, password) {
  if (!sb) throw new Error("Supabase is not initialized.");
  const { data, error } = await sb.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

async function logOut() {
  if (!sb) return;
  const { error } = await sb.auth.signOut();
  if (error) throw error;
  window.location.href = '/';
}

async function getSession() {
  if (!sb) return null;
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
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}

// ── UI Helpers ───────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return 'N/A';
  return new Date(iso).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' });
}

function getStatusBadge(status) {
  const s = status ? status.toLowerCase() : 'pending';
  return `<span class="badge badge-${s}">${status || 'Pending'}</span>`;
}
