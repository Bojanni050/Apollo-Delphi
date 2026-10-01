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
