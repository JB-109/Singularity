import { useState, useRef, useEffect } from 'react';
import type { KeyboardEvent, ChangeEvent, MouseEvent } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Register from './pages/Register';
import './App.css';

interface FunctionCall {
  name: string;
  args?: Record<string, unknown>;
  success?: boolean;
  error?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  functionCalls?: FunctionCall[];
}

interface ChatResponse {
  response: string;
  function_calls: FunctionCall[];
  session_id: string;
  conversation_id: string;
}

interface ConversationItem {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

const API_URL = 'http://localhost:8000';

function ChatApp() {
  const { user, token, logout } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [sidebarWidth, setSidebarWidth] = useState(260);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load conversations on mount
  useEffect(() => {
    if (token) {
      loadConversations();
    }
  }, [token]);

  const loadConversations = async () => {
    try {
      const response = await fetch(`${API_URL}/api/conversations`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setConversations(data.conversations);
      }
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadConversation = async (convId: string) => {
    try {
      const response = await fetch(`${API_URL}/api/conversations/${convId}`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setConversationId(convId);
        setSessionId(null); // Reset session for loaded conversation
        // Convert saved messages to UI format
        const loadedMessages: Message[] = data.messages.map((msg: { role: string; content: string; function_calls?: FunctionCall[] }, index: number) => ({
          id: `${convId}-${index}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          functionCalls: msg.function_calls,
        }));
        setMessages(loadedMessages);
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  };

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    adjustTextareaHeight();
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: userMessage.content,
          session_id: sessionId,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response');
      }

      const data: ChatResponse = await response.json();

      if (!sessionId) {
        setSessionId(data.session_id);
      }

      if (data.conversation_id && !conversationId) {
        setConversationId(data.conversation_id);
      }

      // Reload conversations to show the new one in sidebar
      loadConversations();

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.response,
        functionCalls: data.function_calls.length > 0 ? data.function_calls : undefined,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please make sure the backend server is running.',
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setConversationId(null);
    setInput('');
  };

  // Sidebar resize handlers
  const handleResizeStart = (e: MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: globalThis.MouseEvent) => {
      if (isResizing) {
        const newWidth = Math.max(200, Math.min(400, e.clientX));
        setSidebarWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing]);

  const formatMessageContent = (content: string) => {
    const parts = content.split(/(```[\s\S]*?```)/g);

    return parts.map((part, index) => {
      if (part.startsWith('```')) {
        const codeContent = part.replace(/```[\w]*\n?/g, '').replace(/```$/g, '');
        return (
          <pre key={index}>
            <code>{codeContent}</code>
          </pre>
        );
      }

      const inlineParts = part.split(/(`[^`]+`)/g);
      return inlineParts.map((inlinePart, inlineIndex) => {
        if (inlinePart.startsWith('`') && inlinePart.endsWith('`')) {
          return <code key={`${index}-${inlineIndex}`}>{inlinePart.slice(1, -1)}</code>;
        }
        return <span key={`${index}-${inlineIndex}`}>{inlinePart}</span>;
      });
    });
  };

  return (
    <div className="app">
      {/* Sidebar */}
      <aside
        className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`}
        style={{ width: isSidebarCollapsed ? 0 : sidebarWidth }}
      >
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={handleNewChat}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14" />
            </svg>
            New chat
          </button>
        </div>
        <div className="sidebar-content">
          <div className="sidebar-section-title">Recent Chats</div>
          {conversations.length === 0 ? (
            <div className="sidebar-empty">No conversations yet</div>
          ) : (
            <div className="conversation-list">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`conversation-item ${conversationId === conv.id ? 'active' : ''}`}
                  onClick={() => loadConversation(conv.id)}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  <span>{conv.title}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="sidebar-footer">
          <div className="sidebar-user" onClick={logout}>
            <div className="user-avatar">{user?.username?.charAt(0).toUpperCase()}</div>
            <span className="user-name">{user?.username}</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="logout-icon">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </div>
        </div>

        {/* Resize handle */}
        <div
          className="sidebar-resize-handle"
          onMouseDown={handleResizeStart}
        />
      </aside>

      {/* Sidebar toggle button */}
      <button
        className="sidebar-toggle"
        onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        style={{ left: isSidebarCollapsed ? 16 : sidebarWidth + 16 }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          {isSidebarCollapsed ? (
            <path d="M3 12h18M3 6h18M3 18h18" />
          ) : (
            <path d="M18 6L6 18M6 6l12 12" />
          )}
        </svg>
      </button>

      {/* Main Content */}
      <main className="main-content">
        {messages.length === 0 ? (
          <div className="welcome-screen">
            <div className="welcome-logo">S</div>
            <h1 className="welcome-title">Hello, {user?.username}!</h1>
            <p className="welcome-subtitle">
              Your AI coding assistant. Start a conversation by typing below.
            </p>
          </div>
        ) : (
          <div className="chat-container">
            <div className="chat-messages">
              {messages.map((message) => (
                <div key={message.id} className="message">
                  <div className={`message-avatar ${message.role}`}>
                    {message.role === 'user' ? user?.username?.charAt(0).toUpperCase() : 'S'}
                  </div>
                  <div className="message-content">
                    <div className="message-sender">
                      {message.role === 'user' ? 'You' : 'Singularity'}
                    </div>
                    <div className="message-text">
                      {formatMessageContent(message.content)}
                    </div>
                    {message.functionCalls && message.functionCalls.length > 0 && (
                      <div className="function-calls">
                        <div className="function-calls-title">Functions Called</div>
                        {message.functionCalls.map((fc, index) => (
                          <div key={index} className="function-call">
                            <span className="function-call-icon">⚡</span>
                            <span className="function-call-name">{fc.name}</span>
                            {fc.success && <span className="function-call-success">✓</span>}
                            {fc.error && <span className="function-call-error">✗ {fc.error}</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="message loading-message">
                  <div className="message-avatar assistant">S</div>
                  <div className="message-content">
                    <div className="message-sender">Singularity</div>
                    <div className="loading-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="input-container">
          <div className="input-wrapper">
            <div className="input-box">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Message Singularity..."
                rows={1}
                disabled={isLoading}
              />
              <button
                className={`send-button ${input.trim() && !isLoading ? 'active' : ''}`}
                onClick={sendMessage}
                disabled={!input.trim() || isLoading}
              >
                <svg viewBox="0 0 24 24" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                </svg>
              </button>
            </div>
            <div className="input-hint">
              Singularity can make mistakes. Check important info.
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

// Protected route component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner"></div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/" element={
        <ProtectedRoute>
          <ChatApp />
        </ProtectedRoute>
      } />
    </Routes>
  );
}

export default App;
