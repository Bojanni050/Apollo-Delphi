"""Codecheck: docs naast repo's leggen.

Slice 1: repo's oplossen (al geïmporteerd document of vers via URL) en de
digest splitsen in docs-secties en code-secties, zodat een latere slice per
bewering uit de docs bewijs kan zoeken in de code.
Slice 2: oordeel-engine (verdicts.py: beweringen via bestaande
claim-extractie, bewijs via termoverlap in codesecties, oordeel van het
redeneer-model of offline-heuristiek bij mock) + API (POST /codecheck/run).
Slice 4: live voortgang (progress.py) en een achtergrond-run die de pagina
pollt, zodat gevonden oordelen meteen verschijnen en klikbaar zijn.
"""
