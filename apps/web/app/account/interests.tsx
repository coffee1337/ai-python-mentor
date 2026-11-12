"use client";

import { useEffect, useState } from "react";
import { api, errorMessage } from "../lib/api";

type Payload = { vocabulary: Record<string, string>; selected: string[] };

export default function InterestsSelector() {
  const [vocabulary, setVocabulary] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api<Payload>("/me/interests")
      .then((data) => {
        if (!alive) return;
        setVocabulary(data.vocabulary);
        setSelected(data.selected);
      })
      .catch(() => alive && setStatus("Интересы временно недоступны."));
    return () => {
      alive = false;
    };
  }, []);

  async function toggle(key: string) {
    const next = selected.includes(key)
      ? selected.filter((item) => item !== key)
      : [...selected, key].slice(0, 3);
    setBusy(true);
    setStatus("");
    try {
      const saved = await api<{ selected: string[]; scenario: string | null }>("/me/interests", {
        method: "PUT",
        body: JSON.stringify({ interests: next }),
      });
      setSelected(saved.selected);
      setStatus(saved.scenario ? "Сохранено: примеры в практике будут ближе к теме." : "Сохранено.");
    } catch (reason) {
      setStatus(errorMessage(reason, "Не удалось сохранить интересы."));
    } finally {
      setBusy(false);
    }
  }

  if (Object.keys(vocabulary).length === 0) return null;

  return (
    <section className="panel" aria-labelledby="interests-title">
      <h3 id="interests-title">Интересы для примеров</h3>
      <p className="product-field-hint">
        Влияют только на обёртку примеров в практике — условие, тесты и сложность те же.
        Можно выбрать до трёх.
      </p>
      <div className="interests-row" role="group" aria-label="Темы примеров">
        {Object.entries(vocabulary).map(([key, title]) => (
          <button
            key={key}
            type="button"
            className={`mentor-mode ${selected.includes(key) ? "is-active" : ""}`}
            aria-pressed={selected.includes(key)}
            disabled={busy}
            onClick={() => void toggle(key)}
          >
            {title}
          </button>
        ))}
      </div>
      {status ? (
        <p className="product-field-hint" role="status">
          {status}
        </p>
      ) : null}
    </section>
  );
}
