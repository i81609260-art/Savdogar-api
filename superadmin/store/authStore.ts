"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { SAUser, AuthState } from "@/lib/types";

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      setAuth: (user: SAUser, token: string) => {
        if (typeof window !== "undefined") {
          localStorage.setItem("sa_access_token", token);
        }
        set({ user, accessToken: token });
      },
      logout: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("sa_access_token");
          localStorage.removeItem("sa_user");
        }
        set({ user: null, accessToken: null });
      },
    }),
    {
      name: "sa-auth-storage",
      partialize: (state) => ({ user: state.user, accessToken: state.accessToken }),
    }
  )
);
