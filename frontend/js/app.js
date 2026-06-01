/**
 * js/app.js — Shared application state, API client, and shared UI components
 * Loaded on every page.  MVC: Service + shared View helpers.
 */

/* ── Config ── */
// Use a relative path so the frontend always talks to the server that served it.
// This prevents connectivity issues when switching between localhost and 127.0.0.1.
const API_BASE = window.EXAMPREP_API || '/api/v1';
const MOCK_ALLOWED = false; // Set to false to force real API calls and see actual errors

/* ── State ── */
const State = {
  user: null,
  purchases: [],

  init() {
    const raw = localStorage.getItem('ep_user');
    if (raw) try { this.user = JSON.parse(raw); } catch {}
    const rawP = localStorage.getItem('ep_purchases');
    if (rawP) try { this.purchases = JSON.parse(rawP); } catch {}
  },

  setUser(user) {
    this.user = user;
    if (user) localStorage.setItem('ep_user', JSON.stringify(user));
    else { localStorage.removeItem('ep_user'); localStorage.removeItem('ep_token'); localStorage.removeItem('ep_refresh'); }
  },

  logout() {
    this.user = null;
    this.purchases = [];
    localStorage.removeItem('ep_user');
    localStorage.removeItem('ep_token');
    localStorage.removeItem('ep_refresh');
    localStorage.removeItem('ep_purchases');
  },

  hasPurchased(examId) {
    return this.purchases.includes(examId);
  },

  addPurchase(examId) {
    if (!this.purchases.includes(examId)) {
      this.purchases.push(examId);
      localStorage.setItem('ep_purchases', JSON.stringify(this.purchases));
    }
  },

  getToken() { return localStorage.getItem('ep_token'); },
  setToken(t, r) {
    localStorage.setItem('ep_token', t);
    if (r) localStorage.setItem('ep_refresh', r);
  },
};

