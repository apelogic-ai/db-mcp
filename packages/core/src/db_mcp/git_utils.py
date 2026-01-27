"""Git utilities with automatic backend selection.

This module provides a unified interface for git operations, automatically
selecting between native git (if available) and dulwich (pure Python fallback).

Usage:
    from db_mcp.git_utils import git

    # All operations use the same interface
    git.init(path)
    git.add(path, ["file.txt"])
    git.commit(path, "message")
    commits = git.log(path, "file.txt", limit=50)
    content = git.show(path, "file.txt", commit_hash)
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Commit:
    """Represents a git commit."""

    hash: str
    full_hash: str
    message: str
    author: str
    date: datetime


class GitBackend(ABC):
    """Abstract base class for git operations."""

    name: str = "abstract"

    @abstractmethod
    def is_repo(self, path: Path) -> bool:
        """Check if path is a git repository."""
        ...

    @abstractmethod
    def init(self, path: Path) -> None:
        """Initialize a new git repository."""
        ...

    @abstractmethod
    def add(self, path: Path, files: list[str]) -> None:
        """Stage files for commit."""
        ...

    @abstractmethod
    def commit(self, path: Path, message: str) -> str | None:
        """Commit staged changes. Returns commit hash or None if nothing to commit."""
        ...

    @abstractmethod
    def log(self, path: Path, file: str | None = None, limit: int = 50) -> list[Commit]:
        """Get commit history, optionally filtered by file."""
        ...

    @abstractmethod
    def show(self, path: Path, file: str, commit: str) -> str:
        """Get file content at a specific commit."""
        ...

    @abstractmethod
    def rm(self, path: Path, file: str) -> None:
        """Remove a file from git tracking and working directory."""
        ...

    @abstractmethod
    def status(self, path: Path) -> list[str]:
        """Get list of modified/untracked files."""
        ...

    @abstractmethod
    def head_hash(self, path: Path, short: bool = True) -> str:
        """Get the current HEAD commit hash."""
        ...

    # Optional operations - may not be supported by all backends
    def clone(self, url: str, dest: Path) -> None:
        """Clone a repository. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support clone")

    def pull(self, path: Path, rebase: bool = False) -> None:
        """Pull from remote. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support pull")

    def push(self, path: Path) -> None:
        """Push to remote. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support push")

    def stash(self, path: Path) -> None:
        """Stash changes. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support stash")

    def stash_pop(self, path: Path) -> None:
        """Pop stashed changes. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support stash_pop")

    def remote_add(self, path: Path, name: str, url: str) -> None:
        """Add a remote. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support remote_add")

    def remote_get_url(self, path: Path, name: str = "origin") -> str | None:
        """Get remote URL. May raise NotImplementedError."""
        raise NotImplementedError(f"{self.name} backend does not support remote_get_url")

    def has_remote(self, path: Path) -> bool:
        """Check if repository has any remotes."""
        raise NotImplementedError(f"{self.name} backend does not support has_remote")


class NativeGitBackend(GitBackend):
    """Git backend using native git binary via subprocess."""

    name = "native"

    def _run(
        self,
        args: list[str],
        cwd: Path,
        check: bool = True,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=capture,
            text=True,
            check=check,
        )

    def is_repo(self, path: Path) -> bool:
        return (path / ".git").is_dir()

    def init(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        self._run(["init"], cwd=path)

    def add(self, path: Path, files: list[str]) -> None:
        for file in files:
            self._run(["add", file], cwd=path)

    def commit(self, path: Path, message: str) -> str | None:
        result = self._run(["commit", "-m", message], cwd=path, check=False)
        if result.returncode != 0:
            # Check if it's just "nothing to commit"
            if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
                return None
            raise subprocess.CalledProcessError(result.returncode, result.args)
        return self.head_hash(path)

    def log(self, path: Path, file: str | None = None, limit: int = 50) -> list[Commit]:
        args = ["log", f"-{limit}", "--pretty=format:%h|%H|%s|%aI|%an"]
        if file:
            args.extend(["--follow", "--", file])

        result = self._run(args, cwd=path, check=False)
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append(
                    Commit(
                        hash=parts[0],
                        full_hash=parts[1],
                        message=parts[2],
                        date=datetime.fromisoformat(parts[3]),
                        author=parts[4],
                    )
                )
        return commits

    def show(self, path: Path, file: str, commit: str) -> str:
        result = self._run(["show", f"{commit}:{file}"], cwd=path)
        return result.stdout

    def rm(self, path: Path, file: str) -> None:
        self._run(["rm", "-f", file], cwd=path)

    def status(self, path: Path) -> list[str]:
        result = self._run(["status", "--porcelain"], cwd=path)
        files = []
        for line in result.stdout.strip().split("\n"):
            if line:
                # Format: "XY filename" where XY is status
                files.append(line[3:] if len(line) > 3 else line)
        return files

    def head_hash(self, path: Path, short: bool = True) -> str:
        args = ["rev-parse", "--short", "HEAD"] if short else ["rev-parse", "HEAD"]
        result = self._run(args, cwd=path)
        return result.stdout.strip()

    # Full remote support for native git
    def clone(self, url: str, dest: Path) -> None:
        subprocess.run(["git", "clone", url, str(dest)], check=True, capture_output=True)

    def pull(self, path: Path, rebase: bool = False) -> None:
        args = ["pull"]
        if rebase:
            args.extend(["--rebase", "origin", "HEAD"])
        self._run(args, cwd=path)

    def push(self, path: Path) -> None:
        self._run(["push", "-u", "origin", "HEAD"], cwd=path)

    def stash(self, path: Path) -> None:
        self._run(["stash"], cwd=path)

    def stash_pop(self, path: Path) -> None:
        self._run(["stash", "pop"], cwd=path)

    def remote_add(self, path: Path, name: str, url: str) -> None:
        self._run(["remote", "add", name, url], cwd=path)

    def remote_get_url(self, path: Path, name: str = "origin") -> str | None:
        result = self._run(["remote", "get-url", name], cwd=path, check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def has_remote(self, path: Path) -> bool:
        result = self._run(["remote"], cwd=path)
        return bool(result.stdout.strip())


class DulwichBackend(GitBackend):
    """Git backend using dulwich (pure Python)."""

    name = "dulwich"

    def is_repo(self, path: Path) -> bool:
        return (path / ".git").is_dir()

    def init(self, path: Path) -> None:
        from dulwich.repo import Repo

        path.mkdir(parents=True, exist_ok=True)
        Repo.init(str(path))

    def add(self, path: Path, files: list[str]) -> None:
        from dulwich.repo import Repo

        repo = Repo(str(path))
        for file in files:
            if file == ".":
                # Add all files
                for item in path.rglob("*"):
                    if item.is_file() and ".git" not in item.parts:
                        rel_path = item.relative_to(path)
                        repo.stage([str(rel_path)])
            else:
                file_path = path / file
                if file_path.exists():
                    repo.stage([file])

    def commit(self, path: Path, message: str) -> str | None:
        from dulwich.repo import Repo

        repo = Repo(str(path))

        # Check if there's anything to commit
        index = repo.open_index()
        if not index:
            return None

        # Get author info from git config or use defaults
        author = self._get_author(repo)

        try:
            commit_id = repo.do_commit(
                message.encode("utf-8"),
                committer=author,
                author=author,
            )
            return commit_id.decode("ascii")[:7]
        except Exception as e:
            if "nothing to commit" in str(e).lower():
                return None
            raise

    def _get_author(self, repo) -> bytes:
        """Get author string from config or defaults."""
        try:
            config = repo.get_config()
            name = config.get((b"user",), b"name")
            email = config.get((b"user",), b"email")
            if name and email:
                return name + b" <" + email + b">"
        except KeyError:
            pass
        return b"db-mcp <db-mcp@localhost>"

    def log(self, path: Path, file: str | None = None, limit: int = 50) -> list[Commit]:
        from dulwich.repo import Repo
        from dulwich.walk import Walker

        repo = Repo(str(path))
        commits = []

        try:
            walker = Walker(repo.object_store, [repo.head()], max_entries=limit)

            for entry in walker:
                commit_obj = entry.commit

                # If filtering by file, check if file was in this commit
                if file:
                    try:
                        tree = repo[commit_obj.tree]
                        # Walk the tree to find the file
                        file_parts = file.encode().split(b"/")
                        current = tree
                        found = True
                        for part in file_parts:
                            if hasattr(current, "items"):
                                if part in dict(current.items()):
                                    _, sha = dict(current.items())[part]
                                    current = repo[sha]
                                else:
                                    found = False
                                    break
                            else:
                                found = False
                                break
                        if not found:
                            continue
                    except Exception:
                        continue

                commit_time = datetime.fromtimestamp(
                    commit_obj.commit_time,
                    tz=timezone.utc,
                )

                full_hash = commit_obj.id.decode("ascii")
                commits.append(
                    Commit(
                        hash=full_hash[:7],
                        full_hash=full_hash,
                        message=commit_obj.message.decode("utf-8", errors="replace").strip(),
                        date=commit_time,
                        author=commit_obj.author.decode("utf-8", errors="replace")
                        .split("<")[0]
                        .strip(),
                    )
                )

                if len(commits) >= limit:
                    break

        except KeyError:
            # No commits yet
            pass

        return commits

    def show(self, path: Path, file: str, commit: str) -> str:
        from dulwich.repo import Repo

        repo = Repo(str(path))

        # Get commit object
        commit_id = commit.encode("ascii")
        # Try to resolve short hash
        for ref in repo.object_store:
            if ref.decode("ascii").startswith(commit):
                commit_id = ref
                break

        commit_obj = repo[commit_id]
        tree = repo[commit_obj.tree]

        # Navigate to file
        file_parts = file.encode().split(b"/")
        current = tree
        for part in file_parts[:-1]:
            entries = dict(current.items())
            if part in entries:
                _, sha = entries[part]
                current = repo[sha]
            else:
                raise FileNotFoundError(f"Path not found: {file}")

        # Get the file blob
        entries = dict(current.items())
        filename = file_parts[-1]
        if filename in entries:
            _, sha = entries[filename]
            blob = repo[sha]
            return blob.data.decode("utf-8", errors="replace")
        else:
            raise FileNotFoundError(f"File not found: {file}")

    def rm(self, path: Path, file: str) -> None:
        from dulwich.repo import Repo

        repo = Repo(str(path))
        file_path = path / file

        # Remove from index
        index = repo.open_index()
        if file.encode() in index:
            del index[file.encode()]
            index.write()

        # Remove from disk
        if file_path.exists():
            file_path.unlink()

    def status(self, path: Path) -> list[str]:
        from dulwich.porcelain import status as dulwich_status

        result = dulwich_status(str(path))
        files = []

        # Staged changes
        for file in result.staged.get("add", []):
            files.append(file.decode() if isinstance(file, bytes) else file)
        for file in result.staged.get("modify", []):
            files.append(file.decode() if isinstance(file, bytes) else file)
        for file in result.staged.get("delete", []):
            files.append(file.decode() if isinstance(file, bytes) else file)

        # Unstaged changes
        for file in result.unstaged:
            f = file.decode() if isinstance(file, bytes) else file
            if f not in files:
                files.append(f)

        # Untracked
        for file in result.untracked:
            f = file.decode() if isinstance(file, bytes) else file
            if f not in files:
                files.append(f)

        return files

    def head_hash(self, path: Path, short: bool = True) -> str:
        from dulwich.repo import Repo

        repo = Repo(str(path))
        head = repo.head().decode("ascii")
        return head[:7] if short else head

    # Remote operations - basic support
    def clone(self, url: str, dest: Path) -> None:
        from dulwich.porcelain import clone as dulwich_clone

        dulwich_clone(url, str(dest))

    def pull(self, path: Path, rebase: bool = False) -> None:
        from dulwich.porcelain import pull as dulwich_pull

        if rebase:
            logger.warning("Dulwich pull does not support rebase, using regular pull")
        dulwich_pull(str(path))

    def push(self, path: Path) -> None:
        from dulwich.porcelain import push as dulwich_push

        dulwich_push(str(path))

    def remote_add(self, path: Path, name: str, url: str) -> None:
        from dulwich.repo import Repo

        repo = Repo(str(path))
        config = repo.get_config()
        config.set((b"remote", name.encode()), b"url", url.encode())
        config.set((b"remote", name.encode()), b"fetch", b"+refs/heads/*:refs/remotes/origin/*")
        config.write_to_path()

    def remote_get_url(self, path: Path, name: str = "origin") -> str | None:
        from dulwich.repo import Repo

        repo = Repo(str(path))
        try:
            config = repo.get_config()
            url = config.get((b"remote", name.encode()), b"url")
            return url.decode() if url else None
        except KeyError:
            return None

    def has_remote(self, path: Path) -> bool:
        return self.remote_get_url(path) is not None


def _detect_backend() -> GitBackend:
    """Detect which git backend to use.

    Prefers native git if available, falls back to dulwich.
    """
    if shutil.which("git"):
        logger.debug("Using native git backend")
        return NativeGitBackend()
    else:
        logger.debug("Native git not found, using dulwich backend")
        return DulwichBackend()


# Module-level git instance - auto-detected at import
git = _detect_backend()


def get_backend_name() -> str:
    """Return the name of the currently active backend."""
    return git.name
