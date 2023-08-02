import os
import zipfile
import logging
import sys
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler

parser = argparse.ArgumentParser(
    prog="RTXRemix Downloader",
    description="Downloads the latest RTXRemix builds.",
)
parser.add_argument(
    "--debug",
    action="store_true",
    help="Enables debug logging.",
)
args = parser.parse_args()

REPOSITORIES = {
    "NVIDIAGameWorks/rtx-remix": {
        "repo_type": "release",
        "move_to": None,
        "temp_dir": None,
        "main_directory": True,
    },
    "NVIDIAGameWorks/dxvk-remix": {
        "repo_type": "artifact",
        "move_to": ".trex",  # Move this to a special subdirectory
        "temp_dir": None,
        "main_directory": False,
        "artifact_branch": "main",
    },
    "NVIDIAGameWorks/bridge-remix": {
        "repo_type": "artifact",
        "move_to": None,  # Move this to the root of the temp directory
        "temp_dir": None,
        "main_directory": False,
        "artifact_branch": "main",
    }
}

HTTP = httpx.Client(
    headers={
        "User-Agent": f"Python/httpx v{httpx.__version__} - RTXRemix Downloader Script"
    }
)
LOGGER = logging.getLogger("rtxremix")
FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
CONSOLE = Console()
PROGRESS = Progress(
    SpinnerColumn(),
    TextColumn("[bold blue] {task.completed} of {task.total} steps completed"),
    console=CONSOLE
)
STEP_COUNTER = PROGRESS.add_task("Steps", total=len(REPOSITORIES) * 2 + 4)


def replace_recursively(root_path: Path, move_to: Path) -> None:
    """Recursively replaces a directory with its contents while preserving the directory structure"""
    for child in root_path.iterdir():
        if child.is_file():
            LOGGER.debug(f"Replacing {child} with {move_to.joinpath(child.name)}")
            child.replace(move_to.joinpath(child.name))
        elif child.is_dir():
            LOGGER.debug(f"Replacing {child} with {move_to.joinpath(child.name) if move_to else None}")
            move_to.joinpath(child.name).mkdir(exist_ok=True)
            replace_recursively(child, move_to.joinpath(child.name))
            child.rmdir()