/* ── API Client ── */
const API = {
  async request(method, path, body = null, auth = true) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && State.getToken()) headers['Authorization'] = `Bearer ${State.getToken()}`;
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method, headers,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json();
    } catch (e) {
      // For demo mode (no backend) return mock data
      if (MOCK_ALLOWED && (e.message.includes('fetch') || e.message.includes('Failed to fetch'))) {
        console.warn(`[API] Connection failed to ${API_BASE}${path}. Falling back to MOCK mode. Data will not be persisted.`);
        return API._mockFallback(method, path, body);
      }
      throw e;
    }
  },

  // ── Mock fallback for demo without backend ────────────────────
  _mockFallback(method, path, body) {
    if (path.includes('/auth/login') || path.includes('/auth/register')) {
      const email = body?.email || 'user@demo.com';
      // Improved captcha validation mock (Answer is always 123456 in mock mode)
      if (path.includes('/auth/register')) {
        if (!body?.captcha_id || !body?.captcha_answer) throw new Error('Captcha verification required');
        if (body.captcha_answer !== '123456') throw new Error('Invalid captcha verification code');
      }
      const user = { id: 'u1', username: email.split('@')[0], email, role: email.includes('admin') ? 'admin' : 'user' };
      const token = 'demo_token_' + Date.now();
      return { access_token: token, refresh_token: token + '_r', token_type: 'bearer', user_id: 'u1', role: user.role, _user: user };
    }
    if (path.includes('/auth/me')) return State.user;
    if (path.includes('/auth/captcha')) {
      // Mock captcha always shows "123456"
      return { 
        id: 'mock_captcha_id', 
        image_url: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTUwIiBoZWlnaHQ9IjUwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMDAlIiBoZWlnaHQ9IjEwMCUiIGZpbGw9IiNiNmUzZjQiLz48dGV4dCB4PSI1MCUiIHk9IjUwJSIgZG9taW5hbnQtYmFzZWxpbmU9Im1pZGRsZSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZm9udC1mYW1pbHk9Im1vbm9zcGFjZSIgZm9udC1zaXplPSIyOCIgZm9udC13ZWlnaHQ9ImJvbGQiIGZpbGw9IiMwMDMzNjYiPjEyMzQ1NjwvdGV4dD48L3N2Zz4='
      };
    }
    if (path === '/exams' && method === 'GET') return { items: MOCK_EXAMS, total: MOCK_EXAMS.length, page: 1, page_size: 12, total_pages: 1 };
    if (path.startsWith('/exams/') && method === 'GET') {
      const segments = path.split('/');
      // Check if it's a package request: /exams/{id}/packages
      if (segments.length > 3 && segments[3] === 'packages') return MOCK_PACKAGES;
      // Otherwise it's an exam detail request: /exams/{slug}
      const slug = segments[2];
      return MOCK_EXAMS.find(e => e.slug === slug) || MOCK_EXAMS[0];
    }
    if (path.includes('/attempts') && method === 'POST') return { id: 'att_' + Date.now(), status: 'in_progress', total_questions: 5 };
    if (path.includes('/finish')) return { attempt_id: 'att1', score: 80, correct_count: 4, total_questions: 5, passed: true, time_spent_seconds: 300, answers: [], pass_score_pct: 72 };
    if (path.includes('/payments/checkout')) return { checkout_url: '#', session_id: 'demo_session' };
    if (path.includes('/ai/hint')) return { hint: 'Think about the access frequency and cost trade-offs for each storage class.' };
    return {};
  },

  auth: {
    getCaptcha: () => API.request('GET',  '/auth/captcha', null, false),
    login:    (d) => API.request('POST', '/auth/login', d, false),
    register: (d) => API.request('POST', '/auth/register', d, false),
    me:       ()  => API.request('GET',  '/auth/me'),
    logout:   (rt) => API.request('POST', '/auth/logout', { refresh_token: rt }),
  },
  exams: {
    list:        (p = {}) => API.request('GET', '/exams?' + new URLSearchParams(p), null, false),
    get:         (slug)   => API.request('GET', `/exams/${slug}`, null, false),
    packages:    (eid)    => API.request('GET', `/exams/${eid}/packages`),
    questions:   (eid, pid) => API.request('GET', `/exams/${eid}/packages/${pid}/questions`),
    create:      (d)      => API.request('POST', '/exams', d),
    update:      (id, d)  => API.request('PATCH', `/exams/${id}`, d),
    addPackage:  (eid, d) => API.request('POST', `/exams/${eid}/packages`, d),
    addQuestion: (eid, pid, d) => API.request('POST', `/exams/${eid}/packages/${pid}/questions`, d),
    leaderboard: (eid, n=10) => API.request('GET', `/exams/${eid}/leaderboard?top_n=${n}`, null, false),
    analytics:   (eid)    => API.request('GET', `/exams/${eid}/analytics`),
  },
  attempts: {
    start:  (pkgId)  => API.request('POST', '/attempts', { package_id: pkgId }),
    answer: (id, d)  => API.request('POST', `/attempts/${id}/answers`, d),
    finish: (id)     => API.request('POST', `/attempts/${id}/finish`),
    list:   (page=1) => API.request('GET',  `/attempts?page=${page}`),
  },
  payments: {
    checkout:    (examId) => API.request('POST', '/payments/checkout', { exam_id: examId }),
    myPurchases: ()       => API.request('GET',  '/payments/my-purchases'),
  },
  ai: {
    hint:    (qid, q) => API.request('POST', '/ai/hint', { question_id: qid, user_question: q }),
    explain: (qid)    => API.request('GET',  `/ai/explain/${qid}`),
  },
  users: {
    stats:         ()    => API.request('GET',   '/users/me/stats'),
    updateProfile: (d)   => API.request('PATCH', '/users/me', d),
    list:          (p=1) => API.request('GET',   `/users?page=${p}`),
  },
};

