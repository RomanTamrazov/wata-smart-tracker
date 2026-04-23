interface ToastItem {
  id: string;
  kind: "success" | "error";
  text: string;
}

interface ToastViewportProps {
  items: ToastItem[];
  onClose: (id: string) => void;
}

export function ToastViewport({ items, onClose }: ToastViewportProps) {
  if (!items.length) return null;

  return (
    <aside className="toast-viewport" aria-live="polite" aria-atomic="true">
      {items.map((item) => (
        <article key={item.id} className={`toast-card ${item.kind}`} role="status">
          <div className="toast-content">
            <strong>{item.kind === "success" ? "Готово" : "Ошибка"}</strong>
            <p>{item.text}</p>
          </div>
          <button
            type="button"
            className="toast-close"
            onClick={() => onClose(item.id)}
            aria-label="Закрыть уведомление"
          >
            ×
          </button>
        </article>
      ))}
    </aside>
  );
}

