-- Copyright 2026 Therkel
-- Gold schema version 3: every transaction records what classified it, its
-- `Classification` (gold-contract.md): the source, the highest-priority
-- matching rules as a JSON array in priority order, and the deciding manual
-- decision, if any.
--
-- Version 2 recorded none of it, so every transaction it already published
-- reads as unclassified with no rules. The next Gold rebuild publishes what
-- classified each one.

ALTER TABLE transactions ADD COLUMN classification_source TEXT NOT NULL
    DEFAULT 'unclassified' CHECK (
        classification_source IN ('manual', 'transfer_match', 'rule', 'unclassified')
    );

ALTER TABLE transactions ADD COLUMN classification_rule_ids TEXT NOT NULL
    DEFAULT '[]' CHECK (json_valid(classification_rule_ids));

ALTER TABLE transactions ADD COLUMN classification_decision_id TEXT;