/* ── Mock Data ── */
let MOCK_EXAMS = [
  { 
    id:'1', 
    slug:'aws-certified-solutions-architect-associate-saa-c03', 
    title:'AWS Certified Solutions Architect – Associate (SAA-C03)', 
    category:'Cloud', 
    price:29.99, 
    students:12400, 
    questions:360, 
    description:'Master AWS architecture patterns with hands-on practice. Covers EC2, S3, VPC, RDS, Lambda, CloudFront, and all SAA-C03 exam domains.', 
    learns:['AWS core services','High-availability design','Cost optimization','Security best practices','Network architecture','Database selection'],
    requirements:['Basic understanding of cloud computing concepts', 'Experience with virtualization is helpful']
  },
  { 
    id:'4', 
    slug:'aws-certified-cloud-practitioner-clf-c02', 
    title:'AWS Certified Cloud Practitioner (CLF-C02)', 
    category:'Cloud', 
    price:14.99, 
    students:23000, 
    questions:300, 
    description:'Entry-level AWS certification covering cloud concepts, services, pricing, and support.', 
    learns:['Cloud concepts','AWS infrastructure','Core services','Security','Billing','Support plans'],
    requirements:['No prior technical background required']
  },
  { 
    id:'5', 
    slug:'professional-scrum-master-i-psm-i', 
    title:'Professional Scrum Master I (PSM I)', 
    category:'Agile', 
    price:15.00, 
    students:15000, 
    questions:80, 
    description:'Fundamental knowledge of the Scrum framework and how to apply it in real-world situations.', 
    learns:['Scrum Theory','Scrum Framework','Product Backlog management','Sprint management','Scrum Roles'],
    requirements:['Familiarity with software development lifecycle (SDLC)']
  },
];

const MOCK_PACKAGES = Array.from({length:6}, (_, i) => ({
  id: `pkg-${i+1}`, order: i+1,
  title: `Practice Test ${i+1}`,
  description: `Full-length timed exam with ${65 + i*5} questions covering all domains.`,
  question_count: 65 + i*5, time_limit_minutes: 90, pass_score_pct: 72,
}));

const MOCK_QUESTIONS = [
  { id:'q1', text:'A company needs to store 100TB of data accessed once per month at lowest cost. Which S3 storage class should they use?', type:'single', options:[{key:'A',text:'S3 Standard'},{key:'B',text:'S3 Glacier Deep Archive'},{key:'C',text:'S3 Intelligent-Tiering'},{key:'D',text:'S3 One Zone-IA'}], correct:['B'], explanation:'S3 Glacier Deep Archive is the lowest-cost storage class at ~$0.00099/GB/month. Ideal for data accessed once or twice per year.', difficulty:'medium', tags:['s3','storage'] },
  { id:'q2', text:'Which AWS services support VPC Gateway Endpoints? (Select TWO)', type:'multiple', options:[{key:'A',text:'Amazon S3'},{key:'B',text:'Amazon DynamoDB'},{key:'C',text:'Amazon EC2'},{key:'D',text:'Amazon RDS'}], correct:['A','B'], explanation:'VPC Gateway Endpoints support only Amazon S3 and DynamoDB. They enable private connectivity without internet gateway.', difficulty:'hard', tags:['vpc','networking'] },
  { id:'q3', text:'Amazon RDS Multi-AZ automatically replicates to a standby instance in the SAME Availability Zone.', type:'true_false', options:[{key:'A',text:'True'},{key:'B',text:'False'}], correct:['B'], explanation:'Multi-AZ deploys a standby replica in a DIFFERENT AZ for high availability and automatic failover.', difficulty:'easy', tags:['rds','ha'] },
  { id:'q4', text:'An application needs to process messages in strict FIFO order with exactly-once processing. Which SQS queue type should be used?', type:'single', options:[{key:'A',text:'Standard Queue'},{key:'B',text:'FIFO Queue'},{key:'C',text:'Dead Letter Queue'},{key:'D',text:'Delay Queue'}], correct:['B'], explanation:'SQS FIFO queues guarantee exactly-once delivery and strict message ordering. Standard queues offer best-effort ordering.', difficulty:'medium', tags:['sqs','messaging'] },
  { id:'q5', text:'Which EC2 pricing model offers the greatest discount (up to 90%) compared to On-Demand?', type:'single', options:[{key:'A',text:'Reserved Instances'},{key:'B',text:'Dedicated Hosts'},{key:'C',text:'Spot Instances'},{key:'D',text:'Savings Plans'}], correct:['C'], explanation:'Spot Instances can save up to 90% by using AWS spare capacity, but can be interrupted with 2-minute notice.', difficulty:'easy', tags:['ec2','pricing'] },
];

