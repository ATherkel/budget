# Forslag til det mindste nødvendige månedsrapportformat

**Forslag ud fra skærmens behov. Endnu ikke valideret af jer og ikke en
Gold-kontrakt.** Skærmen modtager en rapport fra analyselaget. I den rigtige
applikation skal rapporten komme gennem dette lag; den private forberedelse
af eksempler skal ikke kopieres til produktionskode.

De tekniske feltnavne er bevaret på engelsk. Alle tekster, der vises for
brugeren, skal være danske. Dette sprogkrav er udtrykkeligt bekræftet.

```text
MonthlyReport
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

TransactionDisplay
  id, accountId, accountName, date, description, amount, kind, kindLabel
```

- Beløb er præcise decimalstrenge i én angivet valuta. Penge ud er negative;
  udgifts- og kategorisummer er positive ved forbrug og kan blive negative,
  når tilbagebetalinger er større end køb. Andelen tilbage er null, hvis
  indtægterne ikke er positive. Browseren beregner ikke økonomiske nøgletal.
- Observeret behov: Fortegnet på hver postering skal være tydeligt. Det
  eksisterende signerede `amount` er nok til visning med plus/minus og
  Penge ind/Penge ud; intet ekstra beregnet rapportfelt er nødvendigt.
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
- Ejerskab er en visningsegenskab, ikke en kontotype eller en regel for
  overførselsmatchning. Min/Hendes/Fælles/børn skal ikke være fem kontotyper.
- Posteringernes id'er er rapport-id'er. Skærmen behøver ikke bankkontonumre,
  CSV-filnavne, kilderækkenumre, adgangsoplysninger eller rå kildeindhold.
- `barPercent`, hjælpetekster, `openingBalance` til kontrol og oplysninger om
  eksempeldatasæt er prototypefelter, ikke nødvendige produktionsfelter.
- Lister med alle posteringer er nok her. Opdeling i sider eller en særskilt
  detaljerapport kan afgøres senere. År-til-dato, udvikling over tid og
  yderligere filtre ligger uden for denne første version.

Åbent: Forstår begge deltagere navnene? Er indtægter minus udgifter det bedste
hovedtal? Hvilke kontogrupper skal vises? Forklarer en kategorisum og dens
posteringer en overraskelse? Hvor meget skal vises om manglende kontodata uden
at rulle? Hvad skal den fremtidige kategorisering levere? Ingen foreslåede
ADR'er er accepteret gennem prototypen.
