"""
timeline-extractor CLI entrypoint.

Usage:
    timeline-extractor extract <video> <lyrics> -o <out>
"""
import sys
from pathlib import Path

import click


@click.group()
def main() -> None:
    """Derive a lyric/subtitle timeline from a lyrics-only video."""


@main.command()
@click.argument("video", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("lyrics", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("-o", "--output", required=True, type=click.Path(dir_okay=False, path_type=Path), help="Output timeline JSON path")
def extract(video: Path, lyrics: Path, output: Path) -> None:
    """Extract a timeline from VIDEO using the ordered lyric lines in LYRICS."""
    click.echo(f"video:  {video}")
    click.echo(f"lyrics: {lyrics}")
    click.echo(f"output: {output}")
    click.echo("(change-detection pipeline not yet implemented)")
    sys.exit(0)
