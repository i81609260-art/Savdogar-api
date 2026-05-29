"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Search, Shield, User, Building2, Wrench, KeyRound, Eye, EyeOff, Power } from "lucide-react";
import api from "@/lib/api";
import type { SAUser } from "@/lib/types";

const ROLE_MAP = {
  superadmin: { label: "Superadmin", color: "#b91c1c", bg: "rgba(185,28,28,0.10)", icon: Shield },
  admin:      { label: "Admin",      color: "#3525cd", bg: "rgba(53,37,205,0.08)",   icon: Building2 },
  operator:   { label: "Operator",   color: "#047857", bg: "rgba(4,120,87,0.08)",    icon: Wrench },
  user:       { label: "User",       color: "#4b5563", bg: "rgba(75,85,99,0.08)",    icon: User },
};

const COMPANY_STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  pending:  { label: "Kutilmoqda",   color: "#3525cd", bg: "rgba(53,37,205,0.08)" },
  approved: { label: "Tasdiqlangan", color: "#005338", bg: "rgba(78,222,163,0.15)" },
  rejected: { label: "Rad etilgan",  color: "#ba1a1a", bg: "rgba(186,26,26,0.10)" },
};

function ResetPasswordModal({ user, onClose }: { user: SAUser; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      api.patch(`/api/superadmin/users/${user.id}/reset-password`, { new_password: password }),
    onSuccess: () => setDone(true),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white border border-slate-200 rounded-2xl p-6 w-full max-w-sm space-y-4 shadow-2xl">
        <div>
          <h2 className="text-lg font-bold text-[#0b1c30]">Parol o'zgartirish</h2>
          <p className="text-sm text-slate-500 mt-0.5">{user.full_name} — {user.email}</p>
        </div>

        {done ? (
          <div className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-center">
            <p className="text-emerald-700 font-bold text-sm">✅ Parol muvaffaqiyatli o'zgartirildi</p>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-500 block">Yangi parol</label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Kamida 8 ta belgi"
                  className="w-full h-10 px-3 border border-slate-200 rounded-lg text-sm input-glow pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {mutation.isError && (
              <p className="text-xs text-red-600 font-medium">Xatolik yuz berdi</p>
            )}
            <div className="flex gap-2">
              <button
                className="btn-gradient flex-1 py-2 rounded-lg text-sm font-bold cursor-pointer"
                onClick={() => mutation.mutate()}
                disabled={password.length < 8 || mutation.isPending}
              >
                {mutation.isPending ? "Saqlanmoqda..." : "Saqlash"}
              </button>
              <button className="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm cursor-pointer flex-1 text-center" onClick={onClose}>
                Bekor
              </button>
            </div>
          </>
        )}

        {done && (
          <button className="btn-gradient w-full py-2 rounded-lg text-sm font-bold cursor-pointer" onClick={onClose}>
            Yopish
          </button>
        )}
      </div>
    </div>
  );
}

