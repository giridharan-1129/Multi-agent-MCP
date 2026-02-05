"""
Repository Downloader Service.

WHAT: Download and manage GitHub repositories locally
WHY: Need to access repository files for indexing
HOW: Use GitPython to clone repos, handle updates

Example:
    downloader = RepositoryDownloader()
    repo_path = await downloader.download_repo(
        repo_url="https://github.com/tiangolo/fastapi",
        clone_path="/tmp/fastapi"
    )
    print(repo_path)  # "/tmp/fastapi"
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Optional

from git import GitCommandError, Repo

from .exceptions import RepositoryCloneError
from .logger import get_logger

logger = get_logger(__name__)


class RepositoryDownloader:
    """
    Download and manage GitHub repositories.

    Handles cloning, updating, and removing repositories.

    Attributes:
        default_clone_path: Default directory for cloning repos
    """

    def __init__(self, default_clone_path: str = "/tmp/repositories"):
        """
        Initialize RepositoryDownloader.

        Args:
            default_clone_path: Default directory to clone repositories
        """
        self.default_clone_path = default_clone_path

        # Create default clone path if it doesn't exist
        Path(self.default_clone_path).mkdir(parents=True, exist_ok=True)

        logger.info(
            "RepositoryDownloader initialized",
            clone_path=self.default_clone_path,
        )

    async def download_repo(
        self,
        repo_url: str,
        clone_path: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> str:
        """
        Download a GitHub repository.
        ...
        """
        if not clone_path:
            repo_name = repo_url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            clone_path = os.path.join(self.default_clone_path, repo_name)

        clone_path = os.path.abspath(clone_path)

        try:
            # Check if repo already exists
            # FIXED:
            if os.path.exists(clone_path):
                logger.info("Repository already exists, updating", path=clone_path)
                try:
                    await self._update_repo(clone_path)
                except Exception as update_err:
                    logger.info("Update failed, removing and re-cloning", path=clone_path)
                    try:
                        shutil.rmtree(clone_path)
                    except Exception as cleanup_err:
                        logger.error("Failed to remove old repo", path=clone_path, error=str(cleanup_err))
                        # Continue anyway - try to clone
                    
                    # Now clone fresh
                    await self._clone_repo(repo_url, clone_path, depth)
            else:
                logger.info("Cloning repository", url=repo_url, path=clone_path)
                await self._clone_repo(repo_url, clone_path, depth)

            return clone_path

        except Exception as e:
            logger.error(
                "Failed to download repository",
                url=repo_url,
                path=clone_path,
                error=str(e),
            )
            raise RepositoryCloneError(repo_url=repo_url, error_detail=str(e))

    async def _clone_repo(
        self,
        repo_url: str,
        clone_path: str,
        depth: Optional[int] = None,
    ) -> None:
        """
        Clone a repository (internal helper).

        Args:
            repo_url: Repository URL
            clone_path: Where to clone
            depth: Git depth for shallow clone

        Raises:
            GitCommandError: If git clone fails
        """
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()

        def _do_clone():
            try:
                if depth:
                    Repo.clone_from(repo_url, clone_path, depth=depth)
                else:
                    Repo.clone_from(repo_url, clone_path)
                logger.info("Repository cloned successfully", path=clone_path)
            except GitCommandError as e:
                raise RepositoryCloneError(repo_url=repo_url, error_detail=str(e))

        await loop.run_in_executor(None, _do_clone)

    async def _update_repo(self, repo_path: str) -> None:
        """
        Update an existing repository.

        Args:
            repo_path: Path to repository

        Raises:
            GitCommandError: If git operations fail
        """
        loop = asyncio.get_event_loop()

        def _do_update():
            try:
                repo = Repo(repo_path)
                # Fetch latest changes
                repo.remotes.origin.fetch()
                # Reset to latest
                repo.heads.master.reset(index=True, working_tree=True)
                logger.info("Repository updated successfully", path=repo_path)
            except Exception as e:
                logger.warning(f"Update failed, will re-clone: {str(e)}")
                # If update fails, remove and re-clone
                import shutil
                try:
                    shutil.rmtree(repo_path)
                    logger.info(f"Removed old repo, will re-clone: {repo_path}")
                except Exception as cleanup_err:
                    logger.error(f"Failed to cleanup: {str(cleanup_err)}")
                raise RepositoryCloneError(
                    repo_url=repo_path,
                    error_detail=f"Update failed, need fresh clone",
                )

        await loop.run_in_executor(None, _do_update)

    async def remove_repo(self, repo_path: str) -> bool:
        """
        Remove a cloned repository.

        Args:
            repo_path: Path to repository to remove

        Returns:
            True if successful

        Raises:
            OSError: If removal fails
        """
        try:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
                logger.info("Repository removed", path=repo_path)
                return True
            return False
        except OSError as e:
            logger.error("Failed to remove repository", path=repo_path, error=str(e))
            raise

    def get_repo_info(self, repo_path: str) -> dict:
        """
        Get information about a cloned repository.

        Args:
            repo_path: Path to repository

        Returns:
            Dictionary with repo information

        Raises:
            GitCommandError: If git operations fail
        """
        try:
            repo = Repo(repo_path)
            info = {
                "path": repo_path,
                "url": repo.remotes.origin.url,
                "branch": repo.active_branch.name,
                "commit": repo.head.commit.hexsha,
                "commit_message": repo.head.commit.message,
                "is_dirty": repo.is_dirty(),
                "untracked_files": repo.untracked_files,
            }

            logger.info("Repository info retrieved", path=repo_path)
            return info
        except Exception as e:
            logger.error("Failed to get repository info", path=repo_path, error=str(e))
            raise

    def get_all_python_files(self, repo_path: str) -> list:
        """
        Get all Python files in a repository.

        Args:
            repo_path: Path to repository

        Returns:
            List of Python file paths

        Raises:
            OSError: If directory reading fails
        """
        try:
            python_files = []

            for root, dirs, files in os.walk(repo_path):
                # Skip common directories we don't need
                dirs[:] = [
                    d for d in dirs
                    if d not in {".git", "__pycache__", ".tox", "venv", ".venv", "build", "dist"}
                ]

                for file in files:
                    if file.endswith(".py"):
                        file_path = os.path.join(root, file)
                        python_files.append(file_path)

            logger.info(
                "Python files found",
                repo_path=repo_path,
                count=len(python_files),
            )
            return python_files

        except OSError as e:
            logger.error(
                "Failed to get Python files",
                repo_path=repo_path,
                error=str(e),
            )
            raise

    def read_file(self, file_path: str) -> str:
        """
        Read file content.

        Args:
            file_path: Path to file

        Returns:
            File content as string

        Raises:
            OSError: If file read fails
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            logger.debug("File read", path=file_path, size=len(content))
            return content

        except (OSError, UnicodeDecodeError) as e:
            logger.error("Failed to read file", path=file_path, error=str(e))
            raise

    def get_relative_path(self, file_path: str, repo_path: str) -> str:
        """
        Get relative path of file within repository.

        Args:
            file_path: Absolute path to file
            repo_path: Path to repository root

        Returns:
            Relative path within repository
        """
        try:
            rel_path = os.path.relpath(file_path, repo_path)
            return rel_path
        except ValueError as e:
            logger.error(
                "Failed to get relative path",
                file=file_path,
                repo=repo_path,
                error=str(e),
            )
            raise


# Global downloader instance
repository_downloader: Optional[RepositoryDownloader] = None


def init_downloader(clone_path: str = "/tmp/repositories") -> RepositoryDownloader:
    """
    Initialize repository downloader.

    Args:
        clone_path: Directory for cloning repositories

    Returns:
        RepositoryDownloader instance
    """
    global repository_downloader
    repository_downloader = RepositoryDownloader(clone_path)
    return repository_downloader


def get_downloader() -> RepositoryDownloader:
    """
    Get initialized downloader.

    Returns:
        RepositoryDownloader instance

    Raises:
        RuntimeError: If not initialized
    """
    global repository_downloader
    if not repository_downloader:
        repository_downloader = RepositoryDownloader()
    return repository_downloader
