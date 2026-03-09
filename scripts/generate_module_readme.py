#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

STOP_TITLE = "Contacto / Soporte"


@dataclass
class Section:
    title: str
    content: str


class SectionHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_section = False
        self._inside_h2 = False
        self._capturing = False
        self._current_title_parts: list[str] = []
        self._current_content_parts: list[str] = []
        self.sections: list[Section] = []
        self.stopped = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if self.stopped:
            return
        t = tag.lower()
        if t == "section":
            self._inside_section = True
            self._capturing = True
            self._current_title_parts = []
            self._current_content_parts = []
            self._inside_h2 = False
            return
        if not self._inside_section:
            return
        if t == "h2":
            self._inside_h2 = True
            return
        if t == "br":
            self._current_content_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.stopped:
            return
        t = tag.lower()
        if t == "h2" and self._inside_section:
            self._inside_h2 = False
            return
        if t == "section" and self._inside_section:
            title = normalize_text("".join(self._current_title_parts))
            if title == STOP_TITLE:
                self.stopped = True
                self._inside_section = False
                self._capturing = False
                return
            content = normalize_content("".join(self._current_content_parts))
            if not content:
                content = "—"
            if title:
                self.sections.append(Section(title=title, content=content))
            self._inside_section = False
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self.stopped or not self._inside_section or not self._capturing:
            return
        if self._inside_h2:
            self._current_title_parts.append(data)
        else:
            self._current_content_parts.append(data)



def normalize_title(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_content(value: str) -> str:
    parts = []
    for raw_line in value.split("\n"):
        cleaned = " ".join(raw_line.split()).strip()
        if cleaned:
            parts.append(cleaned)
    return "\n".join(parts).strip()


def normalize_text(value: str) -> str:
    return normalize_title(value)


def escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "\\n")



def module_dirs(repo_root: Path, selected_modules: Iterable[str] | None = None) -> list[Path]:
    modules = []
    selected = set(selected_modules or [])
    for path in sorted(repo_root.iterdir()):
        if not path.is_dir():
            continue
        if selected and path.name not in selected:
            continue
        if (path / "__manifest__.py").exists():
            modules.append(path)
    return modules



def parse_sections(index_html_path: Path) -> list[Section]:
    if not index_html_path.exists():
        return []
    parser = SectionHTMLParser()
    parser.feed(index_html_path.read_text(encoding="utf-8", errors="ignore"))
    parser.close()
    return parser.sections



def get_commit_rows(repo_root: Path, module_name: str, limit: int = 10) -> list[tuple[str, str, str]]:
    cmd = [
        "git",
        "log",
        f"-n{limit}",
        "--date=short",
        "--pretty=format:%ad%x09%h%x09%s",
        "--",
        module_name,
    ]
    result = subprocess.run(cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return []

    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        date, commit_hash, message = parts
        rows.append((date.strip(), commit_hash.strip(), normalize_text(message)))
    return rows



def build_readme(module_path: Path, sections: list[Section], commits: list[tuple[str, str, str]]) -> str:
    lines = [
        "",
        "",
        "## Documentación del módulo",
        "",
        "| Descripción del modulo | Contenido |",
        "|------------------------|-----------|",
    ]
    for section in sections:
        lines.append(f"| {escape_md_cell(section.title)} | {escape_md_cell(section.content)} |")

    lines.extend(
        [
            "",
            "## Historial del módulo",
            "",
            "## Commits recientes",
            "",
            "| Fecha de actualización | Commit | Descripción |",
            "|------------------------|--------|-------------|",
        ]
    )
    for date, commit_hash, description in commits:
        lines.append(
            f"| {escape_md_cell(date)} | {escape_md_cell(commit_hash)} | {escape_md_cell(description)} |"
        )

    lines.append("")
    return "\n".join(lines)



def main() -> int:
    parser = argparse.ArgumentParser(description="Generate README.md for Odoo modules")
    parser.add_argument("modules", nargs="*", help="Optional module names to process")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    for module_path in module_dirs(repo_root, args.modules):
        sections = parse_sections(module_path / "static" / "description" / "index.html")
        commits = get_commit_rows(repo_root, module_path.name)
        content = build_readme(module_path, sections, commits)
        (module_path / "README.md").write_text(content, encoding="utf-8")
        print(f"Generated {module_path.name}/README.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
