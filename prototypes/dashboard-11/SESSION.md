# #11 — sessionsnoter, 15. september 2026

## Status

Den danske prototype er under afprøvning. Brugeren har påpeget, at positive
og negative beløb er for svære at skelne i detaljevisningen. En ændring er
lavet og afventer ny afprøvning. Der er ikke givet godkendelse af hele designet
eller dokumenteret, at de tre opgaver kan løses uden hjælp.

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
- Ændring: Alle posteringer viser nu et udtrykkeligt plus eller minus,
  en grøn eller rød beløbsbaggrund og teksten Penge ind eller Penge ud.
  Nulbeløb er neutrale. Forskellen afhænger dermed ikke alene af farve.
  Beløb, kategorisummer og øvrige rapporttal er uændrede. Brugerens vurdering
  af denne løsning afventes.

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
- Positive og negative posteringer skal være lettere at skelne. Den konkrete
  løsning med fortegn, farve og tekst er endnu ikke bekræftet som tilstrækkelig.
- De beskrevne afgrænsninger og brug af lokale data er aftalt.
- Intet layout eller nogen forklaring af økonomiske tal er endnu valideret
  gennem deltagernes løsning af opgaverne.

## Uafprøvede antagelser og åbne spørgsmål

- Er de danske navne og kategorier forståelige for begge deltagere?
- Er ind- og udbetalinger nu lette at skelne i den kommenterede detaljevisning?
- Bliver markeringerne af ufuldstændige tal set og forstået?
- Forstås Tilbage efter udgifter som indtægter minus udgifter, særskilt fra
  ændringer i saldo og penge uden kategori?
- Er de generelle beskrivelser præcise nok til at undersøge et beløb?
- Hjælper Min/Fælles, og hvordan skal Hendes og børnenes konti vises?
- Er forskellen mellem bekræftet stilstand og manglende oplysninger tydelig?
- Lokale kategorier og fuldstændighed er stadig ikke kontrollerede fakta.
- Forsøget afgør ikke år-til-dato, udviklingsgrafer, lagerets implementeringsparathed,
  import og konfiguration i #10 eller forslagene i #18/#20.
