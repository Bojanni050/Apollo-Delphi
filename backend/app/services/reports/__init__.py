"""Reports: the findings of one analysis run as a report, and as a PDF to download.

A report is built deterministically from the run (no model needed, so it works offline and with the mock provider):
the contradiction and open-question issues with their evidence, plus a summary of the run. The markdown is stored as a
GeneratedDocument (the same place as the generated reports and notes), and the PDF is rendered from that stored content,
so downloading it again later gives the same document.
"""
