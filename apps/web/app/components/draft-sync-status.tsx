"use client";

import type { SyncedDraft } from "../lib/use-synced-draft";

const MESSAGES = {
  loading: "Проверяем черновик в аккаунте… Можно продолжать писать.",
  empty: "Черновик появится в аккаунте после редактирования.",
  saved: "Черновик сохранён в аккаунте и доступен на других устройствах.",
  local: "Изменения в редакторе. Готовим сохранение в аккаунте…",
  saving: "Сохраняем черновик в аккаунте…",
  error: "Синхронизация приостановлена. Текст остался в редакторе.",
  conflict: "В аккаунте другой вариант. Ваш текст сохранён в редакторе.",
  account_changed: "Синхронизация остановлена после смены аккаунта.",
};

export default function DraftSyncStatus<T>({
  sync, preview, disabled = false,
}: { sync: SyncedDraft<T>; preview: (content: T) => string; disabled?: boolean }) {
  if (!sync.enabled) return null;
  const text = (content: T | null) => content === null ? "Черновик очищен." : preview(content);
  return (
    <div className="draft-sync-status" data-sync-phase={sync.phase}>
      <p className="product-field-hint" role="status">{MESSAGES[sync.phase]}</p>
      {sync.message && <p className={sync.phase === "error" || sync.phase === "conflict" || sync.phase === "account_changed" ? "form-error" : "product-field-hint"} role={sync.phase === "error" || sync.phase === "account_changed" ? "alert" : "status"}>{sync.message}</p>}
      {sync.phase === "error" && (
        <button className="text-button" type="button" disabled={disabled} onClick={sync.retry}>Повторить синхронизацию</button>
      )}
      {sync.conflict && (
        <section className="draft-sync-conflict" aria-label="Выбор черновика">
          <h4>Выберите вариант черновика</h4>
          <p>Автоматическая замена остановлена. Сравните тексты: выбор не отправляет ответ на проверку и не запускает код.</p>
          <div className="draft-sync-versions">
            <div>
              <strong>В этом редакторе</strong>
              <pre className="draft-sync-preview" tabIndex={0}>{preview(sync.current)}</pre>
            </div>
            <div>
              <strong>В аккаунте</strong>
              <pre className="draft-sync-preview" tabIndex={0}>{text(sync.conflict.content)}</pre>
            </div>
          </div>
          <div className="draft-sync-actions product-action-row">
            <button className="button button-secondary" type="button" disabled={disabled} onClick={sync.useAccount}>Использовать вариант из аккаунта</button>
            <button className="button" type="button" disabled={disabled} onClick={sync.keepMine}>Сохранить мой вариант в аккаунте</button>
          </div>
        </section>
      )}
      {sync.backup && (
        <details className="lesson-detail">
          <summary>Предыдущий вариант черновика на устройстве</summary>
          <p className="product-field-hint">Резервная копия сохранена до явной замены. Выход из аккаунта удаляет её с устройства.</p>
          <pre className="draft-sync-preview" tabIndex={0}>{text(sync.backup.content)}</pre>
          <button className="text-button" type="button" disabled={disabled} onClick={sync.restoreBackup}>Вернуть предыдущий вариант</button>
        </details>
      )}
    </div>
  );
}
