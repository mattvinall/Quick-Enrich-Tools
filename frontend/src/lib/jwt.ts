// Decode the `exp` claim from a JWT without verifying the signature.
// Returns the epoch-seconds expiry, or null if it can't be parsed.
export function getJwtExp(token: string): number | null {
  const parts = token.split('.');
  if (parts.length !== 3) return null;

  const payload = parts[1];
  // base64url -> base64
  const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
  const padded = b64 + '==='.slice((b64.length + 3) % 4);

  let json: string;
  try {
    json = atob(padded);
  } catch {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return null;
  }

  if (
    parsed &&
    typeof parsed === 'object' &&
    'exp' in parsed &&
    typeof (parsed as { exp: unknown }).exp === 'number'
  ) {
    return (parsed as { exp: number }).exp;
  }
  return null;
}

// True when the token's `exp` claim is in the past, or when it has no usable
// `exp` (treat unparseable tokens as expired so we don't hang on them).
export function isJwtExpired(token: string): boolean {
  const exp = getJwtExp(token);
  if (exp === null) return true;
  return exp * 1000 <= Date.now();
}
