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
      <div className="min-h-screen bg-[#f8f9ff] flex items-center justify-center text-slate-500 font-mono text-sm">
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
    <div className="min-h-screen bg-[#f8f9ff] text-[#0b1c30] relative flex overflow-hidden font-sans select-none">
      {/* Background gradients */}
      <div className="absolute inset-0 bg-gradient-to-tr from-[#f8f9ff] via-[#eff4ff] to-[#f8f9ff] pointer-events-none z-0" />
      <div className="absolute top-0 right-0 w-96 h-96 bg-purple-200/40 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-indigo-200/30 rounded-full blur-[100px] pointer-events-none" />

      {/* Sidebar Backdrop (mobile) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Left Sidebar */}
      <aside
        className={`fixed left-0 top-0 z-50 h-full w-64 flex flex-col transition-transform duration-300 border-r md:static md:translate-x-0 glass-sidebar ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        {/* Logo */}
        <div className="flex h-16 items-center justify-between px-5 border-b border-white/30">
          <Link href="/dashboard" className="flex items-center gap-2">
            <Shield className="h-6 w-6 text-[#3525cd]" />
            <span
              className="font-bold text-sm text-gradient"
              style={{ fontFamily: "'Outfit', sans-serif" }}
            >
              Savdogar HQ
            </span>
          </Link>
          <button
            className="md:hidden p-1.5 rounded-lg hover:bg-white/50 text-[#464555] transition-colors"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Sidebar Nav */}
        <div className="px-5 pt-5 pb-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-[#777587] px-2 py-0.5 rounded-full bg-white/40">
            SYSTEM CONTROL
          </span>
        </div>

        <nav className="flex flex-col gap-1 px-3 flex-1 overflow-y-auto mt-2 custom-scroll">
          {links.map((link) => {
            const Icon = link.icon;
            const active = pathname === link.href || (link.href !== "/dashboard" && pathname.startsWith(link.href));
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-200 ${
                  active
                    ? "sidebar-active"
                    : "text-[#464555] hover:bg-white/60 hover:text-[#0b1c30]"
                }`}
              >
                <Icon className={`h-4.5 w-4.5 shrink-0 ${active ? "text-[#3525cd]" : "text-slate-400"}`} size={18} />
                <span>{link.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Console status */}
        <div className="p-4 border-t border-white/30">
          <div className="bg-white/40 border border-white/60 rounded-xl p-3 text-center">
            <p className="text-[10px] font-semibold text-[#3525cd]">SAVDOGAR CONSOLE</p>
            <p className="text-[10px] text-slate-500 mt-0.5 font-mono">SECURE LEVEL 3</p>
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col min-w-0 z-10">
        {/* Header */}
        <header className="sticky top-0 z-30 h-16 glass-nav flex items-center justify-between px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden p-2 rounded-xl hover:bg-white/50 text-[#464555] transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div className="hidden md:flex items-center gap-2">
            <span className="text-xs text-slate-400 font-mono">NODE_ENV: production</span>
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </div>

          <div className="flex items-center gap-4">
            {/* User */}
            <div className="flex items-center gap-3 pl-3 border-l border-white/30">
              <div className="hidden sm:block text-right">
                <p className="text-sm font-semibold text-[#0b1c30] leading-none">{user.full_name}</p>
                <p className="text-xs text-[#777587] font-mono mt-1 capitalize">{user.role}</p>
              </div>
              <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-[#3525cd] to-[#6b38d4] flex items-center justify-center text-white text-xs font-bold shadow-md">
                {initials}
              </div>
              <button
                onClick={handleLogout}
                className="p-2 rounded-xl hover:bg-red-500/10 text-slate-400 hover:text-red-500 transition-colors"
                title="Tizimdan chiqish"
              >
                <LogOut className="h-4.5 w-4.5 text-[#464555] hover:text-red-500" size={18} />
              </button>
            </div>
          </div>
        </header>

        {/* Content Panel */}
        <main className="flex-1 p-6 overflow-y-auto custom-scroll">
          {children}
        </main>
      </div>
    </div>
  );
}
