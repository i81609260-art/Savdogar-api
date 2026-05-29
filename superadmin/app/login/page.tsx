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
          "radial-gradient(circle at top right, #e2dfff55, transparent 60%), radial-gradient(circle at bottom left, #eff4ff, transparent 70%), #f8f9ff",
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
              width: 60,
              height: 60,
              borderRadius: 18,
              background: "linear-gradient(135deg, #3525cd, #6b38d4)",
              marginBottom: 16,
              boxShadow: "0 8px 24px rgba(53,37,205,0.25)",
            }}
          >
            <Shield size={28} color="#fff" />
          </div>
          <h1
            style={{
              fontSize: 26,
              fontWeight: 800,
              fontFamily: "'Outfit', sans-serif",
              background: "linear-gradient(135deg, #3525cd 0%, #6b38d4 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              marginBottom: 6,
            }}
          >
            Savdogar HQ
          </h1>
          <p style={{ color: "#464555", fontSize: 13, fontWeight: 500 }}>
            Superadmin boshqaruv tizimi
          </p>
        </div>

        {/* Card */}
        <div
          className="glass"
          style={{ padding: "32px", borderRadius: 24, boxShadow: "0 10px 30px rgba(53, 37, 205, 0.05)" }}
        >
          <h2
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: "#0b1c30",
              marginBottom: 4,
            }}
          >
            Kirish
          </h2>
          <p style={{ color: "#777587", fontSize: 12, marginBottom: 28 }}>
            Tizimga kirish uchun ma'lumotlaringizni kiriting
          </p>

          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Email */}
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: 12,
                  fontWeight: 700,
                  color: "#464555",
                  marginBottom: 8,
                }}
              >
                Email
              </label>
              <div style={{ position: "relative" }}>
                <Mail
                  size={16}
                  color="#94a3b8"
                  style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)" }}
                />
                <input
                  className="input-glow"
                  type="email"
                  placeholder="admin@savdogar.uz"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    height: "44px",
                    paddingLeft: 42,
                    paddingRight: 14,
                    borderRadius: 12,
                    border: "1px solid #cbd5e1",
                    background: "rgba(255,255,255,0.7)",
                    fontSize: 14,
                    color: "#0b1c30",
                  }}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label
                style={{
                  display: "block",
                  fontSize: 12,
                  fontWeight: 700,
                  color: "#464555",
                  marginBottom: 8,
                }}
              >
                Parol
              </label>
              <div style={{ position: "relative" }}>
                <Lock
                  size={16}
                  color="#94a3b8"
                  style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)" }}
                />
                <input
                  className="input-glow"
                  type={showPass ? "text" : "password"}
                  placeholder="••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  style={{
                    width: "100%",
                    height: "44px",
                    paddingLeft: 42,
                    paddingRight: 44,
                    borderRadius: 12,
                    border: "1px solid #cbd5e1",
                    background: "rgba(255,255,255,0.7)",
                    fontSize: 14,
                    color: "#0b1c30",
                  }}
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
                    color: "#94a3b8",
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
                  borderRadius: 12,
                  background: "rgba(186,26,26,0.06)",
                  border: "1px solid rgba(186,26,26,0.15)",
                  color: "#ba1a1a",
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                <AlertCircle size={15} />
                {error}
              </div>
            )}

            <button
              className="btn-gradient"
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                marginTop: 4,
                height: 44,
                borderRadius: 12,
                fontSize: 14,
                fontWeight: 700,
              }}
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
            color: "#94a3b8",
            fontSize: 11,
            fontWeight: 500,
            marginTop: 24,
          }}
        >
          © 2025 Savdogar Platform · HQ Console v2.0
        </p>
      </div>
    </div>
  );
}
