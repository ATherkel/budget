-- Copyright 2026 Therkel
-- Gold schema version 4: a recipe records the late-booking window it was built
-- with (`publications.md`, *The Recipe*).
--
-- An earlier recipe did not record it, so the window those builds used is
-- unknown. The profile's default of 7 days is what a build used unless the
-- profile set `[gold] late_booking_days`; it is recorded for them, and every
-- later build records the window it really used.

ALTER TABLE recipes
    ADD COLUMN late_booking_days INTEGER NOT NULL DEFAULT 7
    CHECK (late_booking_days >= 0);
