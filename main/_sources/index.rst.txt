.. Open Legal Data Platform documentation master file, created by
   sphinx-quickstart on Thu Apr  5 20:52:28 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to Open Legal Data Platform's documentation!
====================================================

OLDP is a web application, written in Python 3.12 and based on the Django web framework.
It is used for processing legal text and for providing a REST API and an Elasticsearch-based
search engine. OLDP is developed by the non-profit initiative Open Legal Data with the goal
of building an Open Data platform for legal documents (mainly court decisions and laws).
The platform makes legal information freely accessible for the general public and especially
third-party apps.

New here? Start with :doc:`getting-started`, then read the :doc:`architecture` overview to see
how the pieces fit together. OLDP is the core of a small ecosystem of projects — see
:doc:`ecosystem` for the German theme, the data ingestor, and the dump-preprocessing toolkit.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   getting-started
   docker

.. toctree::
   :maxdepth: 1
   :caption: The OLDP Ecosystem

   ecosystem

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture
   database

.. toctree::
   :maxdepth: 2
   :caption: Guides

   searching
   data-dumps

.. toctree::
   :maxdepth: 2
   :caption: REST API

   api/api-overview
   api/case-creation
   api/court-creation
   api/law-creation
   api/lawbook-creation
   api/me-endpoints
   api/stats
   api/api-swagger

.. toctree::
   :maxdepth: 2
   :caption: MCP Server

   mcp

.. toctree::
   :maxdepth: 2
   :caption: Development

   development
   processing
   django
   testing

.. toctree::
   :maxdepth: 2
   :caption: Operations

   configuration
   deployment
   elasticsearch
   sitemap-xml

.. toctree::
   :maxdepth: 1
   :caption: Internal Notes

   notes/index


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
