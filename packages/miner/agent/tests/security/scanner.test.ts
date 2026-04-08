import { describe, it, expect } from "vitest";
import { scanForSecrets, redactSecrets, type SecretFinding } from "../../src/security/scanner";

describe("scanForSecrets", () => {
  it("detects AWS access keys", () => {
    const findings = scanForSecrets("credentials: AKIAIOSFODNN7EXAMPLE");
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("aws_access_key");
  });

  it("detects database URLs with passwords", () => {
    const findings = scanForSecrets(
      'DATABASE_URL=postgres://admin:s3cretP4ss@db.example.com:5432/mydb'
    );
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("database_url");
  });

  it("detects GitHub tokens", () => {
    const findings = scanForSecrets("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh1234");
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("github_token");
  });

  it("detects Anthropic API keys", () => {
    const findings = scanForSecrets("key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz");
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("anthropic_key");
  });

  it("detects private key blocks", () => {
    const findings = scanForSecrets("-----BEGIN RSA PRIVATE KEY-----\nMIIE...");
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("private_key");
  });

  it("detects JWT tokens", () => {
    const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123";
    const findings = scanForSecrets(`auth: ${jwt}`);
    expect(findings).toHaveLength(1);
    expect(findings[0].type).toBe("jwt_token");
  });

  it("returns empty for clean text", () => {
    const findings = scanForSecrets("just a normal log line with no secrets");
    expect(findings).toEqual([]);
  });

  it("finds multiple secrets in one string", () => {
    const text =
      'AKIA1234567890ABCDEF and postgres://user:pass1234@host:5432/db';
    const findings = scanForSecrets(text);
    expect(findings.length).toBeGreaterThanOrEqual(2);
    const types = findings.map((f) => f.type);
    expect(types).toContain("aws_access_key");
    expect(types).toContain("database_url");
  });

  it("includes match position", () => {
    const findings = scanForSecrets("key: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh1234");
    expect(findings[0].start).toBeGreaterThanOrEqual(0);
    expect(findings[0].end).toBeGreaterThan(findings[0].start);
  });
});

describe("redactSecrets", () => {
  it("replaces AWS keys with redaction marker", () => {
    const result = redactSecrets("key: AKIAIOSFODNN7EXAMPLE");
    expect(result).toContain("[REDACTED:aws_access_key]");
    expect(result).not.toContain("AKIAIOSFODNN7EXAMPLE");
  });

  it("replaces database URLs", () => {
    const result = redactSecrets(
      "postgres://admin:s3cretP4ss@db.example.com:5432/mydb"
    );
    expect(result).toContain("[REDACTED:database_url]");
    expect(result).not.toContain("s3cretP4ss");
  });

  it("replaces multiple secrets", () => {
    const text =
      "aws: AKIAIOSFODNN7EXAMPLE db: postgres://u:pass1234@h:5432/d";
    const result = redactSecrets(text);
    expect(result).toContain("[REDACTED:aws_access_key]");
    expect(result).toContain("[REDACTED:database_url]");
  });

  it("leaves clean text unchanged", () => {
    const text = "just normal text";
    expect(redactSecrets(text)).toBe(text);
  });

  it("is idempotent", () => {
    const text = "key: AKIAIOSFODNN7EXAMPLE";
    const first = redactSecrets(text);
    const second = redactSecrets(first);
    expect(second).toBe(first);
  });
});
