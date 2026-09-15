# #11 — prototype af et månedsoverblik

**Klar til afprøvning; endnu ingen konklusioner om brugervenlighed.** Én dansk
udgave, uden redigering, lavet med HTML/CSS/JavaScript og Pythons standardbibliotek.
Prototypen skal kasseres efter forsøget. Ingen pakker skal installeres.

Spørgsmålet er: Kan I forstå månedens forbrug, undersøge et overraskende
kategoribeløb og se, hvilke tal der er ufuldstændige?

## Start

Kør fra projektets rodmappe i PowerShell:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Åbn <http://127.0.0.1:8011>. Stop med Ctrl+C. Serveren er kun tilgængelig på
denne computer. Visningen er kontrolleret i mobilbredde; adgang fra en separat
telefon er ikke sat op.

Kontrollér rapporteksemplernes regnestykker:

```powershell
py -3.12 prototypes/dashboard-11/check_fixtures.py
```

## Oplysningerne i prototypen

- `example.json` er helt opdigtet: juli–september 2026, to konti, indtægter,
  udgifter, tilbagebetalinger, en kategori med negativt forbrug, en overførsel
  med begge sider, ukendte ind- og udbetalinger, særskilte rettelser, en konto
  med bekræftet stilstand og manglende eller delvise oplysninger for september.
- På brugerens anmodning er der også lavet et fast **privat eksempel baseret
  på bankdata** for 14 måneder fra de to lokale CSV-filer. Det ligger i
  `imports/.dashboard-11/`, som Git allerede ignorerer. Det bruger de faktiske
  datoer og beløb, generelle beskrivelser og foreløbige kategorier baseret på
  bankens kategorier. Det er ikke et kontrolleret husstandsregnskab.
- Tvetydige bevægelser mangler kategori. Det er ikke kontrolleret, om alle
  kontooplysninger er med. Også afsluttede lokale måneder er foreløbige,
  indtil kontoudtogene er kontrolleret. Én slettet postering er udeladt.
  Rapporten indeholder ingen oprindelige banktekster, kontonumre eller
  kildefilnavne. De private JSON-filer og skærmbilleder må ikke offentliggøres.
- Det lokale eksempel vises først, hvis det findes. Ellers bruges det opdigtede
  eksempel. Valget under Data skifter oplysninger, ikke design.
- Serveren læser kun faste JSON-rapporter og udtrykkeligt tilladte skærmfiler.
  Den læser ikke CSV-filer, viser ikke importmappen og beregner ikke økonomiske
  nøgletal. Den engangsforberedelse, der lavede eksemplerne, er ikke en importmotor.
- Ingen database, login, filoverførsel, redigering, klassifikationsmotor,
  overførselsmatchning, afstemningsmotor eller lagring i browseren.
- Beløb er præcise decimalstrenge. Skærmen formaterer dem blot på dansk.
  Søjlerne bruger forudberegnede procenter. Summer kontrolleres mod de
  medvirkende posteringer; de opdigtede summer har også håndkontrollerede facit.

## Afgrænsning og beslutningsstatus

Kontrolleret 15. september 2026: #2 og #11 er åbne. #16, #18 og #20 er åbne og
ikke flettet ind. #16 dokumenterer de accepterede beslutninger fra #5 om
transaktionsdatoer, syv dages frist efter månedsslut og karantæne af hele
kontoudtog. De er endnu ikke på main. Gold-modellen i #18 og reglerne for
kategorisering og overførsler i #20 er stadig forslag, ligesom deres ADR'er.
Prototypen accepterer ikke disse forslag. #10 er fortsat åben og blokerer ikke
arbejde med faste rapporteksempler. Kun opdigtede data ligger i Git.

De to konti er mærket Min og Fælles efter brugerens beskrivelse. Hendes konto
og de to børns opsparingskonti er fremtidige behov. Ejerskab og kontotype
(lønkonto, opsparing osv.) er forskellige begreber.

Sessionens udtrykkelige instruktioner erstatter prototype-skillens trin om
flere varianter og overførsel til produktionskode samt projektets godkendelser
mellem hver rød/grøn testfase — kun for denne prototype. Den kontrolleres med
regnestykker og browserafprøvning. Almindeligt produktionsarbejde følger stadig TDD.

Se [SESSION.md](SESSION.md) for feedback og kontroller samt
[REPORT-SHAPE.md](REPORT-SHAPE.md) for det foreslåede rapportformat.

## Afprøvning sammen

Lad gerne den, der kender projektet mindst, styre først:

1. Find ud af, hvor pengene blev af denne måned.
2. Undersøg, hvorfor beløbet i en kategori virker overraskende.
3. Find de tal, I bør betragte som ufuldstændige.

Fortæl, hvad I prøver, hvad I forventer, og hvor I tøver. Observatøren skal
vente med forklaringerne. Hvis den aktuelle måned er for sparsom til opgave 2,
kan I vælge en tidligere måned. August i det opdigtede eksempel kan også bruges.

#11 skal ikke lukkes, og koden skal ikke gøres til produktionskode på baggrund
af agentens kontroller alene.
