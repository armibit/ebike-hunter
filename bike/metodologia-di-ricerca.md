# Algoritmo di ricerca annunci — v2.10

Versione 2 del 16/09/2026, nata da una review con 5 revisori indipendenti (ricercatore di progetti esistenti, ingegnere di search e pipeline dati, meccanico di e-bike usate in Ticino, product designer di agenti con apprendimento, revisore rischi/compliance). **v2.1**: criteri confermati dall'utente lo stesso giorno (Parte C). **v2.2**: estesa la copertura ai negozi fisici/online di Milano, Como, Varese, Bergamo (Parte C, decisione #15). **v2.3**: aggiunti data di pubblicazione dell'annuncio e parere sincero di Claude a ogni candidata (A14); ampliato il glossario di ricerca con marche mancanti come Fantic, individuate a causa di un annuncio non trovato (Parte C, decisione #16-17). **v2.4**: la ricerca di categoria pura (senza parole chiave di marca) diventa il metodo primario su ogni fonte, non solo una rete di sicurezza; chiarito che un motore con marca non identificabile dal testo non è mai motivo di scarto automatico; chiarito e reso esplicito il limite sull'elusione dei blocchi anti-bot (Parte C, decisione #18). **v2.5 (22/09/2026)**: riconciliati tre criteri rigidi rimasti disallineati dalle istruzioni di progetto e dalle decisioni più recenti dell'utente — budget portato a 1500-2200 CHF, coppia minima portata a 65 Nm, tipo di telaio aggiornato a "fully preferita, hardtail solo per offerta eccezionale" (Parte C, decisione #19, richiesta esplicita dell'utente). **v2.6 (22/09/2026, stesso giorno)**: risposta a un secondo audit esterno — aggiunta una tabella normativa unica per coppia/batteria/tipo telaio richiamabile ovunque (B2); formalizzata in condizioni operative concrete la regola "hardtail solo per offerta eccezionale" (B2); chiarita la policy sui motori proprietari/non riconosciuti (B2, B4); attivate le regole R-009 (freni dedotti dal modello, con distinzione esplicita tra dato scritto e dato dedotto) e R-012 (🟡 su tre livelli di priorità) proposte in "Apprendimento"; introdotta in A12 la regola di ordinamento che impedisce a un 🟡 con dati incompleti di superare un 🟢 nella dashboard solo per il punteggio numerico (Parte C, decisione #20). **v2.7 (22/09/2026, stesso giorno)**: la regola di ordinamento A12 è stata implementata nella dashboard (non più solo documentata) come nuovo ordinamento predefinito "Priorità (classificazione)"; verificato e corretto un punto del riepilogo per l'utente sul pulsante "Non mi interessa", che sulla dashboard pubblicata su claude.ai già salva lo stato in modo persistente (Parte C, decisione #21). **v2.8 (22/09/2026, stesso giorno)**: assegnato automaticamente il livello di priorità R-012 (🟡-A/B/C) alle 118 candidate 🟡 già in dashboard, contando i dati decisivi mancanti nel testo di ciascun annuncio — è una classificazione euristica esplicitamente marcata come tale nell'interfaccia, non una revisione manuale annuncio per annuncio (Parte C, decisione #22). **v2.9 (22/09/2026, stesso giorno)**: introdotta A16 — quando una valutazione tecnica su un componente (forcella, motore, freni, ecc.) è incerta, si verifica con una ricerca web invece di rispondere a memoria/per intuito, e lo si segnala; il parere sincero (A14) deve restare onesto anche quando la valutazione è negativa o mediocre, non solo quando è positiva (richiesta esplicita dell'utente). **v2.10 (22/09/2026, stesso giorno)**: la Moustache Samedi 29 (Cadenazzo) è stata confermata da fonte diretta (link fornito dall'utente, verificato con WebFetch) e riclassificata da 🟡 a 🟢 in dashboard, rating 9.2 — vedi Parte C, decisione #23.

È diviso in due parti:

- **Parte A — Motore**: vale per qualsiasi caccia, oggi e-MTB, domani auto o mobili.
- **Parte B — Pacchetto e-MTB**: criteri, conoscenze tecniche, red flag specifiche.

---

# PARTE A — MOTORE (indipendente dal dominio)

## A0. Regole invalicabili

1. Mai contattare venditori, inviare messaggi, fare offerte, aggiungere ai preferiti o acquistare senza approvazione esplicita per quella singola azione. Le ricerche salvate con notifica sugli account dell'utente si creano solo dopo che l'utente ha approvato l'elenco preciso.
2. Mai fare login, inserire credenziali, codici 2FA o dati di pagamento. Se un sito chiede di accedere, lo fa l'utente.
3. Stop immediato su captcha, richiesta di login, "attività insolita", errori 403/429. Niente ritentativi automatici; va segnalato all'utente.
4. Il fetch automatico rispetta robots.txt. Il browser dell'utente si usa solo in sessioni avviate dall'utente, a ritmo umano: al massimo 1 ricerca e circa 20 pagine per fonte per sessione, pause di almeno 10 secondi, niente paginazione profonda, niente esecuzioni in parallelo. Mai usare il browser per aggirare sistematicamente un blocco.
5. Dati minimi: si salvano URL, prezzo, modello, specifiche, taglia, località (comune o CAP), date. Il nome del venditore si salva solo se serve (negozi; privati con cui è in corso un contatto o una trattativa). Niente telefoni, foto, descrizioni integrali (al massimo la frase-prova di una specifica). Annunci scartati o spariti si riducono a dati aggregati dopo 60 giorni.
6. Mai ripubblicare annunci: in qualsiasi pagina condivisa compaiono solo link e sintesi propria.
7. Dati tecnici solo dal testo scritto. Ciò che viene da foto o da deduzione è marcato come ipotesi incerta, con il livello di confidenza.
8. L'apprendimento può solo proporre regole; non diventano attive senza conferma. **Non si impara mai ad aggirare blocchi, captcha o sistemi anti-bot** — questa è una regola invalicabile, non un'opzione di ottimizzazione: vedi A15 per come si concilia con la richiesta di copertura esaustiva.
9. Prima di sovrascrivere un documento del progetto: rileggerlo, costruire la versione nuova completa, verificare che non perda righe esistenti. Mai scrivere contenuti di prova su un documento reale.
10. **Tutto va sempre tradotto in italiano** (16/09/2026, richiesta dell'utente): quando un annuncio è in tedesco, francese o altra lingua, le frasi salvate in note/stato/descrizione si scrivono in italiano, mai lasciate nella lingua originale (né come testo principale né come citazione tra virgolette senza traduzione). Fa eccezione solo il nome proprio del modello/prodotto, che non si traduce.

## A1. Gerarchia delle fonti (dalla più affidabile e meno rischiosa)

| Livello | Tipo                                                                            | Uso                                                                                                                                                                         |
| ------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1       | **Ricerche salvate native delle piattaforme** (notifiche email/push all'utente) | Copertura continua e immediata, senza scraping. L'utente riceve le notifiche direttamente; se l'email è collegata a Claude, lo scout può leggerle nelle ricerche periodiche |
| 2       | **URL di ricerca salvati** aperti nel browser dell'utente, ordinati per data    | Sessioni avviate dall'utente, per coprire ciò che le notifiche non coprono                                                                                                  |
| 3       | **Pagine "usato/occasioni" dei negozi** (fetch normale, basso rischio)          | A ogni run, con controllo "pagina cambiata?"                                                                                                                                |
| 4       | **Sidebar "annunci simili"** delle pagine di dettaglio dei migliori candidati   | Fonte aggiuntiva e misura della recall                                                                                                                                      |
| 5       | **Ricerca web generica**                                                        | Solo per scoprire nuovi negozi e modelli, mai come fonte di annunci: restituisce annunci vecchi e spesso già rimossi                                                        |

## A2. Ciclo di una ricerca (checklist obbligatoria)

1. **Carica lo stato**: leggere questo documento, il pacchetto di dominio (Parte B), il documento "Apprendimento", il log annunci.
2. **Controlla la salute delle fonti**: per ogni fonte registrare "ok / bloccata / 0 risultati". Se una fonte che di solito dà più di 10 risultati ne dà 0, è un guasto dello strumento, non un mercato vuoto: va detto.
3. **Scopri**: per ogni fonte, **prima la ricerca di categoria pura** (vedi A15), poi le query per marca/linea note (A10). Estrarre dalla pagina dei risultati, in un solo passaggio, **URL, ID nativo, titolo, prezzo, località, data** (estrazione dagli elementi della pagina via script, non dal solo testo, che perde i link). **Il link si salva nel momento della scoperta.**
4. **Pre-filtro economico**: scartare subito solo ciò che è certamente fuori (prezzo oltre il tetto, o già noto nel log).
5. **Estrai il dettaglio** degli annunci rimasti: testo, specifiche, **data di pubblicazione dell'annuncio** (vedi A14), **anno modello/produzione** (vedi A13); raccogliere i link della sidebar "simili" e rimetterli in coda (provenienza = simili).
6. **Normalizza**: taglia su scala unica, motore in famiglia + generazione, prezzo in CHF (EUR convertiti, più IVA svizzera 8,1% e trasporto per l'Italia); tutto il testo tradotto in italiano (A0.10).
7. **Filtri rigidi — solo motivi grossi.** Si scarta unicamente per: non elettrica, motore al mozzo o generico (marca riconosciuta e nota per essere esclusa, es. Bafang/Ananda/Dapu), kit fai-da-te, 45 km/h, taglia dichiarata diversa da M, prezzo fuori tetto, coppia dichiarata sotto la soglia minima, truffa sospetta. **Tutti i dettagli di componentistica (marca sospensioni, gruppo cambio, freni non specificati, km alti, anno) influenzano il punteggio, non lo scarto. Una marca motore non identificabile dal testo (né ammessa né esplicitamente esclusa) non causa mai lo scarto automatico — vedi A15.** Un dato sconosciuto non causa mai lo scarto. Serve una prova che sia davvero elettrica (Wh, Nm, nome motore, "Akku/batteria"): la parola "e-bike" nel titolo non basta.
8. **Red flag**: truffa o furto sospetto → 🔴 con motivo, sopra qualsiasi punteggio.
9. **Punteggio**: giudizio 1-10 sulle preferenze (formula concreta in A12). I campi dedotti o mancanti valgono meno.
10. **Classifica**: 🟢 passa tutto con dati scritti · 🟡 passa ma manca un dato decisivo → escalation (A6) · 🔴 escluso con codice motivo.
11. **Scrivi il parere sincero** (A14): una valutazione onesta della bici in sé, considerando anche le foto quando accessibili, distinta dal codice di classificazione 🟢/🟡/🔴.
12. **Deduplica** (A4).
13. **Registra** nel log (A5) e aggiorna le statistiche in "Apprendimento" (A7).
14. **Riferisci all'utente**: digest breve (A8), con le domande "da decidere insieme".

## A3. Scheda annuncio (schema dati)

```
uid              fonte:id_nativo   (es. tutti:82351319)
fonte, url, titolo
prezzo, valuta, prezzo_chf_stimato (incl. IVA/trasporto se estero), trattabile
localita, distanza_da_lugano_km
marca, modello, anno (vedi A13: sempre valorizzato, anche solo con "non recuperabile" o "non indicato")
per ogni specifica (motore, coppia_nm, batteria_wh, freni, forcella, ammortizzatore, taglia, km):
   valore · confidenza: scritto | dedotto_da_modello | ipotesi_da_foto | sconosciuto · prova: "frase citata" (tradotta in italiano, A0.10)
data_pubblicazione_annuncio (vedi A14: sempre riportata quando il sito la mostra, con formato leggibile es. "04/09/2026, ore 10:17"; se non disponibile: "non mostrata dal sito")
prima_vista, ultima_vista, ultima_verifica
disponibilita: attivo | sparito | venduto
esito: 🟢 | 🟡 | 🔴 · codice_motivo (TAGLIA, PREZZO, MOTORE_MOZZO, MOTORE_GENERICO, COPPIA, NON_ELETTRICA, 45KMH, TRUFFA_SOSPETTA, NON_MTB, MARCA_ESCLUSA, MARCA_SCONOSCIUTA_DA_VERIFICARE...)
punteggio (1-10, vedi A12), provenienza (notifica | url_salvato:<nome> | simili_di:<uid> | negozio:<nome> | categoria_pura:<fonte>)
parere_sincero (vedi A14: valutazione onesta in linguaggio naturale, incl. foto quando accessibili)
venditore (solo se serve, vedi A0.5)
gruppo_duplicati, id_run
decisione_utente (contatta | tieni | scarta:<motivo>) + data
```

## A4. Deduplica

- **Esatta**: stesso uid.
- **Stessa bici su più siti** (tutti/Ricardo/Anibis appartengono allo stesso gruppo e probabilmente condividono inventario): marca + modello + anno + taglia normalizzati, prezzo entro ±5%, stessa località → stesso gruppo; conferma visiva manuale se dubbio.
- **Annuncio ripubblicato**: stesso gruppo con uid nuovo → aggiornare le date, non creare un nuovo candidato.

## A5. Log

- Il log è **accodato**, mai riscritto da capo a mano: le righe esistenti non si cancellano, cambiano solo stato e date.
- Ogni run aggiunge un blocco con data, fonti controllate e loro stato, numeri (visti / nuovi / spariti / 🟢 / 🟡 / 🔴).
- Il "Riepilogo completo" è la vista ragionata per l'utente e si aggiorna dal log, non il contrario.
- Controllo qualità: percentuale di annunci senza URL = deve essere 0%.

**Nota sulla violazione e correzione del 22/09/2026**: il documento "Annunci trovati - log per data" è stato riscritto per intero due volte lo stesso giorno (per correggere le note in cima e per la riclassificazione), e nella prima riscrittura le sezioni di dettaglio dei run del 19/09 mattina e del 18/09 sera sono state condensate in un riassunto, violando questa stessa regola A5. Corretto aggiungendo in coda al log un blocco "Rettifica audit — 22/09/2026" (vedi il log stesso) invece di continuare a riscrivere il documento: **da qui in avanti, ogni correzione al log va sempre accodata in fondo, mai reintrodotta riscrivendo il documento intero**, anche quando serve correggere note in cima — si aggiunge una rettifica che punta alla nota originale, non si riscrive la nota. **Applicato con successo il 22/09/2026 (sera, tardo)**: la conferma della Moustache Samedi 29 tramite fonte diretta è stata accodata in fondo al log come nuovo blocco, senza toccare nessuna sezione precedente.

## A6. Escalation "decidiamo insieme"

Un annuncio va all'utente, invece di essere scartato, quando passa i filtri rigidi su tutto ciò che è scritto ma manca un dato decisivo. Per ognuno si mostra solo:

- titolo, prezzo, località, link;
- checklist dei criteri con ✔ / ✖ / ❓ e da dove viene ogni dato;
- **una sola domanda**;
- 3 risposte rapide: **Chiedi al venditore** (lo scout prepara una bozza di messaggio con le domande mancanti, che l'utente invia lui stesso) · **Tieni in osservazione** · **Scarta** (con motivo: prezzo / km / distanza / venditore / estetica / altro).

Il motivo dello scarto è il dato che alimenta l'apprendimento.

## A7. Apprendimento (senza machine learning)

Si registra nel documento "Apprendimento": resa delle query, resa delle fonti, motivi di scarto, decisioni utente, regole proposte, prezzi osservati, negozi e fonti nuove, marche mancanti dal glossario, annunci a marca sconosciuta tenuti (A15). Vedi `apprendimento-regole-e-statistiche.md` per il dettaglio corrente.

**Protezioni contro la deriva**: nessuna regola attiva senza conferma; una regola può spostare da 🟡 a 🔴 ma non cancella mai dal log; ogni regola ha una scadenza; periodicamente si mostra all'utente un campione degli scartati in automatico ("ti sei perso qualcosa?"); **i criteri rigidi li cambia solo l'utente** (la riconciliazione del 22/09/2026, decisione #19, rientra in questa regola: è stata fatta su richiesta esplicita dell'utente, non di iniziativa dello scout).

## A8. Digest per l'utente

```
🚲 Caccia e-MTB · 16.09 · 41 visti · 3 nuovi
🟢 [modello] – [prezzo] – [località] – link
   Bosch CX 75Nm ✔ · 500Wh ✔ · idraulici ✔ · taglia M ✔ · km 2500 · anno 2023 · pubblicato 12.09
   🗣️ [parere sincero in una riga]
🟡 [modello] – [prezzo] – [località] – link
   ❓ Taglia non indicata → [Chiedi al venditore] [Tieni] [Scarta]
🔴 12 scartati (8 taglia, 3 motore mozzo, 1 prezzo)
⚠️ Fonti: tutti ok · Subito ok · Facebook non tentato
```

## A9. Misurare se la ricerca migliora

- Annunci trovati solo dai "simili" e da nessuna query: devono diminuire nel tempo.
- Doppio percorso: ricerca per categoria contro ricerca per modello, per stimare quanti annunci esistono davvero.
- Set di controllo di annunci noti ancora attivi: ogni run deve ritrovarli.
- Percentuale di campi "sconosciuto" e "dedotto" per run.
- Annunci segnalati dall'utente ma non trovati dallo scout: ogni caso va analizzato e corretto (vedi A7, caso Fantic del 17/09/2026).

## A10. Query: espansione finita e a costo controllato

- **Livello 0 (sempre, per ogni fonte, a ogni run — non solo rete di sicurezza, vedi A15)**: una ricerca di categoria per fonte (e-bike/e-MTB, fascia prezzo, regione, più recenti), **senza filtro di marca/modello**.
- **Livello 1 (sempre)**: le ~13 linee di prodotto più frequenti del pacchetto di dominio.
- **Livello 2**: marche e linee a coda lunga, solo se il livello 1 ha dato almeno 1 annuncio nuovo e unico.
- Se una query a parole chiave non trova nulla, si riprova con termini alternativi generici prima di concludere che la fonte è vuota — vedi A15.
- Stop per fonte: 3 query consecutive senza annunci nuovi (livello 1/2; la categoria pura di livello 0 si fa comunque a ogni run).

## A11. Script e bot esterni (valutazione del 16/09/2026)

Non si usano bot esterni pronti (AI Marketplace Monitor, subot, SubitoScanner, ricardify, ads-scraper, Secondhand MCP, Marketplace Finder MCP): richiedono un computer sempre acceso, fanno scraping su siti che lo vietano nei termini di servizio, le versioni svizzere sono piccole e probabilmente abbandonate, e replicano quello che fanno già le ricerche salvate native (gratuite, legali, mantenute dai siti). Da rivalutare solo se le ricerche salvate native si rivelano troppo lente/incomplete.

## A12. Giudizio 1-10 (formalizzato 16/09/2026 sera; scaglioni prezzo aggiornati 22/09/2026)

Sei componenti che sommano a 10, calcolati solo su dati scritti nel testo:

| Componente                           | Peso max | Regola                                                                                                                                                                                     |
| ------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Motore (marca + coppia)              | 3.0      | Marca ammessa e Nm scritto ≥75 → 3.0 · 65-74 → 2.7 · marca ammessa ma Nm sconosciuto → 1.5 · marca non verificabile dal testo → 0.4 · marca al mozzo/esclusa o Nm scritto sotto 65 → 0     |
| Taglia                               | 2.0      | M confermata esplicitamente → 2.0 · dedotta da range altezza compatibile senza conflitto → 1.5 · ambigua/in conflitto → 1.0 · non indicata → 0.8 · diversa da M → 0                        |
| Batteria                             | 1.0      | ≥500 Wh → 1.0 · 400-499 Wh → 0.7 · sconosciuta → 0.4 · <400 Wh → 0                                                                                                                         |
| Freni                                | 1.0      | Idraulici confermati dal testo → 1.0 · non specificati → 0.5 · meccanici (scarterebbe comunque) → 0                                                                                        |
| Prezzo vs budget                     | 1.5      | 1500-1800 CHF tutto compreso → 1.5 · sotto 1500 (buon affare) → 1.3 · 1800-2200 CHF (eccezione, pienamente in budget) → 1.0 · oltre 2200 → 0.3                                             |
| Stato/usura (testo + eventuali foto) | 1.5      | Km bassi (sotto ~1500) o nuovo → 1.5 · km medi (1500-4000) con buona manutenzione → 1.2 · usura normale o km 4000-8000 → 0.8 · km molto alti (>8000) o danni evidenti → 0.3 · ignoto → 0.6 |

Il giudizio si calcola per tutti gli annunci in dashboard, incluse le 🔴 scartate. La distanza da Lugano non entra nella formula. Il giudizio va ricalcolato quando cambia un dato di base durante lo STEP DI VERIFICA.

**Tre campi separati, non uno solo (introdotto 22/09/2026, v2.6)**: ogni annuncio ha sempre tre informazioni distinte, che non vanno confuse nell'ordinamento:

- `classificazione`: 🟢 / 🟡 / 🔴 — i filtri rigidi (A2.7);
- `punteggio_tecnico`: il giudizio 1-10 di questa sezione;
- `priorità_operativa`: quanto vale la pena agire su quell'annuncio ora (dipende anche da dati mancanti/da verificare, non solo dal punteggio).

**Regola di ordinamento**: il punteggio numerico da solo non decide mai l'ordine sopra la classificazione. Un 🟡 con un dato decisivo mancante non supera mai un 🟢 in cima alla lista, anche se il suo punteggio calcolato è più alto — il punteggio di un 🟡 riflette solo ciò che è noto, non compensa l'incertezza sul dato mancante. L'ordinamento di riferimento è: (1) classificazione (verde prima di giallo prima di rosso/venduto), (2) completezza dei dati (tutto scritto prima di dati dedotti/mancanti), (3) punteggio tecnico decrescente, (4) prezzo/distanza. **Implementato in dashboard il 22/09/2026 (v2.7)**: l'ordinamento predefinito della dashboard è ora "Priorità (🟢→🟡→🔴), poi giudizio" — ordina prima per classificazione, poi per punteggio tecnico all'interno della stessa classificazione. "Ordina per giudizio" resta disponibile come opzione secondaria nel menu, per chi vuole esplorare per solo punteggio. La componente (2) "completezza dei dati" della gerarchia descritta sopra non è ancora un campo separato in dashboard (resta nel punteggio tecnico, componente per componente) — vedi nota in Parte C tra le voci ancora aperte.

## A13. Anno modello/produzione (16/09/2026 sera)

Ogni annuncio deve avere un campo anno valorizzato (mai vuoto), distinto dalla data di scoperta/pubblicazione: prima dal testo, poi dall'URL, poi con una breve ricerca aggiuntiva se conviene. Va sempre distinto l'anno di produzione/modello dall'anno di acquisto dichiarato dal venditore. Se non recuperabile, si scrive esplicitamente "non indicato"/"non recuperabile".

## A14. Data di pubblicazione e parere sincero (17/09/2026)

**Data di pubblicazione dell'annuncio**: riportata quando il sito la mostra, altrimenti "non mostrata dal sito" — mai confusa con la data di scoperta dello scout.

**Parere sincero**: oltre a 🟢/🟡/🔴 e al giudizio numerico, ogni candidata riceve una valutazione onesta in linguaggio naturale (cosa convince, cosa lascia perplessi, plausibilità di prezzo/venditore, cosa chiedere), incluse le foto quando accessibili. Non sostituisce mai i filtri rigidi né il giudizio numerico. **Onestà anche scomoda (rafforzato 22/09/2026)**: il parere non è un elogio automatico — se una bici è mediocre, sovrapprezzata, con componenti deboli per l'uso dichiarato, o semplicemente non all'altezza di alternative già in lista, il parere lo dice chiaramente, con la stessa cura con cui segnala i punti di forza. Un giudizio numerico alto non deve mai essere accompagnato da un parere tiepido che lo contraddice, e viceversa.

## A15. Scansione esaustiva, non filtrata per marca nota (17/09/2026, richiesta esplicita dell'utente)

Tre regole permanenti, nate dal caso Fantic (annuncio non trovato per gap nel glossario):

1. **La ricerca di categoria pura (livello 0 di A10) è il metodo primario su ogni fonte, a ogni run** — non solo una rete di sicurezza. Le query per marca/modello restano utili per dare priorità, ma non sostituiscono mai una scansione di categoria senza filtro di marca.
2. **Un motore la cui marca non è scritta o non è riconoscibile dal testo non è mai motivo di scarto automatico.** Si distingue sempre: (a) marca esplicitamente esclusa perché nota per essere motore al mozzo/generico (Bafang, Ananda, Dapu...) → scarto legittimo; (b) marca non specificata/non riconosciuta → l'annuncio resta almeno 🟡, punteggio motore ridotto (0.4/3.0), domanda diretta al venditore in escalation. Vale anche per marche mai viste prima nel glossario B4.
3. **Se una query a parole chiave non trova nulla, si riprovano termini alternativi** (mountain bike elettrica, bici elettrica mtb, e-mtb, e-bike fuoristrada) prima di concludere che la fonte non ha risultati.

**Limite esplicito, invalicabile**: questa regola **non** autorizza né implica eludere blocchi anti-bot, captcha, rate limit o altre protezioni (A0.3/A0.4/A0.8 restano assoluti). Quando una fonte blocca il fetch resta segnalata come "bloccata", non si forza l'accesso.

## A16. Conoscenza tecnica: verificare, non inventare (22/09/2026, richiesta esplicita dell'utente)

Questa regola riguarda la conoscenza tecnica generale sui componenti (es. "meglio una forcella da 35 o 36mm per questo uso", "che differenza c'è tra Shimano Deore e SLX", "quel motore ha problemi noti"), distinta dai **dati di uno specifico annuncio** (quelli restano sempre governati da A0.7: solo dal testo scritto, mai dedotti/inventati).

1. Quando una domanda tecnica generale ha una risposta abbastanza consolidata e nota, si risponde direttamente, con sicurezza proporzionata a quanto l'informazione è effettivamente stabile nel tempo.
2. **Quando c'è un dubbio reale** — un componente poco comune, un dato che potrebbe essere cambiato di recente (nuovi modelli, richiami, problemi emersi), o semplicemente incertezza — si fa una ricerca web prima di rispondere, invece di rispondere a memoria per intuito. Non si inventa né si arrotonda un'informazione tecnica per sembrare sicuri.
3. Se dopo la ricerca l'informazione resta incerta o contrastante, lo si dice esplicitamente invece di scegliere una versione a caso.
4. Questa regola vale per le domande dirette dell'utente su un tema tecnico e per i pareri sinceri (A14) quando toccano conoscenze generali sui componenti, non solo per la scheda dati di un annuncio.

---

# PARTE B — PACCHETTO DI DOMINIO: e-MTB Pregassona–Bedano

## B1. Obiettivo e contesto

Pendolarismo Pregassona → Bedano (~7 km a tratta, discesa e poi salita verso Vezia/Cadempino), 4–5 giorni a settimana, più gite su sterrato e sentieri facili. Provata a noleggio Merida eBIG.NINE 675 (Shimano 85 Nm): esperienza molto positiva.

## B2. Criteri (confermati il 16/09/2026, riconciliati il 22/09/2026 — vedi Parte C, decisione #19)

| Criterio   | Regola                                                                                                                                                                                                                                                                                 | Tipo                                              |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Motore     | Centrale Bosch / Shimano / Brose / Yamaha (incl. Giant SyncDrive, base Yamaha)                                                                                                                                                                                                         | Rigido                                            |
| Coppia     | **Preferita ≥75 Nm · minimo ammesso 65 Nm**. Sotto 65 Nm scarto. Se l'annuncio dice solo "Bosch"/"motore centrale" la coppia è sconosciuta: non si deduce e non si scarta                                                                                                              | Soglia rigida a 65 Nm, preferenza nel punteggio   |
| Batteria   | ≥400 Wh (meglio 500+)                                                                                                                                                                                                                                                                  | Rigido solo se dichiarata sotto 400               |
| Freni      | Idraulici                                                                                                                                                                                                                                                                              | Scarto solo se dichiarati meccanici/V-brake       |
| Taglia     | **M** (equiv. 17"–18", 44–48 cm). "S/M" o "M/L" → 🟡                                                                                                                                                                                                                                   | Rigido se dichiarata diversa                      |
| Tipo       | **Fully preferita. Hardtail accettata solo per un'offerta eccezionale** (aggiornato 22/09/2026). Marca forcella/ammortizzatore non è motivo di scarto                                                                                                                                  | Preferenza forte nel punteggio, non scarto rigido |
| Budget     | **1500–2200 CHF, tutto compreso**. Fascia preferita 1500-1800 CHF; 1800-2200 CHF pienamente in budget, "eccezione" nel punteggio                                                                                                                                                       | Rigido oltre 2200                                 |
| Esclusioni | Motori al mozzo, motori generici espressamente riconosciuti (Bafang, Ananda, Megamo, AKM/MOMA Bikes, Dapu/Rock Machine), kit fai-da-te, 45 km/h/S-pedelec, chip di sblocco, marca Urbanbiker. Un motore con marca non scritta/riconosciuta non rientra in questa esclusione — vedi A15 | Rigido                                            |

Principio generale: non scendere nel dettaglio dei componenti per scartare; i dettagli servono a ordinare e a preparare le domande al venditore.

Copertura negozi fisici Milano/Como/Varese/Bergamo (16/09/2026, Parte C #15) oltre ai marketplace online.

**Tabella normativa unica (introdotta 22/09/2026, v2.6)** — questa è l'unica tabella di soglie da richiamare ovunque nel documento e nei record; qualsiasi altro riferimento a soglie diverse (es. 50 Nm, 400 Wh come limite superiore) altrove in questo documento è un residuo storico di versioni precedenti e non è più valido:

```
Coppia <65 Nm              → 🔴 rosso (scarto)
Coppia 65–74 Nm            → ammessa, penalizzata nel punteggio (A12: 2.7/3.0)
Coppia ≥75 Nm              → preferita (A12: 3.0/3.0)

Batteria <400 Wh           → 🔴 rosso (scarto)
Batteria 400–499 Wh        → ammessa, penalizzata nel punteggio (A12: 0.7/1.0)
Batteria ≥500 Wh           → preferita (A12: 1.0/1.0)

Full suspension             → preferita, bonus nel punteggio (non un campo A12 a sé: pesa nello "stato/usura" e nel parere sincero)
Hardtail                    → ammessa solo come eccezione motivata, vedi condizioni sotto
```

**Quando una hardtail è "un'eccezione motivata" (formalizzato 22/09/2026, v2.6)**: una hardtail resta candidata (non scartata) solo se soddisfa TUTTE queste condizioni; altrimenti scende di priorità ma non viene comunque scartata (il tipo di telaio resta una preferenza di punteggio, non un criterio rigido — vedi tabella B2 sopra):

```
- prezzo ≤ 1'700 CHF, oppure ≥300 CHF più economica della migliore full comparabile trovata nello stesso run;
- motore ≥75 Nm (preferenza piena, non solo il minimo di 65 Nm);
- batteria ≥500 Wh;
- taglia M confermata esplicitamente nel testo (non dedotta);
- freni idraulici confermati esplicitamente nel testo;
- nessuna full suspension comparabile (stesso budget, stesso motore/coppia) trovata nello stesso run.
```

Una hardtail che soddisfa tutte le condizioni riceve nota "🏆 eccezione hardtail confermata" ed entra in dashboard con priorità piena. Una hardtail che ne manca solo una o due riceve nota "hardtail sotto lo standard dell'eccezione — valutare solo se le full costano di più" e priorità operativa ridotta, ma resta in lista (mai scartata solo per essere hardtail). Questa distinzione può in futuro diventare un campo dedicato in dashboard (`FULL_PRIORITARIA` / `HARDTAIL_ECCEZIONALE` / `HARDTAIL_BASSA_PRIORITÀ`) invece di una nota testuale, se l'utente lo richiede.

**Policy sui motori non Bosch/Shimano/Brose/Yamaha (chiarita 22/09/2026, v2.6)**: il criterio dell'utente è positivo (cercare Bosch/Shimano/Brose/Yamaha), non negativo ("escludere tutto il resto"). Applicare sempre questa gerarchia:

```
Motore al mozzo o kit di conversione                    → 🔴 rosso
Motore centrale di marca esplicitamente in B4/esclusioni → 🔴 rosso (es. Bafang, Ananda, Dapu, Tongsheng, Panasonic, Fazua, OLI — motori generici noti, non OEM di Bosch/Shimano/Brose/Yamaha)
Motore centrale non identificato dal testo               → 🟡 (vedi A15), mai scarto automatico
Bosch/Shimano/Brose/Yamaha confermato dal testo           → candidato normale, valutato su A12
Motore proprietario del produttore della bici (Specialized, Cannondale, Avinox...) → 🟡 "da verificare", non scarto automatico, finché il testo non conferma o esclude un OEM ammesso al suo interno
```

Escludere in modo definitivo un marchio non ancora in questa lista (es. se l'utente volesse escludere sempre Specialized a prescindere) è una decisione rigida che spetta solo all'utente (A7) — lo scout non la introduce di propria iniziativa.

## B3. Tabella motori

Legenda: ✔✔ preferito (≥75 Nm) · ✔ ammesso (65–74 Nm) · ✖ sotto soglia (<65 Nm, scarto — soglia aggiornata 22/09/2026)

| Motore                                | Anni      | Nm                    | Esito                                                    |
| ------------------------------------- | --------- | --------------------- | -------------------------------------------------------- |
| Bosch Active / Active Plus            | 2014–20   | 48/50                 | ✖                                                        |
| Bosch Performance gen2                | 2014–19   | 63                    | ✖                                                        |
| Bosch Performance gen3                | 2020–22   | 65                    | ✔                                                        |
| Bosch Performance Line (Smart System) | 2022+     | 75                    | ✔✔                                                       |
| Bosch Performance CX gen2/gen3        | 2014–19   | 75                    | ✔✔                                                       |
| Bosch Performance CX gen4/Smart       | 2020+     | 85 (Smart fino a 100) | ✔✔                                                       |
| Bosch Performance SX                  | 2024+     | 55                    | ✖                                                        |
| Shimano E6000/E6100/E7000             | 2014–21   | 50–60                 | ✖                                                        |
| Shimano E8000                         | 2016–21   | 70                    | ✔                                                        |
| Shimano EP8/EP801/EP6/EP600           | 2020+     | 85                    | ✔✔                                                       |
| Shimano EP5                           | 2024+     | 60                    | ✖                                                        |
| Yamaha PW/PW-SE/PW-ST                 | 2014+     | 70                    | ✔                                                        |
| Yamaha PW-X/PW-X2                     | 2017/2020 | 80                    | ✔✔                                                       |
| Yamaha PW-X3                          | 2022+     | 85                    | ✔✔                                                       |
| Yamaha PW-TE/PW-CE                    | 2018+     | 60/50                 | ✖ (Rockrider E-EXPL 520 monta PW-CE — ora sotto soglia)  |
| Giant SyncDrive Pro/Sport/Core        | —         | 80–85/75/60           | ✔✔/✔✔/✖                                                  |
| Brose Drive/S/T, Drive S Mag          | 2015+     | 90                    | ✔✔                                                       |
| Brose Drive C Mag                     | 2019+     | 50                    | ✖ (tipico su Fantic XF2 Integra base — ora sotto soglia) |

Senza anno, niente deduzione. Marca assente dalla tabella non è di per sé motivo di scarto — vedi A15.

## B4. Glossario di ricerca

**Linee principali:** Cube Reaction/Stereo Hybrid · Scott Strike/E-Strike/Aspect eRide · Cannondale Trail Neo/Moterra Neo · Merida eBIG.NINE/SEVEN · Giant Talon E+/Fathom E+ · Trek Powerfly/Marlin+ · KTM Macina · Haibike SDURO/AllMtn/HardNine/HardSeven · Rockrider E-EXPL/E-ST · Crosswave · Fantic XF1/XF2 Integra.

**Coda lunga:** Focus Jam²/Jarifa²/Thron²/Whistler · Orbea Rise/Wild · Bianchi T-Tronik · Lapierre Overvolt HT/TR · Whistle B-Rush/B-Racer · Ghost Hybride/E-Asx/Lector · Conway Cairon S/Xyron · Bulls Copperhead EVO/Sonic · Stevens E-Cayolle · Corratec E-Power X Vert · Husqvarna Light/Hard Cross · Thömus · Thok · Specialized Turbo Levo HT/Tero · Moustache Samedi 29/XROAD · Simplon Rapcon · BMC Speedfox AMP/Alpenchallenge AMP · Flyer Goroc/Uproc · Riese & Müller · Winora/Kalkhoff (solo MTB) · Canyon Grand Canyon:ON/Spectral:ON · Mondraker (Chaser/Dusk/Crafty) · Nox Cycles · Giant Trance X E+ · BH · Bulls Sonic EVO · HoheAcht Sento · Raymon Crossray · Bergamont E-Contrail · Atala (linee MTB elettriche).

Il glossario dà priorità alle query, non filtra: un brand non presente qui non va escluso — vedi A15.

**Alias taglia:** M = 17"–18" = 44–48 cm. "S/M"/"M/L" → 🟡.

**Parole di esclusione rapida (indizio, mai scarto automatico da sole):** mozzo, Bafang, Ananda, AKM, MOMA, Dapu, kit, conversione, 45 km/h, S-Pedelec, targa, bambino.

## B5. Red flag specifiche

Testo: solo spedizione, "sono all'estero", solo WhatsApp, acconto/Twint prima di vedere, link "pagamento sicuro", senza caricatore, "sbloccata/tuning". Prezzo: oltre 40% sotto mediana, "nuova 0km" a metà prezzo, prezzo in € su sito svizzero. Foto: immagini di catalogo, numero di telaio abraso. Venditore: account nuovo senza recensioni, rifiuta domande tecniche.

## B6. Domande standard al venditore

Taglia/altezza consigliata · anno modello e batteria, cicli/capacità residua · km totali dal menu motore · fattura con numero telaio · ultimo service · caricatore e chiavi inclusi · se marca motore non scritta: quale motore monta (A15).

## B7. Checklist prima dell'acquisto

Fattura con numero di telaio · controllo furto (bikefinder.ch, velofinder.ch, Crimnet, Registro Italiano Bici) · incontro pubblico con prova su strada · diagnosi batteria/motore in negozio · pagamento in contanti/Twint solo alla consegna · contratto scritto · verifica usura catena/cassetta/corona/pastiglie · Bosch Classic vs Smart System (non compatibili tra loro).

## B8. Acquisto in Italia (da residente in Svizzera)

Dazi industriali svizzeri aboliti dal 1.1.2024. IVA svizzera 8,1% obbligatoria sopra CHF 150, dichiarazione QuickZoll. Solo pedelec 25km/h/250W. Garanzia da privato di fatto nulla in entrambi i Paesi; da negozio italiano 12 mesi sull'usato; su nuovo da negozio ufficiale garanzia standard produttore (~2 anni). Budget reale = prezzo + 8,1% + viaggio.

## B9. Fonti e-MTB (stato al 22/09/2026)

Fonti attive principali: Subito.it (ricerca salvata + categoria pura, gap su query strette corretto con A15), Ricardo.ch, tutti.ch, eBay (ricerca salvata da creare dall'utente per policy anti-agenti-AI), Decathlon.ch second-hand (fonte produttiva), Decathlon.it second-hand, **Decathlon.it Rockrider NUOVO — E-EXPL 520 ora sotto soglia coppia (Yamaha PW-CE 50Nm), da riclassificare 🔴 al prossimo run**, Rebike.ch, Upway.ch (fonte più produttiva del progetto, sotto-collezioni per marca), TrovoBici.it, TCS Velocorner (prezzo lista inaffidabile, aprire sempre la scheda), Velomarkt.ch, Andrist Sport (tutto fuori budget finora), Bikeflip, Newsed.it/Ebike Lab/Cicli Conti/Mondobicistore/Sportmo (Milano/Como/Varese/Bergamo).

Bloccate/escluse: buycycle (richiede login/JS), Anibis (404, JS lato client), Kijiji.it (chiuso, reindirizza a Subito), Facebook Marketplace (in sospeso), Wallapop (escluso), Mister Bike e Cycle Village (guasti tecnici persistenti, controllo ridotto proposto), Re-Cyclist Bike Shop (dichiara di non ritirare e-bike). JD eBIKE Pusiano: vetrina Subito, rivenditore affidabile.

## B10. Candidate storiche

Superate dalla dashboard interattiva e dal log per data — non più mantenute qui manualmente.

---

# PARTE C — DECISIONI DELL'UTENTE

**16/09/2026**: taglia M rigida · coppia preferita ≥75 Nm (soglia minima aggiornata il 22/09, decisione #19) · ammortizzatori X-Fusion ammessi · nomi venditori salvati solo se servono · ricerche salvate richieste su Subito/Ricardo/eBay · Decathlon.ch monitorato · Rebike.ch e Upway.ch aggiunte · Decathlon.it e TrovoBici.it aggiunte · TCS Velocorner aggiunto · verifica shop ufficiali per il nuovo · STEP DI VERIFICA sistematico introdotto · giudizio 1-10 con ordinamento (A12) · hardtail mai scartate (poi aggiornato il 22/09, decisione #19: ora fully preferita) · A0.10 e A13 introdotte · copertura negozi fisici Milano/Como/Varese/Bergamo.

**17/09/2026**: caso Fantic XF2 Integra risolto (glossario B4 aggiornato) · A14 introdotta (data pubblicazione + parere sincero) · A15 formalizzata (ricerca di categoria pura come metodo primario, marca sconosciuta mai motivo di scarto, limite invalicabile su elusione anti-bot).

**22/09/2026 — decisione #19, riconciliazione dei criteri**: su richiesta esplicita dell'utente ("e me li puoi sistemare? su claude non me li fa modificare a mano"), dopo che un audit pre-export aveva rilevato tre incoerenze tra questo documento e le istruzioni di progetto/il log più recente:

- **Budget**: da "1500-1800 CHF, eccezione fino a ~2000" a **1500-2200 CHF tutto compreso** (fascia preferita 1500-1800, 1800-2200 fascia "eccezione" nel punteggio).
- **Coppia minima**: da "ammessa da 50 Nm" a **minimo rigido 65 Nm** (preferenza resta ≥75 Nm). Effetto pratico: candidate storiche con motori 50-64 Nm (es. Rockrider E-EXPL 520/Yamaha PW-CE, alcune Lapierre Overvolt HT 4.5/Bosch Active Line Plus) passano da ammesse a sotto soglia.
- **Tipo di telaio**: da "hardtail o full equivalenti, mai scarto" a **fully preferita, hardtail accettata solo per un'offerta eccezionale**.

Questi cambi riguardano criteri rigidi: la modifica è stata fatta perché richiesta esplicitamente dall'utente, non di iniziativa dello scout (coerente con la regola A7 "i criteri rigidi li cambia solo l'utente"). **Eseguito lo stesso giorno**: le 12 candidate in dashboard con coppia 50-64 Nm sono state riclassificate 🔴 (Rockrider E-EXPL 520 ×3 esemplari, Lapierre Overvolt HT 4.5 ×5, Liv Tempt E+ 3, Raymon FullRay E-Nine 5.0, Raymon CrossRay FS E 4.0, Giant Talon E+ 2); la Moustache Samedi 29 di Cadenazzo è stata aggiunta come 🟡 "da verificare", provenienza "segnalata dall'utente".

**22/09/2026 — decisione #20, risposta a un secondo audit esterno**: lo stesso giorno l'utente ha condiviso un'analisi esterna più approfondita del progetto, che ha confermato la riconciliazione sopra ma ha segnalato altri punti di inconsistenza operativa (non di criteri): tabella di soglie duplicata in più punti del documento, regola "hardtail eccezionale" descrittiva ma non operativa, rischio che un 🟡 con dati incompleti superi un 🟢 nell'ordinamento per solo effetto del punteggio numerico, policy sui motori proprietari poco esplicita, R-009 e R-012 (in "Apprendimento") già proposte ma mai attivate, e la violazione della regola A5 sul log (vedi sopra). Risposta, tutta in questa versione (v2.6):

- Aggiunta la **tabella normativa unica** in B2, con nota esplicita che qualsiasi soglia diversa altrove nel documento è un residuo storico non valido.
- Formalizzata la regola hardtail-eccezione con condizioni verificabili (B2).
- Chiarita la policy sui motori proprietari/non riconosciuti come 🟡, non scarto automatico (B2).
- Introdotta in A12 la separazione classificazione/punteggio_tecnico/priorità_operativa e la regola di ordinamento che protegge i 🟢 dall'essere superati da 🟡 con dati mancanti.
- **Attivate R-009 e R-012** (vedi "Apprendimento" per il testo completo delle regole): R-009 con la precisazione richiesta dall'audit — un freno dedotto dal modello scritto va registrato con provenienza "scheda tecnica del modello", non "scritto nell'annuncio", e resta 🟡 se il dato è decisivo; R-012 attiva la suddivisione del 🟡 in tre livelli di priorità (da chiedere / da verificare / bassa priorità). **Nota**: lo stato "attiva" di queste due regole non è ancora stato aggiornato nei campi di stato del documento "Apprendimento" stesso (documento troppo esteso per una riscrittura sicura in questa stessa sessione) — vale comunque da qui in avanti per i nuovi run, e va allineato in "Apprendimento" alla prima occasione.

**22/09/2026 — decisione #21, implementazione dell'ordinamento A12 e verifica del pulsante "Non mi interessa"**: proseguendo sulle correzioni segnalate dal secondo audit, sono state fatte due cose concrete sulla dashboard pubblicata (non solo sui documenti):

- Lo stato "attiva" di R-009 e R-012 è stato allineato nel documento "Apprendimento" (chiudendo il punto lasciato aperto nella decisione #20).
- L'ordinamento predefinito della dashboard è stato cambiato da "solo giudizio decrescente" a "classificazione, poi giudizio" (vedi A12), cioè la regola di ordinamento introdotta il 22/09 è ora effettivamente applicata all'interfaccia, non solo descritta nella metodologia.
- Verificato il codice della dashboard pubblicata: il pulsante "🗑️ Non mi interessa" **salva già lo stato in modo persistente** tramite la funzione di pubblicazione live di claude.ai (capability "artifact") — il punto segnalato dall'audit come "non persistente" risultava vero solo per la copia esportata in locale (fuori da claude.ai, documentato in CLAUDE.md), non per la dashboard live. Non era quindi un problema da correggere sulla dashboard stessa; il riepilogo per l'utente è stato corretto di conseguenza.

Un campo `priority` (A/B/C) è stato poi effettivamente aggiunto e popolato per tutte le candidate 🟡 il 22/09/2026 (vedi decisione #22 sotto) — resta aperta la fonte dati unica strutturata.

**22/09/2026 — decisione #22, assegnazione automatica della priorità R-012 alle candidate 🟡**: aggiunto un campo `priority` (A/B/C) a ciascuna delle 118 candidate 🟡 in dashboard, calcolato contando quanti dei cinque dati decisivi (taglia, motore/marca, coppia, batteria, freni) risultano non scritti/non confermati nel testo dell'annuncio: 🟡-A "da chiedere" (0-1 mancanti, 34 candidate), 🟡-B "da verificare" (2 mancanti, 14 candidate), 🟡-C "bassa priorità" (3+ mancanti o annuncio con dati quasi assenti/probabilmente scaduto, 70 candidate). **È una classificazione euristica automatica, non una revisione manuale annuncio per annuncio** — la dashboard lo segnala esplicitamente vicino al tag (tooltip "assegnazione automatica euristica, da rivedere manualmente") e nella legenda, coerente con la regola A0.7/A15 di non presentare un'ipotesi come un fatto verificato. L'ordinamento predefinito della dashboard ora usa anche questo livello come criterio secondario dentro il 🟡 (prima classificazione, poi priorità R-012, poi punteggio).

**22/09/2026 (sera, tardo) — decisione #23, conferma diretta della Moustache Samedi 29 (Cadenazzo)**: l'utente ha fornito il link diretto dell'annuncio (https://www.tutti.ch/it/vi/ticino/sport-e-outdoor/biciclette/e-bike-mtb-fully-moustache-29-samedi-2022/82694016), fino a quel momento mancante. Verificato con WebFetch: tutti i dati precedentemente riferiti a memoria (Bosch CX 85 Nm, 625 Wh, taglia M, freni idraulici Shimano XT) sono risultati scritti testualmente nell'annuncio. **Riclassificata da 🟡 a 🟢** in dashboard (versione 42), rating ricalcolato a 9.2 con la formula A12. Unico dato non confermabile sulla fonte diretta: la trattativa verso 2'000 CHF resta riferita dall'utente, il prezzo scritto sull'annuncio è 2'200 CHF. Zona Cadenazzo, solo ritiro in loco, nessuna spedizione — segnalato come limite pratico, non come motivo di scarto. Questo è il primo caso in cui la regola "non trattare come 🟢 senza fonte diretta" (introdotta proprio per questa candidata, decisione #19) ha funzionato come previsto fino alla conferma effettiva.

**Ancora aperte**: Facebook Marketplace da decidere · collegare l'email a Claude per le notifiche delle ricerche salvate · buycycle e TrovoBici: ricerche salvate da creare/valutare · ebiketicino.ch da confermare se ancora attivo · le rimanenti regole proposte R-001–R-008, R-010, R-011, R-013 ancora in attesa di decisione · revisione manuale dei tag 🟡-A/B/C assegnati euristicamente il 22/09/2026 (decisione #22) · introdurre in dashboard i campi separati `classificazione`/`punteggio_tecnico`/`priorità_operativa` come dati pienamente distinti (oggi l'ordinamento li rispetta ma solo `status`+`rating`+`priority` esistono davvero) · valutare una fonte dati unica strutturata (es. `candidates.json`) da cui derivare dashboard, log e riepilogo, per evitare futuri disallineamenti.

# PARTE D — ROADMAP

- **v2 (fatta)**: algoritmo + "Apprendimento" + log con codici motivo e link salvati alla scoperta.
- **v2.5 (fatta, 22/09/2026)**: riconciliazione dei criteri rigidi (budget, coppia minima, tipo di telaio) con le istruzioni di progetto.
- **v2.6 (fatta, 22/09/2026)**: tabella normativa unica, regola hardtail-eccezione formalizzata, policy motori proprietari chiarita, separazione classificazione/punteggio/priorità, attivazione R-009 e R-012.
- **v2.7 (fatta, 22/09/2026)**: ordinamento A12 implementato in dashboard (non solo documentato), stato R-009/R-012 allineato in "Apprendimento", verificata la persistenza del pulsante "Non mi interessa" sulla dashboard live.
- **v2.8 (fatta, 22/09/2026)**: campo `priority` (R-012, 🟡-A/B/C) assegnato euristicamente a tutte le candidate 🟡 in dashboard, con disclosure esplicita che è un'assegnazione automatica da rivedere.
- **v2.9 (fatta, 22/09/2026)**: introdotta A16 (verificare con ricerca web le conoscenze tecniche incerte, mai inventarle) e rafforzata A14 (parere sincero onesto anche quando è negativo).
- **v2.10 (fatta, 22/09/2026)**: Moustache Samedi 29 (Cadenazzo) confermata da fonte diretta e riclassificata 🟡→🟢 in dashboard.
- **v3 (in corso)**: run periodica, STEP DI VERIFICA sistematico, giudizio 1-10, anno modello sempre valorizzato, testi tradotti, copertura negozi fisici IT, data pubblicazione + parere sincero, A15 (categoria pura come metodo primario), digest mobile.
- **v4 (artifact, in corso)**: dashboard con schede, filtri, ordinamento, pulsante "Non mi interessa" (fatto); pubblicazione e parere sincero visibili (fatto); coda regole proposte da accettare, grafici di resa (da fare); poi generatore di nuovi "pacchetti di dominio" tramite intervista.
