import { describe, it, expect } from "vitest";
import { mkdtempSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  generateKeypair,
  loadKeypair,
  signPayload,
  verifyPayload,
  getPublicKeyFingerprint,
  type Keypair,
} from "../src/identity";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-identity-"));
}

describe("generateKeypair", () => {
  it("creates private and public key files", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    expect(existsSync(join(dir, "miner.key"))).toBe(true);
    expect(existsSync(join(dir, "miner.pub"))).toBe(true);
  });

  it("private key is PEM-encoded", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const privKey = readFileSync(join(dir, "miner.key"), "utf-8");
    expect(privKey).toContain("PRIVATE KEY");
  });

  it("public key is PEM-encoded", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const pubKey = readFileSync(join(dir, "miner.pub"), "utf-8");
    expect(pubKey).toContain("PUBLIC KEY");
  });

  it("does not overwrite existing keypair", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const firstPub = readFileSync(join(dir, "miner.pub"), "utf-8");

    generateKeypair(dir); // should be a no-op
    const secondPub = readFileSync(join(dir, "miner.pub"), "utf-8");
    expect(secondPub).toBe(firstPub);
  });
});

describe("loadKeypair", () => {
  it("loads an existing keypair", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const kp = loadKeypair(dir);
    expect(kp).not.toBeNull();
    expect(kp!.publicKeyPem).toContain("PUBLIC KEY");
  });

  it("returns null when no keypair exists", () => {
    const dir = makeTmpDir();
    const kp = loadKeypair(dir);
    expect(kp).toBeNull();
  });
});

describe("signPayload + verifyPayload", () => {
  it("signs and verifies a string payload", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const kp = loadKeypair(dir)!;

    const payload = '{"developer":"alice","entries":["line1","line2"]}';
    const signature = signPayload(payload, kp);

    expect(signature).toBeTruthy();
    expect(typeof signature).toBe("string");

    const valid = verifyPayload(payload, signature, kp.publicKeyPem);
    expect(valid).toBe(true);
  });

  it("rejects tampered payload", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const kp = loadKeypair(dir)!;

    const payload = '{"developer":"alice"}';
    const signature = signPayload(payload, kp);

    const tampered = '{"developer":"mallory"}';
    const valid = verifyPayload(tampered, signature, kp.publicKeyPem);
    expect(valid).toBe(false);
  });

  it("rejects wrong public key", () => {
    const dir1 = makeTmpDir();
    const dir2 = makeTmpDir();
    generateKeypair(dir1);
    generateKeypair(dir2);
    const kp1 = loadKeypair(dir1)!;
    const kp2 = loadKeypair(dir2)!;

    const payload = '{"data":"test"}';
    const signature = signPayload(payload, kp1);

    const valid = verifyPayload(payload, signature, kp2.publicKeyPem);
    expect(valid).toBe(false);
  });
});

describe("getPublicKeyFingerprint", () => {
  it("returns a hex fingerprint", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const kp = loadKeypair(dir)!;

    const fp = getPublicKeyFingerprint(kp.publicKeyPem);
    expect(fp).toMatch(/^[0-9a-f]{64}$/); // SHA-256 hex
  });

  it("same key produces same fingerprint", () => {
    const dir = makeTmpDir();
    generateKeypair(dir);
    const kp = loadKeypair(dir)!;

    const fp1 = getPublicKeyFingerprint(kp.publicKeyPem);
    const fp2 = getPublicKeyFingerprint(kp.publicKeyPem);
    expect(fp1).toBe(fp2);
  });

  it("different keys produce different fingerprints", () => {
    const dir1 = makeTmpDir();
    const dir2 = makeTmpDir();
    generateKeypair(dir1);
    generateKeypair(dir2);
    const kp1 = loadKeypair(dir1)!;
    const kp2 = loadKeypair(dir2)!;

    const fp1 = getPublicKeyFingerprint(kp1.publicKeyPem);
    const fp2 = getPublicKeyFingerprint(kp2.publicKeyPem);
    expect(fp1).not.toBe(fp2);
  });
});
