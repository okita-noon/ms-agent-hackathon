export interface AuthUser {
  user_id: string;
  tenant_id: string;
  email: string;
  display_name: string;
}

interface JwtPayload {
  sub?: string;
  tenant_id?: string;
  email?: string;
  display_name?: string;
  exp?: number;
}

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  return atob(padded);
}

export function readUserFromToken(token: string): AuthUser | null {
  try {
    const [, payloadPart] = token.split(".");
    if (!payloadPart) return null;

    const payload = JSON.parse(decodeBase64Url(payloadPart)) as JwtPayload;
    if (!payload.sub || !payload.tenant_id || !payload.email) return null;
    if (payload.exp && payload.exp * 1000 <= Date.now()) return null;

    return {
      user_id: payload.sub,
      tenant_id: payload.tenant_id,
      email: payload.email,
      display_name: payload.display_name || payload.email,
    };
  } catch {
    return null;
  }
}
