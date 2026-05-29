"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, MapPin, Clock, CheckCircle2, XCircle, ChevronDown, ChevronUp, Users, Map, Mail, Phone, Globe, ShieldAlert } from "lucide-react";
import api from "@/lib/api";
import type { Company } from "@/lib/types";

const STATUS_MAP = {
  pending:  { label: "Kutilmoqda",    color: "#3525cd", bg: "rgba(53,37,205,0.08)",   icon: Clock,       chip: "chip-pending" },
  approved: { label: "Tasdiqlangan",  color: "#005338", bg: "rgba(78,222,163,0.15)",   icon: CheckCircle2, chip: "chip-success" },
  rejected: { label: "Rad etilgan",   color: "#ba1a1a", bg: "rgba(186,26,26,0.10)",    icon: XCircle,      chip: "chip-error" },
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
    <div className="space-y-6 relative z-10">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-[#0b1c30] flex items-center gap-2" style={{ fontFamily: "'Outfit',sans-serif" }}>
            <Building2 className="h-6 w-6 text-[#3525cd]" />
            Kompaniyalar
          </h1>
          <p className="text-sm text-[#464555] mt-0.5">{data?.length ?? 0} ta kompaniya</p>
        </div>
        {/* Filter pills */}
        <div className="flex gap-2 flex-wrap">
          {FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all border ${
                filter === s
                  ? "btn-gradient text-white border-transparent"
                  : "bg-white/60 text-[#464555] border-slate-200 hover:bg-white/90"
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
        <div className="glass p-12 rounded-2xl text-center text-sm text-slate-500">Kompaniya topilmadi</div>
      )}

      <div className="space-y-3">
        {filtered.map((company) => {
          const st = STATUS_MAP[company.status];
          const Icon = st.icon;
          const isOpen = expanded === company.id;

          return (
            <div key={company.id} className="glass rounded-2xl card-hover overflow-hidden">
              {/* Header row */}
              <div
                className="flex items-center justify-between gap-4 p-4 cursor-pointer transition-all"
                style={{ background: isOpen ? "rgba(53,37,205,0.03)" : undefined }}
                onClick={() => setExpanded(isOpen ? null : company.id)}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {company.logo_url ? (
                    <img src={company.logo_url} alt={company.name} className="h-10 w-10 rounded-xl object-cover shrink-0 border border-slate-200 shadow-sm" />
                  ) : (
                    <div
                      className="h-10 w-10 rounded-xl flex items-center justify-center text-white font-bold shrink-0 text-sm"
                      style={{ background: "linear-gradient(135deg,#3525cd,#6b38d4)" }}
                    >
                      {company.name[0].toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="font-semibold text-[#0b1c30] truncate" style={{ fontFamily: "'Outfit',sans-serif" }}>
                      {company.name}
                    </p>
                    <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                      <MapPin className="h-3.5 w-3.5 text-slate-400" />{company.city}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                  <div className="hidden sm:flex items-center gap-3 text-xs text-slate-500">
                    <span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" />{company.users_count} xodim</span>
                    <span className="flex items-center gap-1"><Map className="h-3.5 w-3.5" />{company.tours_count} tur paket</span>
                  </div>
                  <span className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${st.chip}`}>
                    <Icon className="h-3 w-3" />{st.label}
                  </span>
                  {isOpen ? <ChevronUp className="h-4 w-4 text-slate-500" /> : <ChevronDown className="h-4 w-4 text-slate-500" />}
                </div>
              </div>

              {/* Expanded details */}
              {isOpen && (
                <div className="border-t border-slate-200/60 px-5 pb-5 pt-4 space-y-4 bg-white/30">
                  {/* Stats on mobile */}
                  <div className="sm:hidden grid grid-cols-2 gap-2 text-xs text-slate-500">
                    <span className="flex items-center gap-1 bg-white/50 p-2 rounded-lg"><Users className="h-3.5 w-3.5 text-[#3525cd]" />{company.users_count} xodim</span>
                    <span className="flex items-center gap-1 bg-white/50 p-2 rounded-lg"><Map className="h-3.5 w-3.5 text-[#3525cd]" />{company.tours_count} tur</span>
                  </div>

                  {/* Core details */}
                  <div className="grid md:grid-cols-2 gap-6">
                    <div className="space-y-2.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Aloqa ma'lumotlari</h4>
                      <div className="space-y-2 text-sm text-[#464555]">
                        <div className="flex items-center gap-2"><Phone className="h-4 w-4 text-slate-400" /><span>{company.phone}</span></div>
                        <div className="flex items-center gap-2"><Mail className="h-4 w-4 text-slate-400" /><span>{company.email}</span></div>
                        {company.description && (
                          <p className="text-xs text-[#777587] mt-2 bg-white/50 p-2.5 rounded-lg border border-slate-100">{company.description}</p>
                        )}
                      </div>
                    </div>

                    <div className="space-y-2.5">
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Tizim ma'lumotlari</h4>
                      <div className="space-y-2 text-sm text-slate-500">
                        <div>Ro'yxatdan o'tgan sana: <span className="font-mono text-[#0b1c30]">{new Date(company.created_at).toLocaleDateString("uz-UZ")}</span></div>
                        {company.rejection_reason && (
                          <div className="bg-red-50 border border-red-200 text-red-700 p-2.5 rounded-lg text-xs flex gap-2">
                            <ShieldAlert className="h-4 w-4 shrink-0" />
                            <div>
                              <p className="font-bold">Rad etish sababi:</p>
                              <p className="mt-0.5">{company.rejection_reason}</p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Reject reason input */}
                  {rejectingId === company.id && (
                    <div className="bg-white/60 p-3.5 rounded-xl border border-slate-200 space-y-2.5">
                      <label className="text-xs font-semibold text-[#0b1c30] block">Rad etish sababini kiriting:</label>
                      <input
                        className="w-full h-10 px-3 border border-slate-200 rounded-lg text-sm input-glow"
                        placeholder="Masalan: noto'g'ri hujjatlar yoki telefon raqam"
                        value={rejectReason}
                        onChange={(e) => setRejectReason(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <button
                          className="px-3 py-1.5 text-xs font-bold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors cursor-pointer"
                          onClick={() => rejectMutation.mutate({ id: company.id, reason: rejectReason })}
                          disabled={!rejectReason || rejectMutation.isPending}
                        >
                          Rad etishni tasdiqlash
                        </button>
                        <button
                          className="px-3 py-1.5 text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors cursor-pointer"
                          onClick={() => { setRejectingId(null); setRejectReason(""); }}
                        >
                          Bekor qilish
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  {company.status === "pending" && rejectingId !== company.id && (
                    <div className="flex gap-2 border-t border-slate-200/60 pt-3">
                      <button
                        className="px-4 py-1.5 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition-all cursor-pointer"
                        onClick={() => approveMutation.mutate(company.id)}
                        disabled={approveMutation.isPending}
                      >
                        Tasdiqlash
                      </button>
                      <button
                        className="px-4 py-1.5 text-xs font-bold bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 rounded-lg transition-all cursor-pointer"
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
