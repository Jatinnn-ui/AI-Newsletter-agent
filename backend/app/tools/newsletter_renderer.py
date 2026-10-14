"""Tool 3: Newsletter rendering, validation and saving.

The HTML is an email-friendly, self-contained document: table layout, inline
CSS, no JavaScript, no remote assets. Every piece of text is HTML-escaped and
every link is checked to be http(s), so nothing from external sources can
inject markup.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, Field

from app.models.domain import NewsletterDraft, NewsletterSection, SavedOutput
from app.storage.base import NewsletterStorage

# ---------------------------------------------------------------------------
# Escaping helpers
# ---------------------------------------------------------------------------

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def esc(text: str | None) -> str:
    """Escape untrusted text for HTML element content and attribute values."""
    return html.escape(_CTRL.sub("", text or ""), quote=True)


def safe_href(url: str | None) -> str | None:
    """Return an escaped http(s) URL, or None if the URL is unsafe/invalid."""
    if not url:
        return None
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None
    if any(ch in url for ch in ('"', "<", ">", " ", "\n", "\r", "\t", "`")):
        url = quote(url, safe=":/?#[]@!$&'()*+,;=%-._~")
    return html.escape(url, quote=True)


def format_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return None
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def date_label(section: NewsletterSection) -> str:
    formatted = format_date(section.published_date)
    if not formatted:
        return "Publication date unavailable"
    source = {"page_metadata": "per article metadata", "search_api": "per search API"}.get(
        section.date_source or "", "unverified"
    )
    return f"Published {formatted} ({source})"


def basis_label(section: NewsletterSection) -> str:
    if section.content_basis == "full_text":
        return "Summary based on retrieved article text."
    return "Summary based on the search snippet only; the full article was not retrieved."


def generated_label(draft: NewsletterDraft) -> str:
    try:
        dt = datetime.fromisoformat(draft.generated_at)
        return dt.strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return draft.generated_at[:10]


PREVIEW_NOTICE = (
    "Generated preview. Delivery is simulated: this newsletter was saved to a file and was not sent to any subscriber."
)
TEST_DATA_NOTICE = "TEST DATA: this newsletter was generated from fictional fixture articles in deterministic test mode."

# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_SERIF = "Georgia,'Times New Roman',Times,serif"


def _section_html(index: int, section: NewsletterSection) -> str:
    href = safe_href(section.source_url)
    headline = esc(section.headline)
    headline_html = (
        f'<a href="{href}" target="_blank" rel="noopener noreferrer" '
        f'style="color:#0f1f3d;text-decoration:none;">{headline}</a>'
        if href
        else headline
    )
    facts = ""
    if section.key_facts:
        items = "".join(
            f'<li style="margin:0 0 4px 0;">{esc(f)}</li>' for f in section.key_facts[:4]
        )
        facts = (
            '<p style="margin:12px 0 4px 0;font-size:12px;font-weight:600;color:#475569;'
            'text-transform:uppercase;letter-spacing:0.04em;">Reported facts</p>'
            f'<ul style="margin:0 0 0 18px;padding:0;font-size:14px;line-height:1.5;color:#334155;font-family:{_FONT};">{items}</ul>'
        )
    source_link = (
        f'<a href="{href}" target="_blank" rel="noopener noreferrer" '
        f'style="color:#1d3fa8;text-decoration:underline;">Read the original at {esc(section.publisher)}</a>'
        if href
        else '<span style="color:#b91c1c;">Source link unavailable</span>'
    )
    return f"""
          <tr>
            <td class="story" style="padding:24px 32px;border-top:1px solid #e2dccf;">
              <p style="margin:0 0 6px 0;font-size:12px;color:#64748b;font-family:{_FONT};">
                <span style="font-weight:600;color:#1d3fa8;">{index:02d}</span>
                &nbsp;·&nbsp; {esc(section.publisher)} &nbsp;·&nbsp; {esc(date_label(section))}
              </p>
              <h2 style="margin:0 0 10px 0;font-size:19px;line-height:1.35;font-weight:600;color:#13213a;font-family:{_SERIF};">{headline_html}</h2>
              <p style="margin:0;font-size:15px;line-height:1.6;color:#1e293b;font-family:{_FONT};">{esc(section.summary)}</p>
              {facts}
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:14px 0 0 0;">
                <tr>
                  <td style="background:#f3f1eb;border-left:3px solid #1d3fa8;padding:10px 14px;font-family:{_FONT};">
                    <p style="margin:0 0 2px 0;font-size:12px;font-weight:600;color:#1d3fa8;text-transform:uppercase;letter-spacing:0.04em;">Why it matters</p>
                    <p style="margin:0;font-size:14px;line-height:1.55;color:#1e293b;">{esc(section.why_it_matters)}</p>
                  </td>
                </tr>
              </table>
              <p style="margin:12px 0 0 0;font-size:13px;font-family:{_FONT};">{source_link}</p>
              <p style="margin:4px 0 0 0;font-size:11px;color:#94a3b8;font-family:{_FONT};">{esc(basis_label(section))}</p>
            </td>
          </tr>"""


def render_html(draft: NewsletterDraft) -> str:
    sections = "".join(_section_html(i + 1, s) for i, s in enumerate(draft.sections))
    test_banner = (
        f"""
          <tr>
            <td style="padding:10px 32px;background:#fff7ed;color:#9a3412;font-size:13px;font-weight:600;font-family:{_FONT};">{esc(TEST_DATA_NOTICE)}</td>
          </tr>"""
        if draft.is_test_data
        else ""
    )
    limitations = ""
    if draft.limitations:
        items = "".join(f'<li style="margin:0 0 4px 0;">{esc(x)}</li>' for x in draft.limitations)
        limitations = f"""
          <tr>
            <td style="padding:16px 32px;border-top:1px solid #e2dccf;font-family:{_FONT};">
              <p style="margin:0 0 6px 0;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.04em;">Editorial notes</p>
              <ul style="margin:0 0 0 18px;padding:0;font-size:13px;line-height:1.5;color:#475569;">{items}</ul>
            </td>
          </tr>"""
    count = len(draft.sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="generator" content="Newsletter Agent">
<title>{esc(draft.subject)}</title>
<style>
  @media only screen and (max-width: 620px) {{
    .container {{ width: 100% !important; }}
    .story, .pad {{ padding-left: 18px !important; padding-right: 18px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#f6f3ec;font-family:{_FONT};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#f6f3ec;">{esc(draft.preheader)}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f6f3ec;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" class="container" width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px;max-width:640px;background:#ffffff;border:1px solid #e2dccf;border-radius:10px;">
          <tr>
            <td style="padding:10px 32px;background:#efeadf;color:#3a465c;font-size:12px;font-family:{_FONT};border-radius:10px 10px 0 0;">{esc(PREVIEW_NOTICE)}</td>
          </tr>{test_banner}
          <tr>
            <td class="pad" style="padding:28px 32px 8px 32px;font-family:{_FONT};">
              <p style="margin:0 0 8px 0;font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#64748b;">{esc(generated_label(draft))} &nbsp;·&nbsp; {count} {"story" if count == 1 else "stories"}</p>
              <h1 style="margin:0 0 14px 0;font-size:30px;line-height:1.2;font-weight:600;color:#13213a;font-family:{_SERIF};">{esc(draft.title)}</h1>
              <p style="margin:0 0 20px 0;font-size:15px;line-height:1.65;color:#334155;">{esc(draft.intro)}</p>
            </td>
          </tr>{sections}{limitations}
          <tr>
            <td class="pad" style="padding:24px 32px;border-top:1px solid #e2dccf;font-family:{_FONT};">
              <p style="margin:0;font-size:15px;line-height:1.65;color:#334155;">{esc(draft.closing)}</p>
            </td>
          </tr>
          <tr>
            <td class="pad" style="padding:16px 32px 24px 32px;border-top:1px solid #e2dccf;font-size:12px;line-height:1.5;color:#94a3b8;font-family:{_FONT};">
              Generated by Newsletter Agent on {esc(generated_label(draft))}. Summaries were written by an AI model from the linked sources; follow the links for full reporting.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>#|])")


def md_escape(text: str | None) -> str:
    return _MD_SPECIAL.sub(r"\\\1", _CTRL.sub("", text or "")).strip()


def md_url(url: str) -> str:
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("<", "%3C").replace(">", "%3E")


def render_markdown(draft: NewsletterDraft) -> str:
    lines = [
        f"# {md_escape(draft.title)}",
        "",
        f"**Subject:** {md_escape(draft.subject)}  ",
        f"**Preheader:** {md_escape(draft.preheader)}  ",
        f"**Generated:** {generated_label(draft)} · {len(draft.sections)} stories",
        "",
        f"> {PREVIEW_NOTICE}",
    ]
    if draft.is_test_data:
        lines += [">", f"> **{TEST_DATA_NOTICE}**"]
    lines += ["", md_escape(draft.intro), ""]
    for i, s in enumerate(draft.sections, start=1):
        lines += ["---", "", f"## {i}. {md_escape(s.headline)}", ""]
        lines.append(f"*{md_escape(s.publisher)} · {date_label(s)}*")
        lines += ["", md_escape(s.summary), ""]
        if s.key_facts:
            lines.append("**Reported facts**")
            lines.append("")
            lines += [f"- {md_escape(f)}" for f in s.key_facts[:4]]
            lines.append("")
        lines += [f"**Why it matters:** {md_escape(s.why_it_matters)}", ""]
        href = s.source_url if safe_href(s.source_url) else None
        lines.append(
            f"Source: [{md_escape(s.publisher)}]({md_url(href)})" if href else "Source: link unavailable"
        )
        lines += ["", f"<sub>{basis_label(s)}</sub>", ""]
    if draft.limitations:
        lines += ["---", "", "### Editorial notes", ""]
        lines += [f"- {md_escape(x)}" for x in draft.limitations]
        lines.append("")
    lines += ["---", "", md_escape(draft.closing), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_FORBIDDEN = {"script", "iframe", "object", "embed", "form", "frame", "frameset", "applet", "base"}


class HtmlValidation(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class _Validator(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.links: list[str] = []
        self.seen: set[str] = set()
        self.doctype = False

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype html"):
            self.doctype = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.seen.add(tag)
        if tag in _FORBIDDEN:
            self.errors.append(f"Forbidden element <{tag}>.")
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.errors.append(f"Event handler attribute '{name}' is not allowed.")
            if name in ("href", "src") and value is not None:
                scheme = urlsplit(value.strip()).scheme.lower()
                if name == "src":
                    self.errors.append("Remote or embedded resources (src) are not allowed.")
                elif scheme not in ("http", "https"):
                    self.errors.append(f"Unsafe link scheme: {value[:60]}")
                else:
                    self.links.append(value)
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.seen.add(tag)
        if tag not in _VOID:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if not self.stack:
            self.errors.append(f"Unexpected closing tag </{tag}>.")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                unclosed = self.stack.pop()
                if unclosed not in {"p", "li", "td", "tr"}:
                    self.errors.append(f"Unclosed <{unclosed}> before </{tag}>.")
            self.stack.pop()
        else:
            self.errors.append(f"Closing tag </{tag}> without matching opening tag.")


def validate_html(document: str, expected_urls: list[str] | None = None) -> HtmlValidation:
    validator = _Validator()
    try:
        validator.feed(document or "")
        validator.close()
    except Exception as exc:  # pragma: no cover - HTMLParser is lenient
        return HtmlValidation(valid=False, errors=[f"HTML could not be parsed: {exc}"])
    errors = list(validator.errors)
    warnings: list[str] = []
    if not validator.doctype:
        errors.append("Missing <!DOCTYPE html> declaration.")
    for required in ("html", "head", "title", "body"):
        if required not in validator.seen:
            errors.append(f"Missing <{required}> element.")
    if validator.stack:
        errors.append(f"Unclosed elements at end of document: {', '.join(validator.stack[:5])}.")
    if expected_urls:
        unescaped = {html.unescape(link) for link in validator.links}
        for url in expected_urls:
            if url not in unescaped and html.unescape(safe_href(url) or "") not in unescaped:
                errors.append(f"Source link missing from HTML: {url[:80]}")
    if len(document or "") > 400_000:
        warnings.append("HTML is unusually large for an email (>400 KB).")
    return HtmlValidation(valid=not errors, errors=errors, warnings=warnings, links=validator.links)


# ---------------------------------------------------------------------------
# Render + save
# ---------------------------------------------------------------------------


class RenderedNewsletter(BaseModel):
    html: str
    markdown: str
    validation: HtmlValidation


def render_newsletter(draft: NewsletterDraft) -> RenderedNewsletter:
    document = render_html(draft)
    validation = validate_html(document, [s.source_url for s in draft.sections if safe_href(s.source_url)])
    return RenderedNewsletter(html=document, markdown=render_markdown(draft), validation=validation)


def save_newsletter(
    rendered: RenderedNewsletter, *, run_id: str, title: str, storage: NewsletterStorage
) -> SavedOutput:
    """Validate then persist both formats. Raises ValueError if the HTML is invalid."""
    if not rendered.validation.valid:
        raise ValueError("Refusing to save invalid HTML: " + "; ".join(rendered.validation.errors[:3]))
    return storage.save(run_id=run_id, title=title, html=rendered.html, markdown=rendered.markdown)
