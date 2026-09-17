# Forslag til det mindste nødvendige månedsrapportformat

**Forslag ud fra skærmens behov, ikke en Gold-kontrakt.** Ejeren har bekræftet
prototypens retning 17. september; det konkrete rapportinterface er stadig
et forslag. Se [HANDOFF.md](HANDOFF.md). Skærmen modtager en rapport fra analyselaget. I den rigtige
applikation skal rapporten komme gennem dette lag; den private forberedelse
af eksempler skal ikke kopieres til produktionskode.

De tekniske feltnavne er bevaret på engelsk. Alle tekster, der vises for
brugeren, skal være danske. Dette sprogkrav er udtrykkeligt bekræftet.

```text
ReportRequest
  accountIds: id[]  // vilkårlig kombination, uafhængigt af ejerskab
  month: YYYY-MM
  trendPeriod: {startMonth, endMonth}

MonthlyReport
  accountIds: id[]
  period: id, label, start, end, provisional, provisionalReasons[]
  currency: DKK
  coverage: status, incompleteAccounts[{id, name, status, reasons[]}]
  measures: income, expenses, netCashFlow, savings, savingsRate
  incomeTransactions: TransactionDisplay[]
  categories: [{id, name, purchases, refunds, netSpending,
                coverage, transactions: TransactionDisplay[]}]
  unclassified: {moneyIn, moneyOut, count, transactions}
  adjustments: {moneyIn, moneyOut, count, transactions}
  transfers: {moneyIn, moneyOut, count, transactions}
  accounts: [{id, name, ownerLabel, accountType, coverage,
              balance: {amount|null, asOf|null}, quietConfirmed,
              transactions: TransactionDisplay[]}]

TrendReport
  accountIds: id[]
  startMonth, endMonth, asOf
  months: [{month, income|null, expenses|null, netCashFlow|null,
            provisional, coverage, missingReasons[]}]

AvailableAccounts: [{id, name, ownerLabel, accountType}]

TransactionDisplay
  id, accountId, accountName, date, description, amount, kind, kindLabel
```

- Beløb er præcise decimalstrenge i én angivet valuta. Penge ud er negative;
  udgifts- og kategorisummer er positive ved forbrug og kan blive negative,
  når tilbagebetalinger er større end køb. Andelen tilbage er null, hvis
  indtægterne ikke er positive. Browseren beregner ikke økonomiske nøgletal.
- Observeret behov: Fortegnet på hver postering skal være tydeligt. Det
  eksisterende signerede `amount` er nok til visning med plus/minus og
  farve; intet ekstra beregnet rapportfelt er nødvendigt. Brugeren fandt
  gentaget Penge ind/Penge ud overflødigt; det beholdes kun som hjælpetekst
  for skærmlæsere ved beløbene.
  Fortegnet må ikke udledes af posteringens type. Kategorisummer har en anden
  fortegnskonvention og skal ikke mærkes som ind- eller udbetalinger.
- Hvert husstandstal skal bære oplysninger om kontodækning. Én fælles reference
  i rapporten er tilstrækkelig, hvis alle tal omfatter samme konti, og detaljerne
  altid viser oplysningerne. Foreløbig periode, manglende kontodata og
  posteringer uden kategori er tre forskellige forhold.
- Datoen for saldoen skal stå ved beløbet. Ukendt saldo er null, ikke nul.
  Ingen bevægelser kan kun bekræftes med fuldstændige oplysninger. En senest
  oplyst saldo må ikke give indtryk af en fuldstændig måned. Der er endnu
  ikke behov for en samlet saldo på tværs af konti.
- Kategoridetaljer kræver køb, tilbagebetalinger og nettobeløb fra analyselaget.
  En tilbagebetaling beholder sin egen dato og flyttes ikke til købsmåneden.
  Detaljerne gentager periode og oplysninger om manglende kontodata.
- Ukendte beløbs ind/ud/antal skal vises, også når de netto er nul. Rettelser
  uden kategori vises særskilt. Interne overførsler er uden for indtægter,
  udgifter og opsparing. Hver postering tilhører præcis én rapportgruppe.
- Observeret behov: Visningen af manglende kategorier skal også forklare
  mulighederne for at komme videre. Prototypen kræver kun hjælpetekst om
  manglende redigeringsmulighed. En fremtidig henvisning til vedligeholdelse
  må afvente #10; der tilføjes ikke et opdigtet link, en kommando eller et
  redigeringsfelt til rapportkontrakten nu.
- Ejerskab er en visningsegenskab, ikke en kontotype eller en regel for
  overførselsmatchning. Min/Hendes/Fælles/børn skal ikke være fem kontotyper.
