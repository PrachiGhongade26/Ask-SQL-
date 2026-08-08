import { useState, useRef, useEffect } from "react";
import axios from "axios";

const API_BASE = "http://localhost:8000";

function Navbar({ theme, onToggleTheme }) {
  return (
    <nav className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--bg)]/90 backdrop-blur">
      <div className="max-w-2xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[var(--accent)] font-['JetBrains_Mono'] text-sm">{'>'}</span>
          <span className="font-['Space_Grotesk'] font-bold text-lg tracking-tight">
            Ask<span className="text-[var(--accent)]">SQL</span>
          </span>
        </div>

        <div className="flex items-center gap-6">
          <a href="#home" className="text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            Home
          </a>
          <a href="#about" className="text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors">
            About
          </a>
          <button
            onClick={onToggleTheme}
            aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            title={theme === "dark" ? "Light mode" : "Dark mode"}
            className="w-8 h-8 rounded-lg border border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors flex items-center justify-center"
          >
            {theme === "dark" ? (
              // Sun icon (click to go light)
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <line x1="12" y1="2" x2="12" y2="4" />
                <line x1="12" y1="20" x2="12" y2="22" />
                <line x1="4.93" y1="4.93" x2="6.34" y2="6.34" />
                <line x1="17.66" y1="17.66" x2="19.07" y2="19.07" />
                <line x1="2" y1="12" x2="4" y2="12" />
                <line x1="20" y1="12" x2="22" y2="12" />
                <line x1="4.93" y1="19.07" x2="6.34" y2="17.66" />
                <line x1="17.66" y1="6.34" x2="19.07" y2="4.93" />
              </svg>
            ) : (
              // Moon icon (click to go dark)
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </nav>
  );
}

function Step({ number, title, active, done, children }) {
  return (
    <div className="relative pl-14">
      <div
        className={`absolute left-0 top-0 w-9 h-9 rounded-full flex items-center justify-center font-['JetBrains_Mono'] text-xs border transition-colors ${
          done
            ? "bg-[var(--accent-dim)] border-[var(--accent)] text-[var(--accent)]"
            : active
            ? "border-[var(--accent)] text-[var(--accent)]"
            : "border-[var(--border)] text-[var(--text-muted)]"
        }`}
      >
        {done ? "✓" : number}
      </div>
      <h2 className="font-['Space_Grotesk'] font-semibold text-[var(--text)] mb-3">
        {title}
      </h2>
      {children}
    </div>
  );
}