def fetch_release(repo: str, temp_dir: TemporaryDirectory) -> TemporaryDirectory:
    """Fetches the latest release from a repository"""
    path = Path(temp_dir.name)

    PROGRESS.print(f"Fetching the latest release info from [bold blue][{repo}[/bold blue]")
    resp = HTTP.get(f"https://api.github.com/repos/{repo}/releases/latest")
    json = resp.json()

    for asset in json["assets"]:
        if "symbols" not in asset["name"]:
            download_url = asset["browser_download_url"]
            size = asset["size"]

    PROGRESS.print(f"Downloading latest release from [bold blue][{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    with open(path.joinpath(f"{json['name']}.zip"), "wb") as f:
        with HTTP.stream("GET", download_url, timeout=30, follow_redirects=True) as resp:
            for data in resp.iter_bytes():
                f.write(data)

    PROGRESS.print(f"Extracting latest release from [bold blue][{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    zipfile.ZipFile(path.joinpath(f"{json['name']}.zip")).extractall(path)
    path.joinpath(f"{json['name']}.zip").unlink()

    # Move the contents of the zip to the root of the temp directory.
    child_path = next(path.iterdir())
    replace_recursively(child_path, path)
    child_path.rmdir()

    return temp_dir


def fetch_artifact(repo: str, temp_dir: TemporaryDirectory) -> TemporaryDirectory:
    """Fetches the latest artifact from a repository"""
    path = Path(temp_dir.name)

    PROGRESS.print(f"Fetching the latest artifact info from [bold blue][{repo}[/bold blue]")
    resp = HTTP.get(f"https://api.github.com/repos/{repo}/actions/runs")
    json = resp.json()

    # Grab the first succeeded run on the specified artifact branch.
    # Runs are sorted from newest to oldest by GitHub. So no need to date check.
    for run in json["workflow_runs"]:
        if run['head_branch'] == REPOSITORIES[repo]['artifact_branch'] and run['conclusion'] == "success":
            resp = HTTP.get(run['artifacts_url'])
            json = resp.json()
            break

    for artifact in json["artifacts"]:
        if "release" in artifact["name"]:
            artifact_name = artifact["name"]
            id = artifact["id"]
            size = artifact["size_in_bytes"]  # GitHub gives this as pre-compression size. So it's useless
            break

    PROGRESS.print(f"Downloading latest artifact from [bold blue][{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    with open(path.joinpath(f"{artifact_name}.zip"), "wb") as f:
        with HTTP.stream("GET", f"https://nightly.link/{repo}/actions/artifacts/{id}.zip", timeout=30, follow_redirects=True) as resp:
            for data in resp.iter_bytes():
                f.write(data)

    PROGRESS.print(f"Extracting latest artifact from [bold blue][{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    zipfile.ZipFile(path.joinpath(f"{artifact_name}.zip")).extractall(path)
    path.joinpath(f"{artifact_name}.zip").unlink()

    return temp_dir


def main() -> None:
    """Main loop"""
    CONSOLE.input(
        "[b]RTX Remix Download Script[/b]\n"
        "This script requests the latest artifact builds from the official Github repositories.\n"
        "This downloads the file in the same location as the script, unzips and cleans up after itself.\n"
        "Find us on Discord [blue]https://discord.gg/rtxremix[/blue]\n"
        "\n"
        "Press Enter to continue..."
    )

    with PROGRESS:

        for repo, data in REPOSITORIES.items():
            if data["repo_type"] == "release":
                data["temp_dir"] = fetch_release(repo, TemporaryDirectory(prefix="RTXREMIX-"))
            elif data["repo_type"] == "artifact":
                data["temp_dir"] = fetch_artifact(repo, TemporaryDirectory(prefix="RTXREMIX-"))

        main_directory = None
        for repo, data in REPOSITORIES.items():
            if data["main_directory"]:
                main_directory = Path(data["temp_dir"].name)  # Returns a TemporaryDirectory object
                break

        # Move all the files to their appropiate locations
        PROGRESS.print("Moving artifacts to their appropiate locations")
        PROGRESS.advance(STEP_COUNTER)
        for repo, data in REPOSITORIES.items():
            if data["main_directory"] is False:
                if data["move_to"] is None:
                    replace_recursively(Path(data["temp_dir"].name), main_directory)
                else:
                    replace_recursively(Path(data["temp_dir"].name), main_directory.joinpath(data["move_to"]))

        # Delete debugging symbols
        # Yes this looks ugly. Too bad!
        PROGRESS.print("Cleaning up debugging symbols")
        PROGRESS.advance(STEP_COUNTER)
        for child in main_directory.rglob("*.pdb"):
            child.unlink()
        for child in main_directory.rglob("CRC.txt"):
            child.unlink()
        for child in main_directory.rglob("artifacts_readme.txt"):
            child.unlink()

        # Move main_directory to working dir
        PROGRESS.print("Moving files to the \"remix\" directory")
        PROGRESS.advance(STEP_COUNTER)
        final_path = Path(sys.argv[0]).parent.joinpath("remix")
        final_path.mkdir(exist_ok=True)
        replace_recursively(main_directory, final_path)

        # Cleanup the temp dirs
        PROGRESS.print("Cleaning up temporary directories")
        PROGRESS.advance(STEP_COUNTER)
        for repo, data in REPOSITORIES.items():
            data["temp_dir"].cleanup()

        PROGRESS.print("[green]Success![/green]")

    CONSOLE.input(
        "\n"
        "Press Enter to exit..."
    )


if __name__ == "__main__":
    if args.debug is True:
        LOGGER.setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)
    main()


# TODO LIST
# Clean up code
# Add more user instructions
# Push to GH, Add workflows for autobuild on tag
# Add a progress bar for the whole script... Thanks copilot
