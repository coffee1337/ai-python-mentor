# Отдельный Python execution host

Worker находится в `apps/runner`. API никогда не запускает source ученика. Запросы используют mTLS TLS1.3, dedicated client CA и allowlist URI SAN workload identities; bearer token — дополнительная защита.

1. Подготовьте отдельный Linux host с Docker/cgroups v2, runsc, user namespaces, AppArmor profile `ai-tutor-runner` и reviewed seccomp. Worker/reaper имеют доступ к runtime socket только на этом host; API/web не получают socket и mounts host.
2. Создайте пользователя `tutor-runner`, отдельные `/etc/ai-tutor-runner` и `/var/lib/ai-tutor-runner`, установите Python package из `apps/runner`. Поставьте два systemd units из `deploy/`.
3. Соберите `Sandbox.Dockerfile`, проверьте базовый образ, зафиксируйте digest итогового image в `SANDBOX_IMAGE`. Приём задания не скачивает образы.
4. Экспортируйте доверенный каталог: `PYTHONPATH=apps/api python scripts/export-runner-catalog.py /private/catalog.json`. Файл содержит hidden expected values; не кладите его в web/public или guest. При обновлении сохраняйте версии, на которые ссылаются pending jobs/generated bindings.
5. Создайте deployment PKI, issued certificates с SAN URI для API/dispatcher, серверный сертификат с hostname/SAN endpoint и отдельный client CA. Настройте env по `deploy/environment.example`, доступ на чтение только service user. Секреты не входят в Git/image.
6. Выполните на целевом host обязательные abuse checks из `runner-security-review.md`: network denial, filesystem/mount/socket denial, secrets, fork/CPU/RAM/PID/disk/inode/time/output limits, child-tree kill, worker/reaper crash cleanup. Unit tests этого не проверяют.
7. После проверки создайте reviewed attestation JSON с `policy:"python-authored-v1"`, `isolation_verified:true`, `image` (тот же digest), `seccomp_sha256`, `catalog_sha256`, `expires_at` (Unix timestamp). Это подтверждение оператора, не автоматически сгенерированный сертификат безопасности. Worker дополнительно проверяет текущий runtime, образ и свежий heartbeat reaper.
8. Запустите reaper, затем worker. Настройте API HTTPS `RUNNER_URL`, auth token, CA/client certificate/key и client policy JSON `{"policy":"python-authored-v1","isolation_verified":true}` (точную схему см. `load_runner_settings`). Mount этих файлов — deployment secret storage. Включите durable dispatcher, затем `EXECUTION_JOBS_ENABLED=true`.

Fixed guest command принимает только source и один набор input args/kwargs. Expected values и вычисление pass counts остаются на trusted host. Каждый test получает новую среду; stdout/stderr cap общий для задания. Host journal сохраняет intent до запуска и не перезапускает неопределённый исход с тем же ключом после restart. Reaper убивает orphan контейнеры по deadline независимо от HTTP service.

Ресурсы: 1 CPU, 512 MiB RAM+swap cap, 32 PID, 64 FD, readonly/nonroot/no caps/network none, ограниченные tmpfs и inodes, 15 секунд на всё задание плюс cleanup. Неудача cleanup quarantines host; при истёкшем attestation/reaper heartbeat новые задания отклоняются.

Ротация: выдайте новые short-lived workload certs до expiry, обновите readonly secret mounts, перезапустите API dispatcher/worker. Проверьте, что старые revoked/expired certs и неизвестные SAN URI отклоняются. Выделенная CA позволяет менять bearer token без ослабления identity. Не включайте выполнение на host без проверки revoke/rotation.
