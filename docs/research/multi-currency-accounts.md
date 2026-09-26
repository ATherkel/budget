# Multi-currency bank accounts

Research written 2026-09-26 for the owner's question: would a bank like Revolut break this project's rule of one currency per account? Sources are the banks' own help centres, terms and API documentation, and the specifications that own the formats. I read every bank page, terms document and API page on **2026-09-26**. Bank pages change, so check them again before relying on them. No blogs, forums or comparison sites were used, and no household data. Where a claim rests on a product (marketing) page, or I could not open a page, the text says so. Claims I could not verify are listed at the end.

**Short answer.** Revolut and Wise hold several currencies inside one customer account, but each currency balance has its own balance, statement and API ID, and the Berlin Group, UK Open Banking and camt.053 standards model it the same way. Registering each currency balance as its own account in `accounts.toml` therefore keeps "every amount is in its account's currency" true. What breaks is anything that compares or adds money across accounts: transfer matching needs amounts that cancel exactly, so a DKK-to-EUR exchange can never pair, and a household total across currencies needs an exchange-rate rule that does not exist yet.

## 1. Revolut

### How accounts are organised

| | Personal | Business |
| --- | --- | --- |
| Unit | One "currency account" per currency. "You can only have one currency account for each currency" ([open a currency account][rev-open]) | Several accounts, "each with unique account details" ([currency accounts][revb-create]). A second account in the same currency gets another IBAN ([multi-currency IBAN][revb-iban]) |
| Account details | EEA customers get a EUR account with a Lithuanian (LT) IBAN, GBP sort code and account number, and SWIFT details for other currencies ([account details][rev-details]) | "A single IBAN that can accept funds in many currencies". Incoming money goes to "the correct currency account associated with the IBAN, without doing any FX exchange" ([multi-currency IBAN][revb-iban]) |
| Balance | Chosen per currency in the app ([statement vs app balance][rev-baldiff]) | API `Account` has one required `currency` and one `balance` ([Business API schema][revb-yaml], [Retrieve all accounts][revb-accounts]) |
| Statement | Per currency: pick the currency, then Statement, then "PDF or Excel" ([currency statement][rev-stmt]) | Account statements: "Each currency account will have an individual statement generated", as PDF, CSV, XML (camt.053) or TXT (MT940) ([account statements][revb-stmt]). Separate transaction statements, PDF or CSV, can be filtered "by your accounts, cards, currencies" ([transaction statements][revb-txstmt]) |

A personal currency statement contains holder details, BIC and IBAN, a "Balance summary", "Pending, completed, and reverted transactions" and Pocket transactions ([currency statement][rev-stmt]). Its closing balance is "your available funds to spend plus pending transactions" ([statement vs app balance][rev-baldiff]). The help pages do not list the CSV or Excel **columns**. I found no Revolut page saying whether each row carries a running balance or a currency column.

Currency accounts come and go. A personal currency account can be removed once its balance is cleared, and the main one cannot ([open a currency account][rev-open]). Exchanging into an inactive currency re-activates its account ([exchange help][rev-exfind]).

### Exchanges and card payments

- **Exchange.** You pick two currencies and an amount in the app. A completed exchange cannot be cancelled, only reversed by a new exchange ([how to exchange][rev-exchange]). In the Business API an internal move "out of the GBP account and into the EUR account" is **one transaction with two legs**, one per account. Each leg has its own `account_id`, `amount`, `currency` and `balance` ([`Transaction.legs`, `TransactionLeg`][revb-yaml]). How an exchange appears in a *personal* Excel statement is not documented.
- **Card payment in a currency you don't hold.** Revolut checks "Transaction currency", then "Your base currency", then "The active currency with the highest balance". It charges the first one with enough funds and "won't combine multiple currencies" ([what currency will I be charged in][rev-charged]; the en-DK copy returned 404, so this is the Irish copy from Revolut Bank UAB). A card can be pinned to spend from chosen currencies (same page).
- **Fees.** On Standard, a 1% exchange fee applies above kr. 7.500 a month, plus 1% on weekends ([card fees][rev-cardfee]). The allowance covers "exchanges made automatically as part of a transaction" ([exchange fees][rev-exfee]). For card payments "you'll be able to view the breakdown of the total cost within the app after the transaction" ([exchange rates][rev-rate]). Where the fee lands in a personal export is not documented.
- **Automatic moves between currencies.** If a balance goes negative, "We'll try to use money from your other currency accounts to bring your account back to a positive balance" ([negative balance][rev-neg]).
- In the Business API a card leg carries `amount` and `currency` in the account's currency, `bill_amount` and `bill_currency` ("The billing amount for cross-currency payments"), a separate `fee`, and the account `balance` ([`TransactionLeg`][revb-yaml]). The example debits an AED account −47.8 for a USD 13 purchase, with a fee of 0.66.

