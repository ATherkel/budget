# #11 — sessionsnoter, 15.–17. september 2026

## Status

**17. september: Retningen er bekræftet af ejeren; prototypeiterationen er
frosset og overleveret til implementering.** Se [HANDOFF.md](HANDOFF.md).
Ejeren viderebringer sin kones feedback om mange tal/posteringer og uklarheden
ved Mangler en kategori. Enkel/Avanceret er derfor et nyt implementeringskrav;
det er ikke føjet til prototypen. Der er stadig ikke dokumenteret en fuld
selvstændig gennemførsel af de tre opgaver fra begge deltagere.

Noterne nedenfor er den kronologiske historik. Formuleringer om at afvente
feedback beskriver status på det daværende tidspunkt, ikke den nye overlevering.

## Brugerens input og ændringerne

- Brugeren bad om ét lille, sammenhængende design, faste rapporteksempler og
  en undtagelse for testproceduren alene til prototypen. Dette er gennemført.
- Brugeren bad derefter om at bruge de to lokale CSV-filer og beskrev
  ejerskabet som min, hendes og fælles samt opsparingskonti til to børn.
  Tilføjede et lokalt, privat rapporteksempel, generelle beskrivelser og
  mærkerne Min/Fælles for de to tilgængelige konti. Et separat, opdigtet
  eksempel dækker de særlige situationer, som kontoudtogene ikke nødvendigvis har.
- Efter den første visning bad brugeren om dansk overalt. Oversatte hele
  skærmen, begge rapporteksemplers visningstekster, kategorier, beskrivelser,
  månedsnavne, datoer, hjælpetekster, tilgængelighedstekster og vejledninger.
  Beløb, datoernes betydning, statuskoder og rapporternes struktur er uændrede.
- Sprogønsket er konkret feedback og er håndteret. Det bekræfter et sprogkrav,
  men siger endnu ikke, om tallene eller forklaringerne er forståelige.
- Browserkommentar 1: Brugeren pegede på tilbagebetalingen på 300,00 kr.
  i septemberudgifterne i det opdigtede eksempel og efterlyste tydeligere
  visuel forskel på positive og negative beløb. Det er en konkret observation
  fra detaljevisningen; den dokumenterer ikke i sig selv en løst opgave.
- Ændring: Første ændring: Alle posteringer fik et udtrykkeligt plus eller minus,
  en grøn eller rød beløbsbaggrund og teksten Penge ind eller Penge ud.
  Nulbeløb er neutrale. Forskellen afhænger dermed ikke alene af farve.
  Beløb, kategorisummer og øvrige rapporttal er uændrede. Brugerens vurdering
  af farverne blev senere bekræftet, se nedenfor.
- Browserkommentar om Mangler en kategori: Brugeren kunne ikke se, hvordan
  manglende kategorier skulle løses, og spurgte, om det var relevant for denne
  visning. Det afdækker et uklart næste skridt; det er ikke en bestilling på
  en redigeringsfunktion eller en beslutning om den fremtidige arbejdsgang.
- Ændring: Oversigten siger nu, at kategorier ikke kan ændres i prototypen.
  Detaljerne forklarer, at afprøvningen kan fortsætte, og inviterer deltagerne
  til at fortælle, hvilken kategori de forventer. Den fremtidige arbejdsgang
  er tydeligt angivet som uafklaret. #10 er fortsat stedet for at afklare
  vedligeholdelse uden for den skrivebeskyttede oversigt. Ingen kategorier,
  finansielle tal eller foreslåede ADR'er er ændret.

## Fire nye browserkommentarer — håndteret 16. september

- **Kontovalg:** Brugeren vil kunne vælge enhver kombination af konti,
  uafhængigt af ejer og antal. Tilføjet individuelle afkrydsningsfelter og
  Vælg alle. Alle dele af skærmen bruger valget. De faste eksempler har to
  konti og tre ikke-tomme kombinationer; flere konti er endnu ikke afprøvet.
- **Graf:** Brugeren efterlyste indtægter, udgifter og resten over tid med
  seneste 12 måneder, indeværende år og egen periode. Tilføjet én graf med
  disse valg, danske månedsnavne og en tabel med præcise tal og datagrundlag.
- **Gentaget tekst:** Brugeren skrev, at Penge ind/Penge ud var overflødigt,
  fordi retningen nu var tydelig fra farverne. Fjernet synlig tekst ved hvert
  beløb; farver og +/− bevares. Retningen findes stadig i tilgængelighedsteksten.
  Dette er brugerens konkrete bekræftelse af farvernes nytte, ikke en samlet
  godkendelse fra begge deltagere.
- **Rækkehøjde:** Brugeren fandt posteringerne for høje og foreslog tættere
  rækker eller et valg. Valgt kompakte rækker som standard uden ekstra knap.
  Almindelige rækker er omkring 60 px; længere beskrivelser kan ombrydes.

## Agentens kontroller

