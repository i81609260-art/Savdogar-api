"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard, Building2, Users, LogOut, Menu, X, Shield, Bell,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";

const links = [
  { href: "/dashboard",           label: "Dashboard",          icon: LayoutDashboard },
  { href: "/dashboard/companies", label: "Kompaniyalar",        icon: Building2 },
  { href: "/dashboard/users",     label: "Foydalanuvchilar",    icon: Users },
];

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!user || user.role !== "superadmin") {
      router.push("/login");
    }
  }, [user, router]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!user || user.role !== "superadmin") {
    return (
      <div className="min-h-screen bg-[#0a0a1a] flex items-center justify-center text-slate-400">
        Yuklanmoqda...
      </div>
    );
  }

  const initials = user.full_name
    ?.split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) ?? "SA";

  return (
    <div className="min-h-screen bg-[#03001e] text-slate-100 relative flex overflow-hidden font-sans select-none">
      {/* Background gradients */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_var(--tw-gradient-stops))] from-indigo-950/30 via-slate-950 to-slate-950 pointer-events-none z-0" />
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-900/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-900/10 rounded-full blur-[100px] pointer-events-none" />

      {/* Sidebar Backdrop (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Left Sidebar */}
      <aside
        className={`fixed left-0 top-0 z-50 h-full w-64 flex flex-col transition-transform duration-300 border-r md:static md:translate-x-0 bg-slate-950/80 border-indigo-950/80 backdrop-blur-xl ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        {/* Logo */}
        <div className="flex h-16 items-center justify-between px-5 border-b border-indigo-950/50">
          <Link href="/dashboard" className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-purple-400" />
            <span
              className="font-bold text-base bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent"
              style={{ fontFamily: "'Outfit', sans-serif" }}
            >
              SAVDOGAR HQ
            </span>
          </Link>
          <button
            className="md:hidden p-1.5 rounded-lg hover:bg-slate-900 text-slate-400 transition-colors"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Sidebar Nav */}
        <div className="px-5 pt-5 pb-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-purple-400/80 bg-purple-500/10 px-2 py-0.5 rounded-full">
            SYSTEM CONTROL
          </span>
        </div>

        <nav className="flex flex-col gap-1 px-3 flex-1 overflow-y-auto mt-2">
          {links.map((link) => {
            const Icon = link.icon;
            const active = pathname === link.href || (link.href !== "/dashboard" && pathname.startsWith(link.href));
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setSidebarOpen(false)}
                className={`nav-link ${active ? "active" : ""}`}
              >
                <Icon className={`h-4.5 w-4.5 shrink-0 ${active ? "text-purple-400" : "text-slate-500"}`} size={18} />
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Console status */}
        <div className="p-4 border-t border-indigo-950/50">
          <div className="bg-slate-900/40 border border-indigo-950/80 rounded-xl p-3 text-center">
            <p className="text-[10px] font-semibold text-purple-400">SAVDOGAR CONSOLE</p>
            <p className="text-[10px] text-slate-500 mt-0.5 font-mono">SECURE LEVEL 3</p>
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0 z-10">
        {/* Header */}
        <header className="sticky top-0 z-30 h-16 bg-slate-950/40 border-b border-indigo-950/50 backdrop-blur-md flex items-center justify-between px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-2 rounded-xl hover:bg-slate-900 text-slate-400 transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div className="hidden md:flex items-center gap-2">
            <span className="text-xs text-slate-500 font-mono">NODE_ENV: production</span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>

          <div className="flex items-center gap-4">
            {/* User */}
            <div className="flex items-center gap-3 pl-3 border-l border-indigo-950/50">
              <div className="hidden sm:block text-right">
                <p className="text-sm font-semibold text-slate-200 leading-none">{user.full_name}</p>
                <p className="text-xs text-purple-400/80 font-mono mt-1 capitalize">{user.role}</p>
              </div>
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-md">
                {initials}
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-xl hover:bg-red-500/10 text-slate-400 hover:text-red-400 transition-colors"
                title="Tizimdan chiqish"
              >
                <LogOut className="h-4.5 w-4.5" size={18} />
              </button>
            </div>
          </div>
        </header>

        {/* Content Panel */}
        <main className="flex-1 p-6 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
