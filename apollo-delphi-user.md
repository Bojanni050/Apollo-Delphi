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
  werkmap is ook een git-map: elke upload wordt vastgelegd in `Inbox/`. Ook je beslissingen bij Delphi
   Pulse (accepteren, negeren, ook alles tegelijk) worden vastgelegd: één commit per beslissing, met per voorstel een
   regel in `Decisions/decisions.jsonl` (wanneer, welk document, wat besloten is, de thema’s en verbanden). Zo kun je
   later terugzien wat je wanneer hebt besloten, en op de Werkmap-pagina staan ze in de geschiedenis.
- **De werkwijze in de kop**: bovenin links, naast de knop van de zijbalk, staan de stappen in volgorde: **Importeren › Delphi Pulse › Analyse**. Een klik opent die
  pagina; een vinkje betekent dat de stap gedaan is (er zijn documenten, er zijn groepen). **Analyse** is pas te openen als er
  groepen zijn: draai Delphi Pulse en accepteer de voorstellen, dan komen er groepen en wordt de knop actief. (Op een smal
  venster is de balk verborgen.) Het menu links heeft dezelfde volgorde: bovenaan **Importeren, Delphi Pulse, Analyse, Delphi
  Weave**, dan een streep en de rest (Zoeken, Vragen, Issues, Knowledge, Generated, Werkmap, Instellingen); ook daar is Analyse
  pas actief als er groepen zijn.
- **Delphi Weave** laat zien hoe de werkmap aan elkaar hangt: elke groep is een blok met zijn documenten, en een lijn tussen
  twee documenten is een verbinding die je bij Delphi Pulse hebt geaccepteerd (grijs: hangt samen met, groen: ondersteunt,
  rood: spreekt tegen, blauw: breidt uit; met de knoppen bovenaan zet je een soort lijnen aan of uit). Wijs een document aan
  om zijn lijnen te zien en onderaan te lezen waarom het verbonden is; klik erop om het te lezen in het leesvenster. Wat Pulse
  alleen heeft voorgesteld staat er pas in als je het accepteert.
- **Documents → Upload documents**: PDF, Word, Markdown en tekst. Bestanden worden geïndexeerd.
- **Map toevoegen…**: kies een map met de eigen mappenkiezer van de app; alle submappen worden doorlopen. Je ziet
  eerst wat wordt toegevoegd en wat wordt overgeslagen (verborgen/tooling-mappen, niet-ondersteunde, lege en tijdelijke
  bestanden). Elk bestand krijgt zijn pad als naam (`docs/adr/001.md`). Opnieuw dezelfde map kiezen voegt alleen toe
  wat nieuw is. Stoppen kan tussendoor. ("of upload via de browser" kan ook, maar dan toont de browser zelf een
  bevestiging.)
- **Eerst lezen, dan embedden**: bestanden zijn binnen een paar seconden toegevoegd en daarna meteen **gelezen**
  (uitgelezen en in fragmenten geknipt). Een gelezen document (status "gelezen") is al te lezen in het leesvenster
  en te doorzoeken op woorden. Het **embedden** (nodig om op betekenis te zoeken) is het trage deel en loopt daarna op
  de achtergrond, een document tegelijk; zodra een document klaar is staat het op "indexed". Boven op de
  Documents-pagina staat de voortgang ("gelezen 36 van 36 · geëmbed 2 van 36") met de geschatte tijd. Je kunt gewoon
  verder werken. Is het embeddingmodel niet bereikbaar, dan blijven de documenten "gelezen" met de reden erbij en
  probeert "Nu indexeren" het later opnieuw; wachten er documenten na een herstart, dan staat die knop er ook.
- Een GitHub-repository toevoegen kan ook (de inhoud wordt als één document geïndexeerd).

## Het leesvenster

Het leesvenster is een eigen kolom, vóór de contextkolom (de smalle strook rechts met de naam van de pagina: het
pijltje daarin opent en sluit het paneel, dat het leesvenster en de pagina opzij schuift), waarin je een document
**in zijn geheel** leest. Het staat
standaard open; met **▤ Lezen** rechtsboven sluit of open je het (dat wordt onthouden).
**Klik op een document in de lijst** op de Documents-pagina om het te lezen; bij een zoekresultaat, een bron bij Vragen
of bewijs bij een issue staat **Lees in het leesvenster**. Je ziet de tekst met regelnummers (bij een PDF met de pagina-overgangen), de plek waar je voor kwam
gemarkeerd en in beeld gebracht (bij een bron het hele fragment) en je zoekwoorden gemarkeerd. Bovenin kun je in het
document zoeken (Enter of ▲▼ naar de volgende treffer). Het venster start op 40% van de breedte van het venster en blijft dat aandeel houden als je het
venster groter of kleiner maakt. Sleep de linkerrand
(het streepje) om de pagina en het leesvenster breder of smaller te maken; die breedte wordt onthouden. Bij Markdown, Word en PDF kies je bovenin **Opgemaakt** (zoals het bedoeld is: koppen, lijsten,
tabellen, of het originele PDF-bestand in de PDF-viewer) of **Tekst** (met regelnummers, markering en zoeken). Open je een
document zonder specifieke plek, dan zie je het opgemaakt; kom je via een zoekresultaat, bron of bewijs, dan zie je de
tekst met de plek gemarkeerd (een PDF opent op de juiste pagina). Een tekstbestand toont altijd de tekst. Scripts en
externe afbeeldingen in een document worden nooit geladen. Het venster toont de tekst zoals Apollo die las; de regelnummers zijn die van die tekst.

