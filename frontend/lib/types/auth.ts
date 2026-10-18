export interface UserClaims {
  sub: string;       // user UUID
  org_id: string;    // organization UUID
  role: string;      // org_admin, operator, etc.
  exp?: number;
}

export interface AuthUser extends UserClaims {
  username: string;  // email or display username
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}
