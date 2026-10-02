# Walkthrough Apollo Delphi

Logboek van significante wijzigingen, oudste bovenaan. Protocol: zie `agents.md` (lokaal, niet in git). Na elke significante
wijziging wordt hier onderaan een blok toegevoegd; bij 1000 regels begint `walkthrough2.md`. De eerste blokken zijn
achteraf ingevuld voor het werk van 2026-10-01 (commits tussen haakjes).

## 2026-10-01 (Chunk-reconciler bij herindexeren)

- Findings: Herindexeren verwijderde alle chunks van een document en maakte ze opnieuw aan. Daardoor werd elke chunk opnieuw ge-embed (kosten, tijd) en raakte evidence die naar een chunk wees (`chunk_id`) losgekoppeld.
- Conclusions: Een chunk wordt geïdentificeerd door zijn tekst. Onveranderde chunks houden id en embedding; alleen nieuwe tekst wordt ge-embed. Alle embeddings worden berekend vóór er iets in de database verandert, zodat een falende provider niets half achterlaat.
- Actions: `backend/app/services/documents/indexer.py` (`_reconcile_chunks`, `ReconcileStats`), `backend/tests/integration/test_chunk_reconcile.py`; validated. (0d522db)

## 2026-10-01 (Regelbereik per chunk en bij evidence)

- Findings: Een bron werd alleen met pagina of sectie aangeduid; dat is te grof om een citaat terug te vinden.
- Conclusions: Chunks krijgen een exact regelbereik (uit echte offsets in de chunker). Regelnummers zijn alleen betekenisvol voor geüploade txt/md-bestanden: bij pdf/docx zijn het regels van uitgelezen tekst en een GitHub-digest is een samengestelde tekst, dus daar worden ze niet getoond. Evidence wordt versmald tot de regels van de geciteerde zin, met de hele chunk als terugval.
- Actions: `chunker.py`, `models/document.py`, `models/claim.py` + migraties `a1c9e5d73b24` en `c3e8a1b94d27`, `search/service.py` (`has_citable_lines`, `evidence_lines`), `analysis/service.py`, `issues/investigation.py`, schema's, Ask/Documents/Issues-pagina; validated. (de50fc8, ff83456, 7d896d5)

## 2026-10-01 (Vervolgvragen in Vragen)

- Findings: Elke vraag stond op zichzelf; "En wanneer is dat klaar?" vond niets.
- Conclusions: Een vervolgvraag wordt herschreven tot een zelfstandige vraag (door het model, offline door het onderwerp van de vorige vraag ervoor te zetten); daarmee wordt gezocht. De vorige beurten gaan als context mee maar nooit als bron: elke bewering heeft nog steeds een vers, genummerd fragment nodig en dezelfde controles gelden.
- Actions: `ask/service.py`, `api/ask.py`, `models/qa.py` (ook voor het eerst gecommit: `.gitignore` negeerde `models/`) + migratie `b7d2f4a86c15`, `AskPage.tsx`; validated. (313f987)

## 2026-10-01 (Instellingen: vragen en zoeken; CORS)

- Findings: ASK_TOP_K, ASK_HISTORY_TURNS en de zoekafstemming waren alleen via omgevingsvariabelen te zetten. De app via `127.0.0.1:5173` openen werd door CORS geblokkeerd (alleen `localhost` stond toe).
- Conclusions: Dezelfde opslag als de modelinstellingen (`app_settings`, direct actief, zelfde grenzen). CORS staat elke loopback-origin toe (`localhost`, `127.0.0.1`, `[::1]`).
- Actions: `api/retrieval.py`, `llm_settings.py`, `RetrievalCard.tsx`, `main.py` (`allow_origin_regex`), tests; validated. (b6defb8, 27f301e)

## 2026-10-01 (Embeddings: lokaal model en llama-server in Compose)

- Findings: "Kiezen" bij een lokaal model liet de Base URL leeg, waardoor het model onbruikbaar was terwijl de pagina "opgeslagen" meldde. De GGUF-bestanden hebben geen pooling-type (de server weigert embeddings zonder `--pooling`) en de catalogus gaf Jina 768 dimensies terwijl het model er 1536 geeft.
- Conclusions: De runtimes melden zelf hun endpoint (`LLAMACPP_BASE_URL`, in Compose `http://llama:8080/v1`). Een optionele `llama`-service (profiel) gebruikt het bestand dat de app al in `backend/models` downloadde, dus niets dubbel.
- Actions: `EmbeddingsCard.tsx`, `model_manager.py`, `embeddings.py` (foutmelding, dimensie), `docker-compose.yml`, `.env.example`; validated met een echt draaiende llama-server. (3c6e6b5, 330ca70)

## 2026-10-01 (Onboarding-wizard en mappenkiezer)

- Findings: Zonder werkmap opende de app een onbruikbare schil.
- Conclusions: Drie stappen (naam, map, eerste documenten) naar het voorbeeld van `K:\Projects\Apollo`; de werkmap wordt aan het einde van stap 2 aangemaakt en de wizard meldt zich pas bij het voltooien af. De mappenkiezer toont alleen mapnamen en kan met `FOLDER_BROWSE_ENABLED=false` uit (de API heeft geen inlog).
- Actions: `SetupWizard.tsx`, `FolderPickerModal.tsx`, `api/system.py`, `App.tsx`; validated in de browser op een lege database. (7831b63, 14bdf60)

## 2026-10-01 (Desktop-app met Tauri 2)

- Findings: De app was een webapp op Docker/PostgreSQL; gewenst was een echte desktop-app.
- Conclusions: Zelfde opzet als het referentieproject: een klein Rust-venster dat `python -m app.serve` uit `.venv` start, wacht tot de API antwoordt en het venster daarheen wijst (zelfde origin, geen CORS). Eigen gegevensmap in `%LOCALAPPDATA%\Apollo-Delphi`, migraties bij elke start. Nog geen installer: de schil draait vanuit de repository.
- Actions: `backend/app/serve.py`, `src-tauri/`, `package.json`, `scripts/setup-desktop.ps1`, icoon, README; tests starten de echte server in een subprocess en stoppen de hele proces-boom (de venv-launcher laat anders een kind-interpreter achter); validated: app gebouwd, gestart en gesloten. (6ce7ff9, 468a1c3)

## 2026-10-01 (Lokale PostgreSQL voor de desktop-app)

