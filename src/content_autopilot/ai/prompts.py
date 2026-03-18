"""Jinja2-based prompt template loader."""

from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

log = structlog.get_logger()

_DEFAULT_TEMPLATES_DIR = "config/personas/prompts"


class PromptLoader:
    """Load and render Jinja2 prompt templates from a directory."""

    def __init__(self, templates_dir: str = _DEFAULT_TEMPLATES_DIR) -> None:
        self._templates_dir = Path(templates_dir)
        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        log.debug("prompt_loader_init", templates_dir=str(self._templates_dir))

    def render(self, template_name: str, **kwargs: object) -> str:
        """Render a template by name with provided variables.

        Args:
            template_name: Filename relative to templates_dir (e.g. "summarize.txt").
            **kwargs: Variables passed into the template context.

        Returns:
            Rendered string.

        Raises:
            TemplateNotFound: If the template file does not exist.
        """
        try:
            template = self._env.get_template(template_name)
        except TemplateNotFound:
            log.error("prompt_template_not_found", template=template_name)
            raise
        rendered = template.render(**kwargs)
        log.debug("prompt_rendered", template=template_name, length=len(rendered))
        return rendered

    def load_summarize_prompt(
        self,
        source_content: str,
        source_url: str,
        source_title: str,
    ) -> str:
        """Render the summarize.txt template."""
        return self.render(
            "summarize.txt",
            source_content=source_content,
            source_url=source_url,
            source_title=source_title,
        )

    def load_humanize_prompt(
        self,
        summary_ko: str,
        source_url: str,
        source_title: str,
        persona_config: dict,
    ) -> str:
        """Render the humanize.txt template."""
        return self.render(
            "humanize.txt",
            summary_ko=summary_ko,
            source_url=source_url,
            source_title=source_title,
            persona_config=persona_config,
        )
