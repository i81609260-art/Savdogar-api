"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Shield, Mail, Lock, Eye, EyeOff, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { SAUser } from "@/lib/types";

export default function LoginPage() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post<{ user: SAUser; access_token: string }>(
        "/api/auth/login",
        { email, password }
      );
      if (data.user.role !== "superadmin") {
        setError("Bu panel faqat superadmin uchun. Sizda ruxsat yo'q.");
        return;
      }
      setAuth(data.user, data.access_token);
      router.push("/dashboard");
    } catch {
      setError("Email yoki parol noto'g'ri");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background:
          "radial-gradient(ellipse at top, rgba(139,92,246,0.12) 0%, transparent 60%), #0a0a1a",
      }}
    >
      <div style={{ width: "100%", maxWidth: "400px" }}>
        {/* Logo / Brand */}
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 64,
              height: 64,
              borderRadius: 18,
              background: "linear-gradient(135deg, #8b5cf6, #6d28d9)",
              marginBottom: 20,
              boxShadow: "0 8px 32px rgba(139,92,246,0.35)",
            }}
          >
            <Shield size={32} color="#fff" />
          </div>
          <h1
            style={{
              fontSize: 28,
              fontWeight: 800,
              fontFamily: "'Outfit', sans-serif",
              background: "linear-gradient(135deg, #c4b5fd, #8b5cf6)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              marginBottom: 8,
            }}
          >
            SAVDOGAR HQ
          </h1>
          <p style={{ color: "#64748b", fontSize: 14 }}>
            Superadmin boshqaruv tizimi
          </p>
        </div>

        {/* Card */}
        <div
          className="glass-card"
          style={{ padding: "32px" }}
        >
          <h2
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: "#f1f0ff",
              marginBottom: 4,
            }}
          >
            Kirish
          </h2>
          <p style={{ color: "#64748b", fontSize: 13, marginBottom: 28 }}>
            Tizimga kirish uchun ma'lumotlaringizni kiriting
          </p>

          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Email */}
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 600,
                  color: "#94a3b8",
                  marginBottom: 8,
                }}
              >
                Email
              </label>
              <div style={{ position: "relative" }}>
                <Mail
                  size={16}
                  color="#475569"
                  style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)" }}
                />
                <input
                  className="sa-input"
                  type="email"
                  placeholder="admin@savdogar.uz"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={{ paddingLeft: 42 }}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 600,
                  color: "#94a3b8",
                  marginBottom: 8,
                }}
              >
                Parol
              </label>
              <div style={{ position: "relative" }}>
                <Lock
                  size={16}
                  color="#475569"
                  style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)" }}
                />
                <input
                  className="sa-input"
                  type={showPass ? "text" : "password"}
                  placeholder="••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  style={{ paddingLeft: 42, paddingRight: 44 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  style={{
                    position: "absolute",
                    right: 14,
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#475569",
                    display: "flex",
                    padding: 0,
                  }}
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "10px 14px",
                  borderRadius: 10,
                  background: "rgba(239,68,68,0.12)",
                  border: "1px solid rgba(239,68,68,0.25)",
                  color: "#fca5a5",
                  fontSize: 13,
                }}
              >
                <AlertCircle size={15} />
                {error}
              </div>
            )}

            <button
              className="btn-primary"
              type="submit"
              disabled={loading}
              style={{ width: "100%", marginTop: 4 }}
            >
              {loading ? (
                <span style={{ opacity: 0.8 }}>Kirish...</span>
              ) : (
                <>
                  <Shield size={16} />
                  Tizimga kirish
                </>
              )}
            </button>
          </form>
        </div>

        <p
          style={{
            textAlign: "center",
            color: "#334155",
            fontSize: 12,
            marginTop: 24,
          }}
        >
          © 2025 Savdogar Platform · HQ Console v2.0
        </p>
      </div>
    </div>
  );
}