- Findings: Gewenst was de lokale PostgreSQL 18 (wachtwoord vereist, pgvector ontbrak; er is geen officiële Windows-download).
- Conclusions: `DATABASE_URL` in `backend/.env` kiest de database; de app maakt hem zo nodig aan en controleert pgvector met duidelijke meldingen. pgvector wordt uit de officiële bron gebouwd met het MSVC-script; kopiëren vraagt administrator-rechten en blijft aan de gebruiker. Tests lezen nooit de echte `backend/.env`.
- Actions: `serve.py` (`ensure_database`), `core/config.py`, `main.py` (dialect van de engine i.p.v. config), `scripts/install-pgvector-windows.ps1`; validated: migraties tot `c3e8a1b94d27` op PostgreSQL 18.6 met `vector`. (44f4362, 7f0454a)

## 2026-10-01 (start.cmd)

- Findings: `start.cmd` bestond al maar was leeg. `start.cmd` zonder `.\` wordt door `cmd` als het ingebouwde `start` gelezen.
- Conclusions: Eerste keer instellen, daarna starten; `start.cmd setup` alleen instellen. `.gitattributes` houdt `*.cmd` op CRLF (labels).
- Actions: `start.cmd`, `.gitattributes`, README; validated: setup en start/stop. (9206cef)

## 2026-10-01 (Modellen ophalen zonder eerst op te slaan; providerpresets; modelkaartjes)

- Findings: Modellen ophalen gebruikte alleen opgeslagen gegevens, dus eerst opslaan gaf een rode "no model selected". De opgeslagen sleutel kon naar een ander getypt adres gaan.
- Conclusions: `POST /api/llm/models` gebruikt het formulier (sleutel in de body); een opgeslagen sleutel gaat alleen naar het opgeslagen adres. Providerdropdown met presets (OpenAI, Anthropic, Google, OpenRouter, EdenAI, Ollama, LM Studio, eigen server, mock). Een eigen modellenlijst die zo breed is als het veld, met zoekveld; OpenRouter/EdenAI-modellen als kaartjes met prijs per 1M tokens, provider, context en beschrijving.
- Actions: `api/llm.py`, `core/llm_models.py`, `SettingsPage.tsx`, `ModelPicker.tsx`; een race (traag antwoord van een eerder gekozen provider overschreef het nieuwste) verholpen; validated met de echte API's van OpenRouter (462) en EdenAI (1127). (63bc8d2, 08693a8, 1b4dfc9)

## 2026-10-01 (Modeldetailvenster, mock-namen weg, mappen uploaden)

- Findings: "Lees meer" deed niets zichtbaars; `mock-model`/`mock-embedder` bleven staan na het verlaten van de mock-provider; er was geen manier om een hele map te uploaden.
- Conclusions: "Lees meer" opent een venster met alle modelinformatie (modaliteiten, functies, kosten, limieten). De mock-namen gelden niet meer als model van een echte provider (UI én backend). Een map wordt recursief doorlopen; elk bestand krijgt zijn relatieve pad als naam en behoudt de mapstructuur in `Inbox/`; reeds aanwezige bestanden (zelfde pad en hash) worden overgeslagen. Een pad mag de map niet verlaten, een gewone upload houdt de strenge naamcontrole.
- Actions: `ModelDetails.tsx`, `modelFormat.ts`, `llm_models.py`, `llm.py`, `embeddings.py`; `FolderUpload.tsx`, `documents/service.py`, `workspace_repo.py`, `api/documents.py`, `schemas/documents.py`; validated in de browser. (5611a45, 8ab1ab7)

## 2026-10-01 (Werkafspraken uit agents.md ingevoerd)

- Findings: `agents.md` beschrijft het werkprotocol (walkthrough, versieregel, `npm run build`, gebruikersdocument) maar stond ongetrackt in de repository.
- Conclusions: `agents.md` is persoonlijk en gaat op `.gitignore`; `walkthrough.md` is onderdeel van het project en wordt gecommit. De versieregel komt in de sidebar onder de apptitel (één bron: `frontend/src/version.ts`). Het gebruikersdocument heet `apollo-delphi-user.md`.
- Actions: `.gitignore`, `walkthrough.md`, `frontend/src/version.ts`, `frontend/src/layout/AppShell.tsx`, `apollo-delphi-user.md`; `npm --prefix frontend run build` gedraaid; validated.

## 2026-10-01 (Buildnummer automatisch, zoals melodiq)

- Findings: Ik had de versieregel onder de apptitel als handmatige constante (`version.ts`) gemaakt, die na elke taak bijgewerkt moest worden. In melodiq (`next.config.mjs`) wordt het buildnummer bij elke build vanzelf gemaakt: `0.` + jaar, maand, dag, uur, minuut, via `NEXT_PUBLIC_BUILD_VERSION` getoond in de zijbalk ("build number …").
- Conclusions: Automatisch is beter: geen vergeten updates en geen wijziging in git bij elke taak. Hetzelfde patroon voor Vite: de configuratie berekent het nummer bij het bouwen of starten van de dev-server. Het nummer verandert dus bij `npm run build`, bij elke start van de desktop-app (`start.cmd` bouwt de frontend) en bij een Docker-herstart van de frontend. De leesbare dag en tijd (do 1 okt 2026 · 15:56) komt uit hetzelfde moment.
- Actions: `frontend/vite.config.ts` (`define` met `__BUILD_VERSION__` en `__BUILD_TIME__`), `frontend/src/version.ts` (leest die, geen handmatige constante meer), `frontend/src/layout/AppShell.tsx` ("build 0.202610011556 · do 1 okt 2026 · 15:56"), `apollo-delphi-user.md`; `npm --prefix frontend run build` gedraaid en in de browser gecontroleerd; validated.

## 2026-10-01 (Embedden op de GPU via Vulkan)

- Findings: De tragere kant was de CPU (Ryzen 7 5800X, ~1,3 s per fragment). De machine heeft een AMD Radeon RX 7800 XT (16 GB) met een werkende Vulkan-driver. Docker Desktop geeft op Windows geen Vulkan-GPU aan containers. De standaardinstellingen van de nieuwe llama-server (context 32768 × 4 slots, `--fit`) lieten de Vulkan-build tijdens het laden hangen (27 MB, geen CPU-gebruik meer).
- Conclusions: De officiële Windows-Vulkan-build (b11320, 31,6 MB, SHA-256 gecontroleerd tegen GitHub) draait rechtstreeks, met `-ngl 99 -c 4096 -np 1 --fit off`: een kleine context volstaat voor fragmenten van enkele honderden tokens. Resultaat: 0,04 s per fragment tegenover 1,33 s op de CPU (ongeveer 30 keer sneller); de eigen embedding-provider van de app haalde 288 fragmenten in 12 s. Dezelfde modelnaam geeft praktisch dezelfde vectoren (cosine 0,9998 tussen GPU en CPU), dus er hoeft niets opnieuw geïndexeerd.
- Actions: `scripts/llama-vulkan.ps1` (download eenmalig, controleert de checksum, start de server, `-Stop`), README en gebruikersdocument; gestart op poort 8082; validated met `bench`-metingen en een volledige map-import via de UI.

## 2026-10-01 (Mappen toevoegen zonder browser-popup, en indexeren op de achtergrond)

- Findings: Een map kiezen met `<input webkitdirectory>` laat de browser zelf vragen "117 bestanden uploaden naar deze site?", in zijn eigen, niet te stylen venster bovenin; `UnassignedBanner` gebruikte `window.confirm`. Daarnaast ging het toevoegen van een map enorm traag: gemeten op de echte Jina-server kost opslaan ~0,25 s per bestand maar indexeren ~1,3 s per fragment (3,8 KB = 11 fragmenten = 10 s; README van 18 KB = 25 fragmenten = 32 s), dus 117 bestanden ≈ een half uur waarin de pagina niet verlaten kon worden. Batches of parallelle aanvragen maken het niet sneller: de 8 CPU-threads zijn al vol.
- Conclusions: De backend draait in de desktop-app op dezelfde computer, dus de app kiest de map met haar eigen (gecentreerde, gestylede) dialoog en de backend leest hem zelf recursief van schijf: geen browserpopup, geen bytes door de pagina. Opslaan en indexeren worden gescheiden: bestanden staan in seconden in de werkmap en worden in een wachtrij gezet die op de server op de achtergrond één document tegelijk indexeert (parallel is niet sneller); de voortgang en geschatte tijd staan op de Documents-pagina. Alle popups zijn nu gecentreerde `Modal`s. Symlinks worden niet gevolgd (ze kunnen uit de map wijzen) en de schakelaar `FOLDER_BROWSE_ENABLED` geldt ook hier.
- Actions: `backend/app/services/documents/folder_import.py`, `index_queue.py` (+ `recover_interrupted_indexing` bij het opstarten: een document dat door een gestopte app op `processing` bleef staan, wordt weer `pending`), `api/documents.py` (`/folder/scan`, `/folder/file`, `/index-queue`), schema's, `main.py`; `frontend/src/components/Modal.tsx`, `FolderUpload.tsx` (herschreven), `IndexProgress.tsx`, `UnassignedBanner.tsx` (geen `window.confirm` meer), `DocumentsPage.tsx`, `api.ts`; tests `test_folder_import.py`, `test_index_queue.py` (de symlink-test slaat op Windows over: geen rechten); validated in de browser: 36 bestanden in 11 s toegevoegd, daarna in 3 s geïndexeerd.

## 2026-10-01 (Zoeken op een eigen pagina)

- Findings: Zoeken zat als laatste kaart onderaan de Documents-pagina, onder het uploaden, de GitHub-repository en de lange lijst met documenten. Daardoor was het moeilijk te vinden en deelde het de pagina met beheer.
- Conclusions: Zoeken is een eigen activiteit naast Vragen; het krijgt een eigen pagina ("Zoeken", tussen Documents en Vragen). Dezelfde API en dezelfde methodes (hybride, betekenis, trefwoorden); toegevoegd: de sectie bij elk resultaat, de zoekwoorden gemarkeerd in het fragment, een lege toestand met uitleg en een melding dat niet-geïndexeerde documenten niet worden doorzocht. Resultaten horen bij één werkmap en worden bij wisselen gewist.
- Actions: `frontend/src/pages/SearchPage.tsx` (nieuw), `App.tsx` (menu-item, paginatitel, route), `DocumentsPage.tsx` (zoekkaart, state en functie weggehaald), `apollo-delphi-user.md`; `npm --prefix frontend run build` gedraaid; validated in de browser met 36 echt geïndexeerde documenten (hybride, betekenis, trefwoorden, Enter-toets, geen resultaten).

## 2026-10-01 (Ambient/donker thema in het palet van Gaia)

- Findings: De app had alleen een licht thema. Het palet staat op intro.higaia.nl: een warm "smoke"-grijs (achtergrond #0D0C0A, Dark Smoke #1A1916, Dark Graphite #2E2C26, tekst #E9E7E0) en de "sage"-schaal (Luminous Forest #C7D7CA, Muted Mint #7C9A82, Subtle Mint #5D7D64, Dark Mint #3A503F), met een zacht groen schijnsel op de achtergrond. De componenten gebruiken ongeveer 70 verschillende Tailwind-kleurklassen (slate, white, amber, emerald, red, sky).
- Conclusions: In plaats van overal `dark:`-varianten toe te voegen, geeft één stylesheet (`dark.css`, actief bij `html[data-theme="dark"]`) dezelfde klassen een donkere betekenis; het lichte thema blijft onaangeroerd (gecontroleerd: dezelfde kleuren als voorheen). Het thema volgt de keuze licht / ambient / automatisch (opgeslagen in `localStorage`, standaard automatisch) en wordt vóór het eerste tekenen op `<html>` gezet, zodat een donkere pagina niet wit oplicht. "Ambient" is het schijnsel van drie zachte radiale verlopen die langzaam driften (stil bij `prefers-reduced-motion`). Twee valkuilen die bij het testen boven kwamen en nu zijn opgelost: `backdrop-filter` op een kaart maakt die kaart de referentie voor alles met `position: fixed` erin, waardoor de dialogen (die in kaarten staan) onzichtbaar waren, dus de kaarten zijn doorschijnend zonder blur; en een `color-scheme`-meta liet de invoervelden het besturingssysteem volgen in plaats van het gekozen thema, dus `color-scheme` staat nu per thema.
- Actions: `frontend/src/dark.css`, `theme.ts`, `components/ThemeToggle.tsx` (knop rechtsboven, ook op de wizard), `pages/AppearanceCard.tsx` (Instellingen → Weergave), `index.html` (thema vóór het tekenen), `App.tsx`, `layout/AppShell.tsx`, `pages/SettingsPage.tsx`, `pages/SetupWizard.tsx`, `apollo-delphi-user.md`; `npm --prefix frontend run build` gedraaid; validated in de browser: Documents, Zoeken, Instellingen, de mappenkiezer (gecentreerd), de wizard, wisselen licht/donker/automatisch.

## 2026-10-01 (Leesvenster: een document in zijn geheel lezen)

- Findings: Een zoekresultaat, bron of bewijs toonde alleen een fragment van een paar regels; om de omgeving te lezen moest je het bestand buiten de app openen. De regelbereiken en pagina's die we sinds vandaag vastleggen, werden nergens gebruikt om ter plekke te lezen.
- Conclusions: Een extra kolom rechts, vóór de contextkolom (volgorde: zijbalk, pagina, leesvenster, context), toont de uitgelezen tekst van een document zoals de indexer die las, met regelnummers; zo blijven citaten ("regels 28-36") en de plek in het venster hetzelfde. De plek komt bij voorkeur van het fragment (`chunk_id`, regelbereik uit de tekst-API, voor elk bestandstype), anders uit meegegeven regels, een pagina of door het citaat in de tekst te zoeken (spaties genegeerd). Eén `ReaderProvider` in de shell laat elke pagina het venster openen (`useReader().open`). De tekst-API onthoudt de laatste 8 uitgelezen documenten, want een PDF uitlezen is traag en elke bron vraagt opnieuw. Lange documenten worden in blokken van 200 regels getekend met `content-visibility: auto`.
- Actions: `backend/app/services/documents/reading.py`, `api/documents.py` (`GET /{id}/text`), schema's, `tests/integration/test_document_text.py`; `frontend/src/reader.tsx`, `components/ReadingPane.tsx` (zoeken in het document, ▲▼, markering, sleepbare breedte, pagina-markeringen), `layout/AppShell.tsx` (kolom en knop "Lezen"), `api.ts`, ingangen in `DocumentsPage`, `SearchPage`, `AskPage`, `IssuesPage`, README en `apollo-delphi-user.md`; validated in de browser (zoekresultaat → regels 28–36 gemarkeerd, zoeken 1/4→3/4, breedte slepen en onthouden, sluiten en heropenen, Documents en Vragen). Niet in de browser geprobeerd: de ingang bij Issues en een PDF met pagina-overgangen (de paginaberekening heeft wel een test).

## 2026-10-01 (Eerst lezen, dan embedden: documenten meteen bruikbaar)

- Findings: Uitlezen, in fragmenten knippen en embedden was één stap (`index_document`), en alleen documenten met status `indexed` telden mee bij zoeken, analyse en pulse. Een map was daardoor pas bruikbaar als de hele, trage embedding klaar was (op de CPU ~1,3 s per fragment, een half uur voor 100 bestanden), terwijl het uitlezen zelf een fractie van een seconde kost en het leesvenster een document al rechtstreeks uit het bestand leest.
- Conclusions: Twee stappen. `parse_document` (uitlezen, knippen, de fragmenten opslaan met hun regels, zonder embedding) maakt een document `parsed`: te lezen, met fragmenten, doorzoekbaar op woorden. `embed_document` vult de vectoren aan, per batch opgeslagen (voortgang blijft bewaard, mislukt het embedden dan blijft het document `parsed` met de reden in `error_message` en gaat een nieuwe poging verder waar het bleef), en maakt het `indexed`. De wachtrij leest altijd eerst alles (prioriteit) en embedt daarna één document tegelijk. `READY_STATUSES = (parsed, indexed)` is overal waar tekst volstaat (zoeken, analyse, pulse); de semantische kant gebruikt vanzelf alleen fragmenten met een vector van het actieve model. Een `parsed` document telt als verouderd bij het embeddingmodel, zodat "Her-indexeer verouderde" en "Nu indexeren" het afmaken. De oude test die "alles of niets" eiste bij een embed-fout is bewust vervangen: nu blijft het gelezen en doorzoekbaar.
- Actions: `backend/app/services/documents/indexer.py` (`parse_document`, `embed_document`, `index_document` = beide), `index_queue.py` (twee prioriteiten, `parsed`, `phase`), `models/document.py` (`READY_STATUSES`), `search/service.py`, `analysis/service.py`, `pulse/service.py`, `embeddings/status.py`, `api/documents.py`, schema's; `frontend`: `IndexProgress.tsx` ("gelezen 36 van 36 · geëmbed 2 van 36"), `components.tsx` (badge "gelezen"), `api.ts`, `FolderUpload.tsx`, `SearchPage.tsx`, `DocumentsPage.tsx`; tests in `test_chunk_reconcile.py` en `test_index_queue.py` (o.a. embedding-server uit: alles blijft gelezen en op woorden vindbaar, daarna afmaken); validated met de CPU-server: 36 documenten in 2 s gelezen, zoeken op woorden direct 8 resultaten, het embedden loopt daarna door (~10 s per document).

## 2026-10-01 (Zonder Docker: start.cmd start ook de embedding-server)

- Findings: De Docker-backend draaide zonder `--reload`, dus na een codewijziging gaf de oude container HTML/404 aan de nieuwe frontend ("Unexpected token '<'"). Verder is Docker op Windows het trage pad: de CPU-llama is ~30× trager dan de Vulkan-GPU-server, en de desktop-app (SQLite of lokale Postgres) doet al alles wat Compose deed.
- Conclusions: Docker blijft als optie (compose-bestand behouden, nu met `--reload`), maar de desktop-app wordt het standaardpad. De enige losse stap was de embedding-server: die start `start.cmd` nu zelf, en faalt nooit hard (zonder model of netwerk start de app gewoon).
- Actions: `docker-compose.yml` (`--reload`); `scripts/llama-vulkan.ps1` (`-Optional`, zoekt het model ook in `%LOCALAPPDATA%\Apollo-Delphi\models`); `start.cmd` (roept het script aan, uit te zetten met `APOLLO_LLAMA=0`); `README.md` (tabel "zonder Docker"); validated: script parseert, met een draaiende server meldt `-Optional` dat hij al draait.

## 2026-10-01 (Delphi Pulse onder een divider in het menu)

- Findings: Delphi Pulse stond tussen de gewone pagina's en had een tekstsymbool, terwijl het een eigen onderdeel is met een eigen icoon (`frontend/src/icons/delphi.png`).
- Conclusions: Een algemene optie `below` voor menu-items, zodat de volgorde in `NAV` leesbaar blijft en andere items er later ook onder kunnen.
- Actions: `frontend/src/layout/AppShell.tsx` (`NavItem.below`, divider vóór het eerste item eronder, iconen verticaal gecentreerd), `frontend/src/App.tsx` (Pulse met het icoon achteraan, `below: true`), `frontend/src/icons/delphi.png`; validated met `npm run build` en in de browser.

## 2026-10-01 (Leesvenster standaard open; klik op een document om het te lezen)

- Findings: Het leesvenster stond standaard dicht en een document openen kon alleen via de knop "Lees"; wie op de rij klikte zag niets gebeuren. De sleeprand was een onzichtbare strook van 8 px, dus het was niet te vinden dat pagina en leesvenster in breedte verstelbaar zijn.
- Conclusions: Open als standaard, maar een gesloten venster wordt onthouden (localStorage). De rij zelf is het doel om te klikken; de knop "Lees" is daarmee overbodig. De sleeprand krijgt een zichtbaar greepje, en het venster mag de pagina ernaast niet dichtdrukken (minimaal 320 px) in plaats van een vast percentage.
- Actions: `frontend/src/reader.tsx` (open standaard, onthouden), `frontend/src/pages/DocumentsPage.tsx` (rij opent het document, geselecteerde rij gemarkeerd, "Lees" weg), `frontend/src/components/ReadingPane.tsx` (greep, minimale paginabreedte, lege-tekst), `apollo-delphi-user.md`; validated met `npm run build` en in de browser (klik op rij toont het document; slepen maakt het venster 288 tot 640 px).

## 2026-10-01 (Leesvenster: Markdown, Word en PDF opgemaakt)

- Findings: Het leesvenster toonde van elk type alleen de uitgelezen tekst met regelnummers: een PDF of Word-bestand zag er dus niet uit als het document zelf, en Markdown bleef ruwe tekst.
- Conclusions: Per type de passende weergave, met de tekstweergave behouden voor wat alleen daar kan (regelnummers, markering van de plek, zoeken). Gekozen voor bibliotheken (afgesproken): `marked` en `DOMPurify` in de frontend, `mammoth` in de backend voor Word. Alles wat een document bevat gaat door DOMPurify (geen scripts), links openen in een nieuw tabblad en externe afbeeldingen worden niet geladen. Een PDF is het originele bestand in de viewer van de browser, op de juiste pagina.
- Actions: nieuwe dependencies `marked`, `dompurify` (`frontend/package.json`) en `mammoth` (`backend/requirements.txt`); `backend/app/api/documents.py` (`GET /{id}/file`, `GET /{id}/html`), `schemas/documents.py` (`DocumentHtmlOut`); `frontend/src/components/RichText.tsx`, `ReadingPane.tsx` (schakelaar Opgemaakt/Tekst, automatisch kiezen: opgemaakt bij openen uit de lijst, tekst als een plek gemarkeerd moet worden, PDF op pagina), `api.ts`, `index.css` (`.reader-prose`, themaonafhankelijk); tests in `test_document_text.py` (bestand, PDF, Word naar HTML, 415 voor andere typen); validated met de volledige tests, `npm run build` en in de browser met een .md, .docx, .pdf en .txt.
- Daarbij een onstabiele test hersteld (`test_index_queue.py`): hij zocht de werkmap op als "eerste in de lijst", waarvan de volgorde niet vaststaat; nu gebruikt hij de werkmap die hij zelf maakte (10 keer achter elkaar groen).

## 2026-10-02 (Delphi Pulse: waarschuwing als documenten nog niet gelezen zijn)

- Findings: Pulse draaien terwijl er nog geïndexeerd wordt kan: het leest de tekst zelf en gebruikt geen embeddings, en neemt gelezen (`parsed`) en geïndexeerde documenten mee. Documenten die nog `pending` zijn doen niet mee, en dat was nergens te zien: een te vroege run gaf stilzwijgend een onvolledig voorstel.
- Conclusions: Waarschuwen in plaats van blokkeren: de run is niet schadelijk (een volgende run slaat ongewijzigde documenten over via de hash). Bij documenten die alleen nog embedden juist een korte geruststelling, omdat dat Pulse niet raakt.
- Actions: `frontend/src/pages/PulsePage.tsx` (kijkt elke 3 s, bij niets wachtends elke 15 s, naar de documentstatussen: amberkleurige waarschuwing voor ongelezen, grijze toelichting voor wat nog embedt), `apollo-delphi-user.md`; validated met `npm run build` en in de browser met 4 ongelezen documenten.

## 2026-10-02 (Delphi Pulse pulseert in het menu terwijl het draait)

- Findings: Een Pulse-run kan even duren, en wie naar een andere pagina ging zag niets meer van de lopende run; de knop op de Pulse-pagina bleef na terugkomen ook gewoon klikbaar.
- Conclusions: De status "Pulse draait" hoort bij de hele app, niet bij de pagina die de run startte: een klein gedeeld object (`useSyncExternalStore`) dat de run bijhoudt zolang het verzoek loopt. Zacht pulseren (dekking 1 naar 0,4 in 1,8 s) in plaats van een spinner, en niet bij "verminderde beweging".
- Actions: `frontend/src/pulseActivity.ts` (nieuw: `trackPulse`, `usePulseRunning`), `pages/PulsePage.tsx` (gebruikt de gedeelde status, ook voor de uitgeschakelde knoppen), `layout/AppShell.tsx` (`NavItem.busy`), `App.tsx`, `index.css` (`.nav-busy`); validated met `npm run build` en in de browser met een kunstmatig vertraagd run-verzoek (icoon en tekst pulseren, ook op een andere pagina, en stoppen na afloop).

## 2026-10-02 (Leesvenster: slepen over een PDF liep vast)

- Findings: Bij een PDF in het leesvenster ging het verbreden of versmallen door te slepen mis: zodra de muis boven de PDF-viewer kwam, ving die (een iframe, een eigen document) de muisgebeurtenissen op. De pagina kreeg geen `mousemove` meer en ook geen `mouseup`, dus het slepen bleef hangen.
- Conclusions: De iframe moet tijdens het slepen niet voor de muis bestaan; een eigen toestand `dragActive` is genoeg en houdt de rest van de sleeplogica ongewijzigd.
- Actions: `frontend/src/components/ReadingPane.tsx` (`dragActive`: tijdens het slepen krijgt de iframe `pointer-events: none`); validated in de browser: de rand over de PDF heen slepen verkleinde het venster tot het minimum en het slepen eindigde netjes.

## 2026-10-02 (Vormgeving: zachtere, afgeronde look)

- Findings: De app had scherpe, platte vlakken: vierkante-ish kaarten (`rounded-lg` met alleen een schaduw), een zijbalk met harde scheidingslijnen en een content-gebied dat tegen de rand van het venster plakte. Gevraagd: meer afgeronde hoeken in de stijl van een voorbeeldafbeelding, alleen het uiterlijk.
- Conclusions: Eén wijziging in de bouwstenen in plaats van per pagina. De zijbalk staat zonder kader op de paginakleur, het hele werkgebied (kop, pagina, leesvenster, context) is één afgeronde witte plaat met een dunne rand en lichte schaduw, kaarten krijgen `rounded-2xl` met een rand, knoppen en velden `rounded-lg`, badges zijn pillen. De actieve menu-item is een witte, afgeronde pil. In het donkere thema bleef de afspraak: geen `backdrop-filter` op kaarten of op de plaat (dat breekt de `position: fixed`-dialogen); de kaartregel in `dark.css` wijst nu naar een eigen klasse `.card` in plaats van naar de losse Tailwind-klassen.
- Actions: `frontend/src/components.tsx` (Card met klasse `card`, Badge, Button; de secundaire knop is wit met rand), `layout/AppShell.tsx` (zijbalk, plaat, menu-items), `dark.css` (`.card`), en `rounded` naar `rounded-lg` en `rounded-lg` naar `rounded-2xl` in alle schermen en dialogen; validated met `npm run build` en in de browser in het lichte en donkere thema (documenten, instellingen, mapkiezer).

## 2026-10-02 (Leesvenster start op 40% van het scherm)

- Findings: Het leesvenster begon op een vaste 480 px: op een groot scherm te smal om een document echt te lezen, op een klein scherm te breed ten opzichte van de rest.
- Conclusions: De beginbreedte hoort bij het scherm: 40% van de vensterbreedte, nooit onder het minimum van 288 px. De pagina ernaast mag nooit dichtgedrukt worden, ook niet als het venster smal is (CSS `max-width` in plaats van alleen bij het slepen te begrenzen). De opslagsleutel is `.v2`, anders zou een eerder gesleepte of een oude breedte de nieuwe standaard verbergen; de enige gevolg is dat iedereen één keer opnieuw op 40% begint.
- Actions: `frontend/src/components/ReadingPane.tsx` (`defaultWidth`, `WIDTH_KEY` v2, `maxWidth`), `apollo-delphi-user.md`; validated met `npm run build` en in de browser: 1280 px breed geeft 512 px (precies 40%), 900 px breed geeft 298 px zodat de pagina 320 px houdt.

## 2026-10-02 (Contextkolom schuift zacht open en dicht)

- Findings: De rechter contextkolom verving bij het in- en uitklappen in één keer de smalle strook door het paneel: een harde sprong in de indeling.
- Conclusions: Eén element dat tussen strook en paneel van breedte verandert (300 ms, ease-out), met een korte crossfade van de inhoud. Het paneel houdt zijn eigen vaste breedte binnenin, zodat de tekst niet herschikt terwijl het beweegt. Het paneel wordt eerst onzichtbaar geplaatst en 20 ms later zichtbaar gemaakt (er moet iets zijn om vanaf te faden), en pas 350 ms na het sluiten uit de pagina gehaald, zodat de inhoud tijdens het sluiten niet verdwijnt. Een gesloten paneel is `inert` en `aria-hidden` (geen focus, geen schermlezer). Bij "verminderde beweging" geen animatie.
- Actions: `frontend/src/layout/AppShell.tsx` (`panelMounted`, `panelShown`, één omhullend element met `transition-[width]`); validated met `npm run build` en in de browser: de volgorde onzichtbaar geplaatst, zichtbaar, breedte-overgang van 300 ms bij openen en sluiten, en daarna weg. De snelheid van de animatie zelf kon ik niet op beeld zien: het browservenster werd tijdens de test niet getekend.

## 2026-10-02 (Contextkolom: strook blijft staan en schuift het leesvenster op)

- Findings: Bij het openen van de contextkolom verdween de smalle strook met de titel ("Document details"), en het paneel drukte vooral de pagina en het leesvenster samen zonder dat duidelijk was wie opzij ging; sluiten kon alleen met een kruisje in het paneel.
- Conclusions: De strook blijft altijd staan aan de rechterrand; het pijltje draait om (‹ open, › sluit) en de hele strook is de knop. Het paneel schuift links van de strook open (breedte-overgang van 300 ms) en duwt het leesvenster als geheel naar links; de pagina (kolom 2) wordt smaller. Het leesvenster behoudt zijn breedte zolang de pagina niet onder 240 px komt; pas daarna geeft het leesvenster mee (tot zijn minimum van 288 px), zodat op een klein scherm niets over elkaar valt. Voor het slepen is de rechterrand van het leesvenster het vaste punt, want rechts ervan zit nu het paneel.
- Actions: `frontend/src/layout/AppShell.tsx` (strook als `button` met `aria-expanded`, paneel ervoor, `main` minimaal 240 px, kruisje in het paneel weg), `frontend/src/components/ReadingPane.tsx` (geen vaste `shrink-0`/`maxWidth` meer, `minWidth`, slepen rekent vanaf de rechterrand van het venster en trekt de breedte van het paneel af, `MIN_PAGE_WIDTH` 240), `apollo-delphi-user.md`; validated met `npm run build` en in de browser (zonder overgangen gemeten, 1280 px breed): dicht pagina 486 en leesvenster 512; open pagina 240, leesvenster 374, paneel 384, strook 32; volgorde van links naar rechts pagina, leesvenster, paneel, strook. Een schermafbeelding lukte niet (het venster werd niet getekend).

## 2026-10-02 (Leesvenster: 40% als aandeel van het venster, niet als pixels)

- Findings: De beginbreedte van 40% werd één keer in pixels uitgerekend bij het eerste tekenen. Kreeg het venster van de desktop-app pas daarna zijn echte (grotere) afmeting, bijvoorbeeld door maximaliseren, dan bleef het leesvenster op de kleine pixelwaarde staan en was het geen 40% meer.
- Conclusions: Bewaar en gebruik de breedte als aandeel van het venster (0,4), en reken hem bij elke wijziging van de vensterbreedte opnieuw uit; ook wat je zelf sleept wordt als aandeel onthouden. Zo klopt de verhouding altijd, ongeacht hoe groot het venster wordt. Nieuwe opslagsleutel (`apollo.reader.share`), omdat de oude pixelwaarden anders het nieuwe standaardaandeel zouden verbergen.
- Actions: `frontend/src/components/ReadingPane.tsx` (`share` en `viewport` in plaats van `width`, `resize`-luisteraar, slepen slaat `px / venster` op), `apollo-delphi-user.md`; validated met `npm run build` en in de browser: bij 900 px breed 360 px (40%); na een resize-gebeurtenis bij 1600 px 640 px (40%). De emulatie van het browservenster stuurt zelf geen echte resize-gebeurtenis, dus die heb ik met de hand verstuurd.

## 2026-10-02 (Delphi Pulse: alles accepteren/negeren en documenten lezen)

- Findings: Na een Pulse-run moest elk voorstel apart beslist worden (bij een hele map tientallen klikken), en het document achter een voorstel was niet te lezen zonder naar de Documents-pagina te gaan.
- Conclusions: Eén backend-aanroep per beslissing voor de hele werkmap, in één transactie (alles of niets), in plaats van de frontend N verzoeken te laten doen die halverwege kunnen mislukken. De beslissing wordt vooraf gecontroleerd (ook zonder voorstellen). Omdat accepteren de metadata van documenten verandert en geen eenvoudige ongedaanmaker heeft, vragen beide knoppen eerst een bevestiging. Een genegeerd voorstel komt alleen terug bij een gewijzigd document of "Alles opnieuw" (de hash van het laatste voorstel telt, ongeacht de beslissing); dat staat in de bevestiging. Het document openen werkt zoals op de Documents-pagina: klik op het voorstel, en ook de verbonden documenten zijn klikbaar.
- Actions: `backend/app/services/pulse/service.py` (`_apply`, `decide_all`), `app/api/pulse.py` (`POST /workspaces/{id}/pulse/decision`), `app/schemas/pulse.py` (`PulseDecideAllOut`), `tests/integration/test_pulse.py` (accepteren per werkmap, negeren verandert niets, validatie en 404); `frontend/src/api.ts` (`decideAllPulse`), `pages/PulsePage.tsx` (knoppen met bevestiging, klikbare voorstellen en verbindingen, geselecteerd voorstel gemarkeerd), `apollo-delphi-user.md`; validated met de Pulse-tests en in de browser: klik op een voorstel toont het document in het leesvenster, annuleren verandert niets, bevestigen ruimt de lijst en de backend op.

## 2026-10-02 (Pulse-beslissingen worden vastgelegd in de git-werkmap)

- Findings: Een werkmap is een git-map, maar alleen uploads werden daarin vastgelegd. Accepteren of negeren van een Pulse-voorstel (ook "alles") veranderde alleen de database; het resultaat van een accepteren (thema's en verbanden in de metadata van het document) en het feit dat iemand iets afwees waren daarna nergens meer terug te vinden.
- Conclusions: Elke beslissing is een eigen commit, zoals elke upload dat al is. De inhoud staat in één bestand dat alleen aangevuld wordt, `Decisions/decisions.jsonl` (één JSON-regel per beslissing: moment, document, beslissing, samenvatting, thema's en verbanden, met bestandsnamen in plaats van database-id's, zodat het leesbaar is zonder de database). "Alles" is één commit met een lijst van de documenten in het bericht, niet N commits. Alleen dat ene pad wordt gestaged (zoals de rest van `workspace_repo`: nooit `-A`, nooit herschrijven, nooit pushen). Falen van git mag een beslissing niet ongedaan maken: de beslissing staat dan wel in de database en er komt een waarschuwing in het log, hetzelfde als bij uploads. Een oudere werkmap zonder map krijgt die alsnog.
- Actions: `backend/app/services/workspace_repo.py` (`record_decisions`, `DECISIONS_DIR`/`DECISIONS_FILE`), `app/services/pulse/service.py` (`_log_to_repo`, aangeroepen na `decide` en `decide_all`), `tests/integration/test_pulse.py` (één beslissing is een commit, "alles" is één commit met een regel per voorstel, falend git draait niets terug), `apollo-delphi-user.md`; validated met de tests en met een echte werkmap: "Alles accepteren" gaf één commit `Pulse: accepted 3 suggestions` met drie regels in het bestand en een schone werkmap. Eerder genomen beslissingen worden niet achteraf vastgelegd.

## 2026-10-02 (Delphi Pulse stelt ook typemappen en groepen voor)

- Findings: Pulse stelde alleen thema's en verbanden voor. Documenten bleven in `Inbox/` staan, en er was geen indeling in onderwerpen (bij Gaia: architectuur, besluiten, gebruik).
- Conclusions: Twee soorten indeling, allebei een voorstel dat de gebruiker accepteert. (1) Een typemap op schijf in de git-werkmap, uit een vaste lijst (Drafts, Reports, Chapters, Notes, Specs, Reference, Other) waar het model een nieuwe naam mag voorstellen als niets past; bij accepteren verhuist het bestand van `Inbox/` ernaast (Inbox blijft de instroommap, submappen blijven behouden, een bezette naam krijgt een nummer, nooit overschrijven). (2) Een groep: een virtuele map, alleen in de database (`documents.group_name`), een groep per document, met de bestaande groepen in de prompt zodat verwante documenten dezelfde naam delen. Het verhuizen gebeurt pas nadat de beslissing is opgeslagen, en alle verhuizingen van een "alles accepteren" zijn één commit: een git-probleem laat de beslissing staan en het bestand waar het was. Het bestand in `uploads/` (waar het document uit gelezen wordt) verandert niet, dus lezen, zoeken en indexeren blijven werken. De mock-LLM gebruikt trefwoorden voor de map en de bovenliggende map van het bestand als groep, zodat dit zonder echt model te testen is.
- Actions: migratie `a7d3e9c5b214` (kolommen `pulse_items.folder`/`group_name` en `documents.group_name`, met index); `backend/app/services/workspace_repo.py` (`TYPE_FOLDERS`, `clean_folder_name`, `move_into_folders`); `app/services/pulse/service.py` (prompt, opschonen, mock, `_move_files`, groep zetten bij accepteren, map en groep in het beslissingenlog), `app/api/pulse.py`, `app/schemas/pulse.py` en `documents.py` (`folder`, `folder_is_new`, `group`, `group_name`, `inbox_path`), `app/api/search.py` (`group`); `frontend/src/api.ts`, `pages/PulsePage.tsx` (Map en Groep bij elk voorstel, tekst in de bevestiging), `pages/DocumentsPage.tsx` (koppen per groep en een filter), `pages/SearchPage.tsx` (groepskeuze); 8 nieuwe tests; validated met de volledige tests, een migratie op een lege SQLite-database en in de browser met de Gaia-documentatie (36 documenten): 36 voorstellen met groepen architectuur, besluiten, gebruik en oud, "alles accepteren" gaf twee commits (`Move 36 documents into type folders` en `Pulse: accepted 36 suggestions`) en Documents toonde de vier groepen met een filter.

## 2026-10-02 (Analyse per groep: een, twee of alles)

- Findings: Een analyse deed altijd de hele werkmap. Bij een grote verzameling is dat veel werk, en tegenstrijdigheden tussen documenten over heel verschillende onderwerpen zijn meestal ruis. Met de groepen (virtuele mappen) van Delphi Pulse is er nu een natuurlijke indeling.
- Conclusions: De analyse krijgt een optionele selectie van groepen: een, twee, meer of alles, vrij te kiezen (geen vaste stap van twee). De claims, open vragen en tegenstrijdigheden worden dan alleen binnen de gekozen documenten gezocht; kies je twee groepen, dan kunnen die onderling nog wel tegenspreken. Een onbekende groep analyseert niets (valt dus niet terug op alles), en de groep van een andere werkmap telt niet mee. `__none__` kiest de documenten zonder groep, dezelfde waarde als bij zoeken. De gekozen groepen worden in de statistieken van de run bewaard, zodat te zien blijft waarop een analyse betrekking had.
- Actions: `backend/app/services/analysis/service.py` (`run_analysis(..., groups)`), `app/api/analysis.py` (`groups` als herhaalbare queryparameter), `app/schemas/common.py` (`AnalysisStats.groups`), `tests/integration/test_analysis_groups.py` (6 tests: alles, een groep, twee groepen, zonder groep, onbekende groep, andere werkmap); `frontend/src/api.ts` (`runAnalysis(workspaceId, groups)`), `pages/AnalysisPage.tsx` (keuzeknoppen Alles en per groep met aantallen, een regel over wat er geanalyseerd wordt, "beperkt tot" bij de laatste run); validated met de tests en in de browser met de Gaia-documentatie: architectuur en besluiten samen gaf 18 documenten.

## 2026-10-02 (Grotere tekst; datum en tijd van de laatste Pulse-run)

- Findings: De tekst (`text-sm`, 0,875rem) was in de hele app aan de kleine kant, en op de Delphi Pulse-pagina stond alleen dat er een laatste run was, niet wanneer. Verder bleek dat datums van de API (bij SQLite zonder tijdzone, in UTC) door de browser als lokale tijd werden gelezen en dus uren afweken.
- Conclusions: Alle tekstgroottes in dezelfde verhouding groter, zodat `text-sm` 1rem wordt (factor 8/7): `text-xs` 0,857rem, `text-base` 1,143rem, `text-lg` 1,286rem, enzovoort, met meeschalende regelhoogtes. Dit staat op één plek, de Tailwind-configuratie, en berekend uit de standaardwaarden van Tailwind (dus ook `text-2xl` en groter), in plaats van de wortelfontgrootte te vergroten: dat zou ook afstanden en breedtes (zijbalk, panelen) laten groeien, en gevraagd was alleen de tekst. De tekstgroottes die in pixels waren geschreven (10, 11 en 13 px) en de opgemaakte leesweergave (14 px) gingen mee met dezelfde factor; de basistekst (`body`) ook, zodat velden en knoppen zonder eigen klasse meegroeien. Voor de datum: `serverDate()` leest een datum zonder tijdzone als UTC, en wordt ook op de Documents-pagina gebruikt (de kolom Uploaded had dezelfde afwijking).
- Actions: `frontend/tailwind.config.js` (`fontSize` geschaald uit `defaultTheme`), `src/index.css` (`body` met `text-base`, `.reader-prose` 16 px), `text-[10px]/[11px]/[13px]` naar 11,4/12,6/14,9 px in `ReadingPane.tsx`, `AppShell.tsx`, `AskPage.tsx`, `ModelPicker.tsx`; `src/api.ts` (`serverDate`), `pages/PulsePage.tsx` (datum en tijd van de laatste run, afgerond of gestart), `pages/DocumentsPage.tsx`, `apollo-delphi-user.md`; validated met `npm run build` en in de browser: `text-sm` is 16 px, `text-lg` 20,6 px, de basis 18,3 px; de laatste run toont "2 okt 2026, 03:13" voor een run van 01:13 UTC (tijdzone Amsterdam). Opgemerkt: op een smal venster met het leesvenster op 40% scrolt de documententabel horizontaal; dat was al zo, nu iets eerder.

## 2026-10-02 (De werkwijze als stappen in de kop: Importeren, Delphi Pulse, Analyse)

- Findings: Wat je in welke volgorde doet (importeren, Pulse laten indelen, daarna analyseren) was nergens in de app te zien; het menu toont de pagina's alleen als lijst, met Pulse apart onder de streep. En Analyse per groep heeft alleen zin als er groepen zijn.
- Conclusions: Een korte stappenbalk in de kop, in de volgorde van het werk: Importeren, Delphi Pulse, Analyse, elk een knop naar zijn pagina, met een vinkje als de stap gedaan is (documenten aanwezig; groepen aanwezig). Analyse is uitgeschakeld zolang er geen groep is, met als uitleg in de tooltip wat je eerst moet doen. Het menu links blijft zoals het was: de balk is de begeleiding, het menu de gewone navigatie, en de Analysis-pagina zelf werkt ook zonder groepen (dan voor de hele werkmap). Of de menu-ingang ook geblokkeerd moet worden is een keuze van de gebruiker. De staat (documenten, groepen) wordt bij elke paginawissel en werkmapwissel opnieuw bekeken en direct nadat Pulse iets accepteert of negeert (een gebeurtenis `apollo:groups-changed`), anders zou Analyse pas bij de volgende paginawissel opengaan.
- Actions: `frontend/src/layout/AppShell.tsx` (`FlowStep`, de balk met nummers, vinkjes en pijltjes; verborgen onder `lg`), `src/App.tsx` (`hasDocuments`, `hasGroups`, `refreshFlow`), `src/pulseActivity.ts` (`GROUPS_CHANGED`), `src/pages/PulsePage.tsx` (stuurt de gebeurtenis na een beslissing), `apollo-delphi-user.md`; validated met `npm run build` en in de browser met een werkmap met 4 voorstellen: in het begin Analyse uitgeschakeld met uitleg; na een voorstel accepteren werd Analyse actief en kreeg Delphi Pulse een vinkje; een klik op Analyse opende de pagina met de groepen.
