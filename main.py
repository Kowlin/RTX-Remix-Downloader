import zipfile
import logging
import sys
import argparse
import shutil
from subprocess import Popen
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler
from rich.prompt import Confirm, Prompt

BUILD_NAMES = []

BUILD_TYPES = {
    "1": {"type": "release", "description": "(recommended) The default Remix version that prioritizes speed"},
    "2": {"type": "debugoptimized", "description": "For debugging issues. This build is still fast."},
    "3": {"type": "debug", "description": "For debugging only. Unplayable in games"},
}

def get_build_type():
    print("Please choose a build type:")
    for choice, build_info in BUILD_TYPES.items():
        print(f"{choice}: \033[38;5;208m{build_info['type']}\033[0m - {build_info['description']}")
    while True:
        chosen_build_type = input("Your choice: ")
        if chosen_build_type in BUILD_TYPES:
            return BUILD_TYPES[chosen_build_type]['type']
        else:
            print("Invalid choice. Please try again.")

parser = argparse.ArgumentParser(
    prog="RTXRemix Downloader",
    description="Downloads the latest RTXRemix builds.",
)
parser.add_argument(
    '-d',
    "--debug",
    action="store_true",
    help="Enables debug logging.",
)
parser.add_argument(
    '-b',
    "--build-type",
    default="release",
    choices=["release", "debug", "debugoptimized"],
    help="Specifies the build type to download.",
)
args = argparse.Namespace()
args.debug = False  # or True if you want to enable debug by default
args.build_type = get_build_type()


print(f"Downloading {args.build_type} builds")

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
    },
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
    console=CONSOLE,
)
STEP_COUNTER = PROGRESS.add_task("Steps", total=len(REPOSITORIES) * 2 + 4)


class HiddenPrompt(Prompt):
    prompt_suffix = ""


def replace_recursively(root_path: Path, move_to: Path) -> None:
    """Recursively replaces a directory with its contents while preserving the directory structure"""
    for child in root_path.iterdir():
        if child.is_file():
            LOGGER.debug(f"Replacing {child} with {move_to.joinpath(child.name)}")
            shutil.move(str(child), str(move_to.joinpath(child.name)))
        elif child.is_dir():
            LOGGER.debug(
                f"Replacing {child} with {move_to.joinpath(child.name) if move_to else None}"
            )
            move_to.joinpath(child.name).mkdir(exist_ok=True)
            replace_recursively(child, move_to.joinpath(child.name))
            child.rmdir()


