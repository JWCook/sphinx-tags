"""Sphinx extension to create tags for documentation pages.

"""
import os
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Optional

from docutils import nodes
from sphinx.util.docutils import SphinxDirective
from sphinx.util.logging import getLogger

__version__ = "0.3.0"

logger = getLogger("sphinx-tags")


class TagLinks(SphinxDirective):
    """Custom directive for adding tags to Sphinx-generated files.

    Loosely based on https://stackoverflow.com/questions/18146107/how-to-add-blog-style-tags-in-restructuredtext-with-sphinx

    See also https://docutils.sourceforge.io/docs/howto/rst-directives.html

    """

    # Sphinx directive class attributes
    required_arguments = 1
    optional_arguments = 200  # Arbitrary.
    has_content = False

    # Custom attributes
    separator = ","

    def run(self):
        tags = [arg.replace(self.separator, "") for arg in self.arguments]
        result = nodes.paragraph()
        result["classes"] = ["tags"]
        result += nodes.inline(text=f"{self.env.app.config.tags_intro_text} ")
        count = 0

        for tag in tags:
            count += 1
            # We want the link to be the path to the _tags folder, relative to this document's path
            # where
            #
            #  - self.env.app.config.tags_output_dir
            # |
            #  - subfolder
            #   |
            #    - current_doc_path
            if self.env.app.config.tags_create_badges:
                result += self._get_badge_node(tag)
                tag_separator = " "
            else:
                result += self._get_plaintext_node(tag)
                tag_separator = f"{self.separator} "
            if not count == len(tags):
                result += nodes.inline(text=tag_separator)
        return [result]

    def _get_plaintext_node(self, tag: str) -> List[nodes.Node]:
        """Get a plaintext reference link for the given tag"""
        docpath = Path(self.env.doc2path(self.env.docname)).parent
        rootdir = os.path.relpath(
            os.path.join(self.env.app.srcdir, self.env.app.config.tags_output_dir),
            docpath,
        )
        link = os.path.join(rootdir, f"{tag}.html")
        return nodes.reference(refuri=link, text=tag)

    def _get_badge_node(self, tag: str) -> List[nodes.Node]:
        """Get a sphinx-design reference badge for the given tag"""
        from sphinx_design.badges_buttons import XRefBadgeRole

        tag_color = self._get_tag_color(tag)
        tag_badge = XRefBadgeRole(tag_color)
        tag_ref = f'{tag} <tags/{tag}>'
        return tag_badge(
            f'bdg-ref-{tag_color}',
            tag,
            tag_ref,
            self.lineno,
            self.state.inliner,
        )[0]

    def _get_tag_color(self, tag: str) -> Optional[str]:
        """Check for a matching user-defined color for a given tag.
        Defaults to ``None`` for no plain uncolored badge.
        """
        tag_colors = self.env.app.config.tags_badge_colors or {}
        for pattern, color in tag_colors.items():
            if fnmatch(tag, pattern):
                return color
        return None


class Tag:
    """A tag contains entries"""

    def __init__(self, name):
        self.name = name
        self.items = []

    def create_file(
        self,
        items,
        tags_output_dir,
        srcdir,
        tags_page_title,
        tags_page_header,
    ):
        """Create file with list of documents associated with a given tag in
        toctree format.

        This file is reached as a link from the tag name in each documentation
        file, or from the tag overview page.

        If we are using md files, generate and md file; otherwise, go with rst.

        Parameters
        ----------

        tags_output_dir : Path
            path where the file for this tag will be created
        items : list
            list of files associated with this tag (instance of Entry)
        srcdir : str
            root folder for the documentation (usually, project/docs)
        tags_page_title: str
            the title of the tag page, after which the tag is listed (e.g. "Tag: programming")
        tags_page_header: str
            the words after which the pages with the tag are listed, e.g. "With this tag: Hello World")
        tag_intro_text: str
            the words after which the tags of a given page are listed, e.g. "Tags: programming, python")


        """
        content = []
        filename = f"{self.name}.md"
        content.append(f"# {tags_page_title}: {self.name}")
        content.append("")
        content.append("```{toctree}")
        content.append("---")
        content.append("maxdepth: 1")
        content.append(f"caption: {tags_page_header}")
        content.append("---")
        #  items is a list of files associated with this tag
        for item in items:
            # We want here the filepath relative to /docs/_tags
            relpath = item.filepath.relative_to(srcdir)
            content.append(f"../{relpath}")
        content.append("```")
        content.append("")
        with open(
            os.path.join(srcdir, tags_output_dir, filename), "w", encoding="utf8"
        ) as f:
            f.write("\n".join(content))


