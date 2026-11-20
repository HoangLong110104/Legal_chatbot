document.addEventListener('DOMContentLoaded', () => {
  // Chat Elements
  const messagesContainer = document.getElementById('messages-container');
  const chatForm = document.getElementById('chat-form');
  const userInput = document.getElementById('user-input');
  const sendBtn = document.getElementById('send-btn');
  const sessionListContainer = document.getElementById('session-list');
  const btnNewChat = document.getElementById('btn-new-chat');

  // Drawer Elements
  const articleDrawer = document.getElementById('article-drawer');
  const closeDrawer = document.getElementById('close-drawer');
  const drawerContent = document.getElementById('drawer-content');

  // Stats Elements
  const statDocs = document.getElementById('stat-docs');
  const statChunks = document.getElementById('stat-chunks');
  const statRels = document.getElementById('stat-rels');

  // Upload Modal Elements
  const btnHeaderUpload = document.getElementById('btn-header-upload');
  const btnOpenUpload = document.getElementById('btn-open-upload');
  const uploadDocModal = document.getElementById('upload-doc-modal');
  const closeUploadModal = document.getElementById('close-upload-modal');
  const btnCancelUpload = document.getElementById('btn-cancel-upload');
  const tabBtnFile = document.getElementById('tab-btn-file');
  const tabBtnRaw = document.getElementById('tab-btn-raw');
  const tabContentFile = document.getElementById('tab-content-file');
  const tabContentRaw = document.getElementById('tab-content-raw');
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const selectedFileName = document.getElementById('selected-file-name');
  const rawDocText = document.getElementById('raw-doc-text');
  const uploadDocSymbol = document.getElementById('upload-doc-symbol');
  const uploadDomain = document.getElementById('upload-domain');
  const uploadStatusBox = document.getElementById('upload-status-box');
  const uploadStatusText = document.getElementById('upload-status-text');
  const btnSubmitUpload = document.getElementById('btn-submit-upload');

  // Manage Docs Modal Elements
  const btnOpenManageDocs = document.getElementById('btn-open-manage-docs');
  const manageDocsModal = document.getElementById('manage-docs-modal');
  const closeManageDocs = document.getElementById('close-manage-docs');
  const btnCloseManage = document.getElementById('btn-close-manage');
  const docsTableBody = document.getElementById('docs-table-body');
  const btnSeedData = document.getElementById('btn-seed-data');

  // Settings Modal Elements
  const btnSettings = document.getElementById('btn-settings');
  const settingsModal = document.getElementById('settings-modal');
  const closeSettings = document.getElementById('close-settings');
  const btnSaveSettings = document.getElementById('btn-save-settings');
  const selectOllamaModel = document.getElementById('select-ollama-model');
  const inputGeminiKey = document.getElementById('input-gemini-key');
  const inputOpenaiKey = document.getElementById('input-openai-key');
  const btnScrollBottom = document.getElementById('btn-scroll-bottom');

  // State Variables
  let currentSessionId = localStorage.getItem('legal_current_session_id') || null;
  let activeUploadTab = 'file'; // 'file' or 'raw'
  let selectedFile = null;

  // Smart auto-scroll logic (chỉ tự động cuộn khi người dùng đang ở đáy màn hình)
  let userIsNearBottom = true;
  if (messagesContainer) {
    messagesContainer.addEventListener('scroll', () => {
      const threshold = 150;
      const distFromBottom = messagesContainer.scrollHeight - (messagesContainer.scrollTop + messagesContainer.clientHeight);
      userIsNearBottom = distFromBottom <= threshold;

      if (btnScrollBottom) {
        if (!userIsNearBottom && messagesContainer.scrollHeight > messagesContainer.clientHeight + 250) {
          btnScrollBottom.classList.remove('hidden');
        } else {
          btnScrollBottom.classList.add('hidden');
        }
      }
    });
  }

  if (btnScrollBottom) {
    btnScrollBottom.addEventListener('click', () => {
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        userIsNearBottom = true;
        btnScrollBottom.classList.add('hidden');
      }
    });
  }

  function autoScrollToBottom(force = false) {
    if (!messagesContainer) return;
    if (force || userIsNearBottom) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  // Auto-resize input textarea
  if (userInput) {
    userInput.addEventListener('input', () => {
      userInput.style.height = 'auto';
      userInput.style.height = Math.min(userInput.scrollHeight, 150) + 'px';
    });

    userInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (chatForm) {
          chatForm.dispatchEvent(new Event('submit'));
        }
      }
    });
  }

  // =====================================================================
  // 1. STATS & SYSTEM STATUS
  // =====================================================================
  async function loadStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const data = await res.json();
      if (statDocs) statDocs.textContent = `${data.documents_count} văn bản`;
      if (statChunks) statChunks.textContent = `${data.articles_count} điều luật`;
      if (statRels) statRels.textContent = `${data.relationships_count} quan hệ`;
    } catch (e) {
      console.error('Error loading stats:', e);
    }
  }
  loadStats();

  // =====================================================================
  // 2. CHAT SESSION MANAGEMENT
  // =====================================================================
  async function loadSessions() {
    if (!sessionListContainer) return;
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) return;
      const sessions = await res.json();

      if (!sessions || sessions.length === 0) {
        sessionListContainer.innerHTML = `
          <div class="text-xs text-slate-500 py-4 text-center">Chưa có đoạn chat nào.<br>Bấm "Đoạn chat mới" để bắt đầu.</div>
        `;
        return;
      }

      sessionListContainer.innerHTML = '';
      sessions.forEach(s => {
        const isActive = s.session_id === currentSessionId;
        const item = document.createElement('div');
        item.className = `group flex items-center justify-between p-2 rounded-lg cursor-pointer transition text-xs border ${
          isActive 
            ? 'bg-surface-800 text-emerald-400 border-emerald-500/50 shadow-sm' 
            : 'bg-surface-800/40 hover:bg-surface-800/80 text-slate-300 border-transparent hover:border-slate-700/60'
        }`;
        
        item.innerHTML = `
          <div class="flex items-center gap-2 overflow-hidden flex-1 min-w-0 pr-1">
            <i class="fa-regular fa-message ${isActive ? 'text-emerald-400' : 'text-slate-500 group-hover:text-slate-300'} text-[11px] shrink-0"></i>
            <div class="truncate font-medium text-[11px]">${escapeHtml(s.title || 'Đoạn chat')}</div>
          </div>
          <button title="Xóa đoạn chat" class="btn-delete-session opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 p-1 rounded transition shrink-0">
            <i class="fa-regular fa-trash-can text-[10px]"></i>
          </button>
        `;

        item.addEventListener('click', (e) => {
          if (e.target.closest('.btn-delete-session')) return;
          switchSession(s.session_id);
        });

        const delBtn = item.querySelector('.btn-delete-session');
        if (delBtn) {
          delBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`Bạn có chắc muốn xóa đoạn chat "${s.title}" không?`)) {
              await deleteSession(s.session_id);
            }
          });
        }

        sessionListContainer.appendChild(item);
      });

      // Nếu chưa chọn session nào, tự động chọn session đầu tiên
      if (!currentSessionId && sessions.length > 0) {
        switchSession(sessions[0].session_id);
      }
    } catch (e) {
      console.error('Error loading sessions:', e);
    }
  }

  async function switchSession(sessionId) {
    if (!sessionId) return;
    currentSessionId = sessionId;
    localStorage.setItem('legal_current_session_id', sessionId);
    loadSessions();

    try {
      const res = await fetch(`/api/sessions/${sessionId}`);
      if (!res.ok) {
        // Nếu không tìm thấy session (có thể đã bị xóa trước đó), reset lại
        currentSessionId = null;
        localStorage.removeItem('legal_current_session_id');
        renderWelcomeBanner();
        return;
      }
      const data = await res.json();

      if (messagesContainer) {
        messagesContainer.innerHTML = '';
        if (!data.messages || data.messages.length === 0) {
          renderWelcomeBanner();
          return;
        }

        data.messages.forEach(m => {
          if (m.role === 'user') {
            appendUserMessage(m.content, m.created_at);
          } else {
            renderHistoricalAssistantMessage(m.content, m.citations, m.created_at);
          }
        });
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    } catch (e) {
      console.error('Error switching session:', e);
    }
  }

  async function createNewChat() {
    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'Đoạn chat mới' })
      });
      if (res.ok) {
        const newSession = await res.json();
        currentSessionId = newSession.session_id;
        localStorage.setItem('legal_current_session_id', currentSessionId);
        if (messagesContainer) {
          messagesContainer.innerHTML = '';
          renderWelcomeBanner();
        }
        loadSessions();
        if (userInput) userInput.focus();
      }
    } catch (e) {
      console.error('Error creating new session:', e);
    }
  }

  async function deleteSession(sessionId) {
    try {
      const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      if (res.ok) {
        if (currentSessionId === sessionId) {
          currentSessionId = null;
          localStorage.removeItem('legal_current_session_id');
          if (messagesContainer) {
            messagesContainer.innerHTML = '';
            renderWelcomeBanner();
          }
        }
        loadSessions();
      }
    } catch (e) {
      alert('Lỗi xóa đoạn chat: ' + e);
    }
  }

  if (btnNewChat) btnNewChat.addEventListener('click', createNewChat);
  loadSessions();

  function renderWelcomeBanner() {
    if (!messagesContainer) return;
    messagesContainer.innerHTML = `
      <div id="welcome-banner" class="max-w-3xl mx-auto my-6 p-6 rounded-2xl bg-gradient-to-b from-surface-900 to-surface-900/60 border border-slate-800 shadow-xl text-center space-y-4">
        <div class="w-14 h-14 mx-auto rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center text-2xl shadow-inner">
          <i class="fa-solid fa-gavel"></i>
        </div>
        <div>
          <h2 class="text-xl font-bold text-white">Hệ Thống Trợ Lý Pháp Luật Việt Nam</h2>
          <p class="text-sm text-slate-400 max-w-xl mx-auto mt-1">
            Ứng dụng kiến trúc <strong class="text-slate-200">Agentic RAG + Graph Traversal</strong> truy vết chuỗi sửa đổi văn bản, trích dẫn chính xác và cam kết chống bịa đặt (Zero Hallucination).
          </p>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-left">
          <div class="p-3 rounded-xl bg-surface-800/40 border border-slate-800">
            <i class="fa-solid fa-bolt text-amber-400 text-sm mb-1"></i>
            <div class="font-medium text-xs text-slate-200">Lối tắt Direct Lookup</div>
            <div class="text-[11px] text-slate-400 mt-0.5">Nhận diện đích danh Điều/Văn bản và tra cứu trực tiếp.</div>
          </div>
          <div class="p-3 rounded-xl bg-surface-800/40 border border-slate-800">
            <i class="fa-solid fa-diagram-project text-emerald-400 text-sm mb-1"></i>
            <div class="font-medium text-xs text-slate-200">Truy vết Sửa đổi</div>
            <div class="text-[11px] text-slate-400 mt-0.5">Tự động thay thế điều cũ bằng bản sửa đổi mới nhất còn hiệu lực.</div>
          </div>
          <div class="p-3 rounded-xl bg-surface-800/40 border border-slate-800">
            <i class="fa-solid fa-book-bookmark text-blue-400 text-sm mb-1"></i>
            <div class="font-medium text-xs text-slate-200">Trích dẫn Toàn văn</div>
            <div class="text-[11px] text-slate-400 mt-0.5">Bấm vào trích dẫn để đọc nguyên văn điều luật từ SQLite.</div>
          </div>
        </div>
      </div>
    `;
  }

  // =====================================================================
  // 3. SUBMIT CHAT & STREAMING SSE
  // =====================================================================
  if (chatForm) {
    chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const query = userInput ? userInput.value.trim() : '';
      if (!query) return;

      // Ẩn welcome banner nếu đang hiển thị
      const welcomeBanner = document.getElementById('welcome-banner');
      if (welcomeBanner) welcomeBanner.remove();

      // Reset input
      if (userInput) {
        userInput.value = '';
        userInput.style.height = 'auto';
      }
      if (sendBtn) sendBtn.disabled = true;

      // Append User Message Bubble
      appendUserMessage(query);

      // Append Assistant Message Placeholder
      const assistantMsg = appendAssistantPlaceholder();

      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: query,
            session_id: currentSessionId
          })
        });

        if (!response.body) throw new Error('ReadableStream not supported.');

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const rawJson = line.substring(6).trim();
              if (!rawJson) continue;
              try {
                const event = JSON.parse(rawJson);
                if (event.type === 'session') {
                  if (event.session_id) {
                    currentSessionId = event.session_id;
                    localStorage.setItem('legal_current_session_id', currentSessionId);
                    loadSessions();
                  }
                } else {
                  handleAgentEvent(assistantMsg, event);
                }
              } catch (err) {
                console.error('Error parsing SSE event:', err);
              }
            }
          }
        }
      } catch (err) {
        assistantMsg.updateContent(`<p class="text-red-400">Đã xảy ra lỗi trong quá trình xử lý: ${escapeHtml(err.message)}</p>`);
      } finally {
        if (sendBtn) sendBtn.disabled = false;
        assistantMsg.finish();
        loadSessions();
      }
    });
  }

  function getFormattedTime(dateStr) {
    if (dateStr) {
      // If dateStr is already e.g. "15:45 19/11/2026", take first part
      const parts = dateStr.split(' ');
      if (parts.length >= 1 && parts[0].includes(':')) return parts[0];
      return dateStr;
    }
    const now = new Date();
    return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  // Global helper for copying answer text
  window.copyMessageText = function(btn) {
    try {
      const container = btn.closest('.chat-assistant-container');
      const textElem = container ? container.querySelector('.answer-body') : null;
      const textToCopy = textElem ? textElem.innerText : '';
      if (!textToCopy) return;

      navigator.clipboard.writeText(textToCopy).then(() => {
        const originalHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-check text-emerald-400"></i><span class="text-emerald-400 font-semibold">Đã chép</span>';
        btn.classList.add('border-emerald-500/60');
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          btn.classList.remove('border-emerald-500/60');
        }, 2000);
      });
    } catch (err) {
      console.error('Lỗi khi sao chép:', err);
    }
  };

  function appendUserMessage(text, timestamp) {
    if (!messagesContainer) return;
    const timeStr = getFormattedTime(timestamp);
    const div = document.createElement('div');
    div.className = 'flex justify-end items-end gap-3 my-3 group';
    div.innerHTML = `
      <div class="flex flex-col items-end max-w-2xl">
        <div class="flex items-center gap-1.5 mb-1.5 px-1 text-[11px] text-slate-400 font-medium select-none">
          <span class="text-slate-300">Bạn</span>
          <span class="text-slate-500">•</span>
          <span class="text-slate-400 text-[10px]">${escapeHtml(timeStr)}</span>
        </div>
        <div class="chat-user-bubble shadow-md selection:bg-emerald-800">
          ${escapeHtml(text)}
        </div>
      </div>
      <div class="w-8 h-8 rounded-full bg-surface-800 border border-slate-700 text-slate-300 flex items-center justify-center shrink-0 mb-0.5 shadow-sm text-xs">
        <i class="fa-solid fa-user text-[11px] text-emerald-400"></i>
      </div>
    `;
    messagesContainer.appendChild(div);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendAssistantPlaceholder(timestamp) {
    const timeStr = getFormattedTime(timestamp);
    const div = document.createElement('div');
    div.className = 'flex items-start gap-3 my-4 max-w-4xl group chat-assistant-container';

    div.innerHTML = `
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 via-teal-600 to-cyan-500 text-white flex items-center justify-center shrink-0 mt-0.5 shadow-lg shadow-emerald-500/20 ring-2 ring-emerald-500/20 text-xs">
        <i class="fa-solid fa-scale-balanced text-[13px]"></i>
      </div>
      <div class="flex-1 space-y-2.5 overflow-hidden">
        
        <!-- Header Info -->
        <div class="flex items-center justify-between px-1 select-none">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-slate-200">Trợ Lý Pháp Luật Việt Nam</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 rounded-full">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              Strict Grounding
            </span>
          </div>
          <span class="text-[10px] text-slate-400">${escapeHtml(timeStr)}</span>
        </div>

        <!-- Reasoning / Step Stream Accordion -->
        <div class="reasoning-box rounded-xl bg-surface-900/90 border border-slate-800/90 p-3 text-xs space-y-2 shadow-sm backdrop-blur-sm">
          <div class="flex items-center justify-between text-slate-300 font-semibold cursor-pointer select-none" onclick="this.nextElementSibling.classList.toggle('hidden')">
            <span class="flex items-center gap-2">
              <i class="fa-solid fa-brain text-emerald-400"></i>
              <span class="step-title">Tiến trình suy luận Agentic RAG...</span>
            </span>
            <i class="fa-solid fa-chevron-down text-[10px] text-slate-400 transition-transform"></i>
          </div>
          <div class="steps-list space-y-1.5 pt-1.5 text-slate-400 text-[11px] font-mono border-t border-slate-800/80">
            <!-- Steps injected here -->
          </div>
        </div>

        <!-- Main Answer Card -->
        <div class="chat-assistant-bubble relative group/card">
          <button 
            type="button"
            onclick="copyMessageText(this)" 
            title="Sao chép câu trả lời"
            class="btn-copy-bubble absolute top-3.5 right-3.5 px-2.5 py-1 rounded-lg bg-surface-800/90 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700 text-xs flex items-center gap-1.5 shadow-sm cursor-pointer z-10"
          >
            <i class="fa-regular fa-copy"></i>
            <span>Sao chép</span>
          </button>
          
          <div class="prose-legal answer-body">
            <div class="flex items-center gap-2.5 text-slate-400 text-xs py-2 animate-pulse">
              <i class="fa-solid fa-circle-notch fa-spin text-emerald-400 text-sm"></i>
              <span>Đang tra cứu cơ sở dữ liệu pháp luật và phân tích...</span>
            </div>
          </div>
        </div>

        <!-- Citations Pills -->
        <div class="citations-container hidden pt-1">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-bookmark text-emerald-400"></i>
            <span>Căn cứ pháp lý được trích dẫn (Bấm xem nguyên văn):</span>
          </div>
          <div class="citations-list flex flex-wrap gap-2"></div>
        </div>

      </div>
    `;

    if (messagesContainer) {
      messagesContainer.appendChild(div);
      autoScrollToBottom(true);
    }

    const stepsList = div.querySelector('.steps-list');
    const stepTitle = div.querySelector('.step-title');
    const answerBody = div.querySelector('.answer-body');
    const citationsContainer = div.querySelector('.citations-container');
    const citationsList = div.querySelector('.citations-list');

    return {
      addStep: (node, message) => {
        if (!stepsList) return;
        const stepItem = document.createElement('div');
        stepItem.className = 'flex items-center gap-2 text-slate-300';
        stepItem.innerHTML = `<i class="fa-solid fa-check text-emerald-400 text-[10px]"></i><span>${escapeHtml(message)}</span>`;
        stepsList.appendChild(stepItem);
        if (stepTitle) stepTitle.textContent = message;
        autoScrollToBottom();
      },
      updateContent: (html) => {
        if (answerBody) answerBody.innerHTML = html;
        autoScrollToBottom();
      },
      addCitations: (citations) => {
        if (!citations || citations.length === 0 || !citationsContainer || !citationsList) return;
        citationsContainer.classList.remove('hidden');
        citationsList.innerHTML = citations.map(c => `
          <button onclick="viewArticleDetails('${c.article_id}')" class="px-3 py-1.5 rounded-lg bg-surface-800/90 hover:bg-slate-700 border border-slate-700/80 text-xs text-slate-200 hover:border-emerald-500/60 flex items-center gap-2 transition group shadow-sm">
            <span class="w-2 h-2 rounded-full ${c.status === 'active' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-amber-400'}"></span>
            <span class="font-medium group-hover:text-emerald-400">${c.doc_id} • Điều ${c.article_number}</span>
            <i class="fa-solid fa-arrow-up-right-from-square text-[9px] text-slate-400 group-hover:text-emerald-400"></i>
          </button>
        `).join('');
        autoScrollToBottom();
      },
      finish: () => {
        if (stepTitle) stepTitle.textContent = 'Quy trình Agentic RAG hoàn tất';
      }
    };
  }

  function renderHistoricalAssistantMessage(content, citations, timestamp) {
    if (!messagesContainer) return;
    const timeStr = getFormattedTime(timestamp);
    const div = document.createElement('div');
    div.className = 'flex items-start gap-3 my-4 max-w-4xl group chat-assistant-container';

    const renderedHtml = (typeof marked !== 'undefined' && marked.parse) ? marked.parse(content || '') : escapeHtml(content || '');
    let citationsHtml = '';
    if (citations && citations.length > 0) {
      citationsHtml = `
        <div class="pt-1">
          <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-bookmark text-emerald-400"></i>
            <span>Căn cứ pháp lý được trích dẫn (Bấm xem nguyên văn):</span>
          </div>
          <div class="flex flex-wrap gap-2">
            ${citations.map(c => `
              <button onclick="viewArticleDetails('${c.article_id}')" class="px-3 py-1.5 rounded-lg bg-surface-800/90 hover:bg-slate-700 border border-slate-700/80 text-xs text-slate-200 hover:border-emerald-500/60 flex items-center gap-2 transition group shadow-sm">
                <span class="w-2 h-2 rounded-full ${c.status === 'active' ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]' : 'bg-amber-400'}"></span>
                <span class="font-medium group-hover:text-emerald-400">${c.doc_id} • Điều ${c.article_number}</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[9px] text-slate-400 group-hover:text-emerald-400"></i>
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }

    div.innerHTML = `
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 via-teal-600 to-cyan-500 text-white flex items-center justify-center shrink-0 mt-0.5 shadow-lg shadow-emerald-500/20 ring-2 ring-emerald-500/20 text-xs">
        <i class="fa-solid fa-scale-balanced text-[13px]"></i>
      </div>
      <div class="flex-1 space-y-2.5 overflow-hidden">
        
        <!-- Header Info -->
        <div class="flex items-center justify-between px-1 select-none">
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-slate-200">Trợ Lý Pháp Luật Việt Nam</span>
            <span class="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 rounded-full">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              Strict Grounding
            </span>
          </div>
          <span class="text-[10px] text-slate-400">${escapeHtml(timeStr)}</span>
        </div>

        <!-- Main Answer Card -->
        <div class="chat-assistant-bubble relative group/card">
          <button 
            type="button"
            onclick="copyMessageText(this)" 
            title="Sao chép câu trả lời"
            class="btn-copy-bubble absolute top-3.5 right-3.5 px-2.5 py-1 rounded-lg bg-surface-800/90 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700 text-xs flex items-center gap-1.5 shadow-sm cursor-pointer z-10"
          >
            <i class="fa-regular fa-copy"></i>
            <span>Sao chép</span>
          </button>
          
          <div class="prose-legal answer-body">
            ${renderedHtml}
          </div>
        </div>

        ${citationsHtml}
      </div>
    `;

    messagesContainer.appendChild(div);
  }

  function handleAgentEvent(msgRef, event) {
    if (event.type === 'step') {
      msgRef.addStep(event.node, event.message);
    } else if (event.type === 'answer') {
      const renderedHtml = (typeof marked !== 'undefined' && marked.parse) ? marked.parse(event.content) : escapeHtml(event.content);
      msgRef.updateContent(renderedHtml);
    } else if (event.type === 'citations') {
      msgRef.addCitations(event.citations);
    }
    autoScrollToBottom();
  }

  // =====================================================================
  // 4. ARTICLE DRAWER (PARENT DOCUMENT FULL-TEXT)
  // =====================================================================
  if (closeDrawer && articleDrawer) {
    closeDrawer.addEventListener('click', () => {
      articleDrawer.classList.add('translate-x-full');
    });
  }

  window.viewArticleDetails = async (articleId) => {
    if (!drawerContent || !articleDrawer) return;
    drawerContent.innerHTML = `
      <div class="flex items-center justify-center py-20 text-slate-400">
        <i class="fa-solid fa-circle-notch fa-spin text-2xl text-emerald-400"></i>
      </div>
    `;
    articleDrawer.classList.remove('translate-x-full');

    try {
      const res = await fetch(`/api/article/${encodeURIComponent(articleId)}`);
      if (!res.ok) throw new Error('Không tìm thấy điều luật');
      const data = await res.json();

      drawerContent.innerHTML = `
        <div class="space-y-4">
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <span class="text-xs font-semibold uppercase px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                ${data.status === 'active' ? '● Đang có hiệu lực' : '○ Đã sửa đổi / Hết hiệu lực'}
              </span>
              <div class="text-xs text-slate-400 mt-2">Văn bản: <strong class="text-slate-200">${data.doc_symbol}</strong></div>
            </div>
            <span class="text-xs text-slate-400">Hiệu lực: ${data.effective_date || 'Chưa rõ'}</span>
          </div>

          <div>
            <div class="text-xs font-semibold text-slate-400 uppercase">${data.chapter_title || ''}</div>
            <h4 class="text-base font-bold text-white mt-1">Điều ${data.article_number}: ${data.title || ''}</h4>
          </div>

          <div class="p-4 rounded-xl bg-surface-800/80 border border-slate-700/60 text-sm text-slate-200 whitespace-pre-line leading-relaxed font-mono text-xs">
            ${escapeHtml(data.content)}
          </div>

          ${data.amendment_chain && data.amendment_chain.is_amended ? `
            <div class="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-300">
              <i class="fa-solid fa-triangle-exclamation mr-1"></i>
              <strong>Lưu ý sửa đổi:</strong> Điều này đã được sửa đổi bởi điều khoản <code>${data.amendment_chain.latest_id}</code>.
            </div>
          ` : ''}

          ${data.references && data.references.length > 0 ? `
            <div>
              <div class="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">Tham chiếu liên quan:</div>
              <div class="space-y-1.5">
                ${data.references.map(r => `
                  <button onclick="viewArticleDetails('${r.target_id}')" class="w-full text-left p-2 rounded bg-surface-800 hover:bg-slate-700 text-xs text-emerald-400 flex items-center justify-between transition">
                    <span><i class="fa-solid fa-link text-[10px] mr-1.5"></i>${r.target_id}</span>
                    <span class="text-[11px] text-slate-400">${r.details || ''}</span>
                  </button>
                `).join('')}
              </div>
            </div>
          ` : ''}
        </div>
      `;
    } catch (e) {
      drawerContent.innerHTML = `<div class="p-4 text-xs text-red-400">Lỗi nạp điều luật: ${e.message}</div>`;
    }
  };

  // =====================================================================
  // 5. UPLOAD & INGESTION MODAL
  // =====================================================================
  function openUploadModal() {
    if (uploadDocModal) uploadDocModal.classList.remove('hidden');
    if (uploadStatusBox) uploadStatusBox.classList.add('hidden');
    selectedFile = null;
    if (fileInput) fileInput.value = '';
    if (selectedFileName) selectedFileName.classList.add('hidden');
    if (rawDocText) rawDocText.value = '';
    if (uploadDocSymbol) uploadDocSymbol.value = '';
  }

  function closeUploadModalHandler() {
    if (uploadDocModal) uploadDocModal.classList.add('hidden');
  }

  if (btnHeaderUpload) btnHeaderUpload.addEventListener('click', openUploadModal);
  if (btnOpenUpload) btnOpenUpload.addEventListener('click', openUploadModal);
  if (closeUploadModal) closeUploadModal.addEventListener('click', closeUploadModalHandler);
  if (btnCancelUpload) btnCancelUpload.addEventListener('click', closeUploadModalHandler);

  // Tab switching
  if (tabBtnFile && tabBtnRaw && tabContentFile && tabContentRaw) {
    tabBtnFile.addEventListener('click', () => {
      activeUploadTab = 'file';
      tabBtnFile.className = 'flex-1 py-1.5 rounded-md bg-emerald-600 text-white transition flex items-center justify-center gap-2';
      tabBtnRaw.className = 'flex-1 py-1.5 rounded-md text-slate-400 hover:text-white transition flex items-center justify-center gap-2';
      tabContentFile.classList.remove('hidden');
      tabContentRaw.classList.add('hidden');
    });

    tabBtnRaw.addEventListener('click', () => {
      activeUploadTab = 'raw';
      tabBtnRaw.className = 'flex-1 py-1.5 rounded-md bg-emerald-600 text-white transition flex items-center justify-center gap-2';
      tabBtnFile.className = 'flex-1 py-1.5 rounded-md text-slate-400 hover:text-white transition flex items-center justify-center gap-2';
      tabContentRaw.classList.remove('hidden');
      tabContentFile.classList.add('hidden');
    });
  }

  // Dropzone click & drag
  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        selectedFile = e.target.files[0];
        if (selectedFileName) {
          selectedFileName.textContent = `✓ Đã chọn: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
          selectedFileName.classList.remove('hidden');
        }
      }
    });

    ['dragenter', 'dragover'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.add('border-emerald-500', 'bg-emerald-500/10');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-emerald-500', 'bg-emerald-500/10');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        selectedFile = e.dataTransfer.files[0];
        fileInput.files = e.dataTransfer.files;
        if (selectedFileName) {
          selectedFileName.textContent = `✓ Đã chọn: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
          selectedFileName.classList.remove('hidden');
        }
      }
    });
  }

  // Submit Ingestion
  if (btnSubmitUpload) {
    btnSubmitUpload.addEventListener('click', async () => {
      if (uploadStatusBox) uploadStatusBox.classList.remove('hidden');
      if (uploadStatusText) {
        uploadStatusText.innerHTML = `
          <i class="fa-solid fa-circle-notch fa-spin text-emerald-400"></i>
          <span>Đang phân tích cấu trúc, trích xuất quan hệ & lập chỉ mục 3 kho...</span>
        `;
      }
      btnSubmitUpload.disabled = true;

      try {
        let res;
        const symbolVal = uploadDocSymbol ? uploadDocSymbol.value.trim() : '';
        const domainVal = uploadDomain ? uploadDomain.value : 'chung';

        if (activeUploadTab === 'file') {
          if (!selectedFile) {
            throw new Error('Vui lòng chọn một file văn bản (.txt, .pdf, .docx).');
          }
          const formData = new FormData();
          formData.append('file', selectedFile);
          if (symbolVal) formData.append('doc_symbol', symbolVal);
          if (domainVal) formData.append('domain', domainVal);

          res = await fetch('/api/documents/upload', {
            method: 'POST',
            body: formData
          });
        } else {
          const rawContent = rawDocText ? rawDocText.value.trim() : '';
          if (!rawContent) {
            throw new Error('Vui lòng dán nội dung văn bản vào khung nhập.');
          }
          res = await fetch('/api/documents/raw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              raw_text: rawContent,
              doc_symbol: symbolVal || null,
              domain: domainVal || null
            })
          });
        }

        if (!res.ok) {
          const errJson = await res.json().catch(() => ({}));
          throw new Error(errJson.detail || 'Lỗi không xác định khi nạp văn bản.');
        }

        const result = await res.json();
        if (uploadStatusText) {
          uploadStatusText.innerHTML = `
            <div class="text-emerald-400 space-y-1">
              <div class="font-bold flex items-center gap-1.5"><i class="fa-solid fa-check"></i> Đã nạp thành công: ${result.doc_symbol}</div>
              <div class="text-[11px] text-slate-300">• Số Điều luật: <strong>${result.articles_count}</strong> | Số Qdrant Chunks: <strong>${result.chunks_count}</strong> | Số quan hệ Graph: <strong>${result.relationships_count}</strong></div>
            </div>
          `;
        }

        loadStats();
        setTimeout(() => {
          closeUploadModalHandler();
        }, 2000);

      } catch (e) {
        if (uploadStatusText) {
          uploadStatusText.innerHTML = `
            <span class="text-red-400 flex items-center gap-1.5"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(e.message)}</span>
          `;
        }
      } finally {
        btnSubmitUpload.disabled = false;
      }
    });
  }

  // =====================================================================
  // 6. MANAGE LEGAL DOCUMENTS MODAL
  // =====================================================================
  async function loadDocumentsList() {
    if (!docsTableBody) return;
    docsTableBody.innerHTML = `
      <tr>
        <td colspan="6" class="p-6 text-center text-slate-400">
          <i class="fa-solid fa-circle-notch fa-spin text-emerald-400 mr-2"></i>Đang tải danh sách văn bản...
        </td>
      </tr>
    `;

    try {
      const res = await fetch('/api/documents');
      if (!res.ok) throw new Error('Không thể tải danh sách văn bản.');
      const docs = await res.json();

      if (!docs || docs.length === 0) {
        docsTableBody.innerHTML = `
          <tr>
            <td colspan="6" class="p-6 text-center text-slate-500">Kho dữ liệu hiện chưa có văn bản nào.</td>
          </tr>
        `;
        return;
      }

      docsTableBody.innerHTML = docs.map(d => `
        <tr class="hover:bg-surface-800/60 transition">
          <td class="p-3 font-semibold text-emerald-400 whitespace-nowrap">
            <span class="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">${escapeHtml(d.doc_symbol)}</span>
          </td>
          <td class="p-3 text-slate-200 max-w-xs truncate" title="${escapeHtml(d.title)}">
            ${escapeHtml(d.title)}
          </td>
          <td class="p-3 text-slate-400 whitespace-nowrap">
            ${d.domain === 'giao_thong' ? 'Giao thông' : d.domain === 'lao_dong' ? 'Lao động' : d.domain}
          </td>
          <td class="p-3 text-center text-slate-200 font-bold">${d.articles_count}</td>
          <td class="p-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
              ${d.sync_status}
            </span>
          </td>
          <td class="p-3 text-right whitespace-nowrap">
            <button onclick="window.deleteLegalDoc('${d.doc_id}', '${escapeHtml(d.doc_symbol)}')" class="px-2 py-1 rounded bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 transition text-xs flex items-center gap-1 inline-flex">
              <i class="fa-regular fa-trash-can text-[10px]"></i>
              <span>Xóa</span>
            </button>
          </td>
        </tr>
      `).join('');
    } catch (e) {
      docsTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="p-4 text-center text-red-400">Lỗi: ${e.message}</td>
        </tr>
      `;
    }
  }

  window.deleteLegalDoc = async (docId, docSymbol) => {
    if (!confirm(`Bạn có chắc chắn muốn xóa văn bản "${docSymbol}" khỏi cả 3 kho dữ liệu (SQLite, Qdrant và Graph)?`)) {
      return;
    }
    try {
      const res = await fetch(`/api/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' });
      if (res.ok) {
        alert(`Đã xóa thành công văn bản ${docSymbol}.`);
        loadDocumentsList();
        loadStats();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Lỗi khi xóa: ${err.detail || 'Không rõ'}`);
      }
    } catch (e) {
      alert(`Lỗi kết nối: ${e.message}`);
    }
  };

  if (btnOpenManageDocs) {
    btnOpenManageDocs.addEventListener('click', () => {
      if (manageDocsModal) manageDocsModal.classList.remove('hidden');
      loadDocumentsList();
    });
  }

  if (closeManageDocs && manageDocsModal) closeManageDocs.addEventListener('click', () => manageDocsModal.classList.add('hidden'));
  if (btnCloseManage && manageDocsModal) btnCloseManage.addEventListener('click', () => manageDocsModal.classList.add('hidden'));

  // Nạp lại dữ liệu mẫu
  if (btnSeedData) {
    btnSeedData.addEventListener('click', async () => {
      btnSeedData.disabled = true;
      btnSeedData.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-emerald-400"></i><span>Đang nạp 4 văn bản...</span>`;
      try {
        const res = await fetch('/api/seed', { method: 'POST' });
        if (res.ok) {
          alert('Đã nạp và lập chỉ mục thành công 4 văn bản luật mẫu!');
          loadDocumentsList();
          loadStats();
        }
      } catch (e) {
        alert('Lỗi nạp văn bản mẫu: ' + e);
      } finally {
        btnSeedData.disabled = false;
        btnSeedData.innerHTML = `<i class="fa-solid fa-arrows-rotate text-emerald-400"></i><span>Nạp lại 4 văn bản mẫu mặc định</span>`;
      }
    });
  }

  // Legacy compat for cached btn-seed
  const legacySeedBtn = document.getElementById('btn-seed');
  if (legacySeedBtn) {
    legacySeedBtn.addEventListener('click', () => {
      if (btnSeedData) btnSeedData.click();
    });
  }

  // =====================================================================
  // 7. SETTINGS MODAL
  // =====================================================================
  if (btnSettings && settingsModal) {
    btnSettings.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/settings');
        const cfg = await res.json();
        if (cfg.ollama_model && selectOllamaModel) {
          selectOllamaModel.value = cfg.ollama_model;
        }
        if (inputGeminiKey) inputGeminiKey.value = cfg.gemini_key || '';
        if (inputOpenaiKey) inputOpenaiKey.value = cfg.openai_key || '';
      } catch (e) {}
      settingsModal.classList.remove('hidden');
    });
  }

  if (closeSettings && settingsModal) {
    closeSettings.addEventListener('click', () => {
      settingsModal.classList.add('hidden');
    });
  }

  if (btnSaveSettings && settingsModal) {
    btnSaveSettings.addEventListener('click', async () => {
      try {
        const chosenModel = selectOllamaModel ? selectOllamaModel.value : 'qwen2.5:3b';
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ollama_model: chosenModel,
            gemini_key: inputGeminiKey ? inputGeminiKey.value.trim() : '',
            openai_key: inputOpenaiKey ? inputOpenaiKey.value.trim() : ''
          })
        });
        alert('Đã cập nhật mô hình Ollama thành công: ' + chosenModel);
        settingsModal.classList.add('hidden');
      } catch (e) {
        alert('Lỗi lưu cấu hình: ' + e);
      }
    });
  }

  // Escape HTML Helper
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
