"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isUnauthorized, User } from "./api";

export function useUser(requireOnboarding = false) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const expectedOwner = useRef<string | null>(null);

  const invalidate = useCallback(() => {
    generation.current += 1;
    controller.current?.abort();
    setUser(null);
    setLoading(false);
    setError("Аккаунт изменился. Откройте страницу заново перед продолжением.");
    router.replace("/auth");
  }, [router]);

  const reload = useCallback(async () => {
    const request = ++generation.current;
    controller.current?.abort();
    const nextController = new AbortController();
    controller.current = nextController;
    setUser(null);
    setLoading(true);
    setError("");
    try {
      const result = await api<User>("/me", { signal: nextController.signal, cache: "no-store" });
      if (nextController.signal.aborted || generation.current !== request) return;
      if (expectedOwner.current && expectedOwner.current !== result.id) {
        invalidate();
        return;
      }
      expectedOwner.current = result.id;
      if (requireOnboarding && !result.profile?.onboarding_completed) {
        router.replace("/onboarding");
        return;
      }
      setUser(result);
    } catch (reason) {
      if (nextController.signal.aborted || generation.current !== request) return;
      if (isUnauthorized(reason)) router.replace("/auth");
      else setError(errorMessage(reason));
    } finally {
      if (!nextController.signal.aborted && generation.current === request) setLoading(false);
    }
  }, [requireOnboarding, router, invalidate]);

  useEffect(() => {
    void reload();
    window.addEventListener("mentor:auth-changed", invalidate);
    window.addEventListener("mentor:workspace-account-invalid", invalidate);
    return () => {
      generation.current += 1;
      controller.current?.abort();
      window.removeEventListener("mentor:auth-changed", invalidate);
      window.removeEventListener("mentor:workspace-account-invalid", invalidate);
    };
  }, [reload, invalidate]);
  return { user, setUser, loading, error, reload };
}
