import argparse
import logging
import multiprocessing
import os
import platform
import sys
from pathlib import Path
from shutil import which
from typing import Optional

from ffsubsync.ffsubsync import make_parser, run
from PyQt5.QtWidgets import QApplication, QMessageBox
from sortedcontainers import SortedList

LOGLEVEL = os.environ.get("LOGLEVEL", "WARNING").upper()
logging.basicConfig(level=LOGLEVEL)

multiprocessing.freeze_support()

app = QApplication([])

video_file_endings = [
    ".webm", ".mkv", ".flv", ".vob", ".ogv", ".ogg", ".drc", ".gif", ".gifv",
    ".mng", ".avi", ".MTS", ".M2TS", ".TS", ".mov", ".qt", ".wmv", ".yuv",
    ".rm", ".rmvb", ".viv", ".asf", ".amv", ".mp4", ".m4p", ".m4v", ".mpg",
    ".mp2", ".mpeg", ".mpe", ".mpv", ".m2v", ".svi", ".3gp", ".3g2", ".mxf",
    ".roq", ".nsv", ".f4v", ".f4p", ".f4a", ".f4b",
]


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller"""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    logging.debug(f"base path: {base_path}")
    return os.path.join(base_path, relative_path)


def find_ffmpeg_tools() -> tuple[Optional[str], Optional[str]]:
    """Find ffprobe and ffmpeg executables"""
    ffprobe_command = ""
    ffmpeg_command = ""

    # Check bundled files first
    if os.path.isfile(resource_path("./ffprobe")):
        ffprobe_command = resource_path("./ffprobe")
    if os.path.isfile(resource_path("./ffmpeg")):
        ffmpeg_command = resource_path("./ffmpeg")
    if platform.system() == "Windows":
        ffprobe_command = resource_path("ffprobe.exe")
        ffmpeg_command = resource_path("ffmpeg.exe")

    # Fallback to system PATH
    if not ffprobe_command:
        ffprobe_command = which("ffprobe")
    if not ffmpeg_command:
        ffmpeg_command = which("ffmpeg")

    return ffprobe_command, ffmpeg_command


def validate_tools(ffprobe_command: Optional[str], ffmpeg_command: Optional[str]) -> None:
    """Validate that ffprobe and ffmpeg are found or exit with error"""
    missing_program = ""
    if not ffprobe_command:
        missing_program = "ffprobe"
    if not ffmpeg_command:
        missing_program = "ffmpeg"
    if missing_program:
        QMessageBox.critical(
            None,
            "Migaku Error Dialog",
            f"It seems {missing_program} is not installed. Please retry after installing",
            buttons=QMessageBox.Ok,
        )
        sys.exit(1)

    logging.info(f"ffprobe path: {ffprobe_command}")
    logging.info(f"ffmpeg path: {ffmpeg_command}")


def check_if_video_file(filename: str) -> bool:
    file_extension = Path(filename).suffix.lower()
    return file_extension in video_file_endings


def gather_files() -> tuple[SortedList[str], SortedList[str]]:
    """Get sorted lists of video files and subtitle files in current directory (special handling for Mac app bundle)"""
    current_dir_files = os.listdir(os.curdir)

    if (
        platform.system() == "Darwin"
        and getattr(sys, "frozen", False)
        and "Contents" in str(os.path.abspath(getattr(sys, "executable", os.curdir)))
    ):
        bundle_dir = Path(os.path.dirname(os.path.abspath(getattr(sys, "executable", os.curdir))))
        basepath = str(bundle_dir.parent.parent.parent.absolute())
        current_dir_files = os.listdir(basepath)
        current_dir_files = [os.path.join(basepath, file) for file in current_dir_files]

    video_files = SortedList(filter(check_if_video_file, current_dir_files))
    subtitle_files = SortedList(
        file for file in current_dir_files if Path(file).suffix.lower() in [".srt", ".ass", ".ssa"]
    )
    return video_files, subtitle_files


def warn_uneven_files(video_files: SortedList[str], subtitle_files: SortedList[str]) -> None:
    if len(video_files) != len(subtitle_files):
        QMessageBox.warning(
            None,
            "Migaku Warning Dialog",
            "There is an uneven amount of video files and subtitles in this folder.\n"
            "Please make sure there are as many subtitles as there are video files.",
            buttons=QMessageBox.Ok,
        )
        sys.exit(0)


def sync_subtitles(
    video_files: SortedList[str],
    subtitle_files: SortedList[str],
    ffmpeg_command: str,
) -> None:
    ffmpeg_parent_folder = Path(os.path.abspath(ffmpeg_command)).parent
    for subtitle, video in zip(subtitle_files, video_files):
        subtitle_filename = Path(subtitle)
        new_subtitle_name = subtitle_filename.with_suffix(".synced" + subtitle_filename.suffix)

        logging.debug(f"ffmpeg parent: {ffmpeg_parent_folder}")
        logging.debug(f"video: {video}")
        logging.debug(f"subtitle: {subtitle}")

        unparsed_args = [
            video,
            "-i",
            subtitle,
            "-o",
            str(new_subtitle_name),
            "--ffmpegpath",
            str(ffmpeg_parent_folder),
        ]

        print(unparsed_args)
        parser = make_parser()
        args = parser.parse_args(args=unparsed_args)
        run(args)


def ask_save_overwrite(subtitle_files: SortedList[str], override: bool = False) -> None:
    if override:
        overwrite = True
    else:
        launched_from_cli = sys.stdin.isatty()
        if launched_from_cli:
            print(
                'Would you like to override the original subtitles?\n\n'
                '[y] Save - Replaces each original subtitle with its synced counterpart\n'
                '[n] Close - Quit as-is without renaming subtitles further'
            )
            choice = input('Save synced subtitles over originals? [y/n]: ').strip().lower()
            overwrite = choice == 'y'
        else:
            question = QMessageBox.question(
                None,
                'Save without ".synced"',
                'Would you like to override the original subtitles?\n\n'
                'Save - Replaces each original subtitle with its synced counterpart\n'
                'Close - Quit as-is without renaming subtitles further',
                buttons=QMessageBox.Save | QMessageBox.Close,
            )
            overwrite = question == QMessageBox.Save

    if overwrite:
        for subtitle_file in subtitle_files:
            original_subtitle = Path(subtitle_file)
            synced_subtitle = original_subtitle.with_suffix(".synced" + original_subtitle.suffix)
            os.replace(synced_subtitle, original_subtitle)
            logging.info(f"Saving {synced_subtitle} as {original_subtitle}")
    else:
        print("Skipped replacing original subtitles. Synced versions are left untouched.")


def main():
    parser = argparse.ArgumentParser(
        description="Sync subtitles to video files using ffsubsync."
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help='Automatically override original subtitles with ".synced" versions without prompting.',
    )
    args = parser.parse_args()

    ffprobe_command, ffmpeg_command = find_ffmpeg_tools()
    validate_tools(ffprobe_command, ffmpeg_command)

    video_files, subtitle_files = gather_files()
    warn_uneven_files(video_files, subtitle_files)

    sync_subtitles(video_files, subtitle_files, ffmpeg_command)
    ask_save_overwrite(subtitle_files, override=args.override)


if __name__ == "__main__":
    main()