- Posteringernes id'er er rapport-id'er. Skærmen behøver ikke bankkontonumre,
  CSV-filnavne, kilderækkenumre, adgangsoplysninger eller rå kildeindhold.
- `barPercent`, hjælpetekster, `openingBalance` til kontrol og oplysninger om
  eksempeldatasæt er prototypefelter, ikke nødvendige produktionsfelter.
- Lister med alle posteringer er nok her. Opdeling i sider eller en særskilt
  detaljerapport kan afgøres senere.
- Kontovalg er et sæt konto-id'er. Rapporten skal angive den samme afgrænsning
  for nøgletal, kategorier, detaljer, saldi og graf. En konto, brugeren har
  fravalgt, er ikke en konto med manglende oplysninger i den valgte rapport.
  Interne overførsler bevarer deres betydning uafhængigt af kontovalget.
- Grafen kræver færdige månedstal, ikke posteringer til summering i browseren.
  En manglende måned/værdi er null med årsag; en bekræftet stille måned er nul.
  Foreløbig periode og kontodækning følger hvert punkt. `asOf` definerer, hvad
  seneste 12 måneder og indeværende år refererer til. Ingen periode-total er
  nødvendig for den nuværende graf.
- Prototypens `views` er en endelig samling faste rapporteksempler. En rigtig
  rapporttjeneste skal modtage kontovalget som forespørgsel, ikke materialisere
  alle mulige kontokombinationer. Implementeringen afgøres ikke i forsøget.

Åbent: Forstår begge deltagere navnene? Er indtægter minus udgifter det bedste
hovedtal? Hvilke kontogrupper skal vises? Forklarer en kategorisum og dens
posteringer en overraskelse? Hvor meget skal vises om manglende kontodata uden
at rulle? Hvad skal den fremtidige kategorisering levere? Ingen foreslåede
ADR'er er accepteret gennem prototypen.

## Tilføjelse: budget og øremærkning

Brugeren har bekræftet, at kun udvalgte kategorier fører restbeløb videre.
Almindelige kategoriers restbeløb og overskridelser påvirker Opsparing.
Visning og nedenstående rapportfelter er stadig forslag til afprøvning.

```text
BudgetComparison | null
  month, accountIds, budgetId, currency
  coverage, provisional, unclassifiedWarning
  plannedIncome, plannedSpending, earmarked
  plannedSavings, actualSavings, savingsDifference, incomeDifference
  rows: [{categoryId, name, carryForward,
          opening, allocated, available, actual,
          remaining, carriedForward, savingsImpact}]
```

- Budgetbeløb og øremærkning er ikke transaktioner og ændrer ikke historisk
  forbrug. `actual` bruger udgifter efter tilbagebetalinger.
- `available = opening + allocated`; `remaining = available - actual`.
  Almindelige kategorier starter på nul og afleverer resten til Opsparing.
  Kategorien Ferie gemmer resten til næste måned i det viste eksempel.
- `actualSavings` er månedens bidrag til almindelig opsparing efter ændringen
  i de øremærkede reserver. Det er ikke den eksisterende `measures.savings`,
  som fortsat betyder indtægter minus udgifter i de gældende domænedokumenter.
  Det nye begreb må ikke stiltiende erstatte det eksisterende analyticsmål.
- Browseren modtager alle økonomiske beløb færdigberegnet. Rapporten skal
  udtrykke usikkerhed fra både aktuelle og tidligere måneder ved videreførsel.
  Ukendt forbrug/ukendt startreserve må ikke blive en bekræftet nulværdi.
- Budgetafgrænsningen skal svare til forbrugsafgrænsningen. Ingen automatisk
  forholdsmæssig fordeling af et husstandsbudget på udvalgte konti.
  Prototypen viser derfor kun budget ved begge syntetiske konti.
- Nulbudget, negativ ferierest, ændrede mål, startsaldi og en negativ almindelig
  opsparing skal afprøves før et egentligt budgetkontraktforslag fastlægges.
  Der er ikke lavet budgetmotor eller ændret accepterede domænebeslutninger.


## Enkel og avanceret visning — overlevering 17. september

Brugeren efterspørger et skift i detaljegrad efter viderebragt feedback fra
sin kone. Valget ændrer ikke rapportens økonomiske værdier. De eksisterende
oplysninger om datadækning, foreløbig periode og ukategoriserede beløb er nok
til en kort tillidsmarkering i Enkel og detaljer i Avanceret. Der foreslås
ikke nye beregnede beløb eller brugerroller af den grund. Præcis opdeling,
standardvalg og eventuel lagring af visningspræferencen skal afprøves under
implementeringen; de er ikke valideret af det nuværende skærmbillede.