/* ── Utility helpers ── */
const Utils = {
  navigate(page, params = {}) {
    if (page === 'home')        window.location.href = '/';
    else if (page === 'login')  window.location.href = '/login';
    else if (page === 'signup') window.location.href = '/signup';
    else if (page === 'profile') window.location.href = '/profile';
    else if (page === 'admin')  window.location.href = '/admin';
    else if (page === 'my-learning') window.location.href = '/my-learning';
    else if (page === 'exam-detail') {
      const slug = params.slug || params.exam?.slug;
      window.location.href = `/detail/${slug}`;
    } else if (page === 'exam-quiz') {
      const slug = params.exam?.slug || params.slug;
      const pkgId = params.pkg?.id || params.pkgId;
      window.location.href = `/exam-quiz?slug=${slug}&pkg=${pkgId}`;
    }
  },

  qs(selector, parent = document) { return parent.querySelector(selector); },
  qsa(selector, parent = document) { return [...parent.querySelectorAll(selector)]; },

  el(tag, attrs = {}, ...children) {
    const e = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'class') e.className = v;
      else if (k === 'html') e.innerHTML = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v);
    });
    children.forEach(c => c && e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
    return e;
  },

  formatPrice(p) { return `$${Number(p).toFixed(2)}`; },
  formatNumber(n) { return Number(n).toLocaleString(); },

  getParam(key) {
    return new URLSearchParams(window.location.search).get(key);
  },

  timeAgo(date) {
    const s = Math.floor((Date.now() - new Date(date)) / 1000);
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s/60)}m ago`;
    if (s < 86400) return `${Math.floor(s/3600)}h ago`;
    return `${Math.floor(s/86400)}d ago`;
  },
};

/* ── Toast ── */
const Toast = {
  _container: null,
  init() {
    this._container = document.createElement('div');
    this._container.className = 'toast-container';
    document.body.appendChild(this._container);
  },
  show(msg, type = 'success') {
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.innerHTML = `<span>${type==='success'?'✓':type==='error'?'✕':'ℹ'}</span> ${msg}`;
    this._container.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  },
};

/* ── Modal ── */
const Modal = {
  show({ title, body, footer, size = '' }) {
    const overlay = Utils.el('div', { class: 'modal-overlay', onclick: (e) => { if (e.target === overlay) this.close(); } });
    const modal = Utils.el('div', { class: `modal ${size}` });
    modal.innerHTML = `
      <div class="modal-header">
        <h2 class="t-h2">${title}</h2>
        <button class="btn btn-ghost btn-icon" id="modal-close">${Icons.x(18)}</button>
      </div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
    `;
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    Utils.qs('#modal-close', modal).onclick = () => this.close();
    this._current = overlay;
    return modal;
  },
  close() { this._current?.remove(); this._current = null; },
};

/* ── SVG Icons ── */
const Icons = {
  search: (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
  check:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20,6 9,17 4,12"/></svg>`,
  x:      (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>`,
  chevron:(s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6,9 12,15 18,9"/></svg>`,
  chevronR:(s=16)=> `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9,18 15,12 9,6"/></svg>`,
  clock:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>`,
  users:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
  book:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
  award:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>`,
  chart:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
  logout: (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16,17 21,12 16,7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`,
  user:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  settings:(s=16)=> `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  plus:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  edit:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
  trash:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
  lock:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`,
  home:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9,22 9,12 15,12 15,22"/></svg>`,
  robot:  (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8" cy="16" r="1" fill="currentColor"/><circle cx="16" cy="16" r="1" fill="currentColor"/></svg>`,
  tag:    (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
  info:   (s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  refresh:(s=16) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>`,
};

/* ── Nav Component ── */
const Nav = {
  render(activePage = '') {
    const user = State.user;
    document.getElementById('nav-root').innerHTML = `
      <nav class="nav">
        <div class="nav-inner">
          <a href="/" class="nav-logo">
            <div class="nav-logo-icon">E</div>
            ExamPrep
          </a>
          <div class="nav-links">
            ${user ? `<a href="/my-learning" class="nav-link ${activePage==='my-learning'?'active':''}">My Learning</a>` : ''}
            ${user?.role === 'admin' ? `<a href="/admin" class="nav-link ${activePage==='admin'?'active':''}">Admin</a>` : ''}
            ${user ? `
              <div class="nav-avatar-wrap">
                <div class="nav-avatar" id="nav-avatar">${user.username[0].toUpperCase()}</div>
                <div class="nav-dropdown" id="nav-dropdown">
                  <div class="nav-user-info">
                    <div class="nav-user-name">${user.username}</div>
                    <div class="nav-user-email">${user.email}</div>
                  </div>
                  <a href="/profile" class="nav-dropdown-item">${Icons.user(16)} My Profile</a>
                  <a href="/my-learning" class="nav-dropdown-item">${Icons.book(16)} My Learning</a>
                  ${user.role==='admin' ? `<a href="/admin" class="nav-dropdown-item">${Icons.settings(16)} Admin</a>` : ''}
                  <div class="divider"></div>
                  <div class="nav-dropdown-item danger" id="nav-logout">${Icons.logout(16)} Log Out</div>
                </div>
              </div>
            ` : `
              <a href="/login" class="btn btn-ghost">Log in</a>
              <a href="/signup" class="btn btn-primary">Sign up</a>
            `}
          </div>
        </div>
      </nav>`;

    // Search
    const si = document.getElementById('nav-search-input');
    if (si) si.addEventListener('keydown', e => { if (e.key==='Enter' && si.value.trim()) window.location.href = `/?q=${encodeURIComponent(si.value.trim())}`; });

    // Dropdown
    const avatar = document.getElementById('nav-avatar');
    const dropdown = document.getElementById('nav-dropdown');
    if (avatar) {
      avatar.addEventListener('click', e => { e.stopPropagation(); dropdown.classList.toggle('open'); });
      document.addEventListener('click', () => dropdown?.classList.remove('open'));
    }

    // Logout
    document.getElementById('nav-logout')?.addEventListener('click', async () => {
      try { await API.auth.logout(localStorage.getItem('ep_refresh')); } catch {}
      State.logout();
      window.location.href = '/';
    });
  },
};

/* ── Footer Component ── */
const Footer = {
  render() {
    document.getElementById('footer-root').innerHTML = `
      <footer class="footer">
        <div class="container">
          <div class="footer-grid">
            <div>
              <span class="footer-logo">ExamPrep</span>
              <p class="footer-desc">The most effective way to pass your IT certifications on the first try.</p>
              <div class="footer-social">
                ${['🐦','💼','📘','▶'].map(s=>`<div class="footer-social-btn">${s}</div>`).join('')}
              </div>
            </div>
            <div>
              <h4>Certifications</h4>
              ${['AWS','Azure','GCP','Security+','CISSP','Kubernetes'].map(l=>`<a href="#">${l}</a>`).join('')}
            </div>
            <div>
              <h4>Company</h4>
              ${['About Us','Careers','Blog','Press','Contact'].map(l=>`<a href="#">${l}</a>`).join('')}
            </div>
            <div>
              <h4>Support</h4>
              ${['Help Center','Refund Policy','Accessibility','Privacy Policy','Terms'].map(l=>`<a href="#">${l}</a>`).join('')}
            </div>
          </div>
          <div class="footer-bottom">
            <span>© 2026 ExamPrep. All rights reserved.</span>
            <div class="footer-bottom-links">
              <a href="#">Privacy</a><a href="#">Terms</a><a href="#">Cookies</a>
            </div>
          </div>
        </div>
      </footer>`;
  },
};

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
  State.init();
  Toast.init();
  // Nav and Footer rendered by each page after calling Nav.render() / Footer.render()
});
