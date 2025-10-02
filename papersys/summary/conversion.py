"""Utilities for converting LaTeX archives and PDFs into Markdown."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from loguru import logger

try:  # pragma: no cover - optional dependency guard
    from latex2json import TexReader  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    TexReader = None  # type: ignore[misc]


class MarkdownExtractionError(RuntimeError):
    """Raised when a source cannot be converted into Markdown."""


class JsonToMarkdownConverter:
    """Convert latex2json token streams into Markdown without global state."""

    def __init__(self) -> None:
        self._footnotes: list[str] = []
        self._footnote_counter: int = 0
        self._processed_titles: set[str] = set()

    def convert(
        self,
        json_data: Mapping[str, Any],
        *,
        ignore_reference: bool = True,
        clean_equations: bool = False,
    ) -> str:
        self._footnotes.clear()
        self._footnote_counter = 0
        self._processed_titles.clear()
        tokens = json_data.get("tokens", [])
        markdown = self._process_tokens(
            tokens,
            is_top_level=True,
            ignore_reference=ignore_reference,
            clean_equations=clean_equations,
        )
        if self._footnotes:
            markdown += "\n\n" + "\n".join(self._footnotes)
        return markdown

    # ------------------------------------------------------------------
    def _process_tokens(
        self,
        tokens: Iterable[Any],
        *,
        is_top_level: bool,
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        md_parts: list[str] = []
        for token in tokens:
            if not isinstance(token, Mapping):
                continue
            token_type = token.get("type")
            if token_type == "title":
                md_parts.append(self._process_title(token, ignore_reference, clean_equations))
            elif token_type == "author":
                md_parts.append(self._process_author(token))
            elif token_type == "abstract":
                md_parts.append(self._process_abstract(token, ignore_reference, clean_equations))
            elif token_type == "section":
                md_parts.append(self._process_section(token, ignore_reference, clean_equations))
            elif token_type == "paragraph":
                md_parts.append(
                    self._process_tokens(
                        token.get("content", []),
                        is_top_level=False,
                        ignore_reference=ignore_reference,
                        clean_equations=clean_equations,
                    )
                    + "\n\n"
                )
            elif token_type == "list":
                md_parts.append(self._process_list(token, ignore_reference, clean_equations))
            elif token_type == "figure":
                md_parts.append(self._process_figure(token, ignore_reference, clean_equations))
            elif token_type == "table":
                md_parts.append(self._process_table(token, ignore_reference, clean_equations))
            elif token_type == "equation":
                md_parts.append(self._process_equation(token, clean_equations))
            elif token_type == "citation":
                if not ignore_reference:
                    md_parts.append(self._process_citation(token))
            elif token_type == "footnote":
                md_parts.append(self._process_footnote(token, ignore_reference, clean_equations))
            elif token_type == "bibliography" and not ignore_reference:
                md_parts.append(self._process_bibliography(token, ignore_reference, clean_equations))
            elif token_type in {"document", "group"}:
                md_parts.append(
                    self._process_tokens(
                        token.get("content", []),
                        is_top_level=False,
                        ignore_reference=ignore_reference,
                        clean_equations=clean_equations,
                    )
                )
            elif token_type == "text":
                if not is_top_level:
                    md_parts.append(self._process_text(token))
            elif token_type == "ref":
                content = token.get("content", [""])
                if content:
                    md_parts.append(f"[{content[0]}]")
            elif token_type == "math_env":
                md_parts.append(self._process_math_env(token, ignore_reference, clean_equations))
            else:
                md_parts.append(f"<!-- Unknown token type: {token_type} -->")
        return "".join(md_parts)

    # Individual token handlers ------------------------------------------------
    def _process_title(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        content = self._process_content(token.get("content", []), ignore_reference, clean_equations)
        if not content or content in self._processed_titles:
            return ""
        self._processed_titles.add(content)
        return f"# {content}\n"

    def _process_author(self, token: Mapping[str, Any]) -> str:
        md_parts: list[str] = []
        current_author: list[str] = []
        current_superscripts: list[str] = []
        for group in token.get("content", []):
            items = group if isinstance(group, Iterable) and not isinstance(group, (str, bytes)) else [group]
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                if item.get("type") == "text":
                    text = str(item.get("content", "")).strip()
                    if not text or text in {",", ";"}:
                        continue
                    styles = item.get("styles", [])
                    if "superscript" in styles:
                        current_superscripts.append(text)
                    else:
                        if current_superscripts:
                            current_author.append(f"<sup>{','.join(current_superscripts)}</sup>")
                            current_superscripts = []
                        current_author.append(f"<b>{text}</b>")
                elif item.get("type") == "url":
                    title = self._process_content(item.get("title", []), ignore_reference=False)
                    current_author.append(f"[{title}]({item.get('content', '')})")
            if current_author or current_superscripts:
                if current_superscripts:
                    current_author.append(f"<sup>{','.join(current_superscripts)}</sup>")
                md_parts.append("".join(current_author))
                current_author = []
                current_superscripts = []
        return "## Authors\n" + ", ".join(md_parts) + "\n" if md_parts else ""

    def _process_abstract(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        content = self._process_content(token.get("content", []), ignore_reference, clean_equations)
        return "## Abstract\n" + content + "\n" if content else ""

    def _process_section(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        level = int(token.get("level", 1))
        numbering = token.get("numbering", "")
        title = self._process_content(token.get("title", []), ignore_reference, clean_equations)
        if numbering:
            title = f"{numbering}. {title}"
        content = self._process_tokens(
            token.get("content", []),
            is_top_level=False,
            ignore_reference=ignore_reference,
            clean_equations=clean_equations,
        )
        return f"{'#' * (level + 1)} {title}\n{content}\n" if title or content else ""

    def _process_list(self, token: Mapping[str, Any], ignore_reference: bool, clean_equations: bool) -> str:
        items: list[str] = []
        for item in token.get("content", []):
            if not isinstance(item, Mapping):
                continue
            item_content = self._process_tokens(
                item.get("content", []),
                is_top_level=False,
                ignore_reference=ignore_reference,
                clean_equations=clean_equations,
            )
            if token.get("name") == "enumerate":
                items.append(f"{token.get('depth', 0) * '  '}1. {item_content}")
            else:
                items.append(f"{token.get('depth', 0) * '  '}- {item_content}")
        return "\n".join(items) + "\n" if items else ""

    def _process_figure(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        caption = ""
        for item in token.get("content", []):
            if isinstance(item, Mapping) and item.get("type") == "caption":
                caption = self._process_content(
                    item.get("content", []),
                    ignore_reference=False,
                    clean_equations=clean_equations,
                )
                break
        numbering = token.get("numbering", "")
        return f"[Figure {numbering}]: {caption}\n" if caption else ""

    def _process_table(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        caption = ""
        content = token.get("content", [])
        for item in content:
            if isinstance(item, Mapping) and item.get("type") == "caption":
                caption = self._process_content(item.get("content", []), ignore_reference, clean_equations)
                break
        numbering = token.get("numbering", "")
        if not content:
            return ""
        first = content[0]
        tabular = first.get("tabular") if isinstance(first, Mapping) else None
        if not tabular:
            return (
                f"[Table {numbering}]: {caption}\nFollowing table is represented in JSON:\n````json\n"
                f"{json.dumps(token, separators=(',', ':'), ensure_ascii=False)}\n````\n"
            )
        rows: list[str] = []
        for row in tabular:
            row_cells: list[str] = []
            for cell in row:
                if cell is None:
                    row_cells.append("")
                elif isinstance(cell, Mapping):
                    row_cells.append(
                        self._process_content(
                            cell.get("content", []),
                            ignore_reference,
                            clean_equations,
                        )
                    )
                elif isinstance(cell, list):
                    row_cells.append(
                        self._process_tokens(
                            cell,
                            is_top_level=False,
                            ignore_reference=ignore_reference,
                            clean_equations=clean_equations,
                        )
                    )
                else:
                    row_cells.append(str(cell))
            rows.append("| " + " | ".join(row_cells) + " |")
        if not rows:
            return ""
        if len(rows) > 1:
            header_separator = "|-" + "-|-".join("-" for _ in rows[0].split("|")[1:-1]) + "-|"
            table_md = "\n".join([rows[0], header_separator] + rows[1:])
        else:
            table_md = rows[0]
        return f"[Table {numbering}]: {caption}\n{table_md}\n"

    def _process_equation(self, token: Mapping[str, Any], clean_equations: bool) -> str:
        content = str(token.get("content", "")).strip()
        if clean_equations:
            content = json.dumps(content)[1:-1]
        if token.get("display") == "block":
            return f"$$ {content} $$\n"
        return f"${content}$"

    def _process_citation(self, token: Mapping[str, Any]) -> str:
        content = token.get("content", [])
        title = self._process_content(token.get("title", []), ignore_reference=False)
        joined = ", ".join(str(part) for part in content if str(part).strip())
        if title:
            return f"[{joined}, {title}]"
        return f"[{joined}]"

    def _process_footnote(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        self._footnote_counter += 1
        content = self._process_tokens(
            token.get("content", []),
            is_top_level=False,
            ignore_reference=ignore_reference,
            clean_equations=clean_equations,
        )
        self._footnotes.append(f"[^{self._footnote_counter}]: {content}")
        return f"[^{self._footnote_counter}]"

    def _process_bibliography(
        self,
        token: Mapping[str, Any],
        ignore_reference: bool,
        clean_equations: bool,
    ) -> str:
        items: list[str] = []
        for entry in token.get("content", []):
            if not isinstance(entry, Mapping):
                continue
            cite_key = entry.get("cite_key", "")
            content = self._process_content(entry.get("content", []), ignore_reference, clean_equations)
            items.append(f"[{cite_key}]: {content}")
        return "## References\n" + "\n".join(items) + "\n" if items else ""

    def _process_text(self, token: Mapping[str, Any]) -> str:
        text = str(token.get("content", ""))
        styles = token.get("styles", [])
        if "bold" in styles and "italic" in styles:
            return f"<b><i>{text}</i></b>"
        if "bold" in styles:
            return f"<b>{text}</b>"
        if "italic" in styles:
            return f"<i>{text}</i>"
        return text

    def _process_math_env(self, token: Mapping[str, Any], ignore_reference: bool, clean_equations: bool) -> str:
        content = token.get("content", "")
        if isinstance(content, list):
            content = self._process_content(content, ignore_reference, clean_equations)
        content = str(content).strip()
        if not content:
            return ""
        if content.startswith("\\begin{"):
            return f"$$ {content} $$\n"
        if clean_equations:
            content = content.replace("$$", "").replace("$", "")
        return f"{content}\n"

    def _process_content(
        self,
        content: Any,
        ignore_reference: bool,
        clean_equations: bool = False,
    ) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, Iterable):
            return self._process_tokens(
                content,
                is_top_level=False,
                ignore_reference=ignore_reference,
                clean_equations=clean_equations,
            )
        return ""


class LatexToMarkdownConverter:
    """Run latex2json and convert the output to Markdown."""

    def __init__(self) -> None:
        if TexReader is None:  # pragma: no cover - guarded by optional dependency
            raise MarkdownExtractionError("latex2json is not available")
        self._reader = TexReader()
        self._silence_logging()
        self._json_converter = JsonToMarkdownConverter()

    def convert(self, archive_path: Path) -> str:
        try:
            logger.debug("Processing LaTeX archive %s via latex2json", archive_path)
            result = self._reader.process(str(archive_path), cleanup=False)
            json_output = self._reader.to_json(result, merge_inline_tokens=True)
        except Exception as exc:  # noqa: BLE001
            raise MarkdownExtractionError(f"latex2json failed: {exc}") from exc
        try:
            structured = json.loads(json_output)
        except json.JSONDecodeError as exc:  # pragma: no cover - unlikely but guarded
            raise MarkdownExtractionError(f"Invalid JSON output from latex2json: {exc}") from exc
        markdown = self._json_converter.convert(structured, ignore_reference=True)
        if not markdown.strip():
            raise MarkdownExtractionError("Empty Markdown generated from LaTeX")
        return markdown

    def _silence_logging(self) -> None:
        noisy_loggers = (
            "latex2json",
            "latex2json.tex_reader",
            "latex2json.parser",
            "tex_reader",
            "chardet",
            "chardet.charsetgroupprober",
            "chardet.universaldetector",
            "charset_normalizer",
        )
        for name in noisy_loggers:
            logging.getLogger(name).setLevel(logging.ERROR)


class MarkerMarkdownConverter:
    """Use marker-pdf CLI to convert PDFs into Markdown."""

    def __init__(
        self,
        *,
        timeout: int = 180,
        executable: str = "marker",
    ) -> None:
        self._timeout = timeout
        self._executable = executable

    def convert(self, pdf_path: Path, paper_id: str) -> str:
        if shutil.which(self._executable) is None:
            raise MarkdownExtractionError("marker executable not found in PATH")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            pdf_dir = tmp_root / "pdf"
            output_dir = tmp_root / "output"
            pdf_dir.mkdir()
            output_dir.mkdir()
            target_pdf = pdf_dir / f"{paper_id}.pdf"
            shutil.copy(pdf_path, target_pdf)
            command = [
                self._executable,
                str(pdf_dir),
                "--disable_image_extraction",
                "--output_dir",
                str(output_dir),
            ]
            logger.debug("Running marker for %s", paper_id)
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise MarkdownExtractionError(f"marker timed out ({self._timeout}s)") from exc
            if result.returncode != 0:
                stderr = result.stderr.strip() or "unknown error"
                raise MarkdownExtractionError(f"marker failed: {stderr}")
            marker_dir = output_dir / paper_id
            md_path = marker_dir / f"{paper_id}.md"
            if not md_path.exists():
                raise MarkdownExtractionError("marker output Markdown not found")
            markdown = md_path.read_text(encoding="utf-8")
            if not markdown.strip():
                raise MarkdownExtractionError("marker produced empty Markdown")
            return markdown


__all__ = [
    "JsonToMarkdownConverter",
    "LatexToMarkdownConverter",
    "MarkdownExtractionError",
    "MarkerMarkdownConverter",
]
