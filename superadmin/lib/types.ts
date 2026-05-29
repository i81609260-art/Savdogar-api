export interface SAUser {
  id: number;
  email: string;
  full_name: string;
  phone?: string;
  role: "superadmin" | "admin" | "operator" | "user";
  company_id?: number;
  company_name?: string;
  company_status?: "pending" | "approved" | "rejected";
  is_active: boolean;
  created_at?: string;
}

export interface Company {
  id: number;
  name: string;
  description?: string;
  city: string;
  phone: string;
  email: string;
  logo_url?: string;
  status: "pending" | "approved" | "rejected";
  rejection_reason?: string;
  owner_id?: number;
  created_at: string;
  updated_at: string;
  users_count: number;
  tours_count: number;
}

export interface PlatformStats {
  total_companies: number;
  pending_companies: number;
  approved_companies: number;
  total_users: number;
  total_tours: number;
  total_bookings: number;
  total_revenue: number;
}

export interface AuthState {
  user: SAUser | null;
  accessToken: string | null;
  setAuth: (user: SAUser, token: string) => void;
  logout: () => void;
}
