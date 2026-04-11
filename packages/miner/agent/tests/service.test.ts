import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, existsSync, readFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  generateLaunchdPlist,
  generateSystemdUnit,
  getServicePaths,
  type ServiceConfig,
} from "../src/service";

function makeTmpDir(): string {
  return mkdtempSync(join(tmpdir(), "miner-service-"));
}

const makeConfig = (overrides?: Partial<ServiceConfig>): ServiceConfig => ({
  binaryPath: "/Users/testuser/.local/bin/miner",
  homeDir: "/Users/testuser",
  logPath: "/Users/testuser/.miner/miner.log",
  ...overrides,
});

describe("generateLaunchdPlist", () => {
  it("generates valid plist XML", () => {
    const plist = generateLaunchdPlist(makeConfig());
    expect(plist).toContain("<?xml");
    expect(plist).toContain("<plist");
    expect(plist).toContain("com.miner.agent");
  });

  it("includes the binary path", () => {
    const plist = generateLaunchdPlist(makeConfig({
      binaryPath: "/opt/bin/miner",
    }));
    expect(plist).toContain("/opt/bin/miner");
    expect(plist).toContain("daemon");
  });

  it("includes log paths", () => {
    const plist = generateLaunchdPlist(makeConfig({
      logPath: "/tmp/miner.log",
    }));
    expect(plist).toContain("/tmp/miner.log");
  });

  it("sets RunAtLoad and KeepAlive", () => {
    const plist = generateLaunchdPlist(makeConfig());
    expect(plist).toContain("RunAtLoad");
    expect(plist).toContain("KeepAlive");
  });
});

describe("generateSystemdUnit", () => {
  it("generates valid systemd unit", () => {
    const unit = generateSystemdUnit(makeConfig());
    expect(unit).toContain("[Unit]");
    expect(unit).toContain("[Service]");
    expect(unit).toContain("[Install]");
  });

  it("includes ExecStart with binary path", () => {
    const unit = generateSystemdUnit(makeConfig({
      binaryPath: "/usr/local/bin/miner",
    }));
    expect(unit).toContain("ExecStart=/usr/local/bin/miner daemon");
  });

  it("sets restart policy", () => {
    const unit = generateSystemdUnit(makeConfig());
    expect(unit).toContain("Restart=on-failure");
  });
});

describe("getServicePaths", () => {
  it("returns launchd paths on macOS", () => {
    const paths = getServicePaths("darwin", "/Users/testuser");
    expect(paths.plistPath).toContain("LaunchAgents");
    expect(paths.plistPath).toContain("com.miner.agent.plist");
  });

  it("returns systemd paths on Linux", () => {
    const paths = getServicePaths("linux", "/home/testuser");
    expect(paths.unitPath).toContain("systemd/user");
    expect(paths.unitPath).toContain("miner.service");
  });

  it("returns null for unsupported platforms", () => {
    const paths = getServicePaths("win32", "C:\\Users\\test");
    expect(paths.plistPath).toBeUndefined();
    expect(paths.unitPath).toBeUndefined();
  });
});
