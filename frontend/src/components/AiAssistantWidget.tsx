import { useState } from "react";

import { assistantChat } from "../api";

interface Message {
  id: string;
  from: "user" | "assistant";
  text: string;
}

interface AiAssistantWidgetProps {
  token: string;
  screen: string;
}

function formatActions(actions: string[]): string {
  const cleaned = actions
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 3);
  if (!cleaned.length) return "";
  return cleaned.map((item, index) => `${index + 1}. ${item}`).join("\n");
}

function buildAssistantText(reply: string, actions: string[]): string {
  const cleanedReply = reply.trim();
  const actionsText = formatActions(actions);
  if (!actionsText) return cleanedReply;
  return `${cleanedReply}\n\nШаги:\n${actionsText}`;
}

export function AiAssistantWidget({ token, screen }: AiAssistantWidgetProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      from: "assistant",
      text: "Привет! Я помогу понять, куда нажимать и как быстро сделать нужный сценарий.",
    },
  ]);

  async function send() {
    const prompt = text.trim();
    if (!prompt || isLoading) return;

    const userMessage: Message = {
      id: `u-${Date.now()}`,
      from: "user",
      text: prompt,
    };
    setMessages((prev) => [...prev, userMessage]);
    setText("");
    setIsLoading(true);

    try {
      const response = await assistantChat(token, { message: prompt, screen });
      const assistantMessage: Message = {
        id: `a-${Date.now()}`,
        from: "assistant",
        text: buildAssistantText(response.reply, response.suggested_actions),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const details = error instanceof Error ? error.message : "Сервис ИИ временно недоступен.";
      const failure: Message = {
        id: `e-${Date.now()}`,
        from: "assistant",
        text:
          `Не удалось получить живой ответ от ИИ.\n${details}\n\n` +
          "Проверьте, что Ollama запущен и модель доступна, затем повторите запрос.",
      };
      setMessages((prev) => [...prev, failure]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="ai-chat-root">
      {open && (
        <section className="ai-chat-panel fade-up">
          <header>
            <div>
              <p className="badge">ИИ Навигатор</p>
              <h3>Подскажу по шагам</h3>
            </div>
            <button className="button ghost" onClick={() => setOpen(false)}>
              Закрыть
            </button>
          </header>

          <div className="ai-chat-log">
            {messages.map((message) => (
              <article key={message.id} className={`ai-message ${message.from}`}>
                {message.text}
              </article>
            ))}
          </div>

          <div className="ai-chat-input-row">
            <input
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Например: куда сначала зайти, чтобы добавить задачу?"
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            <button className="button secondary" onClick={() => void send()} disabled={isLoading}>
              {isLoading ? "..." : "Отправить"}
            </button>
          </div>
        </section>
      )}

      <button className="ai-fab" onClick={() => setOpen((prev) => !prev)} aria-label="Открыть чат ИИ">
        ИИ
      </button>
    </div>
  );
}
