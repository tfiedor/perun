from docutils import nodes

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Perun documentation build configuration file, created by
# sphinx-quickstart on Mon Oct 16 20:46:06 2017.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.mathjax', 'sphinx.ext.viewcode',
              'sphinx.ext.todo', 'sphinx.ext.intersphinx', 'sphinx_click.ext']

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# source_suffix = ['.rst', '.md']
source_suffix = '.rst'

# The master toctree document.
master_doc = 'index'

# General information about the project.
project = 'Perun'
copyright = '2017, Tomas Fiedor, Jiri Pavela, Simon Stupinsky, et al.'
author = 'Tomas Fiedor, Jiri Pavela, Simon Stupinsky, et al.'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
version = '0.15.3'
# The full version, including alpha/beta/rc tags.
release = '0.15.3'

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = None

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = 'alabaster'
html_style = "perun.css"

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
html_theme_options = {
    'show_related': True
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# This is required for the alabaster theme
# refs: http://alabaster.readthedocs.io/en/latest/installation.html#sidebars
html_sidebars = {
    'index': [
        'about.html', 'sourcelink.html', 'searchbox.html'
    ],
    '**': [
        'logo.html',
        'localtoc.html',
        'relations.html',  # needs 'show_related': True theme option to display
        'sourcelink.html',
        'searchbox.html',
    ]
}


# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = 'Perundoc'


# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'Perun.tex', 'Perun Documentation',
     'Tomas Fiedor, Jiri Pavela, et al.', 'manual'),
]


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, 'perun', 'Perun Documentation',
     [author], 1)
]


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'Perun', 'Perun Documentation',
     author, 'Perun', 'One line description of project.',
     'Miscellaneous'),
]


def doctree_read_handler(_, doctree):
    """Handler for postprocessing the read doctree

    This is used to remove \b (or \x08) characters from the text since they are
    the remnants of Click library, which uses these characters to literally
    interpret and not rewrap paragraphs.

    Iterates through all of the node.Text children and replace them with
    \b/\x08 free text.

    :param _: unused parameter, the application of document
    :param doctree: parsed document tree
    """
    # Traverse all of the literal block and paragraph glocks
    # if "\b" or "\x08" is found in the text, we remove it.
    # Note: this is remnant of click documentation, which uses this
    # character to literally interpret paragraphs and not rewrap
    postprocesses_node_list = (
        nodes.paragraph, nodes.literal_block, nodes.term
    )

    for postprocessed_node in postprocesses_node_list:
        for child in doctree.traverse(postprocessed_node):
            if '\b' in str(child) or '\x08' in str(child):
                for text_node in child.traverse(nodes.Text):
                    replaced_text = text_node.replace("\b\n", '')
                    replaced_text = replaced_text.replace("\b", '')
                    replaced_text = replaced_text.replace("\x08\n", '')
                    replaced_text = replaced_text.replace("\x08", '')
                    child.replace(text_node, nodes.Text(replaced_text))


def setup(app):
    # Profile Format specific markup
    import sphinx
    app.add_object_type(
        'perfreg', 'preg',
        objname='perf format region',
        indextemplate='pair: %s; perf format region'
    )
    app.add_object_type(
        'perfkey', 'pkey',
        objname='perf format key',
        ref_nodeclass=sphinx.addnodes.literal_emphasis,
        indextemplate='pair: %s; perf format key'
    )

    # Matrix specific markup
    app.add_object_type(
        'matrixunit', 'munit',
        objname='matrix format unit',
        indextemplate='pair: %s; matrix format unit'
    )

    # Configuration specific markup
    app.add_object_type(
        'confunit', 'cunit',
        objname='configuration unit',
        indextemplate='pair: %s; configuration unit'
    )
    app.add_object_type(
        'confkey', 'ckey',
        objname='configuration key',
        indextemplate='pair: %s; configuration key'
    )

    app.connect('doctree-read', doctree_read_handler)