### Revolut's Open Banking API

It follows the UK Open Banking data model (`OBReadAccount3`, `OBReadTransaction4`) ([Open Banking API schema][rob-yaml]). Each account in `/accounts` has one `Currency`. Revolut warns: "Identification will typically contain an account number or an IBAN, but these can be the same across several currency subaccounts. Each of the subaccounts will always have a unique and immutable `AccountId`" ([AIS tutorial, step 6][rob-tut]). Transactions are read per `AccountId`. The examples carry `Amount`, a per-transaction `Balance`, and for exchanges a `CurrencyExchange` block with `SourceCurrency`, `TargetCurrency` and `ExchangeRate` ([schema examples][rob-yaml]). Business domestic payments note that "Revolut Business users can have multiple accounts in the same currency" (same file).

## 2. Wise

- **Structure.** "All currencies are held in your one Wise account" ([What is a Wise account?][wise-what]). In Wise's API, "A multi-currency account has the ability to have one or multiple balance accounts in different currencies", and "A balance account has a specific currency" ([multi-currency accounts][wise-mca]). Only one `STANDARD` balance can exist per currency. `SAVINGS` balances (jars) can repeat a currency ([balance accounts][wise-bal]). The help centre says jars can "hold the same currency in two different places" ([What is a Wise account?][wise-what]).
- **Account details.** Available for some currencies only, one set per currency. "Account details aren't separate accounts — they're a way to make a pay-in or receive money into your Wise account" ([What is a Wise account?][wise-what]). Wise's Open Banking guide adds that not every currency account has bank details, so clients should use `AccountId` ([Open Banking][wise-ob]).
- **Statements.** Downloaded "for your currencies and jars", 365 days at a time. Formats on the web: PDF, XLSX, CSV, MT940, QIF or CAMT.053 (version 10); in the app: PDF, CSV and XLSX. Several currencies at once arrive as a zip file. Accounting statements can show fees separately ([download a statement][wise-stmt]). The API statement is per `balanceId` and currency, in the same formats ([Get Balance Statement][wise-bs]). Each row has `amount` with its currency, `totalFees`, a `runningBalance` ("Running balance after the transaction"), a `details.type` such as `CARD`, `CONVERSION`, `INCOMING_CROSS_BALANCE` or `OUTGOING_CROSS_BALANCE`, and a `referenceNumber`. `COMPACT` gives one line per transaction. `FLAT` gives "Accounting statements where transaction fees are on a separate line" (same page).
- **Conversions.** One `balance-movements` call converts between two balances. The response lists `balancesAfter` for both, plus `sourceAmount`, `targetAmount` and `rate` ([convert between balances][wise-move]). On the statement a conversion row carries `sourceAmount`, `targetAmount`, `fee` and `rate` ([Get Balance Statement][wise-bs]).
- **Card spending.** "Smart Conversion" takes the money "from the currency with the lowest conversion fees". "You can't set a default or preferred currency to convert from". Moving money to a jar is the only way to exclude it ([spending a currency you don't have][wise-spend]). In the API example a EUR balance is debited −7.76 for "Card transaction of 6.80 GBP". The original amount is in `details.amount` and `exchangeDetails.forAmount`, with the rate beside it ([Get Balance Statement][wise-bs]).
- **API model for third parties.** Wise's Open Banking API "follows the Open Banking UK standard" v3.1.11. `/accounts` returns "all open currency accounts". Fees "are returned as separate DEBIT transactions with an attached reference to the original transaction" ([Open Banking][wise-ob]).
- For cards issued through Wise Platform partners, "When a refund or credit arrives in a new currency, Wise automatically creates a balance in that currency" ([Manage multi-currency balances][wise-cards]). That guide is for partner integrations. I did not confirm the same for Wise's own consumer card.

## 3. Danish banks

**Currency accounts.** Danske Bank and Nordea offer a *valutakonto* (currency account) on their **business** pages. Each is an account opened in one currency.

- Danske: "En valutakonto er en indbetalingskonto i udenlandsk valuta … i den valuta, som kontoen er oprettet i, f.eks. EUR på en EUR-konto" [a deposit account in the currency it was opened in]. Danske recommends one account per currency. It offers a routing agreement "så du slipper for at skifte kontonummer på fakturaer … EUR-indbetalinger ender på din EUR-konto" [so you avoid changing account number on invoices]. I read that as each currency account having its own number ([Danske valutakonto, product page][db-valuta]). The private account list shows no currency account ([Danske private accounts][db-konti]).
- Nordea: "En valutakonto er i princippet det samme som en almindelig konto - bare i fremmed valuta" [the same as an ordinary account, just in a foreign currency]. "Som erhvervskunde … kan du oprette konti i alle gængse valutaer" [business customers can open accounts in all common currencies] ([Nordea valutakonto, product page][nd-valuta]). I found no private-customer page.
- Lunar: in its Open Banking API each account has one `currency` ("e.g., DKK, SEK, NOK") ([Lunar Accounts API][lunar-api]). I found no Lunar consumer account in a foreign currency.

**A card payment in EUR on a DKK account is booked in DKK.**

- Danske's Visa/Dankort terms (from 2 September 2024), section 18.3: "Køb foretaget i udlandet omregnes til danske kroner og skal altid betales i danske kroner" [purchases abroad are converted to and always paid in DKK]. The rate is a daily average of Visa rates, and "Der kan være sket ændringer i valutakursen fra det tidspunkt, hvor du har brugt kortet, til beløbet hæves på kortkontoen" [the rate may have changed between card use and debit] ([Regler for Visa/Dankort][db-vd]). Danske also charges 0.5% (EU/EEA, Switzerland, UK) or 1.5% for a foreign card payment ([cards on holiday][db-ferie]).
- Nordea's Visa/Dankort terms (August 2025), section 17.3: "Beløbet vil altid blive trukket i danske kroner på din konto" [always debited in DKK], with the same warning that the rate can change before the amount is debited ([Nordea Regler for Visa/Dankort][nd-vd]).
- **Dynamic currency conversion (DCC).** The merchant may offer to convert to DKK at the terminal. The merchant then sets the rate and fee, and the bank has no influence ([Danske terms 18.4][db-vd], [Nordea terms 17.5][nd-vd]). Danske's example: EUR 100 via DCC costs DKK 800; paid in euro and converted by the bank, DKK 755 ([DKK or local currency][db-dcc]). Either way the account shows DKK.
- Lunar's API makes the split explicit. `billingAmount` is "the amount that was actually posted to the account, in the currency of the posting". `transactionAmount` is the original. Example: EUR −20.0 posted as DKK −149.0 ([Lunar Accounts API][lunar-api]).
- **Owner's observation, not a sourced fact.** On the Danske export a foreign card payment shows only DKK in `Beløb`. The foreign amount appears only inside `Tekst`, e.g. `LIDL €15.00`, whether the owner paid in local currency or accepted the terminal's DKK. This fits the terms above and the repo's note that the Danske file "contains no account, currency, or transaction identifier" ([bronze-layer.md:129](../architecture/bronze-layer.md)). No Danske page documents what the CSV text contains.

**Pending versus booked amounts.** Both banks' terms say the rate can change between card use and the debit, and both allow merchants such as hotels to reserve an amount ([Danske 3.1, 18.3][db-vd]; [Nordea 3.2, 17.3][nd-vd]). Lunar says `transactionAmount` can be null "when the payment was never reserved on the account" ([Lunar Accounts API][lunar-api]). So a reserved amount differing from the final booked amount is expected. None of the sources says a *booked* amount changes afterwards. In this repo, pending rows stay `UnbookedRecord` provenance and "never a transaction" ([silver-layer.md:111, 191–193](../architecture/silver-layer.md)). The sources therefore support the owner's view that the difference is harmless. The Danske data map also knows no pending status yet: the first such export is quarantined for a person to decide ([data map, booking status](../architecture/data-maps/danske-csv-v1-to-silver.md)).

## 4. Specifications

**Berlin Group NextGenPSD2.** "A multicurrency account is an account which is a collection of different sub-accounts which are all addressed by the same account identifier like an IBAN … The sub-accounts are legally different accounts and they all differ in their currency, balances and transactions. An account identifier like an IBAN together with a currency always addresses uniquely a sub-account" ([Implementation Guidelines v1.3.4, §4.5][bg-ig]). A client addresses either the collection (`{"iban": …}`) or one sub-account (`{"iban": …, "currency": "EUR"}`). The Guidelines say the product is used "in some markets in Europe, e.g. … within the Belgium market" (same section). Consent on the IBAN alone "implies getting it for all sub-accounts". At aggregation level, balances come back as an array, one per sub-account, each with its currency. The transaction list "will contain all transactions of all sub-accounts" and "may have different transaction currencies" (§6.3). The bank decides whether to offer aggregation level, sub-account level or both. An aggregated account reports currency `"XXX"`. The current OpenAPI file (v1.3.16, 27 November 2025) still carries the `"XXX"` rule and the multicurrency examples ([v1.3.16 OpenAPI][bg-yaml]). Transactions may carry `balanceAfterTransaction` and `currencyExchange`. Card transactions add `originalAmount` and `markupFee` (same file). I could not open the newest Guidelines PDF, because the [downloads page][bg-dl] builds its table with scripts. The quotes are from v1.3.4 (2019).

**UK Open Banking Read/Write API (v3.1.11).** An account's `Currency` is "the currency in which the account is held". Its usage note says it matters when "one and the same account number covers several currencies". `SecondaryIdentification` "may be populated with … a currency code where an account has multiple currency sub-accounts" ([Accounts][ob-acc]). Every transaction `Amount` and every balance carries its own currency. A transaction may have a `CurrencyExchange` block (source, target and unit currency, rate, instructed amount) and a `Balance` after the entry ([Transactions][ob-tx]). The standard also allows a "wallet" account with balances in several currencies, a `LocalAmount`, and a `TotalValue`: the "Combined sum of all Amounts in the accounts base currency" ([Balances][ob-bal]). Revolut and Wise do not use the wallet form. They return one `AccountId` per currency (§1, §2).

**ISO 20022 camt.053.** A statement message "can contain reports for more than one account" and "contains information on booked entries only". Each `Statement` block "Reports on booked entries and balances for a cash account". The account's `Currency` "should only be used in case one and the same account number covers several currencies" ([camt.053.001.08 MDR][iso-mdr]). So one account number with several currencies is reported as separate statements, told apart by currency. Entries can carry `InstructedAmount`, `TransactionAmount` and `CounterValueAmount` with exchange details (same document). Revolut Business and Wise both produce camt.053 per currency account or balance (§1, §2).

## 5. What Kimball recommends

"Fact tables that record financial transactions in multiple currencies should contain a pair of columns for every financial fact in the row." One column holds "the true currency of the transaction", the other "a single standard currency". The standard value comes from "an approved business rule for currency conversion". "This fact table also must have a currency dimension to identify the transaction's true currency" ([Multiple Currency Facts][k-mcf]). Kimball's 1998 article adds a currency exchange table of daily rates, and suggests "an agreed upon daily spot rate" ([Think Globally, Act Locally][k-1998]). In that article's example the currency comes from the *country* dimension (same page), a currency carried by another dimension. That is what this repo does with the account. Its six-decimal rule comes from the 1998 euro changeover. I found no Kimball Design Tip on currency conversion.

## What this means for this repo

Everything in this section is my inference from the findings above, not a statement from the sources.

**One account per currency keeps the rule true.** Every source books each amount in exactly one currency per ledger: Revolut currency accounts, Wise balances, Berlin Group sub-accounts, and Danske and Nordea currency accounts. A card payment's merchant currency is a second, *descriptive* amount: Revolut's `bill_amount`, Wise's `forAmount`, Lunar's `transactionAmount`, Berlin Group's `originalAmount`, Danske's text. It is not the booked amount. Registering each currency balance as its own account keeps [gold-layer.md:55](../architecture/gold-layer.md) true, just as Danske's `LIDL €15.00` in text does today. Four conditions follow:

- **One import file per currency account.** An import run declares one account ([bronze-layer.md:11](../architecture/bronze-layer.md)). Currency comes from configuration, "never from the payload" (line 80). Revolut personal statements, Revolut Business account statements and Wise statements already come per currency. A Revolut Business transaction statement across currencies, or a Berlin Group aggregation-level list, would need splitting first.
- **Jars and Pockets are separate balances.** They can share a currency with the main balance, so each is its own account or is left out.
- **The registry must follow the bank.** Currency accounts are added, removed and re-activated. Wise can even create one from a refund. A new currency is a new `account_id`, never an edit. A shared IBAN does not matter, because `account_id` is "Never a bank account number" ([gold-contract.md:58](../architecture/gold-contract.md)).
- **Minor units and parsing.** Each currency must be in ADR-013's ISO 4217 table, or it is rejected ([ADR-013:56–57](../decisions/ADR-013-sqlite-store-integer-minor-units.md)). Revolut and Wise send JSON numbers (`double` in Revolut's schema). A connector must parse them straight to `Decimal`, because ADR-013 forbids passing through `float` (line 59).

**The balance chain still holds, one chain per currency.** An exchange debits the DKK chain and credits the EUR chain, and each checks in its own currency ([ADR-006](../decisions/ADR-006-balance-chain-reconciliation.md): later balance = earlier balance + later amount). Revolut, Wise and both standards all supply a balance after each transaction. Two things need checking against a real export:

- **Fees.** Revolut keeps `fee` apart from `amount`. Wise has `totalFees` on a `COMPACT` line, or a separate `FLAT` line, and a separate debit in Open Banking. The chain holds only if the mapped amount includes the fee, or the fee is its own row.
- **Pending rows.** Revolut's personal statement balance includes pending rows, which this repo never books.

**Transfer matching fails across currencies, as documented.** Candidates need amounts that "cancel exactly" ([classification.md:138](../architecture/classification.md)). A manual `pair` is not applicable when "the amounts do not cancel" (line 199). An exchange of DKK −750.00 for EUR +100.00 is therefore never a candidate and cannot even be paired by hand. Each leg would then fall to rules as income or expense, in two currencies. A EUR-to-EUR transfer still matches. This goes beyond issue #47 (a transfer that loses a fee, line 177): no amount comparison means anything without a rate. The sources do offer other evidence. Revolut Business puts both legs in one transaction, and Wise records one conversion with source and target amounts. Revolut also moves money between currencies on its own when a balance goes negative. The household balance sum at [gold-layer.md:206](../architecture/gold-layer.md) and the "lower by the amount in flight" argument (classification.md:190) also assume one currency. Invariant 13 forbids that sum across currencies ([gold-contract.md:197](../architecture/gold-contract.md)).

**A household total in DKK needs a rate rule.** The owner's work pattern keeps the original currency where the booking happens and converts downstream. That matches Kimball's pair of columns and IAS 21. IAS 21 records a transaction "by applying … the spot exchange rate … at the date of the transaction" (¶21; an average rate is allowed "for practical reasons", ¶22). At each reporting date "foreign currency monetary items shall be translated using the closing rate" (¶23), and differences go to profit or loss (¶28) ([IAS 21 text][ifrs-std]; the [IFRS summary][ifrs-sum] names "which exchange rate(s) to use" as the principal issue). Cash is a monetary item: "units of currency held". A DKK-valued monthly snapshot of a EUR account would therefore change in a month with no transactions. Invariant 12, `opening_balance + sum(amounts) == closing_balance` ([gold-contract.md:196](../architecture/gold-contract.md)), would hold in EUR but not in DKK. EUR is the likeliest second currency, and it barely moves. Denmark keeps "a central rate of 746.038 kroner per 100 euro" within ±2.25% (729.252–762.824). The Nationalbank keeps it "much closer to the central rate". "The krone is floating against all other currencies but the euro" ([Danmarks Nationalbank][dnb]). Even at the band's edges, EUR 10,000 is worth only DKK 72,925.20 to 76,282.40. *Questions:* is a cross-currency total needed at all? If so, which rate (the bank's applied rate, ECB's or the Nationalbank's) and which date (transaction date for flows, month end for balances)? And is the rate table an input or data?

