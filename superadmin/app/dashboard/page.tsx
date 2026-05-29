"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, Users, Map, Calendar, TrendingUp, Clock, DollarSign, ArrowUpRight } from "lucide-react";
import api from "@/lib/api";
import type { PlatformStats } from "@/lib/types";

const KPI_CONFIG = [
  { key: "total_companies",   label: "Kompaniyalar",    icon: Building2,   color: "#a78bfa", bg: "rgba(167,139,250,0.08)"   },
  { key: "pending_companies", label: "Kutilayotgan",    icon: Clock,       color: "#fbbf24", bg: "rgba(251,191,36,0.08)"    },
  { key: "approved_companies",label: "Tasdiqlangan",    icon: TrendingUp,  color: "#34d399", bg: "rgba(52,211,153,0.08)"    },
  { key: "total_users",       label: "Foydalanuvchilar",icon: Users,       color: "#818cf8", bg: "rgba(129,140,248,0.08)"   },
  { key: "total_tours",       label: "Turlar",          icon: Map,         color: "#60a5fa", bg: "rgba(96,165,250,0.08)"    },
  { key: "total_bookings",    label: "Bronlar",         icon: Calendar,    color: "#c084fc", bg: "rgba(192,132,252,0.06)"   },
];

export default function SuperAdminDashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["sa-stats"],
    queryFn: async () => {
      const { data } = await api.get<PlatformStats>("/api/superadmin/stats");
      return data;
    },
  });

  const formatPrice = (val: number) => {
    return new Intl.NumberFormat("uz-UZ", { style: "currency", currency: "UZS", maximumFractionDigits: 0 }).format(val);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-100" style={{ fontFamily: "'Outfit', sans-serif" }}>
          Superadmin Dashboard
        </h1>
        <p className="text-sm text-slate-400 mt-0.5">Platformadagi umumiy statistikalar</p>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-28 skeleton" />
          ))}
        </div>
      )}

      {/* KPI Grid */}
      {data && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {KPI_CONFIG.map((cfg) => {
            const Icon = cfg.icon;
            const value = data[cfg.key as keyof PlatformStats];
            return (
              <div key={cfg.key} className="glass-card stat-card p-5 relative overflow-hidden">
                <div className="flex justify-between items-start mb-3">
                  <div
                    className="h-9 w-9 rounded-xl flex items-center justify-center"
                    style={{ background: cfg.bg }}
                  >
                    <Icon className="h-4.5 w-4.5" style={{ color: cfg.color }} size={18} />
                  </div>
                  <span className="badge badge-success">
                    <ArrowUpRight className="h-3 w-3" />
                    Faol
                  </span>
                </div>
                <p className="text-xs text-slate-400 mb-1">{cfg.label}</p>
                <p className="text-2xl font-bold text-slate-100" style={{ fontFamily: "'Outfit', sans-serif" }}>
                  {value}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* Revenue Card */}
      {data && (
        <div
          className="rounded-2xl p-6 text-white relative overflow-hidden shadow-lg border border-purple-500/20"
          style={{ background: "linear-gradient(135deg, #6d28d9 0%, #4f46e5 100%)" }}
        >
          <div
            className="absolute top-0 right-0 w-48 h-48 rounded-full opacity-10"
            style={{ background: "radial-gradient(circle, #fff 0%, transparent 70%)" }}
          />
          <div className="relative flex items-center gap-4">
            <div className="h-12 w-12 rounded-2xl flex items-center justify-center"
              style={{ background: "rgba(255,255,255,0.15)" }}>
              <DollarSign className="h-6 w-6 text-white" />
            </div>
            <div>
              <p className="text-sm opacity-75">Umumiy daromad</p>
              <p className="text-3xl font-bold" style={{ fontFamily: "'Outfit', sans-serif" }}>
                {formatPrice(data.total_revenue)}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