function App() {
  const [theme, setTheme] = useState("dark");

  useEffect(() => {
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  const [tableName, setTableName] = useState(null);
  const [schema, setSchema] = useState(null);
  const [rowCount, setRowCount] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState(null);
  const [results, setResults] = useState(null);
  const [askError, setAskError] = useState(null);
  const [asking, setAsking] = useState(false);

  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const recognitionRef = useRef(null);

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setVoiceSupported(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join("");
      setQuestion(transcript);
    };

    recognition.onerror = () => {
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, []);

  const handleToggleVoice = () => {
    if (!recognitionRef.current || asking || !tableName) return;

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      setAskError(null);
      setQuestion("");
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const doUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setTableName(null);
    setSql(null);
    setResults(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setTableName(res.data.table_name);
      setSchema(res.data.schema);
      setRowCount(res.data.row_count);
    } catch (err) {
      setUploadError(err.response?.data?.detail || "Upload failed. Try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    doUpload(e.dataTransfer.files[0]);
  };

  const handleAsk = async (e) => {
    e.preventDefault();
    if (!question.trim() || !tableName) return;
    setAsking(true);
    setAskError(null);
    setSql(null);
    setResults(null);

    try {
      const res = await axios.post(`${API_BASE}/ask`, {
        table_name: tableName,
        question,
      });
      setSql(res.data.sql);
      setResults(res.data.results);
    } catch (err) {
      setAskError(err.response?.data?.detail || "Something went wrong. Try again.");
    } finally {
      setAsking(false);
    }
  };

  const columns = results && results.length > 0 ? Object.keys(results[0]) : [];

  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <Navbar theme={theme} onToggleTheme={handleToggleTheme} />

      <div id="home" className="max-w-2xl mx-auto px-6 py-12">
        <header className="mb-14">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[var(--accent)] font-['JetBrains_Mono'] text-sm">{'>'}</span>
            <h1 className="font-['Space_Grotesk'] font-bold text-3xl tracking-tight">
              Ask<span className="text-[var(--accent)]">SQL</span>
            </h1>
          </div>
          <p className="text-[var(--text-muted)] text-sm">
            English in. SQL out. Upload a CSV and ask.
          </p>
        </header>

        <div className="relative flex flex-col gap-10">
          <div className="absolute left-[17px] top-9 bottom-9 w-px bg-[var(--border)]" />

          <Step number="1" title="Upload your data" active={!tableName} done={!!tableName}>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`rounded-xl border border-dashed p-6 cursor-pointer transition-all ${
                dragOver
                  ? "border-[var(--accent)] bg-[var(--accent-dim)]"
                  : "border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-hover)]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={(e) => doUpload(e.target.files[0])}
                className="hidden"
              />
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-[var(--accent-dim)] flex items-center justify-center text-[var(--accent)] font-['JetBrains_Mono'] text-xs shrink-0">
                  CSV
                </div>
                <div className="text-sm">
                  <p className="text-[var(--text)]">
                    {uploading ? "Uploading..." : "Drop a CSV here, or click to browse"}
                  </p>
                  <p className="text-[var(--text-muted)] text-xs mt-0.5">Max file size applies</p>
                </div>
              </div>
            </div>

            {uploadError && (
              <p className="text-sm text-red-400 mt-3 font-['JetBrains_Mono']">{uploadError}</p>
            )}

            {tableName && (
              <div className="animate-in mt-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 font-['JetBrains_Mono'] text-xs">
                <div className="flex justify-between text-[var(--text-muted)] mb-1">
                  <span>table</span>
                  <span className="text-[var(--accent)]">{tableName}</span>
                </div>
                <div className="flex justify-between text-[var(--text-muted)] mb-2">
                  <span>rows</span>
                  <span className="text-[var(--text)]">{rowCount}</span>
                </div>
                <div className="text-[var(--text-muted)] break-all leading-relaxed border-t border-[var(--border)] pt-2">
                  {schema}
                </div>
              </div>
            )}
          </Step>

          <Step number="2" title="Ask a question" active={!!tableName && !sql} done={!!sql}>
            <form onSubmit={handleAsk} className="relative">
              <div
                className={`flex items-center gap-2 rounded-xl border bg-[var(--surface)] px-4 py-3 transition-colors ${
                  tableName ? "border-[var(--border)] focus-within:border-[var(--accent)]" : "border-[var(--border)] opacity-50"
                }`}
              >
                <span className="text-[var(--accent)] font-['JetBrains_Mono'] text-sm">{'>'}</span>
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  disabled={!tableName || asking}
                  placeholder={
                    isListening
                      ? "Listening..."
                      : tableName
                      ? "How many orders per region?"
                      : "Upload a CSV first"
                  }
                  className="flex-1 bg-transparent outline-none text-sm font-['JetBrains_Mono'] placeholder:text-[var(--text-muted)]"
                />
                {voiceSupported && (
                  <button
                    type="button"
                    onClick={handleToggleVoice}
                    disabled={!tableName || asking}
                    title={isListening ? "Stop listening" : "Ask by voice"}
                    className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center border transition-colors disabled:opacity-40 ${
                      isListening
                        ? "border-red-400 text-red-400 animate-pulse"
                        : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                    }`}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                      <line x1="12" y1="19" x2="12" y2="23" />
                      <line x1="8" y1="23" x2="16" y2="23" />
                    </svg>
                  </button>
                )}
                <button
                  type="submit"
                  disabled={!tableName || asking || !question.trim()}
                  className="text-xs font-['Space_Grotesk'] font-semibold px-3 py-1.5 rounded-lg bg-[var(--accent)] text-[#0A0A0A] disabled:bg-[var(--border)] disabled:text-[var(--text-muted)] transition-colors"
                >
                  {asking ? "Running" : "Run"}
                </button>
              </div>
            </form>
            {askError && (
              <p className="text-sm text-red-400 mt-3 font-['JetBrains_Mono']">{askError}</p>
            )}
            {!voiceSupported && (
              <p className="text-[var(--text-muted)] text-xs mt-2 font-['JetBrains_Mono']">
                Voice input isn't supported in this browser — try Chrome or Edge.
              </p>
            )}
            {asking && (
              <div className="flex gap-1 mt-3 pl-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" style={{ animationDelay: "0.15s" }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" style={{ animationDelay: "0.3s" }} />
              </div>
            )}
          </Step>

          {sql && (
            <Step number="3" title="Result" done>
              <div className="animate-in rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
                <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-[var(--border)] bg-[var(--surface-hover)]">
                  <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
                  <span className="w-2 h-2 rounded-full bg-[var(--amber)]" />
                  <span className="w-2 h-2 rounded-full bg-[var(--border-hover)]" />
                  <span className="text-[var(--text-muted)] text-xs font-['JetBrains_Mono'] ml-2">generated.sql</span>
                </div>
                <pre className="animate-type font-['JetBrains_Mono'] text-xs text-[var(--accent)] p-4 overflow-x-auto whitespace-pre-wrap">
                  {sql}
                </pre>

                {results && results.length > 0 ? (
                  <div className="overflow-x-auto border-t border-[var(--border)]">
                    <table className="min-w-full text-xs font-['JetBrains_Mono']">
                      <thead>
                        <tr className="bg-[var(--surface-hover)]">
                          {columns.map((col) => (
                            <th key={col} className="text-left px-4 py-2 text-[var(--text-muted)] font-medium border-b border-[var(--border)]">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {results.map((row, i) => (
                          <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-hover)] transition-colors">
                            {columns.map((col) => (
                              <td key={col} className="px-4 py-2 text-[var(--text)]">
                                {String(row[col])}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-[var(--text-muted)] text-xs font-['JetBrains_Mono'] p-4 border-t border-[var(--border)]">
                    No rows returned.
                  </p>
                )}
              </div>
            </Step>
          )}
        </div>
        

        <section id="about" className="mt-24 pt-10 border-t border-[var(--border)]">
          <h2 className="font-['Space_Grotesk'] font-semibold text-xl mb-3">About</h2>
          <p className="text-[var(--text-muted)] text-sm leading-relaxed max-w-xl">
            AskSQL turns plain English questions into SQL queries and runs them
            instantly against your uploaded data. Built with FastAPI, DuckDB,
            and Groq's Llama 3.3 70B for natural language understanding — no
            SQL knowledge required to explore your own datasets.
          </p>
        </section>
      </div>
    </div>
  );
}

export default App;
