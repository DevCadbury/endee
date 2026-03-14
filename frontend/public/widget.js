/**
 * =============================================================================
 * ResolveAI — Embeddable Chat Widget v2.0
 * =============================================================================
 * Vanilla JavaScript, zero dependencies.
 *
 * New (recommended) — real-time WebSocket mode:
 *   <script src="widget.js"
 *           data-slug="your-company-slug"
 *           data-api-url="https://api.yourhost.com"></script>
 *
 * Legacy fallback — HTTP-only mode:
 *   <script src="widget.js"
 *           data-api-key="pk_live_xxx"
 *           data-api-url="https://api.yourhost.com"></script>
 *
 * In WebSocket mode the widget:
 *   - Maintains a persistent WebSocket connection
 *   - Shows staff typing indicators and presence
 *   - Delivers staff replies in real-time (<1 s)
 *   - Persists session/conversation across page refreshes
 *   - Auto-reconnects with 3-second backoff
 *   - Sends keepalive pings every 30 s
 * =============================================================================
 */
(function () {
  'use strict';

  /* ======================================================================== */
  /* Config                                                                    */
  /* ======================================================================== */
  var script = document.currentScript;
  var SLUG    = (script && script.getAttribute('data-slug'))    || '';
  var API_KEY = (script && script.getAttribute('data-api-key')) || '';
  var RAW_URL = (script && script.getAttribute('data-api-url')) || 'http://localhost:8000';
  var API_URL = RAW_URL.replace(/\/$/, '');
  var WS_URL  = API_URL.replace(/^http/, 'ws');

  /* ======================================================================== */
  /* Session persistence (WebSocket mode only)                                 */
  /* ======================================================================== */
  function getSessionId() {
    var key = 'resolveai_session_' + SLUG;
    var id = '';
    try { id = localStorage.getItem(key) || ''; } catch (e) {}
    if (!id) {
      id = 'sess_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
      try { localStorage.setItem(key, id); } catch (e) {}
    }
    return id;
  }

  /* ======================================================================== */
  /* State                                                                     */
  /* ======================================================================== */
  var isOpen         = false;
  var messages       = [];
  var ws             = null;
  var reconnectTimer = null;
  var pingTimer      = null;
  var isConnected    = false;
  var isSending      = false;     // for legacy mode only
  var staffOnline    = 0;
  var typingTimeout  = null;
  var typingSendTimer = null;
  var isResolved     = false;
  var SESSION_ID     = SLUG ? getSessionId() : '';

  /* ======================================================================== */
  /* Styles                                                                    */
  /* ======================================================================== */
  var PRIMARY      = '#6366f1';
  var PRIMARY_DARK = '#4f46e5';

  var styleEl = document.createElement('style');
  styleEl.textContent = [
    '#resolveai-root *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}',
    /* FAB button */
    '#resolveai-btn{position:fixed;bottom:24px;right:24px;width:56px;height:56px;background:' + PRIMARY + ';border-radius:50%;border:none;cursor:pointer;box-shadow:0 4px 16px rgba(99,102,241,.4);display:flex;align-items:center;justify-content:center;z-index:99999;transition:transform .2s,background .2s}',
    '#resolveai-btn:hover{transform:scale(1.08);background:' + PRIMARY_DARK + '}',
    /* Panel */
    '#resolveai-panel{position:fixed;bottom:92px;right:24px;width:380px;max-height:580px;background:#fff;border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.18);display:flex;flex-direction:column;z-index:99998;overflow:hidden;transform:scale(.95) translateY(8px);opacity:0;pointer-events:none;transition:transform .2s,opacity .2s}',
    '#resolveai-panel.rai-open{transform:scale(1) translateY(0);opacity:1;pointer-events:all}',
    /* Header */
    '#resolveai-header{background:' + PRIMARY + ';color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}',
    '#resolveai-header-info{flex:1;min-width:0}',
    '#resolveai-header h3{margin:0;font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '#resolveai-status-row{font-size:11px;opacity:.85;display:flex;align-items:center;gap:4px;margin-top:2px}',
    '#resolveai-dot{width:7px;height:7px;border-radius:50%;background:#4ade80;flex-shrink:0;display:inline-block}',
    '#resolveai-dot.rai-offline{background:#f87171}',
    '#resolveai-dot.rai-connecting{background:#fbbf24;animation:rai-pulse 1s infinite}',
    '#resolveai-close{background:none;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1;padding:0 2px;opacity:.8;flex-shrink:0}',
    '#resolveai-close:hover{opacity:1}',
    /* Messages */
    '#resolveai-msgs{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:8px}',
    '.rai-row{display:flex;flex-direction:column;max-width:82%}',
    '.rai-row.rai-customer{align-self:flex-end}',
    '.rai-row.rai-ai,.rai-row.rai-staff{align-self:flex-start}',
    '.rai-bubble{padding:9px 13px;border-radius:12px;font-size:13px;line-height:1.5;word-break:break-word}',
    '.rai-row.rai-customer .rai-bubble{background:' + PRIMARY + ';color:#fff;border-bottom-right-radius:4px}',
    '.rai-row.rai-ai .rai-bubble{background:#f1f5f9;color:#1e293b;border-bottom-left-radius:4px}',
    '.rai-row.rai-staff .rai-bubble{background:#dcfce7;color:#166534;border-bottom-left-radius:4px}',
    /* Badges */
    '.rai-badge{font-size:10px;padding:2px 7px;border-radius:4px;margin-top:4px;align-self:flex-start;font-weight:600;display:inline-block}',
    '.rai-badge.auto_reply{background:#dcfce7;color:#166534}',
    '.rai-badge.clarify{background:#fef3c7;color:#92400e}',
    '.rai-badge.escalate{background:#fee2e2;color:#991b1b}',
    '.rai-badge.staff_reply{background:#dbeafe;color:#1e40af}',
    /* Typing dots */
    '.rai-typing-dots{display:flex;gap:4px;align-items:center;padding:10px 13px;background:#f1f5f9;border-radius:12px;border-bottom-left-radius:4px;align-self:flex-start}',
    '.rai-typing-dots span{width:6px;height:6px;background:#94a3b8;border-radius:50%;animation:rai-bounce 1.2s infinite}',
    '.rai-typing-dots span:nth-child(2){animation-delay:.2s}',
    '.rai-typing-dots span:nth-child(3){animation-delay:.4s}',
    /* Resolved banner */
    '#resolveai-resolved{background:#f0fdf4;border-top:1px solid #bbf7d0;padding:10px 14px;font-size:12px;color:#166534;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}',
    '#resolveai-new-chat{font-size:12px;background:none;border:1px solid #16a34a;color:#16a34a;padding:3px 10px;border-radius:6px;cursor:pointer;font-family:inherit}',
    '#resolveai-new-chat:hover{background:#16a34a;color:#fff}',
    /* Input area */
    '#resolveai-input-area{border-top:1px solid #e2e8f0;padding:10px 12px;display:flex;gap:8px;align-items:flex-end;background:#fff;flex-shrink:0}',
    '#resolveai-input{flex:1;border:1.5px solid #e2e8f0;border-radius:20px;padding:8px 14px;font-size:13px;resize:none;outline:none;min-height:36px;max-height:100px;overflow-y:auto;line-height:1.5;transition:border-color .15s;font-family:inherit}',
    '#resolveai-input:focus{border-color:' + PRIMARY + '}',
    '#resolveai-send{background:' + PRIMARY + ';border:none;width:36px;height:36px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s}',
    '#resolveai-send:hover{background:' + PRIMARY_DARK + '}',
    '#resolveai-send:disabled{opacity:.45;cursor:not-allowed}',
    /* Animations */
    '@keyframes rai-bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}',
    '@keyframes rai-pulse{0%,100%{opacity:1}50%{opacity:.35}}',
    '@keyframes rai-fadein{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}',
    '.rai-row{animation:rai-fadein .2s ease}',
    /* Mobile */
    '@media(max-width:420px){#resolveai-panel{width:calc(100vw - 16px);right:8px;bottom:80px}}',
  ].join('');
  document.head.appendChild(styleEl);

  /* ======================================================================== */
  /* DOM                                                                       */
  /* ======================================================================== */
  var root = document.createElement('div');
  root.id  = 'resolveai-root';

  /* FAB */
  var btn = document.createElement('button');
  btn.id = 'resolveai-btn';
  btn.setAttribute('aria-label', 'Open support chat');
  btn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

  /* Panel */
  var panel = document.createElement('div');
  panel.id  = 'resolveai-panel';

  /* Header */
  var header = document.createElement('div');
  header.id  = 'resolveai-header';
  header.innerHTML = [
    '<div id="resolveai-header-info">',
      '<h3>Support Chat</h3>',
      '<div id="resolveai-status-row">',
        '<span id="resolveai-dot" class="rai-connecting"></span>',
        '<span id="resolveai-status-text">Connecting…</span>',
        '<span id="resolveai-conv-id" style="margin-left:8px;font-family:monospace;font-size:10px;opacity:.6"></span>',
      '</div>',
    '</div>',
    '<button id="resolveai-close" aria-label="Close">×</button>',
  ].join('');

  /* Message list */
  var msgsEl = document.createElement('div');
  msgsEl.id  = 'resolveai-msgs';

  /* Typing indicator row */
  var typingRowEl = document.createElement('div');
  typingRowEl.id  = 'resolveai-typing-row';
  typingRowEl.style.display = 'none';
  typingRowEl.innerHTML = '<div class="rai-typing-dots"><span></span><span></span><span></span></div>';

  /* Resolved banner */
  var resolvedEl = document.createElement('div');
  resolvedEl.id  = 'resolveai-resolved';
  resolvedEl.style.display = 'none';
  resolvedEl.innerHTML = '<span>✓ Conversation resolved</span><button id="resolveai-new-chat">New chat</button>';

  /* Input area */
  var inputAreaEl = document.createElement('div');
  inputAreaEl.id  = 'resolveai-input-area';
  inputAreaEl.innerHTML = [
    '<textarea id="resolveai-input" rows="1" placeholder="Type a message…" disabled></textarea>',
    '<button id="resolveai-send" disabled aria-label="Send">',
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">',
        '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
      '</svg>',
    '</button>',
  ].join('');

  panel.appendChild(header);
  panel.appendChild(msgsEl);
  msgsEl.appendChild(typingRowEl);
  panel.appendChild(resolvedEl);
  panel.appendChild(inputAreaEl);
  root.appendChild(btn);
  root.appendChild(panel);
  document.body.appendChild(root);

  var inputEl   = document.getElementById('resolveai-input');
  var sendBtn   = document.getElementById('resolveai-send');
  var dotEl     = document.getElementById('resolveai-dot');
  var statusTxt = document.getElementById('resolveai-status-text');

  /* ======================================================================== */
  /* UI helpers                                                                */
  /* ======================================================================== */
  function setStatus(state) {
    dotEl.className = state === 'connected' ? '' : ('rai-' + state);
    if (state === 'connected') {
      dotEl.style.background = '#4ade80';
      statusTxt.textContent = staffOnline > 0
        ? staffOnline + ' agent' + (staffOnline > 1 ? 's' : '') + ' online'
        : 'AI Support Active';
    } else if (state === 'connecting') {
      dotEl.style.background = '';
      statusTxt.textContent = 'Connecting…';
    } else {
      dotEl.style.background = '#f87171';
      statusTxt.textContent = 'Reconnecting…';
    }
  }

  function addMessage(role, content, meta, ts) {
    var row = document.createElement('div');
    row.className = 'rai-row rai-' + role;

    var bubble = document.createElement('div');
    bubble.className = 'rai-bubble';
    bubble.textContent = content;
    row.appendChild(bubble);

    /* Timestamp */
    var timeEl = document.createElement('div');
    timeEl.style.cssText = 'font-size:10px;opacity:.5;margin-top:3px;' + (role === 'customer' ? 'text-align:right' : 'text-align:left');
    var d = ts ? new Date(ts) : new Date();
    timeEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    row.appendChild(timeEl);

    /* Badges */
    if (meta && meta.action) {
      var b = document.createElement('span');
      b.className = 'rai-badge ' + meta.action;
      var labels = { auto_reply: '✓ Auto-resolved', clarify: '◎ Clarifying', escalate: '→ Routing to agent' };
      b.textContent = labels[meta.action] || meta.action;
      row.appendChild(b);
    }
    if (role === 'staff') {
      var sb = document.createElement('span');
      sb.className = 'rai-badge staff_reply';
      sb.textContent = '👤 Staff';
      row.appendChild(sb);
    }

    msgsEl.insertBefore(row, typingRowEl);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    messages.push({ role: role, content: content, meta: meta });
  }

  function showTyping(visible) {
    typingRowEl.style.display = visible ? 'flex' : 'none';
    if (visible) msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  function setResolved(resolved) {
    isResolved = resolved;
    resolvedEl.style.display    = resolved ? 'flex' : 'none';
    inputAreaEl.style.display   = resolved ? 'none' : 'flex';
    inputEl.disabled  = true;
    sendBtn.disabled  = true;
  }

  function enableInput(yes) {
    inputEl.disabled  = !yes;
    sendBtn.disabled  = !yes;
    if (yes) inputEl.focus();
  }

  /* ======================================================================== */
  /* WebSocket connection                                                      */
  /* ======================================================================== */
  function connectWS() {
    if (!SLUG) return;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    setStatus('connecting');

    var url = WS_URL + '/api/v1/ws/widget/' + SLUG + '?session_id=' + SESSION_ID;
    ws = new WebSocket(url);

    ws.onopen = function () {
      isConnected = true;
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = setInterval(function () {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    ws.onmessage = function (evt) {
      var data;
      try { data = JSON.parse(evt.data); } catch (e) { return; }
      handleWSEvent(data);
    };

    ws.onclose = function () {
      isConnected = false;
      if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
      if (!isResolved) {
        setStatus('offline');
        enableInput(false);
        showTyping(false);
        reconnectTimer = setTimeout(connectWS, 3000);
      }
    };

    ws.onerror = function () { try { ws.close(); } catch (e) {} };
  }

  function handleWSEvent(data) {
    var t = data.type;

    if (t === 'connected') {
      staffOnline = data.staff_online || 0;
      setStatus('connected');
      enableInput(true);
      var convIdEl = document.getElementById('resolveai-conv-id');
      if (convIdEl && data.conv_id) convIdEl.textContent = '#' + data.conv_id.slice(-8);
      /* Render message history */
      if (data.messages && data.messages.length) {
        data.messages.forEach(function (m) {
          var role = m.sender_type === 'customer' ? 'customer'
                   : m.sender_type === 'staff'    ? 'staff' : 'ai';
          addMessage(role, m.content, m.metadata || null, m.created_at);
        });
      } else {
        addMessage('ai', 'Hello! How can I help you today?', null, new Date().toISOString());
      }

    } else if (t === 'message') {
      showTyping(false);
      if (data.sender_type === 'ai' || data.sender_type === 'staff' || data.sender_type === 'admin') {
        var role2 = data.sender_type === 'ai' ? 'ai' : 'staff';
        addMessage(role2, data.content, data.metadata || null, data.created_at);
      }

    } else if (t === 'message_ack') {
      /* Customer message already shown optimistically — nothing to do */

    } else if (t === 'ai_thinking') {
      showTyping(true);

    } else if (t === 'typing') {
      if (data.sender_type !== 'customer') {
        showTyping(true);
        if (typingTimeout) clearTimeout(typingTimeout);
        typingTimeout = setTimeout(function () { showTyping(false); }, 4000);
      }

    } else if (t === 'conversation_status') {
      if (data.new_status === 'resolved') {
        showTyping(false);
        setResolved(true);
      }

    } else if (t === 'presence') {
      if (data.role === 'staff') {
        staffOnline = data.event === 'joined'
          ? staffOnline + 1
          : Math.max(0, staffOnline - 1);
        setStatus('connected');
      }

    } else if (t === 'error') {
      if (data.code === 'conversation_resolved') setResolved(true);
    }
    /* pong — no action needed */
  }

  /* ======================================================================== */
  /* Send a message                                                            */
  /* ======================================================================== */
  function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isResolved) return;

    if (SLUG && ws && ws.readyState === WebSocket.OPEN) {
      /* --- WebSocket mode --- */
      addMessage('customer', text, null, new Date().toISOString());
      inputEl.value = '';
      autoResizeInput();
      ws.send(JSON.stringify({ type: 'message', content: text }));

    } else if (API_KEY) {
      /* --- Legacy HTTP mode --- */
      sendLegacy(text);

    } else if (SLUG && (!ws || ws.readyState !== WebSocket.OPEN)) {
      /* WS not ready yet — queue message after reconnect */
      connectWS();
    }
  }

  /* Legacy HTTP fallback */
  function sendLegacy(text) {
    if (isSending) return;
    isSending = true;
    addMessage('customer', text, null, new Date().toISOString());
    inputEl.value = '';

    /* Loading dots */
    var loadRow = document.createElement('div');
    loadRow.className = 'rai-row rai-ai';
    loadRow.innerHTML = '<div class="rai-typing-dots"><span></span><span></span><span></span></div>';
    msgsEl.insertBefore(loadRow, typingRowEl);
    msgsEl.scrollTop = msgsEl.scrollHeight;

    var xhr = new XMLHttpRequest();
    xhr.open('POST', API_URL + '/api/v1/chat/incoming', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.setRequestHeader('X-API-Key', API_KEY);
    xhr.onload = function () {
      loadRow.remove();
      var d;
      try { d = JSON.parse(xhr.responseText); } catch (e) { d = {}; }
      if (xhr.status === 429) {
        addMessage('ai', 'Too many requests. Please wait a moment.', { action: 'escalate' }, new Date().toISOString());
      } else if (xhr.status >= 400) {
        addMessage('ai', d.detail || 'Something went wrong. Please try again.', { action: 'escalate' }, new Date().toISOString());
      } else {
        addMessage('ai', d.message || 'No response.', { action: d.action }, new Date().toISOString());
      }
      isSending = false;
    };
    xhr.onerror = function () {
      loadRow.remove();
      addMessage('ai', "I'm having trouble connecting. Please try again.", { action: 'escalate' }, new Date().toISOString());
      isSending = false;
    };
    xhr.send(JSON.stringify({ customer_message: text }));
  }

  /* ======================================================================== */
  /* Typing indicator events → server                                         */
  /* ======================================================================== */
  function autoResizeInput() {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + 'px';
  }

  function onInputChange() {
    autoResizeInput();
    if (!SLUG || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'typing', is_typing: true }));
    if (typingSendTimer) clearTimeout(typingSendTimer);
    typingSendTimer = setTimeout(function () {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'typing', is_typing: false }));
      }
    }, 2000);
  }

  /* ======================================================================== */
  /* Toggle panel                                                              */
  /* ======================================================================== */
  function toggle() {
    isOpen = !isOpen;
    panel.classList.toggle('rai-open', isOpen);
    if (isOpen && SLUG && !isConnected) connectWS();
  }

  /* ======================================================================== */
  /* New chat (after resolution)                                               */
  /* ======================================================================== */
  function startNewChat() {
    try { localStorage.removeItem('resolveai_session_' + SLUG); } catch (e) {}
    SESSION_ID = getSessionId();
    isResolved  = false;
    staffOnline = 0;
    messages    = [];

    /* Clear message nodes except the typing row */
    var children = Array.prototype.slice.call(msgsEl.children);
    children.forEach(function (c) {
      if (c.id !== 'resolveai-typing-row') msgsEl.removeChild(c);
    });

    resolvedEl.style.display  = 'none';
    inputAreaEl.style.display = 'flex';
    showTyping(false);
    setStatus('connecting');
    enableInput(false);

    if (ws) {
      ws.onclose = null;
      try { ws.close(); } catch (e) {}
      ws = null;
    }
    isConnected = false;
    connectWS();
  }

  /* ======================================================================== */
  /* Event listeners                                                           */
  /* ======================================================================== */
  btn.addEventListener('click', toggle);
  document.getElementById('resolveai-close').addEventListener('click', toggle);
  sendBtn.addEventListener('click', sendMessage);
  document.getElementById('resolveai-new-chat').addEventListener('click', startNewChat);

  inputEl.addEventListener('input', onInputChange);
  inputEl.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  /* ======================================================================== */
  /* Auto-connect on load                                                      */
  /* ======================================================================== */
  if (SLUG) {
    connectWS();
  } else if (API_KEY) {
    /* Legacy mode: no WebSocket, enable input immediately */
    setStatus('connected');
    enableInput(true);
    setTimeout(function () {
      addMessage('ai', 'Hello! How can I help you today?', null, new Date().toISOString());
    }, 200);
  }

})();
