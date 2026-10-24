-- Copyright 2026 Therkel
-- Gold schema version 2: classification questions published with their build.
--
-- A review item and both identifier lists belong to one retained result. Child
-- ordinals preserve the order Gold derived, including transaction targets that
-- are absent from the publication.

CREATE TABLE classification_review_items (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    review_item_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'unclassified',
            'rule-conflict',
            'sign-mismatch',
            'ambiguous-transfer',
            'unmatched-transfer',
            'decision-not-applicable'
        )
    ),
    decision_id TEXT,
    reason TEXT,
    PRIMARY KEY (publication_id, review_item_id),
    UNIQUE (publication_id, ordinal)
) STRICT;

CREATE TABLE classification_review_targets (
    publication_id INTEGER NOT NULL,
    review_item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    transaction_id TEXT NOT NULL,
    PRIMARY KEY (publication_id, review_item_id, ordinal),
    UNIQUE (publication_id, review_item_id, transaction_id),
    FOREIGN KEY (publication_id, review_item_id)
        REFERENCES classification_review_items (publication_id, review_item_id)
) STRICT;

CREATE TABLE classification_review_rules (
    publication_id INTEGER NOT NULL,
    review_item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    rule_id TEXT NOT NULL,
    PRIMARY KEY (publication_id, review_item_id, ordinal),
    UNIQUE (publication_id, review_item_id, rule_id),
    FOREIGN KEY (publication_id, review_item_id)
        REFERENCES classification_review_items (publication_id, review_item_id)
) STRICT;
