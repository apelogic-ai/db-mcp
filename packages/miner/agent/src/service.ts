/**
 * Service manager — generates and manages platform-native daemon services.
 *
 * macOS: launchd (~/Library/LaunchAgents/com.miner.agent.plist)
 * Linux: systemd user service (~/.config/systemd/user/miner.service)
 */

import { mkdirSync, writeFileSync, existsSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { execSync } from "node:child_process";

export interface ServiceConfig {
  binaryPath: string;
  homeDir: string;
  logPath: string;
}

export interface ServicePaths {
  plistPath?: string;
  unitPath?: string;
  platform: string;
}

const LABEL = "com.miner.agent";

/**
 * Generate a macOS launchd plist.
 */
export function generateLaunchdPlist(config: ServiceConfig): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${config.binaryPath}</string>
    <string>daemon</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${config.logPath}</string>
  <key>StandardErrorPath</key>
  <string>${config.logPath}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${config.homeDir}</string>
  </dict>
</dict>
</plist>`;
}

/**
 * Generate a Linux systemd user unit.
 */
export function generateSystemdUnit(config: ServiceConfig): string {
  return `[Unit]
Description=Miner Agent — AI trace collection
After=network.target

[Service]
ExecStart=${config.binaryPath} daemon
Restart=on-failure
RestartSec=60
Environment=HOME=${config.homeDir}

[Install]
WantedBy=default.target`;
}

/**
 * Get platform-specific service file paths.
 */
export function getServicePaths(
  platform: string,
  homeDir: string,
): ServicePaths {
  if (platform === "darwin") {
    return {
      plistPath: join(homeDir, "Library", "LaunchAgents", `${LABEL}.plist`),
      platform: "darwin",
    };
  }
  if (platform === "linux") {
    return {
      unitPath: join(homeDir, ".config", "systemd", "user", "miner.service"),
      platform: "linux",
    };
  }
  return { platform };
}

/**
 * Install and start the daemon as a system service.
 */
export function installService(config: ServiceConfig): {
  success: boolean;
  message: string;
} {
  const platform = process.platform;
  const paths = getServicePaths(platform, config.homeDir);

  if (platform === "darwin" && paths.plistPath) {
    const plist = generateLaunchdPlist(config);
    mkdirSync(dirname(paths.plistPath), { recursive: true });
    mkdirSync(dirname(config.logPath), { recursive: true });
    writeFileSync(paths.plistPath, plist);

    try {
      // Unload first if already loaded (idempotent)
      try {
        execSync(`launchctl unload ${paths.plistPath}`, { stdio: "pipe" });
      } catch { /* not loaded, fine */ }

      execSync(`launchctl load ${paths.plistPath}`, { stdio: "pipe" });
      return {
        success: true,
        message: `Daemon installed: ${paths.plistPath}\nStarted via launchd. Will run on login.`,
      };
    } catch (err) {
      return {
        success: false,
        message: `Failed to load launchd service: ${err instanceof Error ? err.message : err}`,
      };
    }
  }

  if (platform === "linux" && paths.unitPath) {
    const unit = generateSystemdUnit(config);
    mkdirSync(dirname(paths.unitPath), { recursive: true });
    mkdirSync(dirname(config.logPath), { recursive: true });
    writeFileSync(paths.unitPath, unit);

    try {
      execSync("systemctl --user daemon-reload", { stdio: "pipe" });
      execSync("systemctl --user enable --now miner.service", { stdio: "pipe" });
      return {
        success: true,
        message: `Daemon installed: ${paths.unitPath}\nStarted via systemd. Will run on login.`,
      };
    } catch (err) {
      return {
        success: false,
        message: `Failed to enable systemd service: ${err instanceof Error ? err.message : err}`,
      };
    }
  }

  return {
    success: false,
    message: `Unsupported platform: ${platform}. Run "miner daemon" manually.`,
  };
}

/**
 * Stop and uninstall the daemon service.
 */
export function uninstallService(homeDir: string): {
  success: boolean;
  message: string;
} {
  const platform = process.platform;
  const paths = getServicePaths(platform, homeDir);

  if (platform === "darwin" && paths.plistPath) {
    try {
      if (existsSync(paths.plistPath)) {
        execSync(`launchctl unload ${paths.plistPath}`, { stdio: "pipe" });
        unlinkSync(paths.plistPath);
      }
      return { success: true, message: "Daemon stopped and uninstalled." };
    } catch (err) {
      return {
        success: false,
        message: `Failed to unload: ${err instanceof Error ? err.message : err}`,
      };
    }
  }

  if (platform === "linux" && paths.unitPath) {
    try {
      execSync("systemctl --user disable --now miner.service", { stdio: "pipe" });
      if (existsSync(paths.unitPath)) {
        unlinkSync(paths.unitPath);
      }
      execSync("systemctl --user daemon-reload", { stdio: "pipe" });
      return { success: true, message: "Daemon stopped and uninstalled." };
    } catch (err) {
      return {
        success: false,
        message: `Failed to disable: ${err instanceof Error ? err.message : err}`,
      };
    }
  }

  return {
    success: false,
    message: `Unsupported platform: ${platform}`,
  };
}