**An account's currency does not change in practice.** Every source ties currency to the account for life. The one real change I found shows how banks handle it: when Bulgaria adopted the euro, Revolut *closed* every BGN account and converted the balance to EUR at the fixed rate. "Your account details won't change" ([Bulgaria and EUR][revb-bgn]). In this repo that is `closed_on` on the old account plus a new account, not an edit. An edit to `currency` is only a correction of a wrong registration. Even that reaches Silver: Silver reads it ([silver-layer.md:12, 33](../architecture/silver-layer.md)), and `transaction_id` hashes the amount "quantized to the minor unit of the account's currency" ([data map:117](../architecture/data-maps/danske-csv-v1-to-silver.md)). The table's "Accounts … `rebuild --from gold`" row ([operations.md:217](../architecture/operations.md)) is right for display name, type, scope and `closed_on`, but a currency correction needs `rebuild --from silver`. *Question:* split that row?

**Which model do Revolut and Wise force?** Neither forces a currency on each transaction, as long as each file or API list covers one currency account. Their per-row currency then only repeats the account's currency. Silver could check that it matches instead of ignoring it. Only combined exports force a choice between splitting at import and a per-transaction currency. The merchant's original amount and currency could become an optional descriptive pair on the transaction without changing the booked-amount model. *Question:* is that pair wanted at all, given Danske only gives it as text?

