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
          localStorage.setItem("access_token", token);
          localStorage.setItem("user", JSON.stringify(user));
        }
        set({ user, accessToken: token });
      },
      logout: () => {
        if (typeof window !== "undefined") {
          localStorage.removeItem("access_token");
          localStorage.removeItem("user");
          localStorage.removeItem("refresh_token");
        }
        set({ user: null, accessToken: null });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({ user: state.user, accessToken: state.accessToken }),
    }
  )
);
