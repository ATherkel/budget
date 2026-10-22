# #11 — month-overview prototype, second round

## Publication handoff — 29 September 2026

The latest prototype includes Enkel / Avanceret, isolated Kontrol diagnostics,
Mod budget in both modes with elapsed-month markers, and category-filtered
actual-versus-budget trends. The interface remains a synthetic, loopback-only
reference; the household has not yet reviewed this latest version.

The production direction is now specified in [issue #100](https://github.com/ATherkel/budget/issues/100)
and the [local implementation plan](../../docs/plans/dashboard-implementation-spec.md).
That plan records the confirmed defaults, group-and-category trend selection,
immutable household budget plans, and the later fixed-expense and reserve work.
Those production decisions do not imply that every feature exists in this demo.
The sections below retain the prototype's development history; the specification
supersedes earlier unresolved scope notes. No production application is included.

🤖 Added by Codex (GPT-6 Astra)

**Throwaway prototype. Not production code, not promoted, and not a substitute
for user testing.** The interface is Danish; this document is English because
the issue, the handoff and the GitHub comments are.

It answers one question: can an everyday reader understand the month without
doing account maintenance, while a curious reader can inspect the same figures
and their evidence? The maintainer confirmed the direction on 17 September
2026 and asked for a `Enkel` / `Avanceret` choice after relaying that the first
screen held too many numbers. That choice exists now, and it is not yet tested
with anyone.

## How to run it

From the repository root:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Open <http://127.0.0.1:8011>. Stop with Ctrl+C. If 8011 is taken, use another
port, for example `py -3.12 prototypes/dashboard-11/serve.py --port 8019`.
The server binds to `127.0.0.1` only: it is not reachable from the home
network, and it never reads `imports/`, a bank export or a private report. A
fresh checkout works with the synthetic fixture alone.

The screen opens on a **demonstration login**. Any input — or none — proceeds.
There is no password, no server check, no cookie, no storage and no security
claim; the fictional household phrase is `fisk-i-haven` and the screen says so.
**Log ud** returns to it.

## What the screen shows

**Enkel** (the default) is the quiet overview: the month, three plain figures
(income, expenses, what is left — text, not buttons), one compact coverage line
that names any incomplete account, a provisional label, one short notice that
some figures are provisional or incomplete and that amounts without a category
are left out, and the short category list. The notice carries a **Se
forklaring** control that opens `Avanceret → Kontrol`. Categories are the only
drill-downs: no counts, no charts, no accounts, no transfers, no adjustments.

**Avanceret** keeps the same figures and adds navigation:

- **Overblik** — the figures, the trend chart, the category list, and the
  synthetic budget experiment (see below). Diagnostics stay out of it.
- **Detaljer** — per-account balances with the statement date and evidence
  through date, the transfers, and the adjustments.
- **Kontrol** — everything diagnostic: coverage per account, the provisional
  status and its reasons, the reconciliation (income − expenses = what is
  left, categories adding up to expenses, entry counts per group), money
  without a category with the documented `budget review` / `budget decide`
  route, and the transfers and adjustments that are held outside the totals.

The mode is a display preference, not a role: it changes detail, never a
figure, the selected accounts, the month or the publication. Saving the
preference is still undecided and nothing is stored in the browser.

### Publications

`Avanceret` also chooses what is being read. The same synthetic data appears as
three publications, and a past view keeps a banner and a **Tilbage til
nutiden** control in both modes:

| View | Data known | Interpretation | June expenses |
| --- | --- | --- | --- |
| Nutid (current) | through 15 September 2026 | today's | 13.110,00 kr. |
| Status 31. august 2026 (`as-was`) | imports by 31 August | the one in force then | 11.680,00 kr. |
| Kendt 31. august 2026 (`as-known-at`) | imports by 31 August | today's | 12.570,00 kr. |

The differences are real data differences, not a relabelled copy: a purchase
reached June in a September import, and a parking charge was unclassified
until a September manual decision. The `as-was` view also shows the old
category name `Tøj`, where the current publication says `Tøj og sko`.
Provisional labels follow the view's own knowledge time.

Provisional follows the accepted seven-day rule, not a guess: a closed month
keeps the label until every imported account has an export whose declared range
covers the month's last day *and* which the bank produced at least seven days
after that day. An account with no imported export at all is exempt. A closed
month can therefore be complete in coverage and still read **Foreløbige tal**
(August does, because Fælleskonto's export is dated 5 September), while the
still-running month reads **Måneden indtil nu — foreløbige tal**.

## The synthetic fixture

`example.json` is generated, and every account, amount and description in it is
invented:

```powershell
py -3.12 prototypes/dashboard-11/build_example.py      # writes example.json
py -3.12 prototypes/dashboard-11/check_fixtures.py     # audits it
```

`build_example.py` reads nothing but its own constants; it is a fixture
builder, not an import engine. `check_fixtures.py` reads only `example.json`
and compares it with hand-checked constants, so the two cannot agree by
construction.

The example holds one account-month with no evidence, one partial account
month, one confirmed quiet month, one category that ends negative because a
refund is larger than the purchases, money without a category, an uncategorised
adjustment, both legs of one paired transfer, one manually decided one-sided
transfer, one transfer claim that has no counterpart anywhere and therefore
appears only as money without a category, and a current month that is still
running. Missing is `Ukendt`, never `0,00 kr.`; a confirmed quiet month is a
real zero. The audit recomputes the provisional verdict from an independently
written export table, including the case that used to be wrong: an export made
late enough, but whose range begins *after* the month it is asked about, cannot
finalise it (Fælleskonto has no export reaching April, so April stays
provisional).

The budget experiment is reachable from any selection: **Åbn opdigtet budget ·
begge konti** selects both example accounts, switches to the current
publication and picks a month the synthetic budget covers (July, August or
September).

## What differs from `main` and from Gold

- `main` holds no dashboard. This folder is untracked prototype work on its own
  branch; it adds no application code, no dependency and no configuration.
- Gold 0.2, `analytics-layer.md`, `publications.md`, `classification.md` and
  `operations.md` are the accepted rules this prototype tries to honour. Where
  it cannot, it says so: see [REPORT-SHAPE.md](REPORT-SHAPE.md), which is a
  proposal and still needs the maintainer's acceptance.
- The dashboard has no publication store, no analytics layer, no login backend
  and no database. It renders one fixed fixture, and the fixture does the
  arithmetic that belongs to analytics.
- Budgeting and earmarked vacation savings stay an experiment under
  `Avanceret` and outside the first-delivery scope; issue #2 excludes budget
  targets, so they need their own scope decision.

## What is not validated

No participant has completed the three original tasks on this version, in
either mode. In particular nobody has tested whether `Enkel` answers "where did
the money go", whether the coverage line is noticed at all, whether the
`Kontrol` wording is understandable, whether the publication banner is
understood as "not today's numbers", or whether the demo login reads as a demo.
The figures and the layout are the agent's own checks, not evidence of
usability. `#11` stays open.

## Testing it together

Let the person who knows the project least drive first, and wait with your
explanations:

1. Find out where the money went this month. (Try September, then August.)
2. Pick one category and explain why its amount looks the way it does.
3. Find the figures you should treat as incomplete.

Then repeat step 1 in the other mode, and try **Avanceret → Kontrol** together.
Note what the driver does, expects, hesitates over, and their own words; help
that was needed means the task was not solved unaided.

## Guardrails

One Danish interface, no editing, no database, no login backend, no imports,
no browser storage, no packages to install (HTML, CSS, JavaScript and the
Python standard library only), and nothing that leaves this computer. See
[ROUND-2-IMPLEMENTATION.md](ROUND-2-IMPLEMENTATION.md) for what this round
changed and how it was checked.

## Third round: budget and category trends

This round adds the comparison the maintainer asked for, without promoting the
prototype.

`Enkel` now carries the same `Beløb` / `Mod budget` switch as `Avanceret`. In
`Mod budget` it lists the ordinary monthly expense plans with the amount used,
the amount available and the remainder, plus the elapsed-time marker in the
running month. The earmarked vacation, its carried-forward reserve and the
savings reconciliation stay out of `Enkel`; one line says why. Tapping a row
still opens the transactions behind the figure.

`Avanceret → Overblik → Udvikling over tid` gains a labelled category selector
with `Alle kategorier` and every category the selected accounts show anywhere in
the selected publication. `Alle kategorier` keeps the existing income, spending
and remainder series and adds `Budgetteret`; choosing a category shows only that
category's actual spending and its own monthly plan. Budget figures exist only
for the publication, account selection and months the synthetic budget covers
(both accounts, the current view, July-September 2026); anywhere else the budget
stays unknown rather than zero. A category with no rows reads `0,00 kr.` only in
a month that is complete, and August's net refund stays negative.

Accepted scope change, recorded here for the maintainer: a **read-only** budget
comparison belongs in the first actual application release. Budget targets are
maintained outside the dashboard, and editing or forecasting inside it is
deferred. This replaces the earlier round's note that budgeting sits outside the
first-delivery scope (#2). Production input, versioning and the reserve
semantics still need the maintainer's acceptance.

What is not validated: no browser pass was completed by the implementing agent
this round, and no participant has used the version. See
[TRENDS-IMPLEMENTATION.md](TRENDS-IMPLEMENTATION.md) for the exact checks, the
missing browser evidence and the open decisions.

---

## Previous round (Danish, kept as history)

The text below describes the first prototype round. The private local dataset
it mentions is no longer served: the server now reads the synthetic fixture
only, and the private files on disk were left untouched.

# #11 — prototype af et månedsoverblik

**Frosset 17. september 2026 som bekræftet retning for implementering.**
Se [HANDOFF.md](HANDOFF.md) for ejerens bekræftelse, viderebragt feedback fra
hans kone og kravet om Enkel/Avanceret til den egentlige løsning. Skiftet er
ikke bygget i prototypen.

Én dansk udgave uden redigering, lavet med HTML/CSS/JavaScript og Pythons
standardbibliotek. Bevares som reference på prototypegrenen; koden skal ikke
promoveres til produktion. Ingen pakker skal installeres.

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

## Kontovalg, graf og kompakte posteringer

Vælg én eller begge af de to tilgængelige konti. Overblik, kategorier,
posteringer, saldi og graf følger samme valg. Ingen valgte konti giver en tom
visning. Kontovælgeren bruger kontolisten; eksemplerne indeholder endnu ikke
flere personlige konti, hendes konto eller børnenes konti.

Grafen viser indtægter, udgifter og beløbet tilbage pr. måned. Vælg seneste
12 måneder, indeværende år eller egne start- og slutmåneder. Eksemplets faste
dato er 15. september 2026. Manglende måneder bliver huller, ikke nul.
Månedstabellen viser beløb og datagrundlag og kan åbne en måned i overblikket.
Posteringer vises kompakt med farve og tydeligt fortegn.

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
- Alle tre ikke-tomme kontokombinationer har egne, forberedte rapporter i
  `views`. Regnekontrollen sammenholder dem med de oprindelige posteringer.
  Browseren vælger rapporter og beregner alene grafens koordinater. En konto
  uden oplysninger giver ukendte beløb; en bekræftet stille måned giver nul.

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

### Budgeteksempel

Vælg **Mod budget** under **Hvor blev pengene af?**. Budgetvisningen findes
for **Opdigtet eksempel** med begge konti valgt. Fra andre datavalg kan knappen
**Åbn opdigtet budget · begge konti** åbne den. Samme startkommando som ovenfor.

Skift mellem juli, august og september: Ferie får 3.000 kr. om måneden og gemmer
resten; almindelige kategoriers over-/underforbrug påvirker Opsparing.
Budgetter, startreserve og de øvrige månedsrammer er opdigtede. De kan ikke
redigeres. September og beløb uden kategori gør sammenligningen foreløbig.
Retningen og reglen om videreførsel er bekræftet. Budgetternes ydertilfælde og
en samlet arbejdsgang med ferieøremærkning mangler stadig afprøvning.