## Not verified

- Revolut personal CSV or Excel column names, and whether rows carry a running balance or currency: third-party sources only. Revolut's help pages list none.
- How an exchange, and a card payment's exchange fee, appear in a *personal* Revolut export. This is inferred from per-currency statements and the Business API.
- Whether a Revolut *personal* EEA IBAN is shared across currency accounts: stated for Business and by the Open Banking tutorial, not on a personal page.
- Whether Wise splits a card payment between a partial balance and a conversion (its help text is ambiguous), and whether a `COMPACT` `amount` includes `totalFees`.
- That Wise's consumer card auto-creates a balance on a refund: the source is a Wise Platform partner guide.
- The absence of private currency accounts at Danske, Nordea and Lunar: I found none, which does not prove there are none.
- What Danske's CSV text contains for foreign payments, and whether its foreign-payment fee is a separate row: owner's observation only.
- Which Revolut API entity and market serves Danish customers; the Berlin Group Guidelines newer than v1.3.4 (checked only through the v1.3.16 OpenAPI file).

[rev-open]: https://help.revolut.com/en-DK/help/wealth/exchanging-money/what-currencies-are-available/how-do-i-open-a-currency-account/
[rev-details]: https://help.revolut.com/en-DK/help/transfers/inbound-transfers/how-to-receive-money-from-another-bank/what-account-details-should-i-use-to-transfer-money-to-my-revolut-account/what-account-details-are-available-for-me/
[rev-baldiff]: https://help.revolut.com/en-DK/help/profile-and-plan/managing-my-account/why-is-the-balance-on-my-statement-different-from-the-balance-shown-in-my-app/
[rev-stmt]: https://help.revolut.com/en-DK/help/profile-and-plan/managing-my-account/account-statement-per-chosen-currency/
[rev-exfind]: https://help.revolut.com/en-DK/help/wealth/exchanging-money/i-just-made-an-exchange-but-i-can-t-find-my-money-where-is-it/
[rev-exchange]: https://help.revolut.com/en-DK/help/wealth/exchanging-money/how-to-make-currency-exchanges/how-do-i-exchange-money/
[rev-charged]: https://help.revolut.com/en-IE/help/card-payments-withdrawals/spending-abroad-or-in-different-currencies/what-currency-will-i-be-charged-in/
[rev-cardfee]: https://help.revolut.com/en-DK/help/card-payments-withdrawals/getting-started-with-card-payments/can-i-pay-in-a-specific-currency/
[rev-exfee]: https://help.revolut.com/en-DK/help/wealth/exchanging-money/how-much-does-it-cost-to-make-an-exchange/will-i-be-charged-for-exchanging-foreign-currencies/
[rev-rate]: https://help.revolut.com/en-DK/help/wealth/exchanging-money/how-much-does-it-cost-to-make-an-exchange/what-foreign-exchange-rate-will-i-get/
[rev-neg]: https://help.revolut.com/en-DK/help/accounts/why-is-my-balance-now-negative/
[revb-iban]: https://help.revolut.com/en-DK/business/help/receiving-payments/transfers-info/international-iban/
[revb-create]: https://help.revolut.com/en-DK/business/help/setting-up-an-account/managing-my-currency-accounts/how-to-create-a-new-currency-account/
[revb-stmt]: https://help.revolut.com/en-IE/business/help/managing-my-business/viewing-my-account-statements/how-to-get-a-monthly-statement/
[revb-txstmt]: https://help.revolut.com/en-IE/business/help/managing-my-business/viewing-my-account-statements/finding-my-account-statement/
[revb-bgn]: https://help.revolut.com/en-DK/business/help/setting-up-an-account/managing-my-currency-accounts/question-bulgaria-is-joining-euro-what-will-happen-business/
[revb-accounts]: https://developer.revolut.com/docs/business/get-accounts
[revb-yaml]: https://developer.revolut.com/docs/api/business.yaml
[rob-yaml]: https://developer.revolut.com/docs/api/open-banking.yaml
[rob-tut]: https://developer.revolut.com/docs/guides/build-banking-apps/tutorials/get-account-and-transaction-information
[wise-what]: https://wise.com/help/articles/2897226/what-is-a-wise-account
[wise-stmt]: https://wise.com/help/articles/2736049/how-do-i-download-a-statement
[wise-spend]: https://wise.com/help/articles/2935778/what-if-i-spend-money-in-a-currency-i-dont-have-in-my-account
[wise-mca]: https://docs.wise.com/guides/product/accounts
[wise-bal]: https://docs.wise.com/guides/product/accounts/balance-accounts
[wise-bs]: https://docs.wise.com/api-reference/balance-statement/balancestatementget
[wise-move]: https://docs.wise.com/api-reference/balance/balancemovement
[wise-ob]: https://docs.wise.com/guides/developer/open-banking
[wise-cards]: https://docs.wise.com/guides/product/issue-cards/balance-currencies
[db-valuta]: https://danskebank.dk/erhverv/daglig-drift/erhvervskonto/valutakonto
[db-konti]: https://danskebank.dk/privat/produkter/konti
[db-vd]: https://danskebank.dk/-/media/pdf/danske-bank/dk/sp/Priser-vilkaar-faktaark/Kort/Regler-VISA-DANKORT-forbrugere-og-erhverv.pdf
[db-dcc]: https://danskebank.dk/privat/produkter/kort/danske-kroner-eller-lokal-valuta-i-udlandet
[db-ferie]: https://danskebank.dk/privat/news/saadan-goer-du-med-betalingskort-paa-ferien
[nd-valuta]: https://www.nordea.dk/erhverv/produkter/konti-betalinger/valutakonto.html
[nd-vd]: https://www.nordea.dk/Images/144-241317/VIL.36%20Kortregler%20for%20VisaDankort%20DK%20%2008.2025.pdf
[lunar-api]: https://docs.openbanking.lunar.app/api-overview/accounts
[bg-ig]: https://www.berlin-group.org/_files/ugd/c2914b_4a9b0db8c35841adb91531ef0faba4c2.pdf
[bg-yaml]: https://gitlab.com/the-berlin-group/nextgenpsd2/-/blob/main/Core%20PSD2%20Compliancy/psd2-api_v1.3.16-2025-11-27.openapi.yaml
[bg-dl]: https://www.berlin-group.org/nextgenpsd2-downloads
[ob-acc]: https://openbankinguk.github.io/read-write-api-site3/v3.1.11/resources-and-data-models/aisp/Accounts.html
[ob-tx]: https://openbankinguk.github.io/read-write-api-site3/v3.1.11/resources-and-data-models/aisp/Transactions.html
[ob-bal]: https://openbankinguk.github.io/read-write-api-site3/v3.1.11/resources-and-data-models/aisp/Balances.html
[iso-mdr]: https://www.iso20022.org/sites/default/files/documents/messages/mdr_part_2/ISO20022_MDRPart2_BankToCustomerCashManagement_2018_2019_v1_0.pdf
[k-mcf]: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multiple-currencies/
[k-1998]: https://www.kimballgroup.com/1998/12/think-globally-act-locally/
[ifrs-sum]: https://www.ifrs.org/issued-standards/list-of-standards/ias-21-the-effects-of-changes-in-foreign-exchange-rates/
[ifrs-std]: https://www.ifrs.org/content/dam/ifrs/publications/html-standards/english/2025/issued/ias21.html
[dnb]: https://www.nationalbanken.dk/en/frequently-asked-questions/questions-regarding-fixed-exchange-rate-policy

🤖 Generated with Claude Code (Claude Opus 5.5)