class Entry:
    """Extracted info from source file (*.rst/*.md)"""

    def __init__(self, entrypath):
        self.filepath = entrypath
        tagstart = "```{tags}"
        tagend = "```"

        with open(self.filepath, "r", encoding="utf8") as f:
            self.lines = f.read().split("\n")
        tagline = [line for line in self.lines if tagstart in line]
        self.tags = []
        if tagline:
            tagline = tagline[0].replace(tagstart, "").rstrip(tagend)
            self.tags = tagline.split(",")
            self.tags = [tag.strip() for tag in self.tags]

    def assign_to_tags(self, tag_dict):
        """Append ourself to tags"""
        for tag in self.tags:
            if tag not in tag_dict:
                tag_dict[tag] = Tag(tag)
            tag_dict[tag].items.append(self)


def tagpage(tags, outdir, title, tags_index_head):
    """Creates Tag overview page.

    This page contains a list of all available tags.

    """
    tags = list(tags.values())

    content = []
    content.append("(tagoverview)=")
    content.append("")
    content.append(f"# {title}")
    content.append("")
    # toctree for this page
    content.append("```{toctree}")
    content.append("---")
    content.append(f"caption: {tags_index_head}")
    content.append("maxdepth: 1")
    content.append("---")
    for tag in sorted(tags, key=lambda t: t.name):
        content.append(f"{tag.name} ({len(tag.items)}) <{tag.name}>")
    content.append("```")
    content.append("")
    filename = os.path.join(outdir, "tagsindex.md")

    with open(filename, "w", encoding="utf8") as f:
        f.write("\n".join(content))


def assign_entries(app):
    """Assign all found entries to their tag."""
    pages = []
    tags = {}

    for entrypath in Path(app.srcdir).rglob("*.md"):
        entry = Entry(entrypath)
        entry.assign_to_tags(tags)
        pages.append(entry)
    return tags, pages


def update_tags(app):
    """Update tags according to pages found"""
    if app.config.tags_create_tags:

        tags_output_dir = Path(app.config.tags_output_dir)

        if not os.path.exists(os.path.join(app.srcdir, tags_output_dir)):
            os.makedirs(os.path.join(app.srcdir, tags_output_dir))

        for file in os.listdir(os.path.join(app.srcdir, tags_output_dir)):
            if file.endswith("md") or file.endswith("rst"):
                os.remove(os.path.join(app.srcdir, tags_output_dir, file))

        # Create pages for each tag
        tags, pages = assign_entries(app)
        for tag in tags.values():
            tag.create_file(
                [item for item in pages if tag.name in item.tags],
                tags_output_dir,
                app.srcdir,
                app.config.tags_page_title,
                app.config.tags_page_header,
            )
        # Create tags overview page
        tagpage(
            tags,
            os.path.join(app.srcdir, tags_output_dir),
            app.config.tags_overview_title,
            app.config.tags_index_head,
        )
        logger.info("Tags updated", color="white")
    else:
        logger.info(
            "Tags were not created (tags_create_tags=False in conf.py)", color="white"
        )


def setup(app):
    """Setup for Sphinx."""

    # Create config keys (with default values)
    # These values will be updated after config-inited

    app.add_config_value("tags_create_tags", False, "html")
    app.add_config_value("tags_output_dir", "_tags", "html")
    app.add_config_value("tags_overview_title", "Tags overview", "html")
    app.add_config_value("tags_intro_text", "Tags:", "html")
    app.add_config_value("tags_page_title", "My tags", "html")
    app.add_config_value("tags_page_header", "With this tag", "html")
    app.add_config_value("tags_index_head", "Tags", "html")
    app.add_config_value("tags_create_badges", False, "html")
    app.add_config_value("tags_badge_colors", {}, "html")

    # internal config values
    app.add_config_value(
        "remove_from_toctrees",
        [app.config.tags_output_dir],
        "html",
    )

    # Update tags
    # TODO: tags should be updated after sphinx-gallery is generated, and the
    # gallery is also connected to builder-inited. Are there situations when
    # this will not work?
    app.connect("builder-inited", update_tags)
    app.add_directive("tags", TagLinks)

    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