def fetch_release(repo: str, temp_dir: TemporaryDirectory) -> TemporaryDirectory:
    """Fetches the latest release from a repository"""
    path = Path(temp_dir.name)

    PROGRESS.print(
        f"Fetching the latest release info from [bold blue]{repo}[/bold blue]"
    )
    resp = HTTP.get(f"https://api.github.com/repos/{repo}/releases/latest")
    json = resp.json()

    for asset in json["assets"]:
        if "symbols" not in asset["name"]:
            download_url = asset["browser_download_url"]
            size = asset["size"]

    PROGRESS.print(f"Downloading latest release from [bold blue]{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    with open(path.joinpath(f"{json['name']}.zip"), "wb") as f:
        with HTTP.stream(
            "GET", download_url, timeout=30, follow_redirects=True
        ) as resp:
            for data in resp.iter_bytes():
                f.write(data)

    PROGRESS.print(f"Extracting latest release from [bold blue]{repo}[/bold blue]")
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

    PROGRESS.print(
        f"Fetching the latest artifact info from [bold blue]{repo}[/bold blue]"
    )
    resp = HTTP.get(f"https://api.github.com/repos/{repo}/actions/runs")
    json = resp.json()

    # Grab the first succeeded run on the specified artifact branch.
    # Runs are sorted from newest to oldest by GitHub. So no need to date check.
    for run in json["workflow_runs"]:
        if (
            run["head_branch"] == REPOSITORIES[repo]["artifact_branch"]
            and run["conclusion"] == "success"
        ):
            resp = HTTP.get(run["artifacts_url"])
            json = resp.json()
            break

    for artifact in json["artifacts"]:
        if args.build_type in artifact["name"]:
            artifact_name = artifact["name"]
            id = artifact["id"]
            size = artifact["size_in_bytes"]
            BUILD_NAMES.append(artifact_name)
            break


    PROGRESS.print(f"Downloading latest artifact from [bold blue]{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    with open(path.joinpath(f"{artifact_name}.zip"), "wb") as f:
        with HTTP.stream(
            "GET",
            f"https://nightly.link/{repo}/actions/artifacts/{id}.zip",
            timeout=30,
            follow_redirects=True,
        ) as resp:
            for data in resp.iter_bytes():
                f.write(data)

    PROGRESS.print(f"Extracting latest artifact from [bold blue]{repo}[/bold blue]")
    PROGRESS.advance(STEP_COUNTER)
    zipfile.ZipFile(path.joinpath(f"{artifact_name}.zip")).extractall(path)
    path.joinpath(f"{artifact_name}.zip").unlink()

    return temp_dir


def main() -> None:
    """Main loop"""
    HiddenPrompt.ask(
        "[b]RTX Remix Download Script[/b]\n"
        "This script requests the latest artifact builds from the official Github repositories.\n"
        "This downloads the file in the same location as the script, unzips and cleans up after itself.\n"
        "Find us on Discord: [blue]https://discord.gg/rtxremix[/blue]\n"
        "[i]This script is not affiliated with NVIDIA or the RTXRemix project.[/i]\n"
        "\n"
        "Press Enter to continue...",
        password=True,
        console=CONSOLE,
    )

    with PROGRESS:
        for repo, data in REPOSITORIES.items():
            if data["repo_type"] == "release":
                data["temp_dir"] = fetch_release(
                    repo, TemporaryDirectory(prefix="RTXREMIX-")
                )
            elif data["repo_type"] == "artifact":
                data["temp_dir"] = fetch_artifact(
                    repo, TemporaryDirectory(prefix="RTXREMIX-")
                )

        main_directory = None
        for repo, data in REPOSITORIES.items():
            if data["main_directory"]:
                main_directory = Path(
                    data["temp_dir"].name
                )  # Returns a TemporaryDirectory object
                break

        # Move all the files to their appropiate locations
        PROGRESS.print("Moving artifacts to their appropiate locations")
        PROGRESS.advance(STEP_COUNTER)
        for repo, data in REPOSITORIES.items():
            if data["main_directory"] is False:
                if data["move_to"] is None:
                    replace_recursively(Path(data["temp_dir"].name), main_directory)
                else:
                    replace_recursively(
                        Path(data["temp_dir"].name),
                        main_directory.joinpath(data["move_to"]),
                    )

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
        PROGRESS.print('Moving files to the "remix" directory')
        PROGRESS.advance(STEP_COUNTER)
        final_path = Path(sys.argv[0]).parent.joinpath("remix")
        final_path.mkdir(exist_ok=True)
        replace_recursively(main_directory, final_path)
        
        # Print the names of the downloaded packages
        print("Downloaded the following packages:")
        for name in BUILD_NAMES:
            print(name)
            
        # Write build names to a text file
        with open(final_path.joinpath('build_names.txt'), 'w') as f:
            for name in BUILD_NAMES:
                f.write(f'{name}\n')

        # Cleanup the temp dirs
        PROGRESS.print("Cleaning up temporary directories")
        PROGRESS.advance(STEP_COUNTER)
        for repo, data in REPOSITORIES.items():
            data["temp_dir"].cleanup()

        PROGRESS.print("[green]Success![/green]")

    if Confirm.ask(
        "Would you like to open the [bold green]Remix[/bold green] directory now?",
        default=True,
        console=CONSOLE,
    ):
        Popen(f'explorer "{final_path}"')

    HiddenPrompt.ask(
        "You can find the latest RTX Remix install in:\n"
        f"[bold blue]{final_path.resolve()}[/bold blue]\n"
        "RTX Remix install guide:\n"
        "[blue]https://github.com/NVIDIAGameWorks/rtx-remix/wiki/runtime-user-guide[/blue]\n"
        "\n"
        "Press [bold]Enter[/bold] to close this window..."
    )


if __name__ == "__main__":
    if args.debug is True:
        LOGGER.setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.DEBUG)
    main()