export default function SuperAdminUsersPage() {
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [resetTarget, setResetTarget] = useState<SAUser | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["sa-users"],
    queryFn: async () => {
      const { data } = await api.get<SAUser[]>("/api/superadmin/users");
      return data;
    },
  });

  const toggleActive = useMutation({
    mutationFn: (userId: number) =>
      api.patch(`/api/superadmin/users/${userId}/toggle-active`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sa-users"] }),
  });

  const filtered = data?.filter((u) => {
    const matchRole = roleFilter === "all" || u.role === roleFilter;
    const matchSearch =
      !search ||
      u.full_name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.phone && u.phone.includes(search));
    return matchRole && matchSearch;
  }) ?? [];

  return (
    <div className="space-y-6 relative z-10">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-[#0b1c30] flex items-center gap-2" style={{ fontFamily: "'Outfit', sans-serif" }}>
          <Users className="h-6 w-6 text-[#3525cd]" />
          Foydalanuvchilar
          {data && <span className="text-sm font-normal text-slate-500">({data.length} ta)</span>}
        </h1>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            placeholder="Ism, email yoki telefon..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-10 pl-9 pr-3 border border-slate-200 rounded-xl text-sm bg-white/60 input-glow"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {["all", "superadmin", "admin", "operator", "user"].map((r) => (
            <button
              key={r}
              onClick={() => setRoleFilter(r)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors border ${
                roleFilter === r
                  ? "btn-gradient text-white border-transparent"
                  : "bg-white/60 text-[#464555] border-slate-200 hover:bg-white/90"
              }`}
            >
              {r === "all" ? "Barchasi" : ROLE_MAP[r as keyof typeof ROLE_MAP]?.label ?? r}
              {r !== "all" && data && (
                <span className="ml-1 opacity-60">
                  ({data.filter((u) => u.role === r).length})
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Skeleton Loading */}
      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-16 skeleton animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div className="glass p-12 rounded-2xl text-center text-slate-400 text-sm">Foydalanuvchi topilmadi</div>
      )}

      {/* Table view */}
      {filtered.length > 0 && (
        <div className="glass rounded-2xl overflow-hidden border border-slate-200/60 shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-slate-50/50 border-b border-slate-200">
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Foydalanuvchi</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Email</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Telefon</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Rol</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Kompaniya</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Holat</th>
                  <th className="p-4 text-left text-xs font-bold uppercase tracking-wider text-slate-400">Amallar</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((user) => {
                  const roleInfo = ROLE_MAP[user.role];
                  const RoleIcon = roleInfo.icon;
                  const companyStatus = user.company_status
                    ? COMPANY_STATUS_MAP[user.company_status]
                    : null;

                  return (
                    <tr key={user.id} className="hover:bg-white/40 transition-colors">
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <div className="h-8 w-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-[#3525cd] text-xs font-bold shrink-0">
                            {user.full_name[0]?.toUpperCase()}
                          </div>
                          <div>
                            <p className="font-semibold text-[#0b1c30]">{user.full_name}</p>
                            <p className="text-[10px] text-slate-400 font-mono">ID: {user.id}</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <span className="font-mono text-xs text-slate-600">
                          {user.email}
                        </span>
                      </td>
                      <td className="p-4 text-[#464555] font-mono text-xs">
                        {user.phone || <span className="text-slate-300">—</span>}
                      </td>
                      <td className="p-4">
                        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: roleInfo.bg, color: roleInfo.color }}>
                          <RoleIcon className="h-3 w-3" />
                          {roleInfo.label}
                        </span>
                      </td>
                      <td className="p-4">
                        {user.company_id ? (
                          <div className="space-y-1">
                            <p className="text-xs text-[#0b1c30] font-semibold">{user.company_name || `ID: ${user.company_id}`}</p>
                            {companyStatus && (
                              <span className="inline-flex text-[9px] font-bold px-1.5 py-0.5 rounded-full" style={{ background: companyStatus.bg, color: companyStatus.color }}>
                                {companyStatus.label}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex text-[11px] font-bold px-2 py-0.5 rounded-full ${user.is_active ? "chip-success" : "bg-slate-100 text-slate-400"}`}>
                          {user.is_active ? "Faol" : "Nofaol"}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setResetTarget(user)}
                            className="inline-flex items-center h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 cursor-pointer"
                            title="Parolni o'zgartirish"
                          >
                            <KeyRound className="h-3.5 w-3.5 mr-1 text-[#3525cd]" />
                            Parol
                          </button>
                          {user.role !== "superadmin" && (
                            <button
                              onClick={() => toggleActive.mutate(user.id)}
                              className={`inline-flex items-center h-8 px-2 rounded-lg border text-xs font-semibold cursor-pointer ${
                                user.is_active
                                  ? "border-red-200 bg-red-50 hover:bg-red-100 text-red-600"
                                  : "border-emerald-200 bg-emerald-50 hover:bg-emerald-100 text-emerald-600"
                              }`}
                              title={user.is_active ? "O'chirish" : "Faollashtirish"}
                            >
                              <Power className="h-3.5 w-3.5 mr-1" />
                              {user.is_active ? "O'chir" : "Yoq"}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {resetTarget && (
        <ResetPasswordModal user={resetTarget} onClose={() => setResetTarget(null)} />
      )}
    </div>
  );
}
