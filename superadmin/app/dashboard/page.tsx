"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, Users, Map, Calendar, TrendingUp, Clock, DollarSign, ArrowUpRight } from "lucide-react";
import api from "@/lib/api";
import type { PlatformStats } from "@/lib/types";

const KPI_CONFIG = [
  { key: "total_companies",   label: "Kompaniyalar",    icon: Building2,   color: "#3525cd", bg: "rgba(53,37,205,0.08)"    },
  { key: "pending_companies", label: "Kutilayotgan",    icon: Clock,       color: "#fbbf24", bg: "rgba(251,191,36,0.08)"    },
  { key: "approved_companies",label: "Tasdiqlangan",    icon: TrendingUp,  color: "#10b981", bg: "rgba(16,185,129,0.08)"   },
  { key: "total_users",       label: "Foydalanuvchilar",icon: Users,       color: "#6366f1", bg: "rgba(99,102,241,0.08)"   },
  { key: "total_tours",       label: "Turlar",          icon: Map,         color: "#3b82f6", bg: "rgba(59,130,246,0.08)"   },
  { key: "total_bookings",    label: "Bronlar",         icon: Calendar,    color: "#8b5cf6", bg: "rgba(139,92,246,0.08)"   },
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
    <div className="space-y-6 relative z-10">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-[#0b1c30]" style={{ fontFamily: "'Outfit', sans-serif" }}>
          Superadmin Dashboard
        </h1>
        <p className="text-sm text-[#464555] mt-0.5">Platformadagi umumiy statistikalar</p>
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
              <div key={cfg.key} className="glass card-hover p-5 rounded-2xl relative overflow-hidden">
                <div className="flex justify-between items-start mb-3">
                  <div
                    className="h-9 w-9 rounded-xl flex items-center justify-center"
                    style={{ background: cfg.bg }}
                  >
                    <Icon className="h-4.5 w-4.5" style={{ color: cfg.color }} size={18} />
                  </div>
                  <span className="badge badge-success text-[11px]">
                    <ArrowUpRight className="h-3 w-3 mr-0.5" />
                    Faol
                  </span>
                </div>
                <p className="text-xs text-[#777587] font-semibold mb-1">{cfg.label}</p>
                <p className="text-2xl font-bold text-[#0b1c30]" style={{ fontFamily: "'Outfit', sans-serif" }}>
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
          className="rounded-2xl p-6 text-white relative overflow-hidden shadow-lg border border-purple-500/10 btn-gradient"
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
              <p className="text-sm opacity-90 font-medium">Umumiy daromad</p>
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
