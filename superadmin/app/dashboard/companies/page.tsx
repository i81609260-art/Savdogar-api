"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, MapPin, Clock, CheckCircle2, XCircle, ChevronDown, ChevronUp, Users, Map, Mail, Phone, Globe, ShieldAlert } from "lucide-react";
import api from "@/lib/api";
import type { Company } from "@/lib/types";

const STATUS_MAP = {
  pending:  { label: "Kutilmoqda",    color: "#fbbf24", bg: "rgba(251,191,36,0.12)",  icon: Clock },
  approved: { label: "Tasdiqlangan",  color: "#34d399", bg: "rgba(52,211,153,0.12)",  icon: CheckCircle2 },
  rejected: { label: "Rad etilgan",   color: "#f87171", bg: "rgba(248,113,113,0.10)",   icon: XCircle },
};

const FILTERS = ["all", "pending", "approved", "rejected"] as const;

export default function CompaniesPage() {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [filter, setFilter] = useState<typeof FILTERS[number]>("all");

  const { data, isLoading } = useQuery({
    queryKey: ["sa-companies"],
    queryFn: async () => {
      const { data } = await api.get<Company[]>("/api/superadmin/companies");
      return data;
    },
  });

  const approveMutation = useMutation({
    mutationFn: (id: number) => api.post(`/api/superadmin/companies/${id}/approve`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sa-companies"] }),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      api.post(`/api/superadmin/companies/${id}/reject`, { reason }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sa-companies"] });
      setRejectingId(null); setRejectReason("");
    },
  });

  const filtered = data?.filter((c) => filter === "all" || c.status === filter) ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2" style={{ fontFamily: "'Outfit',sans-serif" }}>
            <Building2 className="h-6 w-6 text-purple-400" />
            Kompaniyalar
          </h1>
          <p className="text-sm text-slate-400 mt-0.5">{data?.length ?? 0} ta kompaniya</p>
        </div>
        {/* Filter pills */}
        <div className="flex gap-2 flex-wrap">
          {FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all border ${
                filter === s
                  ? "bg-gradient-to-r from-purple-500 to-indigo-500 text-white border-transparent"
                  : "bg-slate-900/60 text-slate-400 border-indigo-950/40 hover:bg-slate-900/80"
              }`}
            >
              {s === "all" ? "Barchasi" : STATUS_MAP[s as keyof typeof STATUS_MAP].label}
              {s !== "all" && data && (
                <span className="ml-1 opacity-70">({data.filter((c) => c.status === s).length})</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Skeleton Loading */}
      {isLoading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-20 skeleton animate-pulse" />)}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div className="glass-card p-12 text-center text-sm text-slate-500">Kompaniya topilmadi</div>
      )}

      <div className="space-y-3">
        {filtered.map((company) => {
          const st = STATUS_MAP[company.status];
          const Icon = st.icon;
          const isOpen = expanded === company.id;

          return (
            <div key={company.id} className="glass-card overflow-hidden">
              {/* Header row */}
              <div
                className="flex items-center justify-between gap-4 p-4 cursor-pointer transition-all"
                style={{ background: isOpen ? "rgba(255,255,255,0.02)" : undefined }}
                onClick={() => setExpanded(isOpen ? null : company.id)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {company.logo_url ? (
                    <img src={company.logo_url} alt={company.name} className="h-10 w-10 rounded-xl object-cover shrink-0 border border-indigo-950/50 shadow-sm" />
                  ) : (
                    <div
                      className="h-10 w-10 rounded-xl flex items-center justify-center text-white font-bold shrink-0 text-sm"
                      style={{ background: "linear-gradient(135deg,#8b5cf6,#6d28d9)" }}
                    >
                      {company.name[0].toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-100 truncate" style={{ fontFamily: "'Outfit',sans-serif" }}>
                      {company.name}
                    </p>
                    <p className="text-xs text-slate-400 flex items-center gap-1">
                      <MapPin className="h-3 w-3 text-slate-500" />{company.city}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="hidden sm:flex items-center gap-3 text-xs text-slate-400">
                    <span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" />{company.users_count} xodim</span>
                    <span className="flex items-center gap-1"><Map className="h-3.5 w-3.5" />{company.tours_count} tur paket</span>
                  </div>
                  <span className="flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-full"
                    style={{ background: st.bg, color: st.color }}>
                    <Icon className="h-3 w-3" />{st.label}
                  </span>
                  {isOpen ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                </div>
              </div>

              {/* Expanded details */}
              {isOpen && (
                <div className="border-t border-indigo-950/40 px-4 pb-4 pt-3 space-y-4 bg-slate-950/30">
                  {/* Stats on mobile */}
                  <div className="sm:hidden grid grid-cols-2 gap-2 text-xs text-slate-400">
                    <span className="flex items-center gap-1 bg-slate-900/60 p-2 rounded-lg"><Users className="h-3.5 w-3.5 text-purple-400" />{company.users_count} xodim</span>
                    <span className="flex items-center gap-1 bg-slate-900/60 p-2 rounded-lg"><Map className="h-3.5 w-3.5 text-purple-400" />{company.tours_count} tur</span>
                  </div>

                  {/* Core details */}
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Aloqa ma'lumotlari</h4>
                      <div className="space-y-1.5 text-sm text-slate-300">
                        <div className="flex items-center gap-2"><Phone className="h-4 w-4 text-slate-500" /><span>{company.phone}</span></div>
                        <div className="flex items-center gap-2"><Mail className="h-4 w-4 text-slate-500" /><span>{company.email}</span></div>
                        {company.description && (
                          <p className="text-xs text-slate-400 mt-2 bg-slate-900/40 p-2.5 rounded-lg border border-indigo-950/40">{company.description}</p>
                        )}
                      </div>
                    </div>

                    <div className="space-y-2.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Tizim ma'lumotlari</h4>
                      <div className="space-y-1.5 text-sm text-slate-400">
                        <div>Ro'yxatdan o'tgan sana: <span className="font-mono text-slate-300">{new Date(company.created_at).toLocaleDateString("uz-UZ")}</span></div>
                        {company.rejection_reason && (
                          <div className="bg-red-950/20 border border-red-900/40 text-red-300 p-2.5 rounded-lg text-xs flex gap-2">
                            <ShieldAlert className="h-4 w-4 shrink-0" />
                            <div>
                              <p className="font-semibold">Rad etish sababi:</p>
                              <p className="mt-0.5">{company.rejection_reason}</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Reject reason input */}
                  {rejectingId === company.id && (
                    <div className="bg-slate-900/60 p-3.5 rounded-xl border border-indigo-950/40 space-y-2.5">
                      <label className="text-xs font-semibold text-slate-300 block">Rad etish sababini kiriting:</label>
                      <input
                        className="sa-input"
                        placeholder="Masalan: noto'g'ri hujjatlar yoki telefon raqam"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          className="px-3 py-1.5 text-xs font-semibold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                          onClick={() => rejectMutation.mutate({ id: company.id, reason: rejectReason })}
                          disabled={!rejectReason || rejectMutation.isPending}
                        >
                          Rad etishni tasdiqlash
                        </button>
                        <button
                          className="btn-ghost"
                          onClick={() => { setRejectingId(null); setRejectReason(""); }}
                        >
                          Bekor qilish
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  {company.status === "pending" && rejectingId !== company.id && (
                    <div className="flex gap-2 border-t border-indigo-950/40 pt-3">
                      <button
                        className="px-4 py-1.5 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl transition-all"
                        onClick={() => approveMutation.mutate(company.id)}
                        disabled={approveMutation.isPending}
                      >
                        Tasdiqlash
                      </button>
                      <button
                        className="px-4 py-1.5 text-xs font-bold bg-red-950/40 hover:bg-red-950/70 text-red-400 border border-red-900/30 rounded-xl transition-all"
                        onClick={() => setRejectingId(company.id)}
                      >
                        Rad etish
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