- Regnestykker bestået for alle 14 lokale og 3 opdigtede måneder: køb,
  tilbagebetalinger, kategorisummer, indtægter, udgifter, beløb tilbage og
  andel tilbage samt ind/ud/antal for ukendte posteringer og rettelser.
  Hver postering er med i præcis én rapportgruppe og kan findes under sin konto.
- De opdigtede rapporter er også kontrolleret mod håndberegnede facit og
  særskilt angivne start- og slutsaldi. De lokale summer er kontrolleret mod
  en separat summering af de faste rapportgrupper. Det beviser regnestykkerne,
  ikke de foreløbige kategorier eller fuldstændigheden af lokale kontodata.
- Før oversættelsen kontrolleret ved 1280×900, 390×844 og 320×740: skift af
  måned og datasæt, kategoridetaljer, tilbagebetalinger og negativt forbrug,
  ukendte posteringer, overførsler, kontobevægelser, ukendt saldo, stille
  kontomåneder og rettelser. Escape lukker detaljer og giver fokus tilbage.
- Agentens rettelser: synlige kategorisøjler, grøn markering ved komplette
  kontodata, stabling på smalle skærme og foreløbig markering af historiske
  lokale rapporter, som ikke har gennemgået importkontroller.
- Oversættelsen blev kontrolleret mod de tidligere rapporter: Alle felter,
  der ikke er visningstekster, er identiske. De oprindelige CSV-filer er urørte.
- Den danske visning er kontrolleret i browseren ved mobil- og computerbredde.
  Månedsvalg, kategoridetaljer, tilbagebetalinger, danske datoer og decimaler
  samt lukning med Escape virker. Ingen vandret overfyldning i de kontrollerede
  mobilvisninger og ingen advarsler eller fejl i browserens log.
- Private rapporter ignoreres af Git. Serveren udstiller kun de valgte faste
  rapporter og skærmfiler på denne computer.
- Efter browserkommentar 1: Tilbagebetalingen på 300,00 kr. viser nu
  +300,00 kr. og Penge ind; de øvrige septemberudgifter viser minus og
  Penge ud. Kontrolleret visuelt på computer og ved 390×844 uden vandret
  overfyldning i detaljevinduet. Begge sider af en overførsel får korrekt
  fortegn og tekst. Regnestykkerne består fortsat for alle 17 måneder.

### Kontroller af den nye version

- Alle tre kontokombinationer for 3 opdigtede og 14 lokale måneder er
  kontrolleret mod posteringerne, inklusive ukendte beløb, overførsler,
  stille måneder og manglende oplysninger. Det er 51 rapporter med kontovalg.
- I browseren virker enkeltkonto, begge konti, tomt valg og Vælg alle.
  Fælleskontoens stille august viser nul, mens september uden data er ukendt.
- Grafens perioder, egen periode med én eller flere måneder, afvisning af
  omvendte datoer og månedsskift fra tabellen er kontrolleret. Ukendte
  måneder tegnes ikke som nul. Danske månedsvalg erstatter browserfelter,
  som viste engelske navne på denne computer.
- Graf og kontovalg er visuelt kontrolleret ved 1280×900, 390×844 og
  320×740. Ingen vandret overfyldning af siden. Browserloggen er uden fejl
  og advarsler. JavaScript-syntaks og Git-diffkontrol består.
- Kompakte beløb viser kun fortegn og tal. Forklaringen om manglende kategorier
  er kontrolleret; Escape lukker fortsat detaljevinduet.

## Afprøvning med jer — afventer næste observationer

1. Find ud af, hvor pengene blev af denne måned.
2. Undersøg og forklar et overraskende kategoribeløb.
3. Find de ufuldstændige tal.

Notér for hver deltager handling, forventning, tøven eller misforståelse og
eventuelt deres egne ord. Notér også hjælp undervejs; et forklaret svar er
ikke en opgave løst uden hjælp. Ret derefter den vigtigste observerede
misforståelse, og gentag den relevante opgave.

## Udtrykkeligt bekræftet

- Dansk er påkrævet i hele brugeroplevelsen.
- Brugeren finder nu farvernes skelnen mellem ind- og udbetaling tydelig.
  Gentagne tekster ved beløbene er uønskede. Den kompakte udgave afventer feedback.
- Frit kontovalg og udviklingsgrafer er udtrykkeligt efterspurgte behov.
- De beskrevne afgrænsninger og brug af lokale data er aftalt.
- Intet layout eller nogen forklaring af økonomiske tal er endnu valideret
  gennem deltagernes løsning af opgaverne.

## Uafprøvede antagelser og åbne spørgsmål

- Er de danske navne og kategorier forståelige for begge deltagere?
- Er de kompakte rækker nemme at skimme for begge deltagere?
- Er kontovalgets virkning på samtlige tal tydelig?
- Forstås grafens huller, stiplede linjer og faste referencedato?
- Er det forståeligt, at interne overførsler forbliver udeladt, selv når
  kun den ene konto er valgt? Denne forklaring er endnu ikke brugerafprøvet.
- Bliver markeringerne af ufuldstændige tal set og forstået?
- Forstås Tilbage efter udgifter som indtægter minus udgifter, særskilt fra
  ændringer i saldo og penge uden kategori?
