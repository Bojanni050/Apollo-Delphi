# Apollo Delphi — gebruikershandleiding

Kort overzicht van wat je als gebruiker kunt doen. Wordt bijgewerkt wanneer gebruikerszijdige functionaliteit verandert.

## Starten

Dubbelklik op `start.cmd` (of typ `.\start.cmd` in een terminal). De eerste keer stelt het alles in; daarna opent het
de app in een eigen venster. Sluit je het venster, dan stopt de app. Gegevens staan in `%LOCALAPPDATA%\Apollo-Delphi`
(SQLite), of in je lokale PostgreSQL als `backend\.env` een `DATABASE_URL` heeft.

## Eerste keer: de wizard

Zonder werkmap opent een wizard in drie stappen: een **naam**, de **map** waar de werkmap komt te staan (zelf typen,
**Bladeren…**, of "Apollo kiest een map"), en optioneel de eerste **documenten** (bestanden of een hele map).

## Werkmappen en documenten

- Een werkmap bundelt de documenten van één onderwerp; zoeken, vragen en analyses blijven binnen de werkmap. Elke
  werkmap is ook een git-map: elke upload wordt vastgelegd in `Inbox/`.
- **Documents → Upload documents**: PDF, Word, Markdown en tekst. Bestanden worden geïndexeerd.
- **Map uploaden…**: kies een map; alle submappen worden doorlopen. Je ziet eerst wat wordt toegevoegd en wat wordt
  overgeslagen (verborgen/tooling-mappen, niet-ondersteunde, lege en tijdelijke bestanden). Elk bestand krijgt zijn pad
  als naam (`docs/adr/001.md`). Opnieuw dezelfde map kiezen voegt alleen toe wat nieuw is. Stoppen kan tussendoor.
- Een GitHub-repository toevoegen kan ook (de inhoud wordt als één document geïndexeerd).

## Vragen stellen

**Vragen**: stel een vraag over de documenten van de werkmap. Het antwoord noemt de fragmenten waarop het steunt
([1], [2]…), met bestand, pagina, sectie en (bij txt/md) regels. Staat het antwoord er niet in, dan zegt Apollo dat.
Stel daarna een **vervolgvraag**; "Nieuw gesprek" begint opnieuw. Een getal dat niet in de bronnen staat wordt gemeld.

## Analyse, issues en kennis

**Analysis** leest claims uit de documenten; **Issues** toont tegenstrijdigheden en open vragen met het bewijs
(bestand, pagina, regels); een onderzoek kan ze oplossen, waarna jij accepteert of afwijst. **Knowledge** toont wat
vaststaat; **Generated** maakt en controleert een samenvattend document.

## Instellingen

- **Taalmodellen** (hoofd- en achtergrondmodel): kies een **provider** (OpenAI, Anthropic, Google, OpenRouter, EdenAI,
  Ollama, LM Studio, een eigen OpenAI-compatibele server of de offline mock); het adres wordt ingevuld. Vul een sleutel
  in als die nodig is en klik **Modellen ophalen** — opslaan hoeft nog niet. Kies een model uit de lijst (zoeken kan);
  bij OpenRouter en EdenAI zie je prijs per 1 miljoen tokens, provider en context, en **Lees meer** toont alle
  informatie: beschrijving, mogelijkheden (tekst, vision, bestanden, audio, video; tools, redeneren…), kosten en limieten.
- **Embeddingmodel**: voor het zoeken op betekenis. Een model wisselen betekent opnieuw indexeren ("Her-indexeer").
  Lokale modellen: Ollama of llama.cpp; met `docker compose --profile llama up -d llama` draait een llama-server mee.
  Dat gaat op de CPU en duurt ongeveer 1,3 s per fragment. Op een Vulkan-GPU (bijvoorbeeld AMD Radeon) is het ongeveer
  30 keer sneller: `powershell -ExecutionPolicy Bypass -File scripts\llama-vulkan.ps1`, daarna Base URL
  `http://localhost:8082/v1` (zelfde modelnaam; opnieuw indexeren is niet nodig).
- **Vragen en zoeken**: aantal fragmenten per vraag, gespreksbeurten als context en de zoekafstemming.

Staat een model op de mock, dan zijn antwoorden eenvoudige fragmenten en is zoeken niet echt semantisch.

## Versie

Onder de titel "Apollo" in de zijbalk staat het buildnummer (`0.` + datum en tijd, bijvoorbeeld `0.202610011556`) met de
dag en tijd van de build. Het wordt bij elke build vanzelf bijgewerkt, ook bij elke start van de desktop-app.
