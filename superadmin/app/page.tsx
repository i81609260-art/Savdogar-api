"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";

export default function RootIndex() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (user && user.role === "superadmin") {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [user, router]);

  return (
    <div className="min-h-screen bg-[#0a0a1a] flex items-center justify-center text-slate-400 font-mono text-sm">
      Yuklanmoqda...
    </div>
  );
}
