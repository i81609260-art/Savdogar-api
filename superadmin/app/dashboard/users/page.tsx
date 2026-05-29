"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Search, Shield, User, Building2, Wrench, KeyRound, Eye, EyeOff, Power } from "lucide-react";
import api from "@/lib/api";
import type { SAUser } from "@/lib/types";

const ROLE_MAP = {
  superadmin: { label: "Superadmin", color: "#f87171", bg: "rgba(248,113,113,0.12)", icon: Shield },
  admin:      { label: "Admin",      color: "#818cf8", bg: "rgba(129,140,248,0.12)", icon: Building2 },
  operator:   { label: "Operator",   color: "#34d399", bg: "rgba(52,211,153,0.12)", icon: Wrench },
  user:       { label: "User",       color: "#94a3b8", bg: "rgba(255,255,255,0.06)", icon: User },
};

const COMPANY_STATUS_MAP: Record<string, { label: string; color: string; bg: string }> = {
  pending:  { label: "Kutilmoqda",   color: "#fbbf24", bg: "rgba(251,191,36,0.12)" },
  approved: { label: "Tasdiqlangan", color: "#34d399", bg: "rgba(52,211,153,0.12)" },
  rejected: { label: "Rad etilgan",  color: "#f87171", bg: "rgba(248,113,113,0.10)" },
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-900 border border-indigo-950/80 rounded-2xl p-6 w-full max-w-sm space-y-4 shadow-2xl">
        <div>
          <h2 className="text-lg font-bold text-slate-100">Parol o'zgartirish</h2>
          <p className="text-sm text-slate-400 mt-0.5">{user.full_name} — {user.email}</p>
        </div>

        {done ? (
          <div className="rounded-xl bg-emerald-950/20 border border-emerald-900/40 p-4 text-center">
            <p className="text-emerald-400 font-medium text-sm">✅ Parol muvaffaqiyatli o'zgartirildi</p>
          </div>
        ) : (
          <>
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 block">Yangi parol</label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Kamida 8 ta belgi"
                  className="sa-input pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShow(!show)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {mutation.isError && (
              <p className="text-xs text-red-400">Xatolik yuz berdi</p>
            )}
            <div className="flex gap-2">
              <button
                className="btn-primary flex-1"
                onClick={() => mutation.mutate()}
                disabled={password.length < 8 || mutation.isPending}
              >
                {mutation.isPending ? "Saqlanmoqda..." : "Saqlash"}
              </button>
              <button className="btn-ghost flex-1 justify-center" onClick={onClose}>
                Bekor
              </button>
            </div>
          </>
        )}

        {done && (
          <button className="btn-primary w-full" onClick={onClose}>
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2" style={{ fontFamily: "'Outfit', sans-serif" }}>
          <Users className="h-6 w-6 text-purple-400" />
          Foydalanuvchilar
          {data && <span className="text-sm font-normal text-slate-400">({data.length} ta)</span>}
        </h1>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            placeholder="Ism, email yoki telefon..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="sa-input pl-9"
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          {["all", "superadmin", "admin", "operator", "user"].map((r) => (
            <button
              key={r}
              onClick={() => setRoleFilter(r)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors border ${
                roleFilter === r
                  ? "bg-gradient-to-r from-purple-500 to-indigo-500 text-white border-transparent"
                  : "bg-slate-900/60 text-slate-400 border-indigo-950/40 hover:bg-slate-900/80"
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
        <div className="glass-card p-12 text-center text-slate-500 text-sm">Foydalanuvchi topilmadi</div>
      )}

      {/* Table view */}
      {filtered.length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="sa-table">
              <thead>
                <tr>
                  <th>Foydalanuvchi</th>
                  <th>Email</th>
                  <th>Telefon</th>
                  <th>Rol</th>
                  <th>Kompaniya</th>
                  <th>Holat</th>
                  <th>Amallar</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user) => {
                  const roleInfo = ROLE_MAP[user.role];
                  const RoleIcon = roleInfo.icon;
                  const companyStatus = user.company_status
                    ? COMPANY_STATUS_MAP[user.company_status]
                    : null;

                  return (
                    <tr key={user.id}>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="h-8 w-8 rounded-lg bg-indigo-950 flex items-center justify-center text-purple-300 text-xs font-bold shrink-0 border border-indigo-900/35">
                            {user.full_name[0]?.toUpperCase()}
                          </div>
                          <div>
                            <p className="font-semibold text-slate-200">{user.full_name}</p>
                            <p className="text-[10px] text-slate-500 font-mono">ID: {user.id}</p>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="font-mono text-xs text-slate-300">
                          {user.email}
                        </span>
                      </td>
                      <td className="text-slate-300 font-mono">
                        {user.phone || <span className="text-slate-600">—</span>}
                      </td>
                      <td>
                        <span className="badge" style={{ background: roleInfo.bg, color: roleInfo.color }}>
                          <RoleIcon className="h-3.5 w-3.5 mr-1" />
                          {roleInfo.label}
                        </span>
                      </td>
                      <td>
                        {user.company_id ? (
                          <div className="space-y-1">
                            <p className="text-xs text-slate-300 font-semibold">{user.company_name || `ID: ${user.company_id}`}</p>
                            {companyStatus && (
                              <span className="badge text-[10px]" style={{ background: companyStatus.bg, color: companyStatus.color }}>
                                {companyStatus.label}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-600">—</span>
                        )}
                      </td>
                      <td>
                        <span className={`badge ${user.is_active ? "badge-success" : "badge-muted"}`}>
                          {user.is_active ? "Faol" : "Nofaol"}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setResetTarget(user)}
                            className="btn-ghost px-2 h-8 hover:border-purple-500/50 hover:text-purple-300"
                            title="Parolni o'zgartirish"
                          >
                            <KeyRound className="h-3.5 w-3.5 mr-1" />
                            Parol
                          </button>
                          {user.role !== "superadmin" && (
                            <button
                              onClick={() => toggleActive.mutate(user.id)}
                              className={`btn-ghost px-2 h-8 ${
                                user.is_active
                                  ? "hover:border-red-500/50 hover:text-red-400"
                                  : "hover:border-emerald-500/50 hover:text-emerald-400"
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
