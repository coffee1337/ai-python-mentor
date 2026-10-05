"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage, isUnauthorized, User } from "./api";

export function useUser(requireOnboarding = false) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api<User>("/me");
      if (requireOnboarding && !result.profile?.onboarding_completed) {
        router.replace("/onboarding");
        return;
      }
      setUser(result);
    } catch (reason) {
      if (isUnauthorized(reason)) router.replace("/auth");
      else setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [requireOnboarding, router]);
  useEffect(() => { void reload(); }, [reload]);
  return { user, setUser, loading, error, reload };
}