## Zoeken

**Zoeken** (eigen pagina, tussen Documents en Vragen) zoekt in de geïndexeerde documenten van de werkmap. Kies een
methode: **Hybride** (betekenis en exacte woorden samen, goed voor bedragen, namen en id's), **Betekenis** of
**Trefwoorden**. Elk resultaat toont het bestand, de sectie, de pagina of regels, waarom het past (betekenis, woorden of
beide) en een fragment met je zoekwoorden gemarkeerd. Documenten die nog niet zijn geïndexeerd worden niet doorzocht.

## Vragen stellen

**Vragen**: stel een vraag over de documenten van de werkmap. Het antwoord noemt de fragmenten waarop het steunt
([1], [2]…), met bestand, pagina, sectie en (bij txt/md) regels. Staat het antwoord er niet in, dan zegt Apollo dat.
Stel daarna een **vervolgvraag**; "Nieuw gesprek" begint opnieuw. Een getal dat niet in de bronnen staat wordt gemeld.

## Analyse, issues en kennis

**Delphi Pulse** (onder de streep in het menu; bovenaan staat wanneer de laatste run was) doet voorstellen voor thema's en verbanden tussen de documenten. Het leest
de tekst zelf, dus het werkt ook terwijl het embedden nog loopt. Documenten die nog niet zijn gelezen doen niet mee: daarvoor
toont de pagina een waarschuwing; terwijl Pulse draait pulseren het icoon en de naam in het menu zacht, ook als je naar een andere
pagina gaat; draai Pulse dan opnieuw als ze klaar zijn (wat al is geanalyseerd wordt overgeslagen).
Naast thema's en verbanden stelt Pulse per document ook **twee indelingen** voor. Een **map** op schijf, naar type: Drafts, Reports,
Chapters, Notes, Specs, Reference of Other (past geen enkele, dan stelt Pulse een nieuwe map voor, met “nieuwe map” erbij):
bij accepteren verhuist het bestand in de git-werkmap van `Inbox/` naar die map (met zijn submappen, in een eigen commit; een
naam die al bestaat krijgt een nummer, er wordt nooit iets overschreven). En een **groep**: een virtuele map in Apollo (bij Gaia
bijvoorbeeld architectuur, besluiten, gebruik). Een document zit in één groep. Op de Documents-pagina staan de documenten dan
gegroepeerd, met een filter; bij Zoeken kun je ook in één groep zoeken. De documenten zelf veranderen niet: ze blijven
leesbaar en doorzoekbaar. Documenten die al eerder zijn geanalyseerd krijgen deze voorstellen pas bij **Alles opnieuw**.
**Alles opnieuw** laat Pulse alle documenten opnieuw bekijken; daar vraagt de app eerst “weet je het zeker?” voor. Elk document
krijgt dan één nieuw voorstel dat vervangt wat nog openstond.
Elk voorstel accepteer of negeer je per document, of allemaal tegelijk met **Alles accepteren** en **Alles negeren** (met
een bevestiging vooraf: accepteren neemt de thema’s en verbanden op in de documenten). Klik op een voorstel, of op een
verbonden document daarin, om dat document in het leesvenster te lezen.

**Analysis** leest claims uit de documenten, van de hele werkmap of alleen van de groepen die je kiest (bovenaan: Alles, of
een of meer groepen, bijvoorbeeld twee tegelijk); tegenstrijdigheden worden dan alleen tussen de gekozen documenten gezocht,
en zo'n analyse is veel kleiner; **Issues** toont tegenstrijdigheden en open vragen met het bewijs
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

## Weergave: licht of ambient (donker)

Rechtsboven staat een knop die wisselt tussen **licht** (☀︎), **ambient** (☾) en **automatisch** (◐, volgt je computer);
dezelfde keuze staat onder Instellingen → Weergave. Ambient is een rustig donker thema in het palet van Gaia (warm
rookgrijs en saliegroen, zoals intro.higaia.nl) met een zacht groen schijnsel dat langzaam beweegt. Staat je computer op
"minder beweging", dan staat het schijnsel stil. De keuze wordt onthouden. Een nieuwe installatie volgt je computer.

## Versie

Onder de titel "Apollo" in de zijbalk staat het buildnummer (`0.` + datum en tijd, bijvoorbeeld `0.202610011556`) met de
dag en tijd van de build. Het wordt bij elke build vanzelf bijgewerkt, ook bij elke start van de desktop-app.
