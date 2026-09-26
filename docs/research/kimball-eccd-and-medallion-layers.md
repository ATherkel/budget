# Kimball's four ETL steps and the medallion layers

Research written 2026-09-26 for the owner's question: does conforming belong in Silver or in Gold, and does Kimball require the data to be saved after every step? Sources are Kimball Group's website, the book pages that Wiley has released, and Databricks' and Microsoft's own documentation. I did not read the full books. Where a claim rests only on a table of contents, or on a page I could not open, the text says so. No household data was used.

**Short answer.** Kimball's *conform* step makes separate sources agree: the same labels, the same measures, with duplicates removed. Building the dimension tables (surrogate keys, change history) and handing them out belong to his *Delivering* group ([34 subsystems][k2007]). Conforming that starts in Silver and ends with Gold's dimensions therefore matches Kimball. His 2004 book recommends saving the data after each of the four steps. Kimball Group later wrote that there is "no single answer" to how often to do so ([Design Tip #99][dt99]), so three stores do not contradict him.

## 1. What Kimball puts in each step

Kimball describes the ETL system (his "back room") in two ways.

- *The Data Warehouse ETL Toolkit* (2004) uses four steps: extract, clean, conform, deliver. "We resist the temptation to change ETL into ECCD!" ([Introduction, p. xxii][intro]).
- From 2007, Kimball Group lists 34 *subsystems* in four groups: "Extracting, Cleaning and Conforming, Delivering and Managing" ([Becker 2007][k2007]). Cleaning and conforming form **one** group there. The same grouping appears on the [Kimball Techniques page][k34] and in the *Lifecycle Toolkit*, 2nd ed., chapter 9 (headings on pp. 375, 380, 387 and 405, [table of contents][lcttoc]).

| Group | Subsystems | Result, per Kimball Group's 2013 slides |
| --- | --- | --- |
| Extracting | 1–3: data profiling, change data capture, extract | "Extracted Tables incl Format Conversions" ([E slide][slide-e]) |
| Cleaning and Conforming | 4–8: data cleansing, error events, audit dimension, deduplication, conforming | "Cleaned Tables and Conformed Dimensions" ([T slide][slide-t]) |
| Delivering | 9–21: slowly changing dimensions (SCD), surrogate keys, hierarchies, fact tables, surrogate key pipeline, late data, dimension manager, fact provider, aggregates, cubes | "Fact & Dim Tables Ready for Delivery" ([L slide][slide-l]) |
| Managing | 22–34: scheduling, backup, restart, versions, monitoring, lineage, security, compliance, metadata | ([M slide][slide-m]) |

The 2004 article "The 38 Subsystems of ETL" numbers its list 1–38 without group headings in the copy I read ([InformationWeek, 23 Nov 2004][iw2004]).

These are the conforming-related subsystems. Wording is from [Becker 2007][k2007]; the 2004 number, in brackets, is from [the 2004 article][iw2004].

| # | Subsystem | Group | What it does |
| --- | --- | --- | --- |
| 7 | Deduplication | Cleaning and Conforming | "Eliminates redundant members of core dimensions, such as customers or products. May require integration across multiple sources and application of survivorship rules …" |
| 8 [5] | Data Conformance (the [T slide][slide-t] calls it "Conforming System") | Cleaning and Conforming | "Enforces common dimension attributes across conformed master dimensions and common metrics across related fact tables." |
| 9 [10] | SCD Manager | Delivering | "Implements logic for slowly changing dimension attributes." |
| 10 [9] | Surrogate Key Generator | Delivering | "Produces surrogate keys independently for every dimension." |
| 14 [19] | Surrogate Key Pipeline | Delivering | "Replaces operational natural keys in the incoming fact table record with the appropriate dimension surrogate keys." |
| 17 [24] | Dimension Manager | Delivering | "Centralized authority who prepares and publishes conformed dimensions to the data warehouse community." |
| 18 [25] | Fact Table Provider | Delivering | "Owns the administration of one or more fact tables and is responsible for their creation, maintenance and use." |

The dimension manager has these duties: implement "the common descriptive labels agreed to by the data stewards", add new rows "generating new surrogate keys", add Type 2 rows, overwrite Type 1 and Type 3 changes, and "Replicate the revised dimension simultaneously to all fact table providers" ([Design Tip #92][dt92]).

**The crux: is building conformed dimensions part of Conform or of Deliver?** Kimball splits the work.

- **Conform decides what the dimension says and enforces it.** "Physically, this step involves enforcing common names of conformed dimension attributes and facts, as well as enforcing common domain contents and common units of measurement" ([ETL Toolkit ch. 1, p. 7][ch1]). The conform step covers "Conforming business labels (in dimensions)", "Conforming business metrics and performance indicators (in fact tables)", "Deduplicating", "Householding" and "Internationalizing" ([Introduction, p. xxvi][intro]). Its saved output is "general data structures", not yet dimensional tables ([Figure 1.2, p. 18][ch1]).
- **Deliver builds the tables and hands them over.** The delivery step covers "Loading types 1, 2, and 3 slowly changing dimensions", "Conforming dimensions and conforming facts" and "Running the surrogate key pipeline for fact tables" ([Introduction, p. xxvii][intro]). Its saved output is "dimensional tables" ([Figure 1.2][ch1]). "The primary mission of the ETL system is the hand-off of the dimension and fact tables in the delivery step" ([Becker 2007][k2007]).

Kimball's own materials do not draw this boundary sharply:

- The 2013 slide lists "Conformed Dimensions" as a result of Clean and Conform ([T slide][slide-t]).
- Design Tip #92 introduces the dimension manager "to facilitate and manage the conforming process" ([Design Tip #92][dt92]).
- The 2004 book covers "The Dimension Manager: Publishing Conformed Dimensions to Affected Fact Tables" in its Cleaning and Conforming chapter (ch. 4, p. 152, per the [table of contents][toc]). I could not open those pages.

## 2. The four staging steps

The claim is confirmed, but it is in chapter 1 of *The Data Warehouse ETL Toolkit*. "There are four staging steps found in almost every data warehouse … Throughout this book, we assume that every ETL system supporting the data warehouse is structured with these four steps and that data is staged (written to the disk) in parallel with the data being transferred to the next stage" ([pp. 17–18, Figure 1.2 "The Four Staging Steps of a Data Warehouse"][ch1]). The Introduction adds: "we recommend at least some form of staging after each of the major ETL steps" ([p. xxix][intro]).

This is a recommendation, and Kimball qualifies it:

- **Steps can overlap.** The same chapter warns that Figure 1.2 "makes it look like you must do all the extracting, cleaning, conforming and delivering serially with well-defined boundaries". In practice "frequently some of the cleaning steps are embedded in the logic that performs extraction" ([p. 19][ch1]).
- **Staging means writing to disk.** "When we say staging, we mean writing data to the disk" ([p. xxix][intro]). The disk can hold "Staging Schemas in DBMS" or "Flat Files on File System" ([Figure 1.1, p. 16][ch1]). Nothing implies a separate database per step.
- **The number of stagings is a judgement.** "How often should you stage your data between source and target? … there is no single answer," and "most current ETL systems stage the data once or twice between the source and the data warehouse target". One copy is not optional: "You should always make a copy of the extracted, untransformed data for auditing purposes" ([Design Tip #99, 2008][dt99]).
- **Kimball later dropped the word.** The *Lifecycle Toolkit*, 2nd ed. (2008), "abandoned the data staging terminology", because others used it "to merely mean the initial dumping of raw source data into a work zone" ([ch. 1, p. 12][lct1]).

Kimball gives these reasons for staging:

| Reason | Source |
| --- | --- |
| Restart the extract after an interruption; read the captured data several times; compare successive extracts | [ch. 1, p. 18][ch1] |
| Cleaning "may even involve human intervention and the exercise of judgment", so its results are "often saved semipermanently because the transformations required are difficult and irreversible" | [p. 19][ch1] |
| Reprocessing, and comparison with new data to detect changes. "All staged data should be archived unless a conscious decision is made that specific data sets will never be recovered" | [p. 8][ch1] |
| Compliance: "Archived copies of data sources and subsequent stagings of data" | [p. 5][ch1] |
| A connection can break mid-stream; a long run holds locks on the source; the audit copy | [Design Tip #99][dt99] |

The section titled "To Stage or Not to Stage" is in chapter 2 (p. 29, per the [table of contents][toc]). Wiley has not released chapter 2, so I could not check what it says.

## 3. What the medallion layers hold

| Layer | Databricks | Microsoft |
| --- | --- | --- |
| Bronze | "Raw data ingestion"; "Enables reprocessing and auditing by retaining all historical data" ([docs][dbx]) | "Store everything exactly as it arrives" ([Fabric][fabric]) |
| Silver | "Data cleaning and validation"; "where you perform data cleansing, deduplication, and normalization" ([docs][dbx]). The glossary heading is "Silver layer (cleansed and conformed data)": the data "is matched, merged, conformed and cleansed ('just-enough') so that the Silver layer can provide an 'Enterprise view'" ([glossary][gloss]). "The silver layer brings the data from different sources together" ([warehousing docs][dbxdw]) | "Fix errors, standardize formats, and remove duplicates", for example "Match customer records across systems" ([Fabric][fabric]). Silver "holds validated, standardized, and cleansed data", for example "Store identifiers align with sales data" ([Cloud Adoption Framework][caf]) |
| Gold | "Dimensional modeling and aggregation"; "the gold layer is where you'll model your data for reporting and analytics using a dimensional model" ([docs][dbx]). "Kimball style star schema-based data models or Inmon style Data marts fit in this Gold Layer" ([glossary][gloss]). "The gold layer is the presentation layer" ([warehousing docs][dbxdw]) | "Organize for reports and dashboards" ([Fabric][fabric]). The retired zones page says the curated (gold) layer "might store data in denormalized data marts or star schemas" ([CAF, 2024][cafzones]) |

Microsoft Learn's Azure Databricks page carries the same text as Databricks' docs ([Microsoft Learn][mslearn]).

Databricks' blog on dimensional modeling puts cross-source conforming in Silver and star schemas in Gold. "The Silver layer for the first time brings the data from different sources together and conforms it to create an Enterprise view of the data — typically using a more normalized, write-optimized data models". Then "In the Gold layer, multiple data marts or warehouses can be built as per dimensional modeling/Kimball methodology", where "different subject areas are connected via conformed dimensions" ([Bhatt and Sekar, 2022][dbx2022]). None of the Databricks or Microsoft pages I read names a layer for conformed dimension *tables* in so many words. They put the dimensional models, which contain those tables, in Gold.

How the two line up (*inference* from the sources above):

| Kimball step | Medallion layer | Fit |
| --- | --- | --- |
| Extract | Bronze | Close. Kimball allows format conversions here ([E slide][slide-e]), while Databricks recommends storing most fields as strings ([Microsoft Learn][mslearn]). |
| Clean | Silver | Close. |
| Conform | Silver for matching across sources; Gold for the dimension tables | Split, just as in Kimball's own grouping (section 1). |
| Deliver | Gold | Close. |
| Manage | None | Runs across every step in both. |

They differ in three ways:

- **Who may query the middle.** Kimball: "No query services are provided in the back room" ([ch. 1, p. 16][ch1]). Databricks names data analysts and data scientists as Silver's users ([Microsoft Learn][mslearn]).
- **Where "the data warehouse" is.** Databricks: "The data warehouse is modeled in the silver layer and feeds specialized data marts in the gold layer" ([warehousing docs][dbxdw]). Kimball accepts normalized structures for cleaning, but urges converting them "into simple dimensional structures for the conforming and final handoff steps" ([ch. 1, p. 27][ch1]).
- **What a layer is.** Medallion layers "denote the quality of data", and following them is "a recommended best practice but not a requirement" ([Microsoft Learn][mslearn]). Kimball's steps are processing steps.

## 4. Terminology

| Source | Its word | Evidence |
| --- | --- | --- |
| Kimball, *ETL Toolkit* | "steps", sometimes "stages"; saving between them is "staging" | "four staging steps" ([p. 17][ch1]); "the basic four stages of Data Flow" ([p. xxix][intro]) |
| Kimball Group, from 2007 | 34 "subsystems" in "four major components", "four major operations" or "categories" | [Becker 2007][k2007]; [architecture page][karch]; [Kimball Techniques][k34] |
| Databricks docs | "layer"; also "multi-hop architectures" | [docs][dbx]; [glossary][gloss] |
| Databricks, 2019 | "Data Quality Levels"; tables at different "quality levels" | [Armbrust slides][arm2019]; [2019 blog][dbx2019] |
| Databricks, 2020 | "Bronze: the initial landing zone for the pipeline" | [2020 blog][dbx2020] |
| Microsoft Fabric | "layer"; once, "a three-stage cleaning and organizing process" | [Fabric][fabric] |
| Microsoft Cloud Adoption Framework (2024, since retired) | raw, enriched and curated "layers", also called zones: "Raw layer (bronze)", "Enriched layer (silver)", "Curated layer (gold)" | [CAF, 2024][cafzones]; deleted in April 2026 ([commit][cafdel]) |

None of the Databricks or Microsoft pages I read calls the layers "tiers". I found no primary source saying who first called lake layers "zones". The retired Microsoft page is where Microsoft paired raw, enriched and curated with bronze, silver and gold. Fabric still names them "bronze (raw data), silver (enriched data), and gold (curated data)" ([Fabric][fabric]).

This repo's vocabulary, and where it collides with these sources:

| Word | Use in this repo | Collision |
| --- | --- | --- |
| layer | Bronze, Silver, Gold, Analytics, Presentation ([ADR-002](../decisions/ADR-002-medallion-architecture.md), lines 7–9) | Kimball's "presentation area" and Databricks' "presentation layer" hold the dimensional models. Here that is Gold, not the Presentation layer, which "Render[s] dashboards" ([`02-architecture.md`](../02-architecture.md), line 85). |
| stage | "One SQLite store per ETL stage" ([ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md), line 57); also `store_identity.stage`, `--stage` and `rebuild --from <stage>` ([`operations.md`](../architecture/operations.md), lines 68, 207 and 427) | Kimball has four stages; here Silver holds two of them. Many readers take "staging" to mean the raw landing area, which is why Kimball dropped the word ([*Lifecycle Toolkit* p. 12][lct1]). |
| tier | production, development and test: "the three tiers stay distinct" (ADR-015, lines 20–21). [`CONTEXT.md`](../../CONTEXT.md) calls these *Profiles* (line 266) | No source above uses "tier" for medallion layers, so using it for them would clash with this meaning. |
| zone | Only for a time zone: "Europe/Copenhagen, the zone presentation already uses" ([`publications.md`](../architecture/publications.md), lines 55–56) | Microsoft used it for the layers, and Databricks' 2020 blog for Bronze. |
| conform | Silver is "Clean and conform" (ADR-015, line 64) | The retired Microsoft page had a "conformance container" inside the raw layer: "Your raw layer contains data quality conformed data" ([CAF, 2024][cafzones]). That is not Kimball's sense of the word. |

## 5. Where Bronze, Silver and Gold came from

These are the earliest Databricks uses I found:

- **July 2019.** A Delta Lake slide deck by Michael Armbrust, hosted by Databricks, shows "Data Quality Levels": Bronze "Raw Ingestion", Silver "Filtered, Cleaned Augmented", Gold "Business-level Aggregates" ([slides][arm2019]). The date comes from the PDF's metadata.
- **14 August 2019.** "A common architecture uses tables that correspond to different quality levels in the data engineering pipeline … ('Bronze' tables) … ('Silver' tables) … ('Gold' tables)" ([Heintz and Lee][dbx2019]).
- **2 June 2020.** "This is the medallion reference architecture that Databricks recommends" ([Ng and Christine][dbx2020]). This is the earliest use of "medallion" I found.

None of these pages claims that Databricks coined the names, and none cites an earlier source. The 2019 blog calls it "a common architecture". The claim that Databricks coined the names is common in secondary sources, but no Databricks page I found makes it.

## What this means for this repo

- **Splitting conforming between Silver and Gold matches Kimball.** Silver makes every source's records say the same thing: "validated, source-neutral canonical records", source statuses mapped "to booked or unbooked", and duplicates resolved ([`silver-layer.md`](../architecture/silver-layer.md), lines 5–6; [`02-architecture.md`](../02-architecture.md), lines 40 and 46). That is Kimball's clean step plus the part of conforming that concerns sources. Gold "Publish[es] the account and category dimensions from the household registries" ([`gold-layer.md`](../architecture/gold-layer.md), line 17), which is Kimball's Delivering group. *Inference:* the household registries play the part of the labels "agreed to by the data stewards" that the dimension manager implements ([Design Tip #92][dt92]). Kimball's deduplication examples are dimension members such as customers, whereas Silver deduplicates transactions.
- **One sentence overstated Kimball.** [`operations.md`](../architecture/operations.md) said "Kimball's *conform* step also builds the conformed dimensions". Kimball's subsystem list puts building dimension tables (keys, history) and publishing them in Delivering. Only the 2013 slide and the 2004 book's chapter placement support the sentence. Its conclusion, that the dimensions are built in Gold, holds either way. The change that added this note rewrote the sentence.
- **The repo credited the four steps to the wrong Kimball framing.** ADR-015 and `operations.md` credited "Kimball's ETL subsystems" with naming the four steps and saving the data after each. The four steps, and the saving after each, come from the *ETL Toolkit*'s data flow. The subsystem list groups the same work as Extracting, Cleaning and Conforming, and Delivering, plus Managing. Those three groups map one-to-one onto Bronze, Silver and Gold. The change that added this note corrected both citations.
- **Kimball does not require four stores.** He recommends writing the data to disk after each step, in files or tables, and says the steps need not be strictly separate. His firm later said the number of stagings has "no single answer", and insisted only on an untransformed copy, which Bronze keeps. *Inference:* the three stores are three of Kimball's four stagings. The missing one would sit between clean and conform, inside Silver.
- **The repo is closer to Kimball than to Databricks on access.** "The dashboard is given only `gold.db`" (ADR-015, line 68). Kimball allows no queries in the back room, while Databricks opens Silver to analysts.

## Could not verify

- *ETL Toolkit* chapter 2, "To Stage or Not to Stage" (pp. 29–31), and chapter 4's dimension-manager pages (pp. 148–160). I saw only their titles in the table of contents.
- The *ETL Toolkit* Introduction comes from a reading sample hosted by a retailer ([e-bookshelf][intro]), not from Wiley's site. Its point about staging after each step is repeated in Wiley's own chapter 1 excerpt.
- Design Tip #92 is quoted from a copy on DecisionWorks Consulting's site. Kimball Group's own address for it now redirects to a "not found" page.
- The 2004 article comes from InformationWeek's copy, not the original *Intelligent Enterprise* page. The byline reads "InformationWeek Staff", but the text is in the first person and ends with Ralph Kimball's author bio.
- *Lifecycle Toolkit*, 2nd ed., chapter 9: I saw its headings and page numbers only, not the subsystem text.

[k34]: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/etl-architecture-34-subsystems/
[k2007]: https://www.kimballgroup.com/2007/10/subsystems-of-etl-revisited/
[karch]: https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/technical-dw-bi-system-architecture/
[slide-e]: https://www.kimballgroup.com/wp-content/uploads/2013/08/Kimball-ETL-Extract-Subsystems1.pdf
[slide-t]: https://www.kimballgroup.com/wp-content/uploads/2013/08/Kimball-ETL-Transformation-Subsystems1.pdf
[slide-l]: https://www.kimballgroup.com/wp-content/uploads/2013/08/Kimball-ETL-Load-Subsystems1.pdf
[slide-m]: https://www.kimballgroup.com/wp-content/uploads/2013/08/Kimball-ETL-Manage-Subsystems1.pdf
[dt99]: https://www.kimballgroup.com/wp-content/uploads/2012/05/DT99StagingAreasETLTools.pdf
[dt92]: https://decisionworks.com/2007/06/design-tip-92-dimension-manager-and-fact-provider/
[iw2004]: https://www.informationweek.com/data-management/the-38-subsystems-of-etl
[ch1]: https://media.wiley.com/product_data/excerpt/78/07645675/0764567578.pdf
[toc]: https://media.wiley.com/product_data/excerpt/78/07645675/0764567578-2.pdf
[intro]: https://content.e-bookshelf.de/media/reading/L-586459-873830c5f9.pdf
[lct1]: https://media.wiley.com/product_data/excerpt/79/04701497/0470149779.pdf
[lcttoc]: https://media.wiley.com/product_data/excerpt/79/04701497/0470149779-1.pdf
[dbx]: https://docs.databricks.com/aws/en/lakehouse/medallion
[mslearn]: https://learn.microsoft.com/en-us/azure/databricks/lakehouse/medallion
[gloss]: https://www.databricks.com/glossary/medallion-architecture
[dbxdw]: https://docs.databricks.com/aws/en/sql/get-started/data-warehousing-concepts
[dbx2022]: https://www.databricks.com/blog/2022/06/24/data-warehousing-modeling-techniques-and-their-implementation-on-the-databricks-lakehouse-platform.html
[fabric]: https://learn.microsoft.com/en-us/fabric/onelake/onelake-medallion-lakehouse-architecture
[caf]: https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/data/operational-standards-data-processing-standards-unify-data-platform
[cafzones]: https://github.com/MicrosoftDocs/cloud-adoption-framework/blob/51f1698822c8309011df0f851279641e9ce27803/docs/scenarios/cloud-scale-analytics/best-practices/data-lake-zones.md
[cafdel]: https://github.com/MicrosoftDocs/cloud-adoption-framework/commit/9b409b1d584e2ff9e84297b2e401b4edf98892d4
[arm2019]: https://www.databricks.com/wp-content/uploads/2019/09/Making-Apache-Spark-Better-with-Delta-Lake.pdf
[dbx2019]: https://www.databricks.com/blog/2019/08/14/productionizing-machine-learning-with-delta-lake.html
[dbx2020]: https://www.databricks.com/blog/2020/06/02/monitor-your-databricks-workspace-with-audit-logs.html

🤖 Generated with Claude Code (Claude Opus 5.5)
