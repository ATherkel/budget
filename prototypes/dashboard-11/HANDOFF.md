# #11 — bekræftet retning og overlevering

## Status pr. 17. september 2026

Ejeren bekræfter, at den aktuelle prototype er en god retning, og ønsker at
gemme øvrige ændringer til den egentlige implementering. Prototypeiterationen
fryses her. Den kørende udgave er fastholdt i commit `78efa47`; efterfølgende
ændringer i denne overlevering er dokumentation.

Gren: `codex/prototype-11-dashboard`. Start fra repositoryets rod:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Åbn <http://127.0.0.1:8011/>. Et nyt checkout fungerer med de syntetiske
rapporter alene. Private lokale rapporter og bankudtog følger ikke med grenen.

## Hvad tilbagemeldingen bekræfter

- Ejeren kan lide den nuværende iteration som udgangspunkt for implementering.
- Dansk, frit kontovalg, udviklingsgrafer, tydelige fortegn og kompakte
  posteringer er efterspurgte behov fra den samlede afprøvning.
- Budget mod faktisk forbrug og øremærkede reserver er ønskede funktioner.
  Kun udvalgte kategorier skal føre rester videre. Almindelige kategoriers
  restbeløb og overskridelser påvirker den almindelige Opsparing.

Det er en bekræftelse af retningen. Der foreligger ikke en dokumenteret,
selvstændig gennemførsel af alle tre oprindelige opgaver fra begge deltagere.
Der skal ikke sættes flueben ved fuld forståelse af ufuldstændige tal.

## Feedback fra den anden deltager

Ejeren viderebringer sin kones oplevelse: Der er mange tal og posteringer,
og afsnittet om manglende kategori nederst er uklart. Ejeren ønsker derfor
et valg mellem enkel og avanceret visning og påtager sig selv afstemningen.
Dette er viderebragt feedback, ikke en direkte observeret opgavegennemførsel.

## Krav til implementering: Enkel / Avanceret

Selve skiftet er efterspurgt af brugeren; opdelingen nedenfor er et forslag
til implementering, som endnu ikke er afprøvet.

- **Enkel** foreslås som standard: måned, kontovalg, indtægter, udgifter,
  tilbage efter udgifter, kategorier og graf. Posteringer åbnes ved behov.
  Lange oversigter over ukategoriserede beløb, rettelser, interne overførsler
  og afstemningsoplysninger er skjult fra selve overblikket.
- **Avanceret** viser de underliggende oplysninger om kontodækning,
  ukategoriserede ind-/udbetalinger og antal, rettelser, overførsler og
  kontobevægelser. Rapporten er stadig uden redigering.
- **Begge** skal kort og synligt angive, når tallene er foreløbige eller
  ufuldstændige, med adgang til forklaringen. Det er en eksisterende
  troværdighedsregel fra præsentationslaget. Skjulte detaljer må ikke få
  ufuldstændige tal til at se endelige ud.
- Samme konto- og periodevalg skal give samme økonomiske værdier i begge
  visninger. Skiftet ændrer detaljegrad, ikke klassifikation eller beregning.
- Valget er en visningspræference for enhver bruger, ikke en rolle, et køn
  eller en adgangsbegrænsning. Lagring af præferencen er endnu ikke besluttet.

Acceptscenarier til den normale TDD-proces: skift uden ændrede tal eller
tabt kontovalg; ufuldstændige og ukategoriserede forhold stadig varslet i
Enkel; detaljer tilgængelige i Avanceret; efterfølgende afprøvning af, om den
enklere udgave er forståelig for begge deltagere.

## Fra prototype til rigtig applikation

1. Brug denne gren som reference for adfærd og visning. Implementer den rigtige
   løsning på en ny gren fra den aftalte produktions-/integrationsbase.
   Prototypens server og faste kontokombinationer skal ikke være produktionsmotor.
2. Aftal det konkrete analytics-interface ud fra
   [REPORT-SHAPE.md](REPORT-SHAPE.md). Det er fortsat et forslag. Beregninger,
   klassifikation og datadækning hører til de respektive lag; skærmen modtager
   færdige rapporter og viser dem.
3. Byg månedsoverblik, undersøgelse af kategorier og tillidsmarkeringer med
   Enkel/Avanceret under repositoryets normale TDD-håndoverdragelser.
4. Brug [SESSION.md](SESSION.md) som feedbackhistorik og eksemplerne som
   acceptscenarier. Gentag de oprindelige tre opgaver på implementeringen.
5. Planlæg budget og øremærket opsparing som særskilt scopeafklaring før
   implementering: #2 udelukker stadig budgetmål fra første leverance.
   Den nye ønskede Opsparing efter øremærkning må ikke erstatte det accepterede
   analyticsmål Savings = Income − Expenses uden en udtrykkelig beslutning.

## Uafklaret, ikke godkendt gennem denne iteration

- Enkel/Avanceret er ikke bygget eller brugerafprøvet i den frosne prototype.
- Budgetafgrænsning ved kontoudvalg, negativ reserve, startreserver, ændrede
  budgetter og faktisk brug af en opsparet ferierest mangler afprøvning.
- En særskilt feriekonto kan muligvis erstattes af øremærkning i værktøjet;
  hensigten er bekræftet, men det er endnu ikke demonstreret som en hel arbejdsgang.
- Import, konfiguration og genopretning i #10 samt warehouse-parathed afgøres
  ikke her. Den eksisterende skærm retter ikke manglende kategorier.
- Kontrolleret 17. september: #16, #18 og #20 er åbne og ikke flettet.
  #16 dokumenterer beslutninger fra #5; forslagene i #18/#20 er ikke accepteret
  gennem prototypen. #2 og #11 er fortsat åbne.

Ingen produktionsoverførsel, merge eller lukning af #11 følger automatisk af
denne opsamling. Den fastholder brugerens bekræftelse og det næste konkrete behov.
