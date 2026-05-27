import { useEffect, useRef, useState } from "react";
import { Circle, Terminal } from "lucide-react";

const AGENT_EVENTS_WS_URL = "ws://127.0.0.1:8000/api/v1/ws/agent-events";
const RECONNECT_DELAY_MS = 2000;

type ConnectionStatus = "connecting" | "connected" | "disconnected";

interface TerminalLog {
  id: number;
  timestamp: string;
  message: string;
}

function formatMessage(event: MessageEvent<string>): string {
  try {
    return JSON.stringify(JSON.parse(event.data), null, 2);
  } catch {
    return event.data;
  }
}

function createLog(message: string): TerminalLog {
  return {
    id: Date.now() + Math.random(),
    timestamp: new Date().toLocaleTimeString(),
    message,
  };
}

export default function AgentTerminal() {
  const [logs, setLogs] = useState<TerminalLog[]>([
    createLog("PAOS agent terminal initialized."),
  ]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [logs]);

  useEffect(() => {
    let shouldReconnect = true;

    const appendLog = (message: string) => {
      setLogs((currentLogs) => [...currentLogs, createLog(message)]);
    };

    const connect = () => {
      setConnectionStatus("connecting");
      appendLog(`Connecting to ${AGENT_EVENTS_WS_URL} ...`);

      const socket = new WebSocket(AGENT_EVENTS_WS_URL);
      socketRef.current = socket;

      socket.onopen = () => {
        setConnectionStatus("connected");
        appendLog("WebSocket connected.");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        appendLog(formatMessage(event));
      };

      socket.onerror = () => {
        appendLog("WebSocket error occurred.");
      };

      socket.onclose = () => {
        socketRef.current = null;
        setConnectionStatus("disconnected");
        appendLog("WebSocket disconnected.");

        if (shouldReconnect) {
          appendLog(`Reconnecting in ${RECONNECT_DELAY_MS / 1000}s ...`);
          reconnectTimerRef.current = window.setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };
    };

    connect();

    return () => {
      shouldReconnect = false;

      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }

      if (socketRef.current !== null) {
        socketRef.current.close();
      }
    };
  }, []);

  const statusClassName =
    connectionStatus === "connected"
      ? "text-emerald-300"
      : connectionStatus === "connecting"
        ? "text-amber-300"
        : "text-rose-300";

  return (
    <section className="flex h-full min-h-[260px] flex-col overflow-hidden rounded-2xl border border-slate-800 bg-black/50 shadow-inner">
      <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2 text-emerald-300">
          <Terminal size={17} />
          <span className="text-sm font-semibold">Agent Event Stream</span>
        </div>
        <div className={`flex items-center gap-1.5 text-xs ${statusClassName}`}>
          <Circle size={8} fill="currentColor" />
          {connectionStatus}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-5 text-emerald-300">
        {logs.map((log) => (
          <div className="mb-3 whitespace-pre-wrap break-words" key={log.id}>
            <span className="mr-2 text-slate-500">[{log.timestamp}]</span>
            <span>{log.message}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