- Er de generelle beskrivelser præcise nok til at undersøge et beløb?
- Forstår deltagerne nu, at kategorier ikke kan ændres her, og hvad de kan
  gøre under afprøvningen? Hvordan skal den færdige oversigt pege videre til
  en arbejdsgang uden for visningen, når denne er besluttet i #10?
- Hjælper Min/Fælles, og hvordan skal Hendes og børnenes konti vises?
- Er forskellen mellem bekræftet stilstand og manglende oplysninger tydelig?
- Lokale kategorier og fuldstændighed er stadig ikke kontrollerede fakta.
- År og udviklingsgrafer er nu med i forsøget, men ikke valideret. Forsøget
  afgør ikke lagerets implementeringsparathed, import og konfiguration i #10
  eller forslagene i #18/#20.

## Budget og øremærket opsparing — 16. september 2026

### Observeret behov og udtrykkeligt svar

- Brugeren efterspurgte Beløb/Mod budget under Hvor blev pengene af?,
  en sammenligning af budget og forbrug samt synlige overskridelser og besparelser.
- Ferie skal kunne få 3.000 kr. hver måned og gemme restbeløbet, så en særskilt
  feriekonto på sigt kan undværes. Opsparing skal absorbere overskridelser.
- På spørgsmålet om videreførsel svarede brugeren: “Ja, kun valgte kategorier
  fører videre”. Ubrugte beløb i øvrige kategorier går til almindelig Opsparing.
  Dette er en bekræftet regel for forsøget; ingen ADR er accepteret eller ændret.

### Ændringer til afprøvning

- Ét skift mellem Beløb og Mod budget i den eksisterende kategorioversigt.
  Budgetrækker viser kendt forbrug, beløb til rådighed og rest/overskridelse;
  detaljer viser regnestykket og de samme posteringer, inklusive tilbagebetalinger.
- Ferie er markeret Opspares til senere med tidligere rest, månedens 3.000 kr.
  og beregnet rest til næste måned. Startrest i juli er nul. Ingen kendte
  ferieudgifter i de tre eksisterende måneder; ukendte posteringer kan ændre det.
- Opsparing efter øremærkning viser månedens budget, bidrag efter kendte udgifter
  og ferieøremærkning samt afvigelse. Kontoens saldo og samlet opsparingsformue
  er andre tal. Eksisterende indtægter minus udgifter er uændret.
- Budgetterne er faste, opdigtede rapporter for begge syntetiske konti samlet.
  Lokale banktal og enkelte kontovalg får en forklaring og en eksplicit knap
  til eksemplet. Husstandsbudgettet bliver ikke fordelt efter kontovalg.
- Der er stadig ingen budgetredigering eller beregningsmotor. Kun grafisk
  fremstilling og opslag i rapporteksempler. Browser- og regnekontrol følger
  brugerens udtrykkelige prototypeundtagelse fra TDD-håndoverdragelser.

### Kontrol og begrænsninger

- Uafhængige facitværdier: Ferie 3.000 / 6.000 / 9.000 kr. i juli–september;
  månedligt bidrag til almindelig Opsparing 17.010 / 8.370 / 17.890 kr.
  mod budget 14.700 kr. Afvigelser 2.310 / −6.330 / 3.190 kr.
- Regnekontrollen sammenholder budgetternes forbrug med de oprindelige
  syntetiske posteringer; alle tidligere 51 kontorapporter består fortsat.
- Browser: skift, detaljeåbning/lukning, tilbagebetaling, videreførsel mellem
  måneder, manglende budget ved kontoudvalg og lokalt datasæt er kontrolleret.
  Desktop og telefon er visuelt inspiceret. Det er agentkontrol, ikke feedback.

### Afventer afprøvning og afklaring

- Forstår begge deltagere ferieøremærkning og månedens almindelige opsparing?
- Kan de udpege overskridelser og forklare deres samlede virkning?
- Kan budgetvisningen fungere som erstatning for en dedikeret feriekonto?
  Dette er brugerens hensigt, ikke et valideret resultat.
- Faktisk brug af en opsparet ferierest er endnu ikke afprøvet. Ved forbrug
  over hele ferierammen skal Opsparing ifølge brugerens hensigt dække forskellen;
  den præcise visning og næste måneds startrest er ikke afgjort.
- Startbeløb, ændrede budgetter/indtægter, utilstrækkelig almindelig opsparing,
  perioder med manglende oplysninger og budgetafgrænsning ved kontoudvalg
  er endnu ikke afprøvet. Tallene er månedlige rammer, ikke dagsfordelte mål.
- Ingen deltagere har endnu afprøvet denne budgetudgave. Klar til feedback.
- Afsluttende kontrol: budgetvisningen fungerer ved 1280×900, 390×844 og
  320×740 uden vandret overfyldning. Opsparingsafsnittet gentager periode og
  datadækning. Under hurtig genindlæsning fandt agenten et datasætskift før
  rapporterne var indlæst; skiftet anvendes nu først, når rapporterne er klar.
