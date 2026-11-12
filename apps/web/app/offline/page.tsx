import type { Metadata } from "next";
import PublicShell from "../components/public-shell";

export const metadata: Metadata = {
  title: "Нет сети — AI Python Mentor",
  robots: { index: false },
};

export default function OfflinePage() {
  return (
    <PublicShell
      title="Нет подключения"
      lead="Страница не загрузилась, потому что пропала сеть. Уроки и прогресс сохранены на сервере — вернитесь, когда связь появится."
    >
      <p className="product-field-hint">
        Проверка кода и вопросы наставнику требуют сети: они исполняются и оцениваются на сервере.
      </p>
    </PublicShell>
  );
}
